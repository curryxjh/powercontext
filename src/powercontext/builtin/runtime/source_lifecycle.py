# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# ruff: noqa: TRY003
"""Persisted dependency graphs for Source-driven artifact availability."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from powercontext.artifacts import ArtifactRef, MemoryCitation
from powercontext.builtin.artifacts.memory import MemoryService
from powercontext.builtin.artifacts.topic_memory import TopicMemory
from powercontext.builtin.persistence.artifacts import ArtifactRepository
from powercontext.builtin.persistence.database import AsyncDatabase
from powercontext.builtin.persistence.errors import RepositoryNotFoundError
from powercontext.builtin.persistence.sources import SourceRepository
from powercontext.builtin.persistence.tables import SOURCE_LIFECYCLE_NODES_TABLE
from powercontext.sources import SourceRef

LifecycleKind = Literal["source", "memory", "topic"]
LifecyclePolicy = Literal["all", "any"]
LifecycleReference = SourceRef | MemoryCitation | ArtifactRef


class SourceLifecycleError(ValueError):
    """Report an invalid lifecycle graph, event, or availability transition."""


class SourceLifecycleEvent(BaseModel):
    """One strict, replayable availability event for a registered Source."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    node_id: str
    revision: int = Field(gt=0)
    sequence: int = Field(gt=0)
    available: bool
    reason: str

    @field_validator("node_id", "reason")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("lifecycle text fields must not be blank")
        return value


@dataclass(frozen=True, slots=True)
class _Node:
    scope_id: str
    node_id: str
    kind: LifecycleKind
    reference: LifecycleReference
    parents: tuple[str, ...]
    policy: LifecyclePolicy | None
    available: bool
    revision: int | None
    sequence: int | None
    reason: str | None


MemoryFactory = Callable[[AsyncConnection], MemoryService]


