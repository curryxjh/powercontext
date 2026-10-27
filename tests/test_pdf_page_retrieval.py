import hashlib
from types import SimpleNamespace

import pytest

from powercontext.artifacts import ArtifactRef
from powercontext.builtin.artifacts.memory import MemoryHit
from powercontext.sources import SourceRef
from powercontext.sources.pdf_pages import PDFDocumentInput, PDFPageInput, pdf_page_source_id, search_pdf_pages

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


class _PageMemory:
    async def get(self, request):
        page = int(request.citation.entry_id.removeprefix("page-"))
        return SimpleNamespace(
            entry=SimpleNamespace(sources=(SourceRef(source_type="pdf-page", source_id=f"page-{page}"),))
        )


@pytest.mark.parametrize("limit", [-1, True, 1.5, "2"])
@pytest.mark.asyncio
async def test_invalid_limit_is_rejected_before_search(limit):
    with pytest.raises(ValueError):
        await search_pdf_pages(object(), "balance sheet", limit=limit)


@pytest.mark.parametrize("question", ["", " \t\n"])
@pytest.mark.asyncio
async def test_blank_questions_are_rejected(question):
    with pytest.raises(ValueError):
        await search_pdf_pages(object(), question)


@pytest.mark.asyncio
async def test_zero_limit_does_not_access_memory():
    assert await search_pdf_pages(object(), "balance sheet", limit=0) == ()


def test_long_document_id_cannot_collide_with_its_digest_as_document_id():
    document_id = "a" * 300
    digest_id = hashlib.sha256(document_id.encode()).hexdigest()
    revision = "b" * 64
    assert pdf_page_source_id(document_id, revision, 1) != pdf_page_source_id(digest_id, revision, 1)
    assert len(pdf_page_source_id(document_id, revision, 10**200)) <= 256


def test_nonblank_document_ids_preserve_significant_whitespace():
    value = PDFDocumentInput(document_id=" report ", content=b"pdf")
    page = PDFPageInput(document_id=value.document_id, document_sha256="b" * 64, page_number=1, text="text")
    assert page.document_id == " report "
    assert pdf_page_source_id(page.document_id, page.document_sha256, 1) != pdf_page_source_id("report", "b" * 64, 1)


@pytest.mark.asyncio
async def test_retrieval_deduplicates_pages_and_excludes_non_pdf_entries():
    class Memory(_PageMemory):
        async def search(self, request):
            return SimpleNamespace(
                hits=(
                    _page(1, "balance sheet"),
                    _page(2, "balance sheet"),
                    _page(3, "balance sheet"),
                    _page(4, "balance sheet"),
                )
            )

        async def get(self, request):
            entry = request.citation.entry_id
            reference = SourceRef(
                source_type="content" if entry == "page-1" else "pdf-page",
                source_id="same" if entry in {"page-2", "page-3"} else "other",
            )
            return SimpleNamespace(entry=SimpleNamespace(sources=(reference,)))

    citations = await search_pdf_pages(Memory(), "balance sheet", limit=3)
    assert [citation.entry_id for citation in citations] == ["page-2", "page-4"]


@pytest.mark.asyncio
async def test_statement_heading_promotes_an_exact_page_citation() -> None:
    class Memory(_PageMemory):
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
    class Memory(_PageMemory):
        async def search(self, request):
            if "reportable segments" in request.query:
                return SimpleNamespace(hits=(_page(4, "Our operations are organized into reportable segments."),))
            return SimpleNamespace(hits=())

    citations = await search_pdf_pages(Memory(), "What geographies does the company operate in?")

    assert [citation.entry_id for citation in citations] == ["page-4"]


@pytest.mark.asyncio
async def test_cash_flow_statement_plural_heading_is_retrieved() -> None:
    class Memory(_PageMemory):
        async def search(self, request):
            if request.query == "consolidated statements of cash flows":
                return SimpleNamespace(hits=(_page(26, "REPORT_2022_10K\nConsolidated Statements of Cash Flows"),))
            if request.query.startswith("What is the dividend payout ratio"):
                return SimpleNamespace(
                    hits=tuple(_page(i, "REPORT_2022_10K\nOther financial data") for i in range(1, 26))
                )
            return SimpleNamespace(hits=())

    citations = await search_pdf_pages(
        Memory(),
        "What is the dividend payout ratio from the cash flow statement and the income statement?",
        limit=20,
    )

    assert citations[0].entry_id == "page-26"


