from __future__ import annotations

from fastapi.testclient import TestClient

from wangchuan.api import create_app

from .fake_store import FakeMemoryStore


def _client() -> tuple[TestClient, FakeMemoryStore]:
    store = FakeMemoryStore()
    return TestClient(create_app(store)), store


def test_first_session_and_new_session_recall() -> None:
    client, _ = _client()

    first = client.post(
        "/v1/session/context",
        json={"player_id": "player-1", "message": "我想典当第一次看海的记忆"},
    )
    assert first.status_code == 200
    assert "第一次来" in first.text
    assert "#1" in first.text

    ticket = client.post(
        "/v1/session/turn",
        json={
            "player_id": "player-1",
            "message": "我想典当第一次看海的记忆，换一次好运。",
            "reply": "这记忆咸得很，值 3 枚忘川币。好运会在你最不需要的时候到。",
        },
    )
    assert ticket.status_code == 200
    assert ticket.text == "1"

    second = client.post(
        "/v1/session/context",
        json={"player_id": "player-1", "message": "我又来了"},
    )
    assert "老客" in second.text
    assert "第一次看海" in second.text
    assert "下一张当票编号：#2" in second.text


def test_ledger_and_redeem() -> None:
    client, _ = _client()
    client.post(
        "/v1/session/turn",
        json={"player_id": "player-2", "message": "典当考试前夜的记忆", "reply": "值 4 枚。"},
    )
    client.post(
        "/v1/session/turn",
        json={"player_id": "player-2", "message": "典当搬家那天的记忆", "reply": "值 2 枚。"},
    )

    ledger = client.post("/v1/session/ledger", json={"player_id": "player-2"})
    assert "#1" in ledger.text
    assert "#2" in ledger.text

    redeemed = client.post(
        "/v1/session/redeem",
        json={"player_id": "player-2", "message": "赎回 1"},
    )
    assert "第 1 号当票" in redeemed.text
    assert "记忆回来了" in redeemed.text
    assert "还剩 1 笔" in redeemed.text

    ledger_after = client.post("/v1/session/ledger", json={"player_id": "player-2"})
    assert "#1" not in ledger_after.text
    assert "#2" in ledger_after.text

    missing = client.post(
        "/v1/session/redeem",
        json={"player_id": "player-2", "message": "赎回 1"},
    )
    assert "没有第 1 号" in missing.text


def test_redeemed_memory_is_not_quoted_from_search_hits() -> None:
    client, store = _client()
    client.post(
        "/v1/session/turn",
        json={"player_id": "player-5", "message": "典当海底沉船的记忆", "reply": "值 5 枚。"},
    )
    store.search_hits = [
        {
            "text": "当票 #1｜典当：海底沉船的记忆｜掌柜批注：值 5 枚。",
            "citation": {"entry_id": "entry-1"},
        }
    ]
    active = client.post(
        "/v1/session/context",
        json={"player_id": "player-5", "message": "海底沉船"},
    )
    assert "海底沉船" in active.text

    client.post("/v1/session/redeem", json={"player_id": "player-5", "message": "赎回 1"})
    redeemed = client.post(
        "/v1/session/context",
        json={"player_id": "player-5", "message": "海底沉船"},
    )
    assert "海底沉船" not in redeemed.text
    assert "已赎回的旧账" in redeemed.text
    assert "下一张当票编号：#2" in redeemed.text


def test_ticket_numbers_survive_retirement() -> None:
    client, _ = _client()
    client.post(
        "/v1/session/turn",
        json={"player_id": "player-3", "message": "典当甲", "reply": "值 1 枚。"},
    )
    client.post(
        "/v1/session/redeem",
        json={"player_id": "player-3", "message": "赎回 1"},
    )
    ticket = client.post(
        "/v1/session/turn",
        json={"player_id": "player-3", "message": "典当乙", "reply": "值 2 枚。"},
    )
    assert ticket.text == "2"


def test_redeem_without_number_returns_instructions() -> None:
    client, _ = _client()
    response = client.post(
        "/v1/session/redeem",
        json={"player_id": "player-4", "message": "我想赎回"},
    )
    assert response.status_code == 200
    assert "需要报上当票编号" in response.text
