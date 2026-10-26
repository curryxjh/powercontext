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

"""Shared in-flight embedding work and a bounded, model-local vector cache."""

from __future__ import annotations

import asyncio
import math
from collections import OrderedDict
from dataclasses import dataclass

from powercontext.builtin.inference.models import EmbeddingResult, EmbeddingVector, InferenceUsage
from powercontext.builtin.inference.protocols import EmbeddingModel, QueryEmbeddingModel


@dataclass(frozen=True, slots=True)
class _EmbeddedText:
    vector: EmbeddingVector
    usage: InferenceUsage
    batch: object


def _observe_failure(future: asyncio.Future[_EmbeddedText]) -> None:
    # All callers may have been cancelled before a shared request fails.
    # Observing the exception prevents an orphaned Future warning; active
    # callers still receive the original exception when they await the Future.
    if not future.cancelled():
        future.exception()


class CoalescingEmbeddingModel:
    """Merge embedding calls on one event loop and cache successful vectors.

    Each caller receives vectors in its own input order and the provider usage
    of each distinct batch it awaited, counted once. Cached vectors carry no
    new usage. Cancelling a caller leaves shared provider work running.

    Query-aware providers use separate query/document cache and in-flight keys;
    symmetric providers share both paths. Cache contents belong to this wrapper
    instance and are neither persisted nor shared across worker processes.
    """

    def __init__(
        self,
        model: EmbeddingModel,
        *,
        max_batch_size: int = 64,
        coalesce_ms: float = 5.0,
        cache_size: int = 1024,
    ) -> None:
        if type(max_batch_size) is not int or max_batch_size < 1:
            raise ValueError("max_batch_size must be a positive integer")  # noqa: TRY003
        if type(cache_size) is not int or cache_size < 0:
            raise ValueError("cache_size must be a nonnegative integer")  # noqa: TRY003
        if (
            isinstance(coalesce_ms, bool)
            or not isinstance(coalesce_ms, (int, float))
            or not math.isfinite(coalesce_ms)
            or coalesce_ms < 0
        ):
            raise ValueError("coalesce_ms must be finite and nonnegative")  # noqa: TRY003
        self.profile = model.profile
        self._model = model
        self._max_batch_size = max_batch_size
        self._coalesce_seconds = coalesce_ms / 1000
        self._cache_size = cache_size
        self._cache: OrderedDict[tuple[bool, str], EmbeddingVector] = OrderedDict()
        self._pending: dict[tuple[bool, str], asyncio.Future[_EmbeddedText]] = {}
        self._queued: dict[tuple[bool, str], asyncio.Future[_EmbeddedText]] = {}
        self._flush_handle: asyncio.TimerHandle | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        """Embed documents, sharing repeated texts across concurrent calls."""

        return await self._embed(texts, query=False)

    async def embed_query(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        """Preserve provider query semantics, sharing symmetric models' cache."""

        return await self._embed(texts, query=isinstance(self._model, QueryEmbeddingModel))

    async def _embed(self, texts: tuple[str, ...], *, query: bool) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=())
        loop = asyncio.get_running_loop()
        vectors: dict[str, EmbeddingVector] = {}
        waiting: dict[str, asyncio.Future[_EmbeddedText]] = {}
        for text in texts:
            key = (query, text)
            if key in self._cache:
                vectors[text] = self._cache[key]
                self._cache.move_to_end(key)
                continue
            future = self._pending.get(key)
            if future is None:
                future = loop.create_future()
                future.add_done_callback(_observe_failure)
                self._pending[key] = future
                self._queued[key] = future
            waiting[text] = future
        if self._queued and self._flush_handle is None:
            # Even a zero window yields to callers already runnable on this
            # event loop before any provider request starts.
            self._flush_handle = loop.call_later(self._coalesce_seconds, self._flush)
        results = await asyncio.gather(*(asyncio.shield(future) for future in waiting.values()))
        batches: dict[object, InferenceUsage] = {}
        for text, result in zip(waiting, results, strict=True):
            vectors[text] = result.vector
            batches[result.batch] = result.usage
        usages = tuple(batches.values())
        input_tokens = tuple(usage.input_tokens for usage in usages if usage.input_tokens is not None)
        output_tokens = tuple(usage.output_tokens for usage in usages if usage.output_tokens is not None)
        return EmbeddingResult(
            vectors=tuple(vectors[text] for text in texts),
            usage=InferenceUsage(
                requests=sum(usage.requests for usage in usages),
                input_tokens=sum(input_tokens) if input_tokens else None,
                output_tokens=sum(output_tokens) if output_tokens else None,
            ),
        )

    def _flush(self) -> None:
        self._flush_handle = None
        queued, self._queued = self._queued, {}
        # Query/document requests have different provider semantics, so they
        # cannot share a provider batch even when they arrive in the same turn.
        for query in (False, True):
            members = tuple((key, future) for key, future in queued.items() if key[0] == query)
            for start in range(0, len(members), self._max_batch_size):
                task = asyncio.create_task(self._run_batch(members[start : start + self._max_batch_size], query=query))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

    async def _run_batch(
        self, members: tuple[tuple[tuple[bool, str], asyncio.Future[_EmbeddedText]], ...], *, query: bool
    ) -> None:
        texts = tuple(key[1] for key, _ in members)
        try:
            if query and isinstance(self._model, QueryEmbeddingModel):
                result = await self._model.embed_query(texts)
            else:
                result = await self._model.embed(texts)
            if len(result.vectors) != len(members):
                raise ValueError("embedding vector count does not match batch text count")  # noqa: TRY003, TRY301
        except (Exception, asyncio.CancelledError) as error:
            for _, future in members:
                future.set_exception(error)
        else:
            batch = object()
            for (key, future), vector in zip(members, result.vectors, strict=True):
                if self._cache_size:
                    self._cache[key] = vector
                    self._cache.move_to_end(key)
                    if len(self._cache) > self._cache_size:
                        self._cache.popitem(last=False)
                future.set_result(_EmbeddedText(vector, result.usage, batch))
        finally:
            for key, _ in members:
                del self._pending[key]


__all__ = ["CoalescingEmbeddingModel"]
