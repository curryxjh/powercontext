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

from powercontext.builtin.artifacts.memory import MemoryEntryInput
from powercontext.builtin.persistence.sqlite import SQLiteConfig
from powercontext.builtin.runtime import (
    BuiltinConfig,
    GetMemoryEntryRequest,
    RememberMemoryRequest,
    SubmitSourceObservation,
    open_builtin_contexts,
    open_builtin_runtime,
)
from powercontext.builtin.scope import ScopeDraft
from powercontext.sources import (
    SourceDefinitionRegistry,
    SourceObservation,
    manifest_for_definition,
    project_source_for_transport,
)
from powercontext.sources.pdf_pages import (
    PDF_PAGE_SOURCE_DEFINITION,
    PDFDocumentInput,
    parse_pdf_document,
    search_pdf_pages,
)
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY, TextEvidence
from tests.test_pdf_pages import make_pdf


class _PageEvidence:
    async def extract(self, request, /):
        entries = tuple(
            MemoryEntryInput(
                kind="source-evidence",
                text=TextEvidence.model_validate(source.projection(TEXT_EVIDENCE_PROJECTION_KEY)).content,
                sources=(source,),
            )
            for source in request.sources
        )
        return (
            *entries,
            MemoryEntryInput(kind="fact", text="Balance sheet corroborating note", sources=(request.sources[0],)),
            MemoryEntryInput(kind="fact", text="Consolidated Balance Sheet without source"),
            MemoryEntryInput(
                kind="fact", text="Balance sheet summary", sources=(request.sources[0], request.sources[3])
            ),
        )


def test_pdf_pages_persist_across_restarts_and_search_returns_exact_distinct_page_revisions(tmp_path):
    async def scenario():
        settings = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'pdf.db'}"))
        registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
        original_bytes = make_pdf((
            "Consolidated Balance Sheet\nProperty plant equipment net 120",
            "",
            "Operating income 80",
        ))
        revised_bytes = make_pdf((
            "Consolidated Balance Sheet\nProperty plant equipment net 150",
            "",
            "Operating income 90",
        ))
        pages = (
            *parse_pdf_document(PDFDocumentInput(document_id="财报: /%", content=original_bytes)),
            *parse_pdf_document(PDFDocumentInput(document_id="财报: /%", content=revised_bytes)),
            *parse_pdf_document(PDFDocumentInput(document_id="another", content=original_bytes)),
        )
        sources = tuple([await registry.resolve(page) for page in pages])
        observations = tuple(project_source_for_transport(registry, source) for source in sources)
        async with open_builtin_runtime(settings) as runtime:
            assert runtime.scopes is not None
            scope = await runtime.scopes.create(ScopeDraft(title="PDF", summary="Page evidence", idempotency_key="pdf"))
            outside = await runtime.scopes.create(
                ScopeDraft(title="Other", summary="Isolated", idempotency_key="other")
            )
            await runtime.ingestion.register(manifest_for_definition(PDF_PAGE_SOURCE_DEFINITION))
            receipts = []
            for observation in observations:
                command = SubmitSourceObservation(scope_id=scope.scope_id, observation=observation)
                first = await runtime.ingestion.submit(command)
                replay = await runtime.ingestion.submit(command)
                assert first == replay
                receipts.append(first)

        async with open_builtin_runtime(settings, candidate_pipeline=_PageEvidence()) as runtime:
            memory = runtime.memory.for_scope(scope.scope_id)
            assert (await memory.flush()).processed
            assert not (await memory.flush()).processed
            entries = (await memory.list()).entries
            assert len(entries) == len(pages) + 3
            original = next(entry for entry in entries if "120" in entry.entry.text and "财报" in entry.entry.text)
            old_citation = original.citation
            # Advance the head while retaining an exact citation to the previous
            # revision. Unrelated notes must not consume page search slots.
            await memory.remember(
                RememberMemoryRequest(
                    entries=(
                        MemoryEntryInput(kind="fact", text="Additional balance sheet narrative without PDF source"),
                    )
                )
            )

        async with open_builtin_contexts(settings) as contexts:
            journal = await (await contexts.get(scope.scope_id)).sources.journal.entries()
            assert len(journal) == len(pages)
            stored_pages = {item.source_ref.source_id: item.source for item in journal}

        async with open_builtin_runtime(settings) as runtime:
            memory = runtime.memory.for_scope(scope.scope_id)
            assert (await memory.get(GetMemoryEntryRequest(citation=old_citation))).entry.text == original.entry.text
            citations = await search_pdf_pages(memory, "What is the net PPNE balance?", limit=20)
            assert len(citations) == 3
            locations = set()
            for citation in citations:
                record = await memory.get(GetMemoryEntryRequest(citation=citation))
                assert len(record.entry.sources) == 1
                reference = record.entry.sources[0]
                stored = stored_pages[reference.source_id]
                assert isinstance(stored, SourceObservation)
                assert stored == next(value for value in observations if value.name == reference.source_id)
                text = TextEvidence.model_validate(stored.projection(TEXT_EVIDENCE_PROJECTION_KEY))
                assert text.metadata["document_sha256"] in {page.document_sha256 for page in pages}
                assert text.metadata["page_number"] == 1
                assert text.content.strip() == record.entry.text
                assert "120" in record.entry.text or "150" in record.entry.text
                locations.add((
                    text.metadata["document_id"],
                    text.metadata["document_sha256"],
                    text.metadata["page_number"],
                ))
            assert len(locations) == 3
            assert len(await search_pdf_pages(memory, "net PPNE balance", limit=1)) == 1
            assert await search_pdf_pages(memory, "net PPNE balance", limit=0) == ()
            assert await search_pdf_pages(runtime.memory.for_scope(outside.scope_id), "balance sheet") == ()

    asyncio.run(scenario())


