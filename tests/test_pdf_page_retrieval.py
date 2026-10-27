from types import SimpleNamespace

import pytest

from powercontext.artifacts import ArtifactRef
from powercontext.builtin.artifacts.memory import MemoryHit
from powercontext.sources.pdf_pages import search_pdf_pages

MEMORY_REF = ArtifactRef(family="memory", artifact_id="report", revision=1)


def _page(page: int, text: str) -> MemoryHit:
    return MemoryHit(
        memory_ref=MEMORY_REF,
        entry_id=f"page-{page}",
        entry_version_id=f"version-{page}",
        text=text,
        score=1,
        matched_by=(),
    )


@pytest.mark.asyncio
async def test_statement_heading_promotes_an_exact_page_citation() -> None:
    class Memory:
        async def search(self, request):
            del request
            return SimpleNamespace(
                hits=(
                    *(_page(i, "An unrelated note refers to the balance sheet.") for i in range(1, 26)),
                    _page(26, "Consolidated Balance Sheet\nProperty, plant and equipment, net 2022 2021"),
                )
            )

    citations = await search_pdf_pages(Memory(), "What is net PPNE on the balance sheet?", limit=20)

    assert len(citations) == 20
    assert citations[0].entry_id == "page-26"
    assert citations[0].entry_version_id == "version-26"


@pytest.mark.asyncio
async def test_geography_question_can_retrieve_reportable_segments() -> None:
    class Memory:
        async def search(self, request):
            if "reportable segments" in request.query:
                return SimpleNamespace(hits=(_page(4, "Our operations are organized into reportable segments."),))
            return SimpleNamespace(hits=())

    citations = await search_pdf_pages(Memory(), "What geographies does the company operate in?")

    assert [citation.entry_id for citation in citations] == ["page-4"]
