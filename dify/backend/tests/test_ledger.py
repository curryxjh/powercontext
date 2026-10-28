from __future__ import annotations

from wangchuan.ledger import parse_pawn, pawn_text


def test_pawn_text_roundtrip() -> None:
    entry = {
        "entry_id": "e1",
        "kind": "wangchuan.pawn",
        "state": "active",
        "text": pawn_text(3, "第一次看海，海水是温的", "这记忆咸得很，值 3 枚忘川币。"),
        "citation": {"entry_id": "e1"},
    }
    pawn = parse_pawn(entry)
    assert pawn is not None
    assert pawn.ticket == 3
    assert pawn.entry_id == "e1"
    assert pawn.memory == "第一次看海，海水是温的"
    assert "3 枚忘川币" in pawn.note


def test_redemption_is_not_a_pawn() -> None:
    entry = {
        "entry_id": "e2",
        "kind": "wangchuan.redeem",
        "state": "active",
        "text": "赎回当票 #3｜原典当：第一次看海｜掌柜批注：值 3 枚",
        "citation": {"entry_id": "e2"},
    }
    assert parse_pawn(entry) is None
