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

from __future__ import annotations

import asyncio

import pytest

from powercontext.builtin.artifacts.memory import EmbeddingProfile
from powercontext.builtin.inference import EmbeddingModel, EmbeddingResult, InferenceUsage, embed_query
from powercontext.builtin.inference.coalescing import CoalescingEmbeddingModel


class _Embedding:
    profile = EmbeddingProfile(profile_id="coalescing-test", model="offline", dimension=1)

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        self.calls.append(texts)
        return EmbeddingResult(
            vectors=tuple((float(len(text)),) for text in texts),
            usage=InferenceUsage(requests=2, input_tokens=7 * len(texts), output_tokens=0),
        )


class _BlockedEmbedding(_Embedding):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        self.started.set()
        await self.release.wait()
        return await super().embed(texts)


@pytest.mark.parametrize("max_batch_size", [1, 3, 64])
@pytest.mark.parametrize("coalesce_ms", [0, 5])
def test_shared_batches_preserve_order_and_provider_usage(max_batch_size, coalesce_ms):
    async def scenario():
        base = _Embedding()
        model: EmbeddingModel = CoalescingEmbeddingModel(base, max_batch_size=max_batch_size, coalesce_ms=coalesce_ms)
        assert model.profile is base.profile
        inputs = (("a", "bb", "a", "ccc"), ("bb", "dddd"), ("ccc", "a", "dddd"))
        results = await asyncio.gather(*(model.embed(texts) for texts in inputs))
        assert sorted(text for call in base.calls for text in call) == ["a", "bb", "ccc", "dddd"]
        assert all(1 <= len(call) <= max_batch_size for call in base.calls)
        for texts, result in zip(inputs, results, strict=True):
            batches = [call for call in base.calls if set(texts).intersection(call)]
            assert result.vectors == tuple((float(len(text)),) for text in texts)
            assert result.usage == InferenceUsage(
                requests=2 * len(batches), input_tokens=7 * sum(map(len, batches)), output_tokens=0
            )
        cached = await model.embed(("dddd", "a", "a"))
        assert cached.vectors == ((4.0,), (1.0,), (1.0,))
        assert cached.usage == InferenceUsage(requests=0)

    asyncio.run(scenario())


def test_empty_input_never_invokes_provider():
    async def scenario():
        base = _Embedding()
        model = CoalescingEmbeddingModel(base)
        assert await model.embed(()) == EmbeddingResult(vectors=())
        assert await model.embed_query(()) == EmbeddingResult(vectors=())
        assert base.calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize("cache_size", [0, 2])