class _FullPageEvidence:
    async def extract(self, request, /):
        return tuple(
            MemoryEntryInput(
                kind="source-evidence",
                text=TextEvidence.model_validate(source.projection(TEXT_EVIDENCE_PROJECTION_KEY)).content,
                sources=(source,),
            )
            for source in request.sources
        )


def test_evidence_recall_with_multiple_reports_years_and_more_than_twenty_distractors(tmp_path):
    """Known synthetic pages exercise recall, not merely citation validity."""

    async def scenario():
        settings = BuiltinConfig(database=SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'recall.db'}"))
        registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
        relevant = (
            "Assets\nProperty plant equipment net 120\n2024 2023",
            "Profitability\nGross margin 35.7 percent\n2024 2023",
            "Consolidated Statements of Cash Flows\nCapital expenditures 450\n2024 2023",
            "Reportable segments\nNorth America Europe Asia\n2024 2023",
        )
        distractors = tuple(
            f"Consolidated Balance Sheet\nProperty plant equipment 900\n"
            f"Gross margin 99 percent\nCapital expenditures 800\nReportable segments\nNote {i}"
            for i in range(28)
        )
        reports = {
            "ACME_2024_10K": (*relevant, "", *tuple(f"Personnel policy {i}" for i in range(24))),
            "ACME_2021_10K": distractors,
            "OTHER_2024_10K": distractors,
            "THIRD_2024_10K": distractors,
            "FOURTH_2023_10K": distractors,
        }
        locations = {}
        async with open_builtin_runtime(settings) as runtime:
            assert runtime.scopes is not None
            scope = await runtime.scopes.create(ScopeDraft(title="Reports", summary="Recall", idempotency_key="recall"))
            await runtime.ingestion.register(manifest_for_definition(PDF_PAGE_SOURCE_DEFINITION))
            for document, texts in reports.items():
                pages = parse_pdf_document(PDFDocumentInput(document_id=document, content=make_pdf(texts)))
                assert len(pages) == len(texts)
                for page in pages:
                    source = await registry.resolve(page)
                    locations[source.name] = (document, page.page_number)
                    await runtime.ingestion.submit(
                        SubmitSourceObservation(
                            scope_id=scope.scope_id, observation=project_source_for_transport(registry, source)
                        )
                    )
        async with open_builtin_runtime(settings, candidate_pipeline=_FullPageEvidence()) as runtime:
            memory = runtime.memory.for_scope(scope.scope_id)
            for _ in range(len(locations) + 1):
                if not (await memory.flush()).processed:
                    break
            else:
                raise AssertionError("PDF processing did not drain")  # noqa: TRY003
        async with open_builtin_runtime(settings) as runtime:
            memory = runtime.memory.for_scope(scope.scope_id)
            questions = (
                ("What was ACME's net PPNE in 2024?", {1}),
                ("What was ACME's gross margin in 2024?", {2}),
                ("How much did ACME spend on capex in 2024?", {3}),
                ("In which geographies did ACME operate in 2024?", {4}),
                ("Compare ACME's gross margin and property plant equipment in 2024.", {1, 2}),
            )
            hits = total = 0
            for question, expected_pages in questions:
                citations = await search_pdf_pages(memory, question, limit=20)
                found = set()
                for citation in citations:
                    record = await memory.get(GetMemoryEntryRequest(citation=citation))
                    assert len(record.entry.sources) == 1
                    found.add(locations[record.entry.sources[0].source_id])
                assert len(found) == len(citations) <= 20
                expected = {("ACME_2024_10K", page) for page in expected_pages}
                hits += len(found & expected)
                total += len(expected)
                assert expected <= found, (question, found)
            assert hits / total >= 0.70

    asyncio.run(scenario())
