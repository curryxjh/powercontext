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

"""HTTP score-service adapter for Memory reranking."""

from __future__ import annotations

from typing import Annotated

import httpx
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from powercontext.builtin.artifacts.memory.models import MemoryHit
from powercontext.builtin.artifacts.memory.reranking import MemoryRerankDecision, _validate_bounds
from powercontext.builtin.inference import InferenceUsage


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _HTTPScore(_StrictModel):
    rank: StrictInt = Field(ge=1)
    score: Annotated[float, Field(strict=True, allow_inf_nan=False)]


class _HTTPScoreResponse(_StrictModel):
    scores: tuple[_HTTPScore, ...]


class HTTPMemoryReranker:
    """Select Memory candidates using scores returned by an HTTP service."""

    def __init__(
        self,
        endpoint: str,
        *,
        client: httpx.AsyncClient,
        batch_size: int = 32,
        policy_id: str = "http-cross-encoder-v1",
    ) -> None:
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size <= 0:
            raise ValueError("rerank batch_size must be a positive integer")  # noqa: TRY003
        self.policy_id = policy_id
        self._endpoint = endpoint
        self._client = client
        self._batch_size = batch_size

    async def rerank(
        self,
        query: str,
        candidates: tuple[MemoryHit, ...],
        limit: int,
        /,
    ) -> MemoryRerankDecision:
        """Score every candidate exactly once and select from the complete pool."""

        _validate_bounds(len(candidates), limit)
        scores: dict[int, float] = {}
        requests = 0
        for start in range(0, len(candidates), self._batch_size):
            batch = candidates[start : start + self._batch_size]
            ranks = tuple(range(start + 1, start + len(batch) + 1))
            response = await self._client.post(
                self._endpoint,
                json={
                    "query": query,
                    "candidates": [
                        {"rank": rank, "text": candidate.text} for rank, candidate in zip(ranks, batch, strict=True)
                    ],
                },
            )
            requests += 1
            response.raise_for_status()
            try:
                response_data = response.json()
            except (UnicodeDecodeError, ValueError) as error:
                raise ValueError("rerank response must be valid JSON") from error  # noqa: TRY003
            payload = _HTTPScoreResponse.model_validate(response_data)
            batch_scores = {item.rank: item.score for item in payload.scores}
            if len(batch_scores) != len(payload.scores) or set(batch_scores) != set(ranks):
                raise ValueError("rerank response ranks must cover the request batch exactly once")  # noqa: TRY003
            scores.update(batch_scores)

        selected_ranks = tuple(sorted(scores, key=lambda rank: (-scores[rank], rank))[:limit])
        return MemoryRerankDecision(
            selected_ranks=selected_ranks,
            usage=InferenceUsage(requests=requests),
        )


__all__ = ["HTTPMemoryReranker"]