def test_late_waiter_and_cancellation_share_inflight_work(cache_size):
    async def scenario():
        base = _BlockedEmbedding()
        model = CoalescingEmbeddingModel(base, coalesce_ms=0, cache_size=cache_size)
        first = asyncio.create_task(model.embed(("shared", "shared")))
        await asyncio.wait_for(base.started.wait(), 2)
        late = asyncio.create_task(model.embed(("shared",)))
        # Run the late caller before cancelling the original caller so it is
        # waiting on already running provider work, outside the batching window.
        await asyncio.sleep(0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        base.release.set()
        result = await asyncio.wait_for(late, 2)
        assert result.vectors == ((6.0,),)
        assert result.usage == InferenceUsage(requests=2, input_tokens=7, output_tokens=0)
        assert base.calls == [("shared",)]
        again = await model.embed(("shared",))
        assert again.usage.requests == (0 if cache_size else 2)
        assert len(base.calls) == (1 if cache_size else 2)

    asyncio.run(scenario())


def test_cancelling_during_batching_window_keeps_other_waiters():
    async def scenario():
        base = _Embedding()
        model = CoalescingEmbeddingModel(base, coalesce_ms=10)
        first = asyncio.create_task(model.embed(("shared",)))
        survivor = asyncio.create_task(model.embed(("shared", "other")))
        await asyncio.sleep(0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        result = await asyncio.wait_for(survivor, 2)
        assert result.vectors == ((6.0,), (5.0,))
        assert base.calls == [("shared", "other")]

    asyncio.run(scenario())


def test_lru_refreshes_every_cached_access_including_duplicate_positions():
    async def scenario():
        base = _Embedding()
        model = CoalescingEmbeddingModel(base, coalesce_ms=0, cache_size=2)
        await model.embed(("a", "bb"))
        await model.embed(("a", "bb", "a"))
        await model.embed(("ccc",))
        assert (await model.embed(("a",))).usage.requests == 0
        assert (await model.embed(("bb",))).usage.requests == 2
        assert base.calls == [("a", "bb"), ("ccc",), ("bb",)]

    asyncio.run(scenario())


def test_late_overlapping_call_counts_shared_and_new_batches_once_without_cache():
    async def scenario():
        base = _BlockedEmbedding()
        model = CoalescingEmbeddingModel(base, max_batch_size=2, coalesce_ms=0, cache_size=0)
        first = asyncio.create_task(model.embed(("alpha", "beta")))
        await asyncio.wait_for(base.started.wait(), 2)
        late = asyncio.create_task(model.embed(("beta", "gamma", "alpha", "beta")))
        await asyncio.sleep(0)
        base.release.set()
        original, joined = await asyncio.wait_for(asyncio.gather(first, late), 2)
        assert original.vectors == ((5.0,), (4.0,))
        assert joined.vectors == ((4.0,), (5.0,), (5.0,), (4.0,))
        assert original.usage == InferenceUsage(requests=2, input_tokens=14, output_tokens=0)
        assert joined.usage == InferenceUsage(requests=4, input_tokens=21, output_tokens=0)
        assert base.calls == [("alpha", "beta"), ("gamma",)]

    asyncio.run(scenario())


def test_mixed_known_and_unknown_token_counts_preserve_zero():
    class PartiallyMetered(_Embedding):
        async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
            result = await super().embed(texts)
            return result.model_copy(
                update={
                    "usage": InferenceUsage(requests=2, output_tokens=3)
                    if texts == ("a",)
                    else InferenceUsage(requests=4, input_tokens=0),
                }
            )

    async def scenario():
        model = CoalescingEmbeddingModel(PartiallyMetered(), max_batch_size=1, coalesce_ms=0)
        result = await model.embed(("a", "b", "a"))
        assert result.usage == InferenceUsage(requests=6, input_tokens=0, output_tokens=3)

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["provider", "too-few", "too-many", "cancelled"])
def test_failed_batch_is_shared_retryable_and_does_not_block_independent_batches(failure):
    class Flaky(_Embedding):
        failed = False

        async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
            if texts == ("bad",) and not self.failed:
                self.failed = True
                self.calls.append(texts)
                if failure == "provider":
                    raise RuntimeError("controlled provider failure")  # noqa: TRY003
                if failure == "cancelled":
                    raise asyncio.CancelledError
                return EmbeddingResult(vectors=() if failure == "too-few" else ((1.0,), (2.0,)))
            return await super().embed(texts)

    async def scenario():
        base = Flaky()
        model = CoalescingEmbeddingModel(base, max_batch_size=1, coalesce_ms=0)
        results = await asyncio.wait_for(
            asyncio.gather(
                model.embed(("bad",)),
                model.embed(("bad", "ok")),
                model.embed(("ok",)),
                return_exceptions=True,
            ),
            2,
        )
        error = (
            RuntimeError if failure == "provider" else asyncio.CancelledError if failure == "cancelled" else ValueError
        )
        assert isinstance(results[0], error)
        assert isinstance(results[1], error)
        assert results[2] == EmbeddingResult(
            vectors=((2.0,),), usage=InferenceUsage(requests=2, input_tokens=7, output_tokens=0)
        )
        retried = await model.embed(("bad", "ok"))
        assert retried.vectors == ((3.0,), (2.0,))
        assert retried.usage == InferenceUsage(requests=2, input_tokens=7, output_tokens=0)
        assert base.calls == [("bad",), ("ok",), ("bad",)]

    asyncio.run(scenario())


def test_independent_batch_finishes_while_another_provider_batch_is_blocked():
    class Independent(_BlockedEmbedding):
        async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
            if texts == ("blocked",):
                return await super().embed(texts)
            return await _Embedding.embed(self, texts)

    async def scenario():
        base = Independent()
        model = CoalescingEmbeddingModel(base, max_batch_size=1, coalesce_ms=0)
        blocked = asyncio.create_task(model.embed(("blocked",)))
        await asyncio.wait_for(base.started.wait(), 2)
        fast = await asyncio.wait_for(model.embed(("fast",)), 2)
        assert fast.vectors == ((4.0,),)
        assert not blocked.done()
        base.release.set()
        assert (await asyncio.wait_for(blocked, 2)).vectors == ((7.0,),)

    asyncio.run(scenario())


def test_usage_identifies_actual_batches_even_if_provider_reuses_result_object():
    class Reused(_Embedding):
        result = EmbeddingResult(vectors=((1.0,),), usage=InferenceUsage(requests=3, output_tokens=0))

        async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
            self.calls.append(texts)
            return self.result

    async def scenario():
        model = CoalescingEmbeddingModel(Reused(), max_batch_size=1, coalesce_ms=0)
        result = await model.embed(("a", "b", "a"))
        assert result.vectors == ((1.0,),) * 3
        assert result.usage == InferenceUsage(requests=6, output_tokens=0)

    asyncio.run(scenario())


def test_query_aware_provider_keeps_document_and_query_vectors_separate():
    class Asymmetric(_Embedding):
        async def embed_query(self, texts: tuple[str, ...], /) -> EmbeddingResult:
            return EmbeddingResult(
                vectors=tuple((-float(len(text)),) for text in texts), usage=InferenceUsage(requests=1)
            )

    async def scenario():
        model = CoalescingEmbeddingModel(Asymmetric(), coalesce_ms=0)
        documents, queries = await asyncio.gather(model.embed(("same",)), embed_query(model, ("same",)))
        assert documents.vectors == ((4.0,),)
        assert queries.vectors == ((-4.0,),)
        for operation, expected in ((model.embed, 4.0), (model.embed_query, -4.0)):
            result = await operation(("same",))
            assert result.vectors == ((expected,),)
            assert result.usage.requests == 0

    asyncio.run(scenario())


def test_symmetric_queries_reuse_document_cache():
    async def scenario():
        base = _Embedding()
        model = CoalescingEmbeddingModel(base, coalesce_ms=0)
        await model.embed(("same",))
        result = await embed_query(model, ("same",))
        assert result.vectors == ((4.0,),)
        assert result.usage.requests == 0
        assert base.calls == [("same",)]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "settings",
    [
        {"max_batch_size": 0},
        {"max_batch_size": -1},
        {"max_batch_size": True},
        {"max_batch_size": 1.5},
        {"cache_size": -1},
        {"cache_size": True},
        {"cache_size": 1.5},
        {"coalesce_ms": -1},
        {"coalesce_ms": True},
        {"coalesce_ms": float("nan")},
        {"coalesce_ms": float("inf")},
        {"coalesce_ms": "5"},
    ],
)
def test_invalid_configuration_is_rejected(settings):
    with pytest.raises(ValueError):
        CoalescingEmbeddingModel(_Embedding(), **settings)
