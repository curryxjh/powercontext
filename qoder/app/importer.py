"""Turn pasted study notes into knowledge-card candidates.

Supported shapes, in priority order:

1. Markdown headings: ``## 概念名`` followed by its explanation.
2. Q/A blocks: ``Q: 问题`` followed by ``A: 答案``.
3. Plain paragraphs: each paragraph becomes a card whose prompt is its first
   sentence (truncated) and whose answer is the whole paragraph.

The parser is intentionally deterministic and offline; it never calls a model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .records import clip_utf8

MAX_ITEMS_PER_IMPORT = 80
MIN_PARAGRAPH_CHARS = 24
QUESTION_PREFIXES = ("q:", "Q:", "问:", "问：", "问题:", "问题：")
ANSWER_PREFIXES = ("a:", "A:", "答:", "答：", "答案:", "答案：")


@dataclass
class ParsedItem:
    topic: str
    prompt: str
    answer: str


@dataclass
class ParsedImport:
    topic: str
    title: str
    items: list[ParsedItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _clean(value: str) -> str:
    return re.sub(r"[ \t]+", " ", value.replace("\r\n", "\n").replace("\r", "\n")).strip()


def _first_sentence(value: str, limit: int = 60) -> str:
    text = " ".join(value.split())
    match = re.search(r"[。！？!?；;\.]", text)
    if match:
        text = text[: match.start()]
    text = text.strip().rstrip("，,、：:")
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text or value[:limit]


def _strip_prefix(line: str, prefixes: tuple[str, ...]) -> str | None:
    for prefix in prefixes:
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return None


def parse_notes(raw: str, default_topic: str, *, max_answer_bytes: int = 6000) -> ParsedImport:
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    document_topic = (default_topic or "未分类").strip() or "未分类"
    title = "粘贴的笔记"
    start = 0
    for index, line in enumerate(lines):
        if line.startswith("# ") and not line.startswith("## "):
            candidate = line[2:].strip()
            if candidate:
                title = candidate
                document_topic = candidate
            start = index + 1
            break

    items: list[ParsedItem] = []
    warnings: list[str] = []

    # 1) Markdown headings
    heading_indices = [
        i for i in range(start, len(lines)) if lines[i].startswith("## ") or lines[i].startswith("### ")
    ]
    if heading_indices:
        for position, index in enumerate(heading_indices):
            heading = lines[index].lstrip("#").strip()
            end = heading_indices[position + 1] if position + 1 < len(heading_indices) else len(lines)
            body = _clean("\n".join(lines[index + 1 : end]))
            if len(body) < MIN_PARAGRAPH_CHARS:
                continue
            items.append(
                ParsedItem(
                    topic=default_topic.strip() or document_topic,
                    prompt=heading[:200],
                    answer=clip_utf8(body, max_answer_bytes),
                )
            )
        if items:
            return ParsedImport(topic=document_topic, title=title, items=_dedupe(items), warnings=warnings)

    # 2) Q/A blocks
    current_question: str | None = None
    answer_lines: list[str] = []
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped:
            if current_question is not None and answer_lines:
                answer_lines.append("")
            continue
        question = _strip_prefix(stripped, QUESTION_PREFIXES)
        if question is not None:
            if current_question is not None and answer_lines:
                answer = _clean("\n".join(answer_lines))
                if answer:
                    items.append(
                        ParsedItem(
                            topic=default_topic.strip() or document_topic,
                            prompt=current_question[:200],
                            answer=clip_utf8(answer, max_answer_bytes),
                        )
                    )
            current_question = question[:200]
            answer_lines = []
            continue
        answer = _strip_prefix(stripped, ANSWER_PREFIXES)
        if answer is not None:
            answer_lines.append(answer)
            continue
        if current_question is not None:
            answer_lines.append(stripped)
    if current_question is not None and answer_lines:
        answer = _clean("\n".join(answer_lines))
        if answer:
            items.append(
                ParsedItem(
                    topic=default_topic.strip() or document_topic,
                    prompt=current_question[:200],
                    answer=clip_utf8(answer, max_answer_bytes),
                )
            )
    if items:
        return ParsedImport(topic=document_topic, title=title, items=_dedupe(items), warnings=warnings)

    # 3) Plain paragraphs
    paragraphs = [_clean(block) for block in re.split(r"\n\s*\n", "\n".join(lines[start:]))]
    for paragraph in paragraphs:
        if len(paragraph) < MIN_PARAGRAPH_CHARS:
            continue
        items.append(
            ParsedItem(
                topic=default_topic.strip() or document_topic,
                prompt=_first_sentence(paragraph),
                answer=clip_utf8(paragraph, max_answer_bytes),
            )
        )

    items = _dedupe(items)
    if not items:
        warnings.append("没有识别到可用的知识点：请使用 ## 标题 + 说明，或 Q:/A: 格式。")
    return ParsedImport(topic=document_topic, title=title, items=items[:MAX_ITEMS_PER_IMPORT], warnings=warnings)


def _dedupe(items: list[ParsedItem]) -> list[ParsedItem]:
    seen: set[str] = set()
    result: list[ParsedItem] = []
    for item in items:
        key = item.prompt.strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result[:MAX_ITEMS_PER_IMPORT]
