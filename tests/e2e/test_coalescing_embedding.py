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

from powercontext.builtin.artifacts.memory import EmbeddingProfile, MemoryEntryInput
from powercontext.builtin.inference import EmbeddingResult, InferenceUsage
from powercontext.builtin.inference.coalescing import CoalescingEmbeddingModel
from powercontext.builtin.persistence.sqlite import SQLiteConfig
from powercontext.builtin.runtime import BuiltinConfig, open_builtin_contexts


@pytest.mark.parametrize("cache_size", [0, 48])
def test_concurrent_memory_writes_and_exact_vector_search_budget(tmp_path, cache_size):
    async def scenario():
        texts = tuple(f"coalesced memory {index}" for index in range(24))

        class Provider:
            profile = EmbeddingProfile(profile_id="coalesced-memory-v1", model="offline", dimension=len(texts))

            def __init__(self):
                self.calls = []

            async def embed(self, values):
                self.calls.append(values)
                return EmbeddingResult(
                    vectors=tuple(tuple(float(text == value) for text in texts) for value in values),
                    usage=InferenceUsage(requests=1, input_tokens=7 * len(values)),
                )

        provider = Provider()
        model = CoalescingEmbeddingModel(provider, max_batch_size=6, coalesce_ms=0, cache_size=cache_size)

        class ConcurrentWrites:
            profile = model.profile

            def __init__(self):
                self.arrived = 0
                self.release = asyncio.Event()
                self.usages = []

            async def embed(self, values):
                # Synchronize at the embedding boundary: database work before
                # this point is allowed to serialize on SQLite's writer lock.
                if self.arrived < 6:
                    self.arrived += 1
                    if self.arrived == 6:
                        self.release.set()
                    await self.release.wait()
                result = await model.embed(values)
                self.usages.append(result.usage)
                return result

        concurrent = ConcurrentWrites()
        settings = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'memory.db'}"))
        async with open_builtin_contexts(settings, embedding_model=concurrent) as contexts:
            services = [(await contexts.get(f"scope-{index}")).artifacts.memory for index in range(6)]
            entries = tuple(MemoryEntryInput(kind="fact", text=text) for text in texts)
            memories = await asyncio.wait_for(
                asyncio.gather(
                    *(service.remember(memory=None, entries=entries, mode="append") for service in services)
                ),
                30,
            )
            assert len(provider.calls) == 4
            assert all(len(batch) == 6 for batch in provider.calls)
            assert sorted(text for batch in provider.calls for text in batch) == sorted(texts)
            assert concurrent.usages == [InferenceUsage(requests=4, input_tokens=168)] * 6
            for index, (service, memory) in enumerate(zip(services, memories, strict=True)):
                assert memory is not None
                result = await service.search(texts[index], memories=(memory,), limit=1, mode="vector")
                assert result.hits[0].text == texts[index]
            assert len(provider.calls) == (4 if cache_size else 10)
            assert [usage.requests for usage in concurrent.usages[6:]] == [0 if cache_size else 1] * 6

    asyncio.run(scenario())
