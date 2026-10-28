from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

PAWN_KIND = "wangchuan.pawn"
REDEEM_KIND = "wangchuan.redeem"

TICKET_PATTERN = re.compile(r"当票\s*#\s*(\d+)")
MEMORY_PATTERN = re.compile(r"典当[：:]\s*(.*?)(?:\s*｜\s*掌柜批注[：:]|\Z)", re.S)
NOTE_PATTERN = re.compile(r"掌柜批注[：:]\s*(.*)\Z", re.S)
REDEEM_PATTERN = re.compile(r"赎回\s*#?\s*(\d+)")


@dataclass(frozen=True)
class Pawn:
    ticket: int
    entry_id: str
    citation: dict[str, Any]
    memory: str
    note: str
    state: str


def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def parse_pawn(entry: dict[str, Any]) -> Pawn | None:
    if entry.get("kind") != PAWN_KIND:
        return None
    text = str(entry.get("text") or "")
    ticket_match = TICKET_PATTERN.search(text)
    if ticket_match is None:
        return None
    memory_match = MEMORY_PATTERN.search(text)
    note_match = NOTE_PATTERN.search(text)
    citation = dict(entry.get("citation") or {})
    entry_id = str(citation.get("entry_id") or entry.get("entry_id") or "")
    return Pawn(
        ticket=int(ticket_match.group(1)),
        entry_id=entry_id,
        citation=citation,
        memory=memory_match.group(1).strip() if memory_match else text,
        note=note_match.group(1).strip() if note_match else "",
        state=str(entry.get("state") or "active"),
    )


def active_pawns(entries: list[dict[str, Any]]) -> list[Pawn]:
    pawns = [pawn for entry in entries if (pawn := parse_pawn(entry)) is not None and pawn.state == "active"]
    return sorted(pawns, key=lambda pawn: pawn.ticket)


def max_ticket(entries: list[dict[str, Any]]) -> int:
    tickets = [int(match.group(1)) for entry in entries for match in TICKET_PATTERN.finditer(str(entry.get("text") or ""))]
    return max(tickets, default=0)


def format_pawn_line(pawn: Pawn, *, memory_limit: int = 90, note_limit: int = 90) -> str:
    memory = _clip(pawn.memory, memory_limit)
    line = f"#{pawn.ticket}｜典当：{memory}"
    if pawn.note:
        line += f"｜掌柜批注：{_clip(pawn.note, note_limit)}"
    return line


def format_ledger(pawns: list[Pawn]) -> str:
    if not pawns:
        return (
            "账本还是空的。\n"
            "说一段你想典当的记忆，再许一个愿望，我给你开第一张当票。"
        )
    lines = [f"忘川账本 · 未赎当票 {len(pawns)} 笔"]
    lines.extend(format_pawn_line(pawn) for pawn in pawns)
    lines.append("")
    lines.append("输入「赎回 1」这样的口令，可以赎回对应编号的当票。")
    return "\n".join(lines)


def format_context(
    *,
    entries: list[dict[str, Any]],
    hits: list[dict[str, Any]],
    next_ticket: int,
    limit: int = 6,
) -> str:
    pawns = active_pawns(entries)
    lines = ["【忘川账本 · 仅供掌柜阅读】"]
    if pawns:
        lines.append(f"这位客人是老客，账本里有 {len(pawns)} 笔未赎当票。")
    elif entries:
        lines.append(
            "这位客人眼下没有未赎当票，但留着已赎回的旧账。"
            "旧账都已结清、记忆都已归还；若他提起旧事，你只说自己记不清了，不要引用旧账内容，也不要编造。"
        )
    else:
        lines.append("这位客人第一次来，账本还是空的。")
    lines.append(f"下一张当票编号：#{next_ticket}")

    hit_entry_ids = {
        str((hit.get("citation") or {}).get("entry_id") or "")
        for hit in hits
    }
    relevant = []
    for hit in hits[:4]:
        text = _clip(str(hit.get("text") or ""), 180)
        if text:
            relevant.append(text)
    if relevant:
        lines.append("")
        lines.append("与这次典当相关的旧账（引用时保留原文细节）：")
        lines.extend(f"- {text}" for text in relevant)

    remaining = [pawn for pawn in pawns if pawn.entry_id not in hit_entry_ids]
    if remaining:
        lines.append("")
        lines.append("其他未赎当票：")
        for pawn in sorted(remaining, key=lambda item: item.ticket, reverse=True)[:limit]:
            lines.append(f"- {format_pawn_line(pawn, memory_limit=70, note_limit=70)}")

    lines.append("")
    lines.append("提示：若客人提到旧账里的人、物或细节，先引用旧账原文，再谈本次交易；不要提账本编号、接口或 AI。")
    return "\n".join(lines)


def pawn_text(ticket: int, message: str, reply: str) -> str:
    return f"当票 #{ticket}｜典当：{_clip(message, 420)}｜掌柜批注：{_clip(reply, 420)}"


def redemption_text(ticket: int, pawn: Pawn) -> str:
    return f"赎回当票 #{ticket}｜原典当：{_clip(pawn.memory, 360)}｜掌柜批注：{_clip(pawn.note, 120)}"


def format_redeem_success(pawn: Pawn, remaining: int) -> str:
    lines = [
        f"掌柜从账本里取下第 {pawn.ticket} 号当票，吹了吹上面的灰。",
        "你典当的那段记忆回来了：",
        f"「{_clip(pawn.memory, 160)}」",
    ]
    if pawn.note:
        lines.append(f"（掌柜当时的批注：{_clip(pawn.note, 120)}）")
    if remaining:
        lines.append(f"账本上还剩 {remaining} 笔未赎。")
    else:
        lines.append("账本清了。你两不相欠——至少账面上是这样。")
    return "\n".join(lines)
