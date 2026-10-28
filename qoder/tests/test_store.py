from __future__ import annotations

import pytest

from app.config import Settings
from app.memory_store import MemoryStore, RecordNotFound
from app.records import knowledge_human, to_iso, utcnow


def make_settings(tmp_path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        usage_log_path=tmp_path / "usage.jsonl",
        db_path=tmp_path / "wengu.db",
        scheduler_path=tmp_path / "wengu.scheduler.db",
        auto_seed=False,
    )


@pytest.fixture
async def store(tmp_path):
    instance = MemoryStore(make_settings(tmp_path))
    await instance.start()
    try:
        yield instance
    finally:
        await instance.close()


async def test_scope_and_profile_roundtrip(store: MemoryStore):
    scope = await store.ensure_learner_scope("alice", "Alice", "复习线代")
    await store.write_profile(
        scope.scope_id,
        name="Alice",
        goal="复习线代",
        daily_minutes=25,
        style="图示",
    )
    profile = await store.get_profile(scope.scope_id)
    assert profile is not None
    assert profile["name"] == "Alice"
    assert profile["daily_minutes"] == 25

    again = await store.ensure_learner_scope("alice", "Alice", "复习线代")
    assert again.scope_id == scope.scope_id

    learners = await store.list_learners()
    assert [learner["slug"] for learner in learners] == ["alice"]
    assert await store.find_scope("missing") is None


async def test_knowledge_chinese_search_revision_and_retire(store: MemoryStore):
    scope = await store.ensure_learner_scope("bob", "Bob", "复习概率")
    moment = utcnow()
    record = await store.append(
        scope.scope_id,
        "knowledge",
        knowledge_human("线代", "特征值是什么", "满足 Av=λv 的 λ 是特征值。"),
        {"id": "k_1", "topic": "线代", "prompt": "特征值是什么", "at": to_iso(moment)},
    )
    assert record.state == "active"
    _, revision_before = await store.list_records(scope.scope_id)
    assert revision_before >= 1

    hits = await store.search(scope.scope_id, "特征值")
    assert any(hit["record"] and hit["record"]["meta"].get("id") == "k_1" for hit in hits["hits"])
    assert hits["memory_revision"] >= revision_before

    revised = await store.revise(
        scope.scope_id,
        record.entry_id,
        kind="knowledge",
        human=knowledge_human("线代", "特征值是什么", "满足 Av=λv 的 λ，且 v 非零。"),
        meta={"id": "k_1", "topic": "线代", "prompt": "特征值是什么", "at": to_iso(moment)},
        reason="test revision",
    )
    assert "v 非零" in revised.human
    _, revision_after = await store.list_records(scope.scope_id)
    assert revision_after > revision_before

    changes = await store.changes(scope.scope_id)
    assert changes
    assert any(change["op"] for revision in changes for change in revision["changes"])

    retired = await store.retire(scope.scope_id, revised.entry_id, reason="test retire")
    assert retired.state != "active"
    active, _ = await store.list_records(scope.scope_id)
    assert active == []
    everything, _ = await store.list_records(scope.scope_id, include_inactive=True)
    assert everything and everything[0].state != "active"

    with pytest.raises(RecordNotFound):
        await store.find_active(scope.scope_id, record.entry_id)


async def test_sources_context_and_inventory(store: MemoryStore):
    scope = await store.ensure_learner_scope("carol", "Carol", "复习机器学习")
    source = await store.capture_source(
        scope.scope_id,
        content="梯度下降沿着负梯度方向更新参数。",
        metadata={"title": "笔记"},
    )
    fetched = await store.get_source(scope.scope_id, source["source_id"])
    assert "负梯度" in fetched["content"]

    await store.append(
        scope.scope_id,
        "knowledge",
        knowledge_human("机器学习", "梯度下降", "沿负梯度方向更新参数。"),
        {"id": "k_1", "topic": "机器学习", "prompt": "梯度下降", "at": to_iso(utcnow())},
    )
    prepared = await store.prepare_context(scope.scope_id, "梯度下降 学习目标", max_bytes=2000)
    assert prepared["status"]
    assert prepared["content_bytes"] >= 0
    assert "content" in prepared

    inventory = await store.inventory(scope.scope_id)
    assert inventory["sources"] == 1
    assert inventory["memory_active"] == 1
    assert inventory["model_requests"] == 0

    with pytest.raises(RecordNotFound):
        await store.get_source(scope.scope_id, "note_missing")
