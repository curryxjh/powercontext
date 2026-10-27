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

"""Coalesce concurrent embedding requests and retain a bounded result cache."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from powercontext.builtin.inference.models import EmbeddingResult, EmbeddingVector, InferenceUsage
from powercontext.builtin.inference.protocols import EmbeddingModel


@dataclass(frozen=True)
class _BatchResult:
    vectors: tuple[EmbeddingVector, ...]
    usage: InferenceUsage
    batch_id: object


class CoalescingEmbeddingModel:
    """Share same-text work across callers while preserving each caller's usage."""

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
        if isinstance(coalesce_ms, bool) or not isinstance(coalesce_ms, (int, float)) or coalesce_ms < 0:
            raise ValueError("coalesce_ms must be non-negative")  # noqa: TRY003
        if type(cache_size) is not int or cache_size < 0:
            raise ValueError("cache_size must be non-negative")  # noqa: TRY003
        self._model = model
        self.profile = model.profile
        self._max_batch_size = max_batch_size
        self._coalesce_seconds = float(coalesce_ms) / 1_000
        self._cache_size = cache_size
        self._cache: OrderedDict[str, EmbeddingVector] = OrderedDict()
        self._pending: dict[str, asyncio.Future[_BatchResult]] = {}
        self._inflight: dict[str, asyncio.Future[_BatchResult]] = {}
        self._flush_task: asyncio.Task[None] | None = None
        self._batch_tasks: set[asyncio.Task[None]] = set()

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        values = tuple(texts)
        if not values:
            return EmbeddingResult(vectors=(), usage=InferenceUsage(requests=0))
        if any(not isinstance(text, str) for text in values):
            raise ValueError("embedding texts must be strings")  # noqa: TRY003

        unique = tuple(dict.fromkeys(values))
        vectors: dict[str, EmbeddingVector] = {}
        waiters: dict[str, asyncio.Future[_BatchResult]] = {}
        for text in unique:
            cached = self._cache.get(text)
            if cached is not None:
                self._cache.move_to_end(text)
                vectors[text] = cached
                continue
            future = self._inflight.get(text)
            if future is None:
                future = self._pending.get(text)
            if future is None:
                future = asyncio.get_running_loop().create_future()
                future.add_done_callback(_consume_future_exception)
                self._pending[text] = future
                if self._flush_task is None or self._flush_task.done():
                    self._flush_task = asyncio.create_task(self._flush_after_window())
            waiters[text] = future

        usages: dict[int, InferenceUsage] = {}
        if waiters:
            results = await asyncio.gather(
                *(asyncio.shield(future) for future in waiters.values()),
            )
            for text, result in zip(waiters, results, strict=True):
                vectors[text] = result.vectors[0]
                usages.setdefault(id(result.batch_id), result.usage)

        usage = _combine_usage(tuple(usages.values()))
        return EmbeddingResult(
            vectors=tuple(vectors[text] for text in values),
            usage=usage,
        )

    async def _flush_after_window(self) -> None:
        if self._coalesce_seconds:
            await asyncio.sleep(self._coalesce_seconds)
        else:
            await asyncio.sleep(0)
        pending = self._pending
        self._pending = {}
        if not pending:
            return
        texts = tuple(pending)
        for start in range(0, len(texts), self._max_batch_size):
            batch = texts[start : start + self._max_batch_size]
            futures = {text: pending[text] for text in batch}
            for text, future in futures.items():
                self._inflight[text] = future
            task = asyncio.create_task(self._run_batch(batch, futures))
            self._batch_tasks.add(task)
            task.add_done_callback(self._batch_tasks.discard)

    async def _run_batch(  # noqa: C901
        self,
        texts: tuple[str, ...],
        futures: dict[str, asyncio.Future[_BatchResult]],
    ) -> None:
        try:
            result = await self._model.embed(texts)
            if len(result.vectors) != len(texts):
                raise ValueError("embedding provider returned the wrong vector count")  # noqa: TRY003, TRY301
            vectors = tuple(tuple(vector) for vector in result.vectors)
            shared = _BatchResult(vectors=vectors, usage=result.usage, batch_id=object())
            if self._cache_size:
                for text, vector in zip(texts, vectors, strict=True):
                    self._cache[text] = vector
                    self._cache.move_to_end(text)
                    while len(self._cache) > self._cache_size:
                        self._cache.popitem(last=False)
            for index, text in enumerate(texts):
                future = futures[text]
                if not future.done():
                    future.set_result(
                        _BatchResult(
                            vectors=(vectors[index],),
                            usage=shared.usage,
                            batch_id=shared.batch_id,
                        )
                    )
        except BaseException as error:
            for future in futures.values():
                if not future.done():
                    future.set_exception(error)
        finally:
            for text, future in futures.items():
                if self._inflight.get(text) is future:
                    self._inflight.pop(text, None)


def _combine_usage(values: tuple[InferenceUsage, ...]) -> InferenceUsage:
    if not values:
        return InferenceUsage(requests=0)
    return InferenceUsage(
        requests=sum(value.requests for value in values),
        input_tokens=_sum_optional(value.input_tokens for value in values),
        output_tokens=_sum_optional(value.output_tokens for value in values),
    )


def _sum_optional(values: Any) -> int | None:
    values = tuple(values)
    if any(value is None for value in values):
        return None
    return sum(values)


def _consume_future_exception(future: asyncio.Future[object]) -> None:
    """Prevent a failed shared future from becoming an unobserved warning."""

    if not future.cancelled():
        future.exception()


__all__ = ["CoalescingEmbeddingModel"]
