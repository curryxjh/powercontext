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

"""Behavior tests for HTTP-backed Memory reranking."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import cast

import httpx
import pytest

from powercontext.artifacts import ArtifactRef
from powercontext.builtin.artifacts.memory import MemoryHit
from powercontext.builtin.artifacts.memory.http_reranker import HTTPMemoryReranker


def _hit(rank: int) -> MemoryHit:
    return MemoryHit(
        memory_ref=ArtifactRef(family="memory", artifact_id="memory", revision=1),
        entry_id=f"entry-{rank}",
        entry_version_id=f"entry-{rank}-v1",
        text=f"Candidate {rank}",
        score=1 / rank,
        matched_by=("fts",),
    )


def test_http_reranker_batches_global_ranks_and_stably_selects_across_batches() -> None:
    async def scenario() -> None:
        requests: list[dict[str, object]] = []
        score_by_rank = {1: 0.1, 2: 0.9, 3: 0.95, 4: 0.9}

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            requests.append(payload)
            return httpx.Response(
                200,
                json={
                    "scores": [
                        {"rank": candidate["rank"], "score": score_by_rank[candidate["rank"]]}
                        for candidate in reversed(payload["candidates"])
                    ]
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            reranker = HTTPMemoryReranker(
                "https://reranker.invalid/score",
                client=client,
                batch_size=2,
                policy_id="test-policy",
            )
            decision = await reranker.rerank("query", tuple(_hit(rank) for rank in range(1, 5)), 2)

        assert reranker.policy_id == "test-policy"
        assert decision.selected_ranks == (3, 2)
        assert decision.usage.requests == 2
        assert decision.discarded_rank_count == 0
        assert decision.used_fallback is False
        assert requests == [
            {
                "query": "query",
                "candidates": [{"rank": 1, "text": "Candidate 1"}, {"rank": 2, "text": "Candidate 2"}],
            },
            {
                "query": "query",
                "candidates": [{"rank": 3, "text": "Candidate 3"}, {"rank": 4, "text": "Candidate 4"}],
            },
        ]

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"scores": [], "extra": True},
        {"scores": [{"rank": 1, "score": 0.5, "extra": True}]},
        {"scores": [{"rank": 1, "score": 0.5}, {"rank": 1, "score": 0.4}]},
        {"scores": [{"rank": 2, "score": 0.5}]},
        {"scores": [{"rank": True, "score": 0.5}]},
        {"scores": [{"rank": 1, "score": True}]},
        {"scores": [{"rank": 1, "score": "0.5"}]},
        {"scores": [{"rank": 1, "score": float("nan")}]},
        {"scores": [{"rank": 1, "score": float("inf")}]},
    ],
)
def test_http_reranker_rejects_invalid_response_schema_and_coverage(payload: object) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
        ) as client:
            with pytest.raises(ValueError):
                await HTTPMemoryReranker("https://reranker.invalid", client=client).rerank("query", (_hit(1),), 1)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "handler, error_type",
    [
        (lambda _request: httpx.Response(200, content=b"not-json"), ValueError),
        (lambda _request: httpx.Response(503), httpx.HTTPStatusError),
    ],
)
def test_http_reranker_preserves_json_and_http_errors(
    handler: Callable[[httpx.Request], httpx.Response], error_type: type[Exception]
) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(error_type):
                await HTTPMemoryReranker("https://reranker.invalid", client=client).rerank("query", (_hit(1),), 1)

    asyncio.run(scenario())


def test_http_reranker_preserves_network_errors() -> None:
    async def scenario() -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("offline", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(httpx.ConnectError):
                await HTTPMemoryReranker("https://reranker.invalid", client=client).rerank("query", (_hit(1),), 1)

    asyncio.run(scenario())


@pytest.mark.parametrize("batch_size", [0, -1, True, 1.5])
def test_http_reranker_rejects_invalid_batch_size(batch_size: object) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient() as client:
            with pytest.raises(ValueError):
                HTTPMemoryReranker("https://reranker.invalid", client=client, batch_size=cast("int", batch_size))

    asyncio.run(scenario())


@pytest.mark.parametrize("candidates, limit", [((), 1), ((_hit(1),), 0), ((_hit(1),), 2), ((_hit(1),), True)])
def test_http_reranker_rejects_invalid_rerank_bounds(candidates: tuple[MemoryHit, ...], limit: int) -> None:
    async def scenario() -> None:
        async with httpx.AsyncClient() as client:
            with pytest.raises(ValueError):
                await HTTPMemoryReranker("https://reranker.invalid", client=client).rerank("query", candidates, limit)

    asyncio.run(scenario())
