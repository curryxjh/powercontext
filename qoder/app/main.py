"""FastAPI application for WenGu.

The HTTP layer is deliberately thin: it validates input, delegates every write
to :mod:`app.service`, and serves the no-build frontend from ``web/``. All
learner state lives in the embedded PowerContext runtime started in the
lifespan handler.
"""

from __future__ import annotations

import json
import logging
import time
from collections import Counter
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .coach import load_timezone
from .config import Settings
from .memory_store import LearnerNotFound, MemoryStore, RecordNotFound
from .records import to_iso, utcnow
from .seed import seed_demo
from .service import (
    ValidationError,
    add_feedback,
    add_knowledge,
    create_learner,
    finish_session,
    import_notes,
    learner_data,
    list_feedback,
    record_review,
    resolve_struggle,
    retire_memory,
    revise_memory,
    update_profile,
)

logger = logging.getLogger("wengu")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
DEMO_LEARNER = "demo"


# ----------------------------------------------------------------------
# Request models
# ----------------------------------------------------------------------


class LearnerIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    goal: str = Field(min_length=1, max_length=500)
    daily_minutes: int = Field(default=20, ge=5, le=120)
    style: str = Field(default="", max_length=80)


class ProfileIn(BaseModel):
    name: str
    goal: str
    daily_minutes: int = 20
    style: str = ""


class KnowledgeIn(BaseModel):
    topic: str
    prompt: str
    answer: str
    source_title: str | None = None


class ImportIn(BaseModel):
    text: str
    topic: str = "粘贴的笔记"


class ReviewIn(BaseModel):
    item_id: str
    rating: int = Field(ge=0, le=3)
    note: str = ""
    session_id: str = ""


class SessionIn(BaseModel):
    session_id: str
    started_at: str
    ended_at: str
    reviewed: int = 0
    ratings: dict[str, int] = Field(default_factory=dict)


class ReviseIn(BaseModel):
    human: str = Field(min_length=1, max_length=6000)


