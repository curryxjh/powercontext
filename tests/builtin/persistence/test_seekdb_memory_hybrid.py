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

"""Compare native seekdb hybrid rankings with the original two-query path."""

from __future__ import annotations

import pytest

pytest.importorskip("pylibseekdb")

from powercontext.builtin.artifacts.memory import EmbeddingProfile, MemoryEntryInput, MemorySearchRequest
from powercontext.builtin.artifacts.search import analyze_fts_query
from powercontext.builtin.inference import EmbeddingResult
from powercontext.builtin.persistence.memory_index import CompositeMemoryIndex
from powercontext.builtin.persistence.oceanbase.memory_index import OceanBaseMemoryFTSIndex, OceanBaseMemoryVectorIndex
from powercontext.builtin.persistence.seekdb import SeekDBConfig
from powercontext.builtin.persistence.seekdb.memory_index import SeekDBMemoryHybridIndex
from powercontext.builtin.runtime import BuiltinConfig, open_builtin_contexts
from powercontext.builtin.tags import MemoryEntryTagTarget, TagFilter

PROFILE = EmbeddingProfile(
    profile_id="seekdb-hybrid-ranking", model="fixed", dimension=3, distance="l2", normalization="unit"
)


class _Embedding:
    profile = PROFILE

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=tuple(
                (1.0, 0.0, 0.0)
                if text == "Alpha semantic record."
                else (0.6, 0.8, 0.0)
                if text == "Alpha beta lexical record."
                else (0.8, 0.0, 0.6)
                if text == "Alpha gamma mixed record."
                else (0.0, 5 / 13, 12 / 13)
                if text == "Beta gamma mixed record."
                else (0.0, 1.0, 0.0)
                if "beta" in text.casefold()
                else (0.0, 0.0, 1.0)
                for text in texts
            )
        )


@pytest.mark.asyncio
async def test_hybrid_candidates_preserve_both_channel_rankings(tmp_path) -> None:
    async with open_builtin_contexts(
        BuiltinConfig(database=SeekDBConfig(path=tmp_path / "seekdb")), embedding_model=_Embedding()
    ) as contexts:
        memory = (await contexts.get("project")).artifacts.memory
        head = await memory.remember(
            memory=None,
            entries=tuple(
                MemoryEntryInput(kind="fact", text=value)
                for value in (
                    "Alpha semantic record.",
                    "Alpha beta lexical record.",
                    "Beta lexical record.",
                    "Gamma vector record.",
                    "Alpha gamma mixed record.",
                    "Beta gamma mixed record.",
                )
            ),
            mode="append",
        )
        assert head is not None
        for entry in head.content.manifest.entries[:3]:
            target = MemoryEntryTagTarget(artifact_id=head.artifact_id, entry_id=entry.entry_id)
            current = await contexts.records.get_tags("project", target)
            await contexts.records.replace_tags("project", target, ("selected",), expected_etag=current.etag)

        fts_index = OceanBaseMemoryFTSIndex()
        vector_index = OceanBaseMemoryVectorIndex(PROFILE)
        original = CompositeMemoryIndex(fts_index, vector_index)
        native = SeekDBMemoryHybridIndex(PROFILE, fts_index, vector_index)
        for query in ("alpha", "beta", "gamma", "alpha beta"):
            for tag_filter in (None, TagFilter(tags=("selected",))):
                request = MemorySearchRequest(
                    query=query,
                    analyzed_query=analyze_fts_query(query),
                    memories=(head.as_ref(),),
                    candidate_limit=3,
                    mode="hybrid",
                    query_vector=(1.0, 0.0, 0.0) if "alpha" in query else (0.0, 1.0, 0.0),
                    embedding_profile=PROFILE,
                    tag_filter=tag_filter,
                )
                async with contexts.database.transaction() as connection:
                    expected = await original.search(connection, "project", request)
                    actual = await native.search(connection, "project", request)
                assert actual.fts == expected.fts, (query, tag_filter)
                assert actual.vector == expected.vector, (query, tag_filter)