@pytest.mark.parametrize(
    ("question", "section", "heading"),
    [
        ("Is the quick ratio healthy?", "consolidated balance sheets", "Consolidated Balance Sheets"),
        ("What is the gross margin?", "consolidated statements of operations", "Consolidated Statements of Operations"),
        (
            "Has the operating margin improved?",
            "consolidated statements of operations",
            "Consolidated Statements of Operations",
        ),
        (
            "What is the effective tax rate?",
            "consolidated statements of operations",
            "Consolidated Statements of Operations",
        ),
        ("What was net income in 2021?", "consolidated statements of income", "Consolidated Statements of Income"),
        (
            "What is the quantity of restructuring costs directly outlined in the income statements for FY2022?",
            "restructuring and impairment charges",
            "Note 3 Restructuring and Impairment Charges",
        ),
        ("Which product categories drive revenue?", "business segment data", "Summary of Business Segment Data"),
        ("Which geographies does the company operate in?", "geographic operations", "Geographic Operations"),
        ("What changed the operating margin?", "results of operations", "Results of Operations"),
        (
            "Which segment had lower growth?",
            "sales and operating income",
            "Sales and Operating Income by Business Segment",
        ),
        (
            "What drove the gross margin change?",
            "analysis of consolidated earnings",
            "Analysis of Consolidated Earnings",
        ),
        ("What is the inventory turnover?", "consolidated balance sheets", "Consolidated Balance Sheets"),
        (
            "What is the inventory turnover?",
            "consolidated statements of earnings",
            "Consolidated Statements of Earnings",
        ),
        (
            "Is free cashflow conversion improving?",
            "consolidated statements of cash flows",
            "Consolidated Statements of Cash Flows",
        ),
    ],
)
@pytest.mark.asyncio
async def test_financial_question_recalls_its_statement_page(question: str, section: str, heading: str) -> None:
    class Memory(_PageMemory):
        async def search(self, request):
            if section in request.query:
                return SimpleNamespace(hits=(_page(26, f"REPORT_2022_10K\n{heading}\n2022 2021"),))
            if request.query == question:
                return SimpleNamespace(
                    hits=tuple(_page(i, "REPORT_2022_10K\nUnrelated discussion") for i in range(1, 26))
                )
            return SimpleNamespace(hits=())

    citations = await search_pdf_pages(Memory(), question, limit=20)

    assert citations[0].entry_id == "page-26"


@pytest.mark.parametrize("company", ["ACME", "3M", "NORTH-WEST"])
@pytest.mark.parametrize("distractor", ["OTHER_2023_10K", "{company}_2021_10K"])
@pytest.mark.asyncio
async def test_question_document_identity_outweighs_other_reports_statement_headings(company, distractor):
    class Memory(_PageMemory):
        async def search(self, request):
            return SimpleNamespace(
                hits=(
                    *(
                        _page(
                            i,
                            f"{distractor.format(company=company)}\nConsolidated Balance Sheet\nProperty plant equipment 900",
                        )
                        for i in range(1, 26)
                    ),
                    _page(26, f"{company}_2024_10K\nAssets\nProperty plant equipment net 120"),
                )
            )

    citations = await search_pdf_pages(Memory(), f"What is {company}'s net PPNE for 2024?", limit=20)
    assert citations[0].entry_id == "page-26"


@pytest.mark.asyncio
async def test_financial_question_retains_margin_as_retrieval_evidence():
    class Memory(_PageMemory):
        async def search(self, request):
            if request.query == "margin":
                return SimpleNamespace(hits=(_page(1, "Report\nGross margin was 35 percent"),))
            return SimpleNamespace(hits=())

    citations = await search_pdf_pages(Memory(), "What was the gross margin?")
    assert [citation.entry_id for citation in citations] == ["page-1"]


@pytest.mark.asyncio
async def test_legal_proceedings_heading_promotes_the_exact_page() -> None:
    class Memory(_PageMemory):
        async def search(self, request):
            del request
            return SimpleNamespace(
                hits=(
                    *(_page(i, "REPORT_2022_10K\nTable of contents\nLegal proceedings") for i in range(1, 26)),
                    _page(
                        26,
                        "REPORT_2022_10K\nTable of Contents\n"
                        + ("Item 2. Properties.\n" * 40)
                        + "Item 3. Legal Proceedings\nThe company is involved in litigation.",
                    ),
                )
            )

    citations = await search_pdf_pages(
        Memory(),
        "Has the company reported any materially important ongoing legal battles?",
        limit=20,
    )

    assert len(citations) == 20
    assert citations[0].entry_id == "page-26"