class ContextIn(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    max_bytes: int = Field(default=6000, ge=512, le=32768)


class FeedbackIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    text: str = Field(min_length=1, max_length=1000)
    role: str = ""
    name: str = ""


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _store(request: Request) -> MemoryStore:
    return request.app.state.store


def _settings(request: Request) -> Settings:
    return request.app.state.settings


async def _scope(request: Request, slug: str) -> Any:
    try:
        return await _store(request).require_scope(slug)
    except LearnerNotFound as error:
        raise HTTPException(status_code=404, detail="没有找到这个学习者") from error


def _learner_slug(path: str) -> str | None:
    parts = path.strip("/").split("/")
    if len(parts) >= 3 and parts[0] == "api" and parts[1] == "learners" and parts[2] != "":
        return parts[2]
    return None


def _path_pattern(path: str) -> str:
    parts = path.strip("/").split("/")
    if parts[:2] == ["api", "learners"]:
        if len(parts) == 2:
            return "/api/learners"
        if len(parts) == 3:
            return "/api/learners/{slug}"
        tail = [
            "{id}" if part.startswith(("k_", "st_", "mem_", "note_", "f_", "se_")) else part
            for part in parts[3:]
        ]
        return "/api/learners/{slug}/" + "/".join(tail)
    return path


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _read_usage(path: Path, limit: int = 5000) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return rows[-limit:]


# ----------------------------------------------------------------------
# App factory
# ----------------------------------------------------------------------


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = MemoryStore(resolved)
        await store.start()
        app.state.store = store
        app.state.settings = resolved
        if resolved.auto_seed:
            try:
                learners = await store.list_learners()
                if not learners:
                    result = await seed_demo(store, resolved)
                    logger.info("demo learner seeded: %s", result.get("slug"))
            except Exception:  # noqa: BLE001 - never block startup on demo data
                logger.exception("demo seed failed")
        try:
            yield
        finally:
            await store.close()

    app = FastAPI(
        title="温故 WenGu",
        description="A learning continuity coach whose memory lives in PowerContext.",
        version=__version__,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def usage_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        response = await call_next(request)
        path = request.url.path
        if path.startswith("/api/"):
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            local = datetime.now(UTC).astimezone(load_timezone(resolved.timezone))
            try:
                _append_jsonl(
                    resolved.usage_log_path,
                    {
                        "ts": to_iso(utcnow()),
                        "date": local.date().isoformat(),
                        "method": request.method,
                        "path": path,
                        "pattern": _path_pattern(path),
                        "status": response.status_code,
                        "ms": elapsed,
                        "learner": _learner_slug(path),
                    },
                )
            except OSError:
                logger.warning("could not append usage log", exc_info=True)
        return response

    @app.exception_handler(ValidationError)
    async def validation_error_handler(request: Request, exc: ValidationError):  # type: ignore[no-untyped-def]
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(RecordNotFound)
    async def record_not_found_handler(request: Request, exc: RecordNotFound):  # type: ignore[no-untyped-def]
        return JSONResponse({"detail": "没有找到这条记忆或资料"}, status_code=404)

    # ------------------------------------------------------------------
    # Meta
    # ------------------------------------------------------------------

    @app.get("/api/health")
    async def health(request: Request) -> dict[str, Any]:
        info = await _store(request).health()
        info["app_version"] = __version__
        info["timezone"] = resolved.timezone
        return info

    @app.get("/api/bootstrap")
    async def bootstrap(request: Request) -> dict[str, Any]:
        store = _store(request)
        learners = await store.list_learners()
        demo = next((item for item in learners if item["slug"] == DEMO_LEARNER), None)
        health = await store.health()
        return {
            "learners": learners,
            "demo": {
                "slug": DEMO_LEARNER,
                "available": demo is not None,
                "name": demo["name"] if demo else None,
            },
            "powercontext_version": health["powercontext_version"],
            "app_version": __version__,
            "timezone": resolved.timezone,
            "server_now": to_iso(utcnow()),
        }

    @app.get("/api/learners")
    async def learners(request: Request) -> dict[str, Any]:
        return {"learners": await _store(request).list_learners()}

    @app.post("/api/learners", status_code=201)
    async def create_learner_route(request: Request, payload: LearnerIn) -> dict[str, Any]:
        result = await create_learner(
            _store(request),
            resolved,
            name=payload.name,
            goal=payload.goal,
            daily_minutes=payload.daily_minutes,
            style=payload.style,
        )
        return result

    @app.post("/api/demo/seed")
    async def seed_route(request: Request, force: bool = Query(default=False)) -> dict[str, Any]:
        return await seed_demo(_store(request), resolved, force=force)

    # ------------------------------------------------------------------
    # Learner state
    # ------------------------------------------------------------------

    @app.get("/api/learners/{slug}")
    async def learner_route(
        request: Request,
        slug: str,
        include_early: bool = Query(default=False),
        max_items: int | None = Query(default=None, ge=1, le=15),
    ) -> dict[str, Any]:
        await _scope(request, slug)
        data = await learner_data(
            _store(request),
            resolved,
            slug,
            include_early=include_early,
            max_items=max_items,
        )
        return {"scope": data["scope"], "view": data["view"]}

    @app.post("/api/learners/{slug}/profile")
    async def update_profile_route(
        request: Request, slug: str, payload: ProfileIn
    ) -> dict[str, Any]:
        scope = await _scope(request, slug)
        profile = await update_profile(
            _store(request),
            resolved,
            scope,
            name=payload.name,
            goal=payload.goal,
            daily_minutes=payload.daily_minutes,
            style=payload.style,
        )
        return {"profile": profile}

    @app.post("/api/learners/{slug}/knowledge", status_code=201)
    async def add_knowledge_route(
        request: Request, slug: str, payload: KnowledgeIn
    ) -> dict[str, Any]:
        scope = await _scope(request, slug)
        return await add_knowledge(
            _store(request),
            resolved,
            scope,
            topic=payload.topic,
            prompt=payload.prompt,
            answer=payload.answer,
            source_title=payload.source_title,
        )

    @app.post("/api/learners/{slug}/import", status_code=201)
    async def import_route(request: Request, slug: str, payload: ImportIn) -> dict[str, Any]:
        scope = await _scope(request, slug)
        return await import_notes(
            _store(request),
            resolved,
            scope,
            text=payload.text,
            default_topic=payload.topic,
        )

    @app.post("/api/learners/{slug}/reviews", status_code=201)
    async def review_route(request: Request, slug: str, payload: ReviewIn) -> dict[str, Any]:
        scope = await _scope(request, slug)
        return await record_review(
            _store(request),
            resolved,
            scope,
            item_id=payload.item_id,
            rating=payload.rating,
            note=payload.note,
            session_id=payload.session_id,
        )

    @app.post("/api/learners/{slug}/sessions", status_code=201)
    async def session_route(request: Request, slug: str, payload: SessionIn) -> dict[str, Any]:
        scope = await _scope(request, slug)
        return await finish_session(
            _store(request),
            resolved,
            scope,
            session_id=payload.session_id,
            started_at=payload.started_at,
            ended_at=payload.ended_at,
            reviewed=payload.reviewed,
            ratings=payload.ratings,
        )

    @app.post("/api/learners/{slug}/struggles/{entry_id}/resolve")
    async def resolve_struggle_route(request: Request, slug: str, entry_id: str) -> dict[str, Any]:
        scope = await _scope(request, slug)
        return await resolve_struggle(_store(request), scope, entry_id)

    # ------------------------------------------------------------------
    # Memory center: PowerContext as the inspectable source of truth
    # ------------------------------------------------------------------

    @app.get("/api/learners/{slug}/memory")
    async def memory_route(
        request: Request,
        slug: str,
        q: str = Query(default=""),
        kind: str = Query(default=""),
        state: str = Query(default=""),
    ) -> dict[str, Any]:
        store = _store(request)
        scope = await _scope(request, slug)
        records, revision = await store.list_records(scope.scope_id, include_inactive=True)
        search_payload: dict[str, Any] | None = None
        if q.strip():
            search_payload = await store.search(scope.scope_id, q.strip(), limit=40)
            rows = []
            for hit in search_payload["hits"]:
                record = hit.get("record")
                if record is None:
                    continue
                if kind and record["kind"] != kind:
                    continue
                if state and record["state"] != state:
                    continue
                rows.append({**record, "score": hit["score"], "matched_by": hit["matched_by"]})
            records_payload = rows
        else:
            rows = [record.public(include_raw=True) for record in records]
            rows.sort(key=lambda row: row.get("created_at") or "", reverse=True)
            records_payload = [
                row
                for row in rows
                if (not kind or row["kind"] == kind) and (not state or row["state"] == state)
            ]
        counts = Counter(record.kind for record in records)
        return {
            "revision": revision,
            "records": records_payload,
            "search": search_payload,
            "counts": dict(counts),
            "total": len(records),
        }

    @app.get("/api/learners/{slug}/memory/{entry_id}")
    async def memory_detail_route(
        request: Request, slug: str, entry_id: str
    ) -> dict[str, Any]:
        store = _store(request)
        scope = await _scope(request, slug)
        record = await store.find_any(scope.scope_id, entry_id)
        source = None
        source_id = record.meta.get("source_id")
        if source_id:
            try:
                source = await store.get_source(scope.scope_id, str(source_id))
            except RecordNotFound:
                source = None
        return {"record": record.public(include_raw=True), "source": source}

    @app.post("/api/learners/{slug}/memory/{entry_id}/revise")
    async def revise_route(
        request: Request, slug: str, entry_id: str, payload: ReviseIn
    ) -> dict[str, Any]:
        scope = await _scope(request, slug)
        return {
            "record": await revise_memory(
                _store(request), scope, entry_id, human=payload.human
            )
        }

    @app.post("/api/learners/{slug}/memory/{entry_id}/retire")
    async def retire_route(request: Request, slug: str, entry_id: str) -> dict[str, Any]:
        scope = await _scope(request, slug)
        return {"record": await retire_memory(_store(request), scope, entry_id)}

    @app.get("/api/learners/{slug}/search")
    async def search_route(
        request: Request,
        slug: str,
        q: str = Query(min_length=1, max_length=200),
    ) -> dict[str, Any]:
        scope = await _scope(request, slug)
        return await _store(request).search(scope.scope_id, q)

    @app.post("/api/learners/{slug}/context")
    async def context_route(
        request: Request, slug: str, payload: ContextIn
    ) -> dict[str, Any]:
        scope = await _scope(request, slug)
        return await _store(request).prepare_context(
            scope.scope_id, payload.query, max_bytes=payload.max_bytes
        )

    @app.get("/api/learners/{slug}/sources/{source_id}")
    async def source_route(request: Request, slug: str, source_id: str) -> dict[str, Any]:
        scope = await _scope(request, slug)
        return await _store(request).get_source(scope.scope_id, source_id)

    @app.get("/api/learners/{slug}/changes")
    async def changes_route(request: Request, slug: str) -> dict[str, Any]:
        scope = await _scope(request, slug)
        return {"revisions": await _store(request).changes(scope.scope_id)}

    @app.get("/api/learners/{slug}/export")
    async def export_route(request: Request, slug: str) -> JSONResponse:
        store = _store(request)
        scope = await _scope(request, slug)
        records, revision = await store.list_records(scope.scope_id, include_inactive=True)
        payload = {
            "format": "wengu.powercontext.export.v1",
            "exported_at": to_iso(utcnow()),
            "scope": {
                "slug": slug,
                "scope_id": scope.scope_id,
                "title": scope.title,
                "summary": scope.summary,
            },
            "memory_revision": revision,
            "records": [record.public(include_raw=True) for record in records],
        }
        filename = f"wengu-{slug}-{datetime.now(UTC).strftime('%Y%m%d')}.json"
        return JSONResponse(
            content=payload,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/learners/{slug}/proof")
    async def proof_route(
        request: Request,
        slug: str,
        q: str = Query(default="卡点"),
    ) -> dict[str, Any]:
        """Live evidence that the learner state really comes from PowerContext."""

        store = _store(request)
        scope = await _scope(request, slug)
        records, revision = await store.list_records(scope.scope_id, include_inactive=True)
        search = await store.search(scope.scope_id, q, limit=5)
        context = await store.prepare_context(
            scope.scope_id, f"{scope.title} 的学习目标、卡点和最近复习", max_bytes=4000
        )
        inventory = await store.inventory(scope.scope_id)
        return {
            "scope_id": scope.scope_id,
            "memory_revision": revision,
            "inventory": inventory,
            "search": search,
            "context": context,
            "sample_citations": [
                {
                    "kind": record.kind,
                    "entry_id": record.entry_id,
                    "version_id": record.version_id,
                    "row_index": index,
                }
                for index, record in enumerate(records[:5])
            ],
            "health": await store.health(),
        }

    # ------------------------------------------------------------------
    # Feedback and usage evidence
    # ------------------------------------------------------------------

    @app.get("/api/feedback")
    async def feedback_route(request: Request) -> dict[str, Any]:
        items = await list_feedback(_store(request))
        return {"feedback": items, "total": len(items)}

    @app.post("/api/feedback", status_code=201)
    async def add_feedback_route(request: Request, payload: FeedbackIn) -> dict[str, Any]:
        return {
            "record": await add_feedback(
                _store(request),
                rating=payload.rating,
                text=payload.text,
                role=payload.role,
                name=payload.name,
            )
        }

    @app.get("/api/usage")
    async def usage_route(
        request: Request, days: int = Query(default=14, ge=1, le=90)
    ) -> dict[str, Any]:
        rows = _read_usage(resolved.usage_log_path)
        timezone = load_timezone(resolved.timezone)
        today = datetime.now(timezone).date()
        by_day = []
        for offset in range(days - 1, -1, -1):
            day = (today - timedelta(days=offset)).isoformat()
            day_rows = [row for row in rows if row.get("date") == day]
            by_day.append(
                {
                    "date": day,
                    "label": day[5:].replace("-", "/"),
                    "requests": len(day_rows),
                    "writes": sum(1 for row in day_rows if row.get("method") in {"POST", "PATCH", "DELETE"}),
                }
            )
        patterns = Counter(row.get("pattern") or row.get("path") or "" for row in rows)
        store = _store(request)
        learners = await store.list_learners()
        memory = []
        for learner in learners:
            scope = await store.find_scope(learner["slug"])
            if scope is None:
                continue
            inventory = await store.inventory(scope.scope_id)
            memory.append(
                {
                    "slug": learner["slug"],
                    "name": learner["name"],
                    "sources": inventory["sources"],
                    "memory_total": inventory["memory_total"],
                    "memory_active": inventory["memory_active"],
                }
            )
        return {
            "total_requests": len(rows),
            "writes": sum(1 for row in rows if row.get("method") in {"POST", "PATCH", "DELETE"}),
            "active_days": len({row.get("date") for row in rows if row.get("date")}),
            "first_seen": rows[0].get("ts") if rows else None,
            "last_seen": rows[-1].get("ts") if rows else None,
            "by_day": by_day,
            "top_endpoints": [
                {"pattern": pattern, "count": count} for pattern, count in patterns.most_common(8)
            ],
            "recent": list(reversed(rows[-20:])),
            "memory": memory,
            "learners": len(learners),
        }

    # ------------------------------------------------------------------
    # Static frontend
    # ------------------------------------------------------------------

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/favicon.svg")
    async def favicon() -> FileResponse:
        return FileResponse(WEB_DIR / "assets" / "logo.svg")

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
    return app


app = create_app()
