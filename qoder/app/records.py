"""Typed records stored as PowerContext Memory entries.

PowerContext Memory entries are free-form text with a ``kind``. WenGu keeps a
small, versioned JSON payload after a marker so the coach can rebuild learner
state from memory alone, while the text before the marker stays readable to a
human and searchable through PowerContext's full-text index.

Record shape::

    <human readable sentence>
    §meta§ {"v":1,"t":"knowledge","id":"k_...","at":"..."}

The marker is stripped everywhere in the UI. Entries written by an older
version (or by a person through another PowerContext client) simply decode with
an empty payload and remain visible in the Memory Center.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

META_MARKER = "\n§meta§ "
SCHEMA_VERSION = 1
MAX_TEXT_BYTES = 8192

KIND_LABELS: dict[str, str] = {
    "profile": "学习画像",
    "knowledge": "知识卡片",
    "review": "复习记录",
    "struggle": "卡点记忆",
    "session": "学习会话",
    "feedback": "使用反馈",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="seconds")


def parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def clip_utf8(value: str, max_bytes: int) -> str:
    """Clip text without splitting a UTF-8 code point."""

    raw = value.encode("utf-8")
    if len(raw) <= max_bytes:
        return value
    if max_bytes <= 3:
        return ""
    clipped = raw[: max_bytes - 3].decode("utf-8", "ignore").rstrip()
    return clipped + "…"


def encode_record(kind: str, human: str, meta: dict[str, Any] | None = None) -> str:
    """Encode one typed record within PowerContext's 8192-byte entry limit."""

    payload_meta = {"v": SCHEMA_VERSION, "t": kind, **(meta or {})}
    payload = json.dumps(payload_meta, ensure_ascii=False, separators=(",", ":"))
    budget = MAX_TEXT_BYTES - len(META_MARKER.encode("utf-8")) - len(payload.encode("utf-8")) - 2
    if budget < 64:
        raise ValueError("record metadata is too large for a PowerContext memory entry")
    return clip_utf8(human.strip(), budget) + META_MARKER + payload


def decode_text(kind: str, text: str) -> tuple[str, dict[str, Any]]:
    """Split a Memory entry into readable text and its typed payload."""

    if META_MARKER not in text:
        return text.strip(), {}
    human, raw_payload = text.split(META_MARKER, 1)
    try:
        parsed = json.loads(raw_payload)
    except (TypeError, ValueError):
        return human.strip(), {}
    if not isinstance(parsed, dict):
        return human.strip(), {}
    parsed.setdefault("t", kind)
    return human.strip(), parsed


@dataclass(frozen=True)
class MemoryRecord:
    """One current Memory entry plus its exact PowerContext citation."""

    entry_id: str
    version_id: str
    kind: str
    state: str
    human: str
    meta: dict[str, Any]
    text: str
    memory_revision: int
    citation: Any

    @classmethod
    def from_entry(cls, entry: Any) -> "MemoryRecord":
        kind = str(entry.entry.kind)
        human, meta = decode_text(kind, str(entry.entry.text))
        return cls(
            entry_id=str(entry.entry.entry_id),
            version_id=str(entry.entry.entry_version_id),
            kind=kind,
            state=str(entry.state),
            human=human,
            meta=meta,
            text=str(entry.entry.text),
            memory_revision=int(entry.citation.memory_ref.revision),
            citation=entry.citation,
        )

    @property
    def at(self) -> datetime | None:
        return parse_iso(self.meta.get("at"))

    @property
    def kind_label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)

    def public(self, *, include_raw: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "entry_id": self.entry_id,
            "version_id": self.version_id,
            "kind": self.kind,
            "kind_label": self.kind_label,
            "state": self.state,
            "human": self.human,
            "meta": self.meta,
            "created_at": to_iso(self.at) if self.at else None,
            "memory_revision": self.memory_revision,
            "citation": {
                "memory_ref": {
                    "family": self.citation.memory_ref.family,
                    "artifact_id": self.citation.memory_ref.artifact_id,
                    "revision": self.citation.memory_ref.revision,
                },
                "entry_id": self.citation.entry_id,
                "entry_version_id": self.citation.entry_version_id,
            },
            "citation_short": self.entry_id.replace("mem_ent_", "")[:10],
        }
        if include_raw:
            payload["raw_text"] = self.text
        return payload


def knowledge_human(topic: str, prompt: str, answer: str) -> str:
    return f"【{topic}】{prompt}\n---\n{answer}"


def split_knowledge_human(human: str) -> tuple[str, str]:
    if "\n---\n" in human:
        prompt, answer = human.split("\n---\n", 1)
        return prompt.strip(), answer.strip()
    return human.strip(), human.strip()
