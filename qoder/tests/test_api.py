from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
async def client(tmp_path):
    settings = Settings(
        data_dir=tmp_path,
        usage_log_path=tmp_path / "usage.jsonl",
        db_path=tmp_path / "wengu.db",
        scheduler_path=tmp_path / "wengu.scheduler.db",
        auto_seed=False,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as instance:
            yield instance


async def create_learner(client: AsyncClient) -> str:
    response = await client.post(
        "/api/learners",
        json={"name": "测试同学", "goal": "两周后通过线代小测", "daily_minutes": 20},
    )
    assert response.status_code == 201, response.text
    return response.json()["slug"]


async def add_card(client: AsyncClient, slug: str, prompt: str = "特征值是什么") -> str:
    response = await client.post(
        f"/api/learners/{slug}/knowledge",
        json={
            "topic": "线代",
            "prompt": prompt,
            "answer": f"关于「{prompt}」的说明，满足 Av=λv 的非零向量 v 对应特征值 λ。",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["item"]["item_id"]


async def test_health_reports_powercontext_runtime(client: AsyncClient):
    payload = (await client.get("/api/health")).json()
    assert payload["status"] == "ok"
    assert payload["powercontext_version"].startswith("1.2")
    assert payload["app_version"]
    assert payload["timezone"]


async def test_learner_flow_writes_and_reads_powercontext_memory(client: AsyncClient):
    slug = await create_learner(client)

    view = (await client.get(f"/api/learners/{slug}")).json()
    assert view["view"]["profile"]["name"] == "测试同学"
    assert view["view"]["plan"]["empty"] is True

    item_id = await add_card(client, slug)
    second_item = await add_card(client, slug, prompt="特征向量是什么")

    forgot = await client.post(
        f"/api/learners/{slug}/reviews",
        json={"item_id": item_id, "rating": 0, "note": "分不清特征向量"},
    )
    assert forgot.status_code == 201, forgot.text
    assert forgot.json()["requeue"] is True
    assert forgot.json()["struggle"] is not None

    remembered = await client.post(
        f"/api/learners/{slug}/reviews",
        json={"item_id": second_item, "rating": 2},
    )
    assert remembered.status_code == 201, remembered.text
    assert remembered.json()["requeue"] is False
    assert remembered.json()["item"]["interval_days"] == 2

    memory = (await client.get(f"/api/learners/{slug}/memory")).json()
    assert memory["counts"]["knowledge"] == 2
    assert memory["counts"]["review"] == 2
    assert memory["counts"]["struggle"] == 1
    assert memory["total"] >= 4

    found = (await client.get(f"/api/learners/{slug}/memory", params={"q": "特征值"})).json()
    assert found["search"]["hits"]

    context = await client.post(
        f"/api/learners/{slug}/context",
        json={"query": "线代 特征值 卡点", "max_bytes": 4000},
    )
    assert context.status_code == 200, context.text
    assert "status" in context.json()

    proof = (await client.get(f"/api/learners/{slug}/proof")).json()
    assert proof["health"]["powercontext_version"].startswith("1.2")
    assert proof["inventory"]["memory_active"] >= 4
    assert proof["inventory"]["model_requests"] == 0
    assert proof["sample_citations"]
    assert proof["memory_revision"] == memory["revision"] or proof["memory_revision"] > 0


async def test_import_creates_cards_and_source(client: AsyncClient):
    slug = await create_learner(client)
    notes = """# 概率复习

## 条件概率
在已知事件 B 发生的条件下，事件 A 发生的概率写作 P(A|B)，等于 P(AB)/P(B)。

## 全概率公式
把样本空间按互斥事件划分，用各分支的条件概率加权求和，得到目标事件的概率。
"""
    response = await client.post(f"/api/learners/{slug}/import", json={"text": notes, "topic": ""})
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["parsed"]["title"] == "概率复习"
    assert payload["parsed"]["items"] == 2
    assert len(payload["created"]) == 2
    assert payload["source"]["source_id"]

    memory = (await client.get(f"/api/learners/{slug}/memory")).json()
    assert memory["counts"]["knowledge"] == 2


async def test_memory_revise_retire_and_proof_history(client: AsyncClient):
    slug = await create_learner(client)
    item_id = await add_card(client, slug)
    memory = (await client.get(f"/api/learners/{slug}/memory")).json()
    entry = next(row for row in memory["records"] if row["kind"] == "knowledge")

    revised = await client.post(
        f"/api/learners/{slug}/memory/{entry['entry_id']}/revise",
        json={"human": "【线代】特征值是什么\n---\n满足 Av=λv 的非零向量 v，对应特征值 λ。"},
    )
    assert revised.status_code == 200, revised.text
    assert revised.json()["record"]["memory_revision"] > entry["memory_revision"]

    retired = await client.post(f"/api/learners/{slug}/memory/{entry['entry_id']}/retire")
    assert retired.status_code == 200, retired.text
    assert retired.json()["record"]["state"] != "active"

    view = (await client.get(f"/api/learners/{slug}")).json()
    assert view["view"]["plan"]["empty"] is True

    changes = (await client.get(f"/api/learners/{slug}/changes")).json()
    assert changes["revisions"]


async def test_feedback_is_stored_as_shared_memory(client: AsyncClient):
    response = await client.post(
        "/api/feedback",
        json={"rating": 5, "text": "第一次看到学习记录能直接查来源，很放心。", "role": "学生"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["record"]["kind"] == "feedback"

    listed = (await client.get("/api/feedback")).json()
    assert listed["total"] == 1
    assert listed["feedback"][0]["meta"]["rating"] == 5


async def test_validation_and_missing_learner(client: AsyncClient):
    assert (await client.get("/api/learners/missing")).status_code == 404
    assert (
        await client.post("/api/feedback", json={"rating": 0, "text": "too low"})
    ).status_code == 422

    slug = await create_learner(client)
    item_id = await add_card(client, slug)
    bad_rating = await client.post(
        f"/api/learners/{slug}/reviews", json={"item_id": item_id, "rating": 9}
    )
    assert bad_rating.status_code == 422
    empty_import = await client.post(
        f"/api/learners/{slug}/import", json={"text": "短", "topic": "线代"}
    )
    assert empty_import.status_code == 400


async def test_demo_seed_is_idempotent_and_visible_on_bootstrap(client: AsyncClient):
    first = await client.post("/api/demo/seed")
    assert first.status_code == 200, first.text
    assert first.json()["created"] is True
    assert first.json()["cards"] == 10

    second = await client.post("/api/demo/seed")
    assert second.status_code == 200
    assert second.json()["created"] is False

    bootstrap = (await client.get("/api/bootstrap")).json()
    assert bootstrap["demo"]["available"] is True
    assert bootstrap["demo"]["slug"] == "demo"

    view = (await client.get("/api/learners/demo")).json()
    assert len(view["view"]["items"]) == 10
    assert view["view"]["stats"]["streak"] >= 1
    assert view["view"]["plan"]["empty"] is False
    assert view["view"]["continuity"]["has_history"] is True
    assert view["view"]["stats"]["memory"]["model_requests"] == 0
