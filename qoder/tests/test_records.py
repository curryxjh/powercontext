from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.records import (
    MAX_TEXT_BYTES,
    META_MARKER,
    clip_utf8,
    decode_text,
    encode_record,
    knowledge_human,
    parse_iso,
    split_knowledge_human,
    to_iso,
)


def test_encode_decode_roundtrip():
    text = encode_record("knowledge", "【线代】特征值是什么\n---\n满足 Av=λv 的 λ", {"id": "k_1"})
    assert META_MARKER in text
    human, meta = decode_text("knowledge", text)
    assert human == "【线代】特征值是什么\n---\n满足 Av=λv 的 λ"
    assert meta["v"] == 1
    assert meta["t"] == "knowledge"
    assert meta["id"] == "k_1"


def test_encode_respects_powercontext_entry_limit():
    text = encode_record("knowledge", "学" * 5000, {"id": "k_1", "topic": "线代"})
    assert len(text.encode("utf-8")) <= MAX_TEXT_BYTES
    human, meta = decode_text("knowledge", text)
    assert human.endswith("…")
    assert len(human) < 5000
    assert meta["id"] == "k_1"


def test_encode_rejects_oversize_metadata():
    with pytest.raises(ValueError):
        encode_record("knowledge", "内容", {"id": "k_1", "blob": "x" * 9000})


def test_decode_without_marker_keeps_plain_text():
    assert decode_text("review", "  普通记忆  ") == ("普通记忆", {})


def test_decode_with_broken_payload_keeps_human_part():
    human, meta = decode_text("review", "复习「梯度」\n§meta§ not-json")
    assert human == "复习「梯度」"
    assert meta == {}


def test_decode_payload_defaults_kind():
    _, meta = decode_text("struggle", '卡点\n§meta§ {"id":"st_1"}')
    assert meta["t"] == "struggle"


def test_clip_utf8_never_splits_code_points():
    value = "学习" * 100
    clipped = clip_utf8(value, 10)
    assert clipped.endswith("…")
    assert len(clipped.encode("utf-8")) <= 10
    clipped.encode("utf-8").decode("utf-8")


def test_clip_utf8_edge_cases():
    assert clip_utf8("abcdef", 100) == "abcdef"
    assert clip_utf8("abcdef", 3) == ""
    assert clip_utf8("abcdef", 4) == "a…"


def test_iso_helpers_normalise_to_utc():
    naive = datetime(2026, 1, 2, 3, 4, 5)
    assert to_iso(naive) == "2026-01-02T03:04:05+00:00"
    parsed = parse_iso("2026-01-02T03:04:05Z")
    assert parsed is not None
    assert parsed.tzinfo is not None
    assert parsed == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert parse_iso("") is None
    assert parse_iso("not-a-date") is None


def test_knowledge_human_roundtrip():
    human = knowledge_human("线代", "特征值是什么", "满足 Av=λv 的 λ")
    assert human == "【线代】特征值是什么\n---\n满足 Av=λv 的 λ"
    prompt, answer = split_knowledge_human(human)
    assert prompt == "【线代】特征值是什么"
    assert answer == "满足 Av=λv 的 λ"