class SourceLifecycleService:
    """Own one Scope's immutable dependency graph and mutable node state."""

    def __init__(
        self,
        *,
        database: AsyncDatabase,
        scope_id: str,
        sources: SourceRepository,
        artifacts: ArtifactRepository,
        memory_factory: MemoryFactory,
        lock: asyncio.Lock,
    ) -> None:
        self._database = database
        self._scope_id = scope_id
        self._sources = sources
        self._artifacts = artifacts
        self._memory_factory = memory_factory
        self._lock = lock

    async def register_source(self, node_id: str, source_ref: SourceRef, *, revision: int) -> None:
        _validate_node_id(node_id)
        if type(revision) is not int or revision < 1:
            raise SourceLifecycleError("source revision must be a positive integer")
        async with self._lock, self._database.transaction() as connection:
            try:
                await self._sources.get(connection, self._scope_id, source_ref)
            except RepositoryNotFoundError as error:
                raise SourceLifecycleError("source reference is not readable") from error
            await self._register(
                connection,
                _Node(
                    self._scope_id,
                    node_id,
                    "source",
                    source_ref,
                    (),
                    None,
                    True,
                    revision,
                    None,
                    None,
                ),
            )

    async def register_memory(
        self,
        node_id: str,
        citation: MemoryCitation,
        *,
        parents: tuple[str, ...],
        policy: LifecyclePolicy,
    ) -> None:
        await self._register_derived(node_id, citation, parents, policy, "memory")

    async def register_topic(
        self,
        node_id: str,
        artifact_ref: ArtifactRef,
        *,
        parents: tuple[str, ...],
        policy: LifecyclePolicy,
    ) -> None:
        if artifact_ref.family != TopicMemory.family:
            raise SourceLifecycleError("topic registration requires a topic-memory ArtifactRef")
        await self._register_derived(node_id, artifact_ref, parents, policy, "topic")

    async def _register_derived(
        self,
        node_id: str,
        reference: LifecycleReference,
        parents: tuple[str, ...],
        policy: LifecyclePolicy,
        kind: LifecycleKind,
    ) -> None:
        _validate_node_id(node_id)
        _validate_parents(parents, policy)
        async with self._lock, self._database.transaction() as connection:
            if kind == "memory":
                if not isinstance(reference, MemoryCitation):
                    raise SourceLifecycleError("memory registration requires a MemoryCitation")
                try:
                    await self._memory_factory(connection).validate_citation(reference)
                except Exception as error:
                    raise SourceLifecycleError("memory citation is not readable") from error
            else:
                if not isinstance(reference, ArtifactRef):
                    raise SourceLifecycleError("topic registration requires an ArtifactRef")
                try:
                    artifact = await self._artifacts.get(connection, self._scope_id, reference)
                except RepositoryNotFoundError as error:
                    raise SourceLifecycleError("topic ArtifactRef is not readable") from error
                if not isinstance(artifact, TopicMemory):
                    raise SourceLifecycleError("topic registration requires a topic-memory ArtifactRef")
            nodes = await self._load_nodes(connection)
            parent_nodes = tuple(nodes.get(parent) for parent in parents)
            if any(parent is None for parent in parent_nodes):
                raise SourceLifecycleError("all lifecycle parents must be registered first")
            available = _combine(tuple(parent.available for parent in parent_nodes if parent is not None), policy)
            requested = _Node(
                self._scope_id,
                node_id,
                kind,
                reference,
                parents,
                policy,
                available,
                None,
                None,
                None,
            )
            existing = nodes.get(node_id)
            if existing is not None and not _same_registration(existing, requested):
                raise SourceLifecycleError("lifecycle node identity conflicts with durable state")
            await self._register(connection, requested)
            if not available:
                await self._set_memory_states(connection, ((reference, False),))

    async def _register(self, connection: AsyncConnection, requested: _Node) -> None:
        existing = await self._load_node(connection, requested.node_id)
        if existing is not None:
            if not _same_registration(existing, requested):
                raise SourceLifecycleError("lifecycle node identity conflicts with durable state")
            return
        payload = _encode_node(requested)
        await connection.execute(insert(SOURCE_LIFECYCLE_NODES_TABLE).values(**payload))

    async def apply(self, event: SourceLifecycleEvent) -> list[str]:  # noqa: C901
        async with self._lock, self._database.transaction() as connection:
            nodes = await self._load_nodes(connection)
            source = nodes.get(event.node_id)
            if source is None or source.kind != "source":
                raise SourceLifecycleError("event must target a registered Source")
            if source.revision != event.revision:
                raise SourceLifecycleError("event revision does not match the registered Source")
            if source.sequence is not None:
                if event.sequence < source.sequence:
                    raise SourceLifecycleError("event sequence must be monotonic")
                if event.sequence == source.sequence:
                    if source.available != event.available or source.reason != event.reason:
                        raise SourceLifecycleError("event sequence conflicts with durable state")
                    return sorted(node.node_id for node in nodes.values() if node.available)

            desired = dict(nodes)
            desired[event.node_id] = _Node(
                source.scope_id,
                source.node_id,
                source.kind,
                source.reference,
                source.parents,
                source.policy,
                event.available,
                source.revision,
                event.sequence,
                event.reason,
            )
            for node_id in _topological_order(desired):
                node = desired[node_id]
                if node.kind == "source":
                    continue
                parent_states = tuple(desired[parent].available for parent in node.parents)
                desired[node_id] = _Node(
                    node.scope_id,
                    node.node_id,
                    node.kind,
                    node.reference,
                    node.parents,
                    node.policy,
                    _combine(parent_states, node.policy or "all"),
                    node.revision,
                    node.sequence,
                    node.reason,
                )

            await self._apply_memory_states(connection, nodes, desired)
            for node_id, node in desired.items():
                if node == nodes[node_id]:
                    continue
                await connection.execute(
                    update(SOURCE_LIFECYCLE_NODES_TABLE)
                    .where(
                        SOURCE_LIFECYCLE_NODES_TABLE.c.scope_id == self._scope_id,
                        SOURCE_LIFECYCLE_NODES_TABLE.c.node_id == node_id,
                    )
                    .values(
                        available=node.available,
                        event_sequence=node.sequence,
                        event_reason=node.reason,
                    )
                )
            return sorted(node.node_id for node in desired.values() if node.available)

    async def _apply_memory_states(
        self,
        connection: AsyncConnection,
        before: dict[str, _Node],
        after: dict[str, _Node],
    ) -> None:
        grouped: dict[str, list[tuple[_Node, bool]]] = {}
        for node_id, node in after.items():
            if node.kind != "memory" or before[node_id].available == node.available:
                continue
            if not isinstance(node.reference, MemoryCitation):
                raise SourceLifecycleError("stored memory reference is invalid")
            grouped.setdefault(node.reference.memory_ref.artifact_id, []).append((node, node.available))

        for changes in grouped.values():
            citation = cast(MemoryCitation, changes[0][0].reference)
            service = self._memory_factory(connection)
            current, current_entries = await service.head_entries(citation.memory_ref.artifact_id)
            entries = {entry.entry_id: entry for entry in current_entries}
            selected = []
            for node, _available in changes:
                reference = cast(MemoryCitation, node.reference)
                entry = entries.get(reference.entry_id)
                if entry is None:
                    raise SourceLifecycleError("registered Memory entry no longer exists")
                selected.append(entry)
            active = [entry for entry, (_node, available) in zip(selected, changes, strict=True) if available]
            inactive = [entry for entry, (_node, available) in zip(selected, changes, strict=True) if not available]
            if inactive:
                await service.forget(current, entries=inactive, reason="source lifecycle withdrawal")
            if active:
                refreshed, refreshed_entries = await service.head_entries(citation.memory_ref.artifact_id)
                refreshed_by_id = {entry.entry_id: entry for entry in refreshed_entries}
                await service.reactivate(
                    refreshed,
                    entries=[refreshed_by_id[entry.entry_id] for entry in active],
                    reason="source lifecycle restore",
                )

    async def _set_memory_states(
        self,
        connection: AsyncConnection,
        changes: tuple[tuple[LifecycleReference, bool], ...],
    ) -> None:
        memory_changes = tuple(
            (reference, available) for reference, available in changes if isinstance(reference, MemoryCitation)
        )
        if not memory_changes:
            return
        first = memory_changes[0][0]
        service = self._memory_factory(connection)
        current, current_entries = await service.head_entries(first.memory_ref.artifact_id)
        by_id = {entry.entry_id: entry for entry in current_entries}
        active = [by_id[reference.entry_id] for reference, available in memory_changes if available]
        inactive = [by_id[reference.entry_id] for reference, available in memory_changes if not available]
        if inactive:
            await service.forget(current, entries=inactive, reason="source lifecycle withdrawal")
        if active:
            refreshed, refreshed_entries = await service.head_entries(first.memory_ref.artifact_id)
            refreshed_by_id = {entry.entry_id: entry for entry in refreshed_entries}
            await service.reactivate(
                refreshed,
                entries=[refreshed_by_id[entry.entry_id] for entry in active],
                reason="source lifecycle restore",
            )

    async def resolve(
        self,
        node_id: str,
        *,
        purpose: Literal["generation", "audit"],
    ) -> LifecycleReference:
        if purpose not in {"generation", "audit"}:
            raise SourceLifecycleError("unknown lifecycle resolution purpose")
        async with self._database.transaction() as connection:
            node = await self._load_node(connection, node_id)
            if node is None:
                raise SourceLifecycleError("unknown lifecycle node")
            if purpose == "generation" and not node.available:
                raise SourceLifecycleError("lifecycle node is unavailable for generation")
            return node.reference

    async def unavailable_topic_refs(self, connection: AsyncConnection) -> set[tuple[str, str, int]]:
        """Identify withdrawn Topics before the search result limit is applied."""

        nodes = await self._load_nodes(connection)
        return {
            (node.reference.family, node.reference.artifact_id, node.reference.revision)
            for node in nodes.values()
            if node.kind == "topic" and isinstance(node.reference, ArtifactRef) and not node.available
        }

    async def _load_node(self, connection: AsyncConnection, node_id: str) -> _Node | None:
        row = (
            (
                await connection.execute(
                    select(SOURCE_LIFECYCLE_NODES_TABLE).where(
                        SOURCE_LIFECYCLE_NODES_TABLE.c.scope_id == self._scope_id,
                        SOURCE_LIFECYCLE_NODES_TABLE.c.node_id == node_id,
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return None if row is None else _decode_node(row)

    async def _load_nodes(self, connection: AsyncConnection) -> dict[str, _Node]:
        rows = (
            await connection.execute(
                select(SOURCE_LIFECYCLE_NODES_TABLE).where(SOURCE_LIFECYCLE_NODES_TABLE.c.scope_id == self._scope_id)
            )
        ).mappings()
        return {node.node_id: node for node in (_decode_node(row) for row in rows)}


def _validate_node_id(node_id: str) -> None:
    if type(node_id) is not str or not node_id.strip():
        raise SourceLifecycleError("node_id must be a non-empty string")
    if node_id != node_id.strip():
        raise SourceLifecycleError("node_id must not have surrounding whitespace")


def _validate_parents(parents: tuple[str, ...], policy: LifecyclePolicy) -> None:
    if policy not in {"all", "any"}:
        raise SourceLifecycleError("policy must be 'all' or 'any'")
    if not parents or any(type(parent) is not str or not parent.strip() for parent in parents):
        raise SourceLifecycleError("derived lifecycle nodes require at least one parent")
    if len(set(parents)) != len(parents):
        raise SourceLifecycleError("lifecycle parents must be unique")


def _combine(states: tuple[bool, ...], policy: LifecyclePolicy) -> bool:
    return all(states) if policy == "all" else any(states)


def _same_registration(left: _Node, right: _Node) -> bool:
    return (
        left.kind == right.kind
        and left.reference == right.reference
        and left.parents == right.parents
        and left.policy == right.policy
        and left.revision == right.revision
    )


def _topological_order(nodes: dict[str, _Node]) -> tuple[str, ...]:
    ordered: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        if node_id in visiting:
            raise SourceLifecycleError("lifecycle graph contains a cycle")
        visiting.add(node_id)
        for parent in nodes[node_id].parents:
            if parent not in nodes:
                raise SourceLifecycleError("lifecycle parent is missing")
            visit(parent)
        visiting.remove(node_id)
        visited.add(node_id)
        ordered.append(node_id)

    for node_id in sorted(nodes):
        visit(node_id)
    return tuple(ordered)


def _encode_node(node: _Node) -> dict[str, object]:
    reference = node.reference.model_dump(mode="json")
    return {
        "scope_id": node.scope_id,
        "node_id": node.node_id,
        "kind": node.kind,
        "reference": json.dumps(reference, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        "parents": json.dumps(node.parents, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        "policy": node.policy,
        "available": node.available,
        "source_revision": node.revision,
        "event_sequence": node.sequence,
        "event_reason": node.reason,
    }


def _decode_node(row) -> _Node:  # type: ignore[no-untyped-def]
    raw_reference = json.loads(bytes(row["reference"]).decode("utf-8"))
    kind = str(row["kind"])
    if kind == "source":
        reference: LifecycleReference = SourceRef.model_validate(raw_reference)
    elif kind == "memory":
        reference = MemoryCitation.model_validate(raw_reference)
    elif kind == "topic":
        reference = ArtifactRef.model_validate(raw_reference)
    else:
        raise SourceLifecycleError("stored lifecycle node kind is invalid")
    return _Node(
        scope_id=str(row["scope_id"]),
        node_id=str(row["node_id"]),
        kind=cast(LifecycleKind, kind),
        reference=reference,
        parents=tuple(json.loads(bytes(row["parents"]).decode("utf-8"))),
        policy=None if row["policy"] is None else cast(LifecyclePolicy, str(row["policy"])),
        available=bool(row["available"]),
        revision=None if row["source_revision"] is None else int(row["source_revision"]),
        sequence=None if row["event_sequence"] is None else int(row["event_sequence"]),
        reason=None if row["event_reason"] is None else str(row["event_reason"]),
    )


__all__ = ["SourceLifecycleError", "SourceLifecycleEvent", "SourceLifecycleService"]
