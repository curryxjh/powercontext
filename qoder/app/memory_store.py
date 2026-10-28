"""Embedded PowerContext runtime used as WenGu's only learner-data store.

Every learner is a PowerContext Scope. Knowledge cards, review events,
struggle notes, session summaries and feedback are Memory entries inside that
Scope; original imported notes are captured as PowerContext Sources. The app
does not keep a second database: all learner state is derived by replaying
these memory entries.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import AsyncExitStack
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any, Iterable

from powercontext.builtin.artifacts.memory import MemoryEntryInput
from powercontext.builtin.persistence.sqlite import SQLiteConfig
from powercontext.builtin.records import BaseValueNotFoundError
from powercontext.builtin.runtime import (
    BuiltinConfig,
    CaptureSource,
    PrepareContextRequest,
    RememberMemoryRequest,
    RetireMemoryEntryRequest,
    ReviseMemoryEntryRequest,
    SearchMemoryRequest,
    open_builtin_runtime,
)
from powercontext.builtin.scope.models import ScopeDescriptor, ScopeDraft, ScopeExternalReference, ScopeMutation

from .config import Settings
from .records import MemoryRecord, encode_record, utcnow, to_iso

LEARNER_REF = "wengu_learner"
FEEDBACK_REF = "wengu_feedback"
CONTENT_SOURCE = "content"


class LearnerNotFound(KeyError):
    pass


class RecordNotFound(KeyError):
    pass


def _matched_by(value: Any) -> str:
    return str(getattr(value, "value", value))


class MemoryStore:
    """Async facade over one embedded PowerContext runtime."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._stack = AsyncExitStack()
        self._runtime: Any = None
        self._write_lock = asyncio.Lock()

    async def start(self) -> None:
        self.settings.ensure_dirs()
        url = f"sqlite+aiosqlite:///{self.settings.db_path.as_posix()}"
        config = BuiltinConfig(database=SQLiteConfig(url=url))
        self._runtime = await self._stack.enter_async_context(
            open_builtin_runtime(config, scheduler_path=self.settings.scheduler_path)
        )

    async def close(self) -> None:
        await self._stack.aclose()

    # ------------------------------------------------------------------
    # Scopes: one per learner, plus one shared feedback inbox
    # ------------------------------------------------------------------

    async def _all_scopes(self) -> list[ScopeDescriptor]:
        return list(await self._runtime.scopes.list())

    async def find_scope(self, slug: str, ref_kind: str = LEARNER_REF) -> ScopeDescriptor | None:
        for scope in await self._all_scopes():
            for reference in scope.external_references:
                if reference.kind == ref_kind and reference.value == slug:
                    return scope
        return None

    async def require_scope(self, slug: str, ref_kind: str = LEARNER_REF) -> ScopeDescriptor:
        scope = await self.find_scope(slug, ref_kind)
        if scope is None:
            raise LearnerNotFound(slug)
        return scope

    async def ensure_learner_scope(
        self,
        slug: str,
        name: str,
        goal: str,
        *,
        title: str | None = None,
        summary: str | None = None,
    ) -> ScopeDescriptor:
        return await self._runtime.scopes.create(
            ScopeDraft(
                title=(title or name).strip()[:200],
                summary=(summary or goal or "温故学习接力学员").strip()[:4000],
                external_references=(ScopeExternalReference(kind=LEARNER_REF, value=slug),),
                idempotency_key=f"wengu:learner:{slug}",
            )
        )

    async def ensure_feedback_scope(self) -> ScopeDescriptor:
        return await self._runtime.scopes.create(
            ScopeDraft(
                title="温故反馈箱",
                summary="WenGu 使用反馈",
                external_references=(ScopeExternalReference(kind=FEEDBACK_REF, value="inbox"),),
                idempotency_key="wengu:feedback-inbox",
            )
        )

    async def list_learners(self) -> list[dict[str, Any]]:
        learners: list[dict[str, Any]] = []
        for scope in await self._all_scopes():
            ref = next((r for r in scope.external_references if r.kind == LEARNER_REF), None)
            if ref is None:
                continue
            learners.append(
                {
                    "slug": ref.value,
                    "name": scope.title,
                    "goal": scope.summary,
                    "scope_id": scope.scope_id,
                    "scope_version": scope.version,
                }
            )
        learners.sort(key=lambda item: item["name"].casefold())
        return learners

    async def update_learner_scope(self, scope: ScopeDescriptor, *, name: str, goal: str) -> ScopeDescriptor:
        return await self._runtime.scopes.update(
            scope.scope_id,
            ScopeMutation(
                expected_version=scope.version,
                title=name.strip()[:200],
                summary=goal.strip()[:4000],
                parent_scope_id=scope.parent_scope_id,
                context_references=scope.context_references,
                external_references=scope.external_references,
            ),
        )

    # ------------------------------------------------------------------
    # Memory entries
    # ------------------------------------------------------------------

    async def list_records(
        self, scope_id: str, *, include_inactive: bool = False
    ) -> tuple[list[MemoryRecord], int]:
        page = await self._runtime.memory.for_scope(scope_id).list(include_inactive=include_inactive)
        revision = int(page.memory_ref.revision) if page.memory_ref is not None else 0
        return [MemoryRecord.from_entry(entry) for entry in page.entries], revision

    async def memory_revision(self, scope_id: str) -> int:
        _, revision = await self.list_records(scope_id)
        return revision

    async def append_many(
        self, scope_id: str, items: Iterable[tuple[str, str, dict[str, Any]]]
    ) -> list[MemoryRecord]:
        prepared = [
            MemoryEntryInput(kind=kind, text=encode_record(kind, human, meta))
            for kind, human, meta in items
        ]
        if not prepared:
            return []
        async with self._write_lock:
            before, _ = await self.list_records(scope_id, include_inactive=True)
            before_ids = {record.entry_id for record in before}
            await self._runtime.memory.for_scope(scope_id).remember(
                RememberMemoryRequest(entries=tuple(prepared))
            )
            after, _ = await self.list_records(scope_id, include_inactive=True)
            return [record for record in after if record.entry_id not in before_ids]

    async def append(
        self, scope_id: str, kind: str, human: str, meta: dict[str, Any]
    ) -> MemoryRecord:
        created = await self.append_many(scope_id, [(kind, human, meta)])
        if not created:
            raise RuntimeError("PowerContext did not create a memory entry")
        return created[-1]

    async def find_active(self, scope_id: str, entry_id: str) -> MemoryRecord:
        records, _ = await self.list_records(scope_id)
        for record in records:
            if record.entry_id == entry_id:
                return record
        raise RecordNotFound(entry_id)

    async def find_any(self, scope_id: str, entry_id: str) -> MemoryRecord:
        records, _ = await self.list_records(scope_id, include_inactive=True)
        for record in records:
            if record.entry_id == entry_id:
                return record
        raise RecordNotFound(entry_id)

    async def revise(
        self,
        scope_id: str,
        entry_id: str,
        *,
        kind: str,
        human: str,
        meta: dict[str, Any],
        reason: str,
    ) -> MemoryRecord:
        async with self._write_lock:
            current = await self.find_active(scope_id, entry_id)
            result = await self._runtime.memory.for_scope(scope_id).revise(
                ReviseMemoryEntryRequest(
                    citation=current.citation,
                    kind=kind,
                    text=encode_record(kind, human, meta),
                    reason=reason,
                )
            )
            if result.entry is None:
                raise RuntimeError("PowerContext did not return the revised entry")
            return MemoryRecord.from_entry(result.entry)

    async def retire(self, scope_id: str, entry_id: str, *, reason: str) -> MemoryRecord:
        async with self._write_lock:
            current = await self.find_active(scope_id, entry_id)
            result = await self._runtime.memory.for_scope(scope_id).retire(
                RetireMemoryEntryRequest(citation=current.citation, reason=reason)
            )
            if result.entry is None:
                raise RuntimeError("PowerContext did not return the retired entry")
            return MemoryRecord.from_entry(result.entry)

    async def retire_all(self, scope_id: str, *, reason: str) -> int:
        """Retire every active entry, refreshing citations after each revision."""

        retired = 0
        for _ in range(2_000):
            records, _ = await self.list_records(scope_id)
            if not records:
                break
            await self.retire(scope_id, records[0].entry_id, reason=reason)
            retired += 1
        return retired

    # ------------------------------------------------------------------
    # Search, context assembly, sources, inventory
    # ------------------------------------------------------------------

    async def search(self, scope_id: str, query: str, *, limit: int = 20) -> dict[str, Any]:
        page = await self._runtime.memory.for_scope(scope_id).search(
            SearchMemoryRequest(query=query, limit=max(1, min(limit, 50)), mode="auto")
        )
        records, revision = await self.list_records(scope_id, include_inactive=True)
        by_entry = {record.entry_id: record for record in records}
        hits: list[dict[str, Any]] = []
        for hit in page.hits:
            record = by_entry.get(str(hit.entry_id))
            hits.append(
                {
                    "entry_id": str(hit.entry_id),
                    "version_id": str(hit.entry_version_id),
                    "score": float(hit.score),
                    "matched_by": [_matched_by(value) for value in hit.matched_by],
                    "text": str(hit.text),
                    "record": record.public() if record else None,
                }
            )
        return {
            "query": query,
            "mode": str(page.mode) if page.mode is not None else None,
            "memory_revision": revision,
            "hits": hits,
        }

    async def prepare_context(self, scope_id: str, query: str, *, max_bytes: int = 6000) -> dict[str, Any]:
        prepared = await self._runtime.context.for_scope(scope_id).prepare(
            PrepareContextRequest(query=query, max_bytes=max(512, min(max_bytes, 32768)))
        )
        return {
            "status": str(prepared.status),
            "content": prepared.content,
            "content_bytes": int(prepared.content_bytes),
        }

    async def capture_source(
        self,
        scope_id: str,
        *,
        content: str,
        metadata: dict[str, Any] | None = None,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        identifier = source_id or f"note_{uuid.uuid4().hex[:16]}"
        clipped = content[:190_000]
        receipt = await self._runtime.sources.for_scope(scope_id).capture(
            CaptureSource(source_id=identifier, content=clipped, metadata=metadata or {})
        )
        return {
            "source_id": receipt.source_ref.source_id,
            "source_type": receipt.source_ref.source_type,
            "sequence": int(receipt.sequence),
            "content": clipped,
            "metadata": metadata or {},
        }

    async def get_source(self, scope_id: str, source_id: str) -> dict[str, Any]:
        try:
            record = await self._runtime.records.for_scope(scope_id).get_source(CONTENT_SOURCE, source_id)
        except BaseValueNotFoundError as error:
            raise RecordNotFound(source_id) from error
        if record is None:
            raise RecordNotFound(source_id)
        return {
            "source_id": record.source_id,
            "source_type": record.source_type,
            "content": record.content,
            "position": int(record.position),
            "digest": record.content_digest,
        }

    async def inventory(self, scope_id: str) -> dict[str, Any]:
        stats = await self._runtime.statistics.for_scope(scope_id).overview()
        inventory = stats.inventory
        memory = inventory.memory.entries
        usage = stats.usage.totals
        return {
            "sources": int(inventory.sources.total),
            "artifacts": int(inventory.artifacts.total),
            "memory_total": int(memory.total),
            "memory_active": int(memory.active),
            "memory_inactive": int(memory.inactive),
            "by_kind": [
                {
                    "kind": item.kind,
                    "total": int(item.total),
                    "active": int(item.active),
                    "inactive": int(item.inactive),
                }
                for item in memory.by_kind
            ],
            "model_requests": int(usage.generation.requests + usage.embedding.requests),
        }

    async def changes(self, scope_id: str, *, limit: int = 30) -> list[dict[str, Any]]:
        page = await self._runtime.memory.for_scope(scope_id).changes()
        revisions = list(page.revisions)[:limit]
        return [
            {
                "revision": int(revision.memory_ref.revision),
                "changes": [
                    {
                        "op": str(change.op),
                        "entry_id": str(change.entry_id),
                        "reason": change.reason,
                        "from_version_id": change.from_entry_version_id,
                        "to_version_id": change.to_entry_version_id,
                    }
                    for change in revision.changes
                ],
            }
            for revision in revisions
        ]

    # ------------------------------------------------------------------
    # Profile helpers
    # ------------------------------------------------------------------

    async def get_profile(self, scope_id: str) -> dict[str, Any] | None:
        records, _ = await self.list_records(scope_id)
        profiles = [record for record in records if record.kind == "profile"]
        if not profiles:
            return None
        latest = max(profiles, key=lambda record: record.at or utcnow())
        return {"record": latest, **latest.meta}

    async def write_profile(
        self,
        scope_id: str,
        *,
        name: str,
        goal: str,
        daily_minutes: int,
        style: str,
        revise_entry_id: str | None = None,
        at: Any = None,
    ) -> MemoryRecord:
        human = (
            f"我是{name}。学习目标：{goal}。每天可投入 {daily_minutes} 分钟，"
            f"偏好{style or '简洁'}的讲解方式。"
        )
        meta = {
            "name": name,
            "goal": goal,
            "daily_minutes": int(daily_minutes),
            "style": style,
            "at": to_iso(at) if at is not None else to_iso(utcnow()),
        }
        if revise_entry_id:
            return await self.revise(
                scope_id,
                revise_entry_id,
                kind="profile",
                human=human,
                meta=meta,
                reason="learner updated profile",
            )
        return await self.append(scope_id, "profile", human, meta)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health(self) -> dict[str, Any]:
        scopes = await self._all_scopes()
        learners = [scope for scope in scopes if any(r.kind == LEARNER_REF for r in scope.external_references)]
        return {
            "status": "ok",
            "powercontext_version": package_version("powercontext"),
            "database": str(self.settings.db_path),
            "scopes": len(scopes),
            "learners": len(learners),
        }
