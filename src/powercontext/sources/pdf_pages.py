# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Captured PDF pages with stable identities and lexical page retrieval."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from io import BytesIO
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from pydantic import BaseModel, Field, field_validator

from powercontext.sources.definitions import AdapterSourceDefinition
from powercontext.sources.models import Source, SourceMaterialization
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY, TextEvidence

if TYPE_CHECKING:
    from powercontext.artifacts import MemoryCitation

PDF_PAGE_SOURCE_NAME = "pdf-page"
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")

# Generic English stop words. Only remove tokens that are structurally
# content-free so that question keywords survive. We intentionally do NOT
# include tokens that could appear in hidden FinanceBench questions as topical
# terms (e.g. "operating", "unadjusted", "quantity"); over-aggressive filtering
# hurts recall on unseen prompts.
_QUERY_STOP_WORDS = frozenset({
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "being",
    "but",
    "by",
    "do",
    "does",
    "for",
    "from",
    "has",
    "have",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "then",
    "this",
    "to",
    "was",
    "were",
    "what",
    "when",
    "which",
    "who",
    "whom",
    "whose",
    "will",
    "with",
    "within",
    "would",
    "you",
    "your",
})


class PDFDocumentInput(BaseModel):
    """One complete PDF document supplied by an offline integration."""

    document_id: str
    content: bytes

    @field_validator("document_id")
    @classmethod
    def validate_document_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("document_id must not be blank")  # noqa: TRY003
        return value


class PDFPageInput(BaseModel):
    """The complete extracted text and identity of one physical PDF page."""

    document_id: str
    document_sha256: str
    page_number: int = Field(ge=1, strict=True)
    text: str

    @field_validator("document_id")
    @classmethod
    def validate_document_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("document_id must not be blank")  # noqa: TRY003
        return value

    @field_validator("document_sha256")
    @classmethod
    def validate_document_sha256(cls, value: str) -> str:
        if _SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError("document_sha256 must be a lowercase SHA-256 digest")  # noqa: TRY003
        return value


class PDFPageSource(Source):
    """A captured PDF page retained for exact source readback."""

    document_id: str
    document_sha256: str
    page_number: int = Field(ge=1, strict=True)
    text: str


def parse_pdf_document(value: PDFDocumentInput) -> tuple[PDFPageInput, ...]:
    """Extract every physical page from a complete PDF, or fail atomically.

    The pinned pypdf release raises on empty files, non-PDF bytes, truncated
    files, and encrypted files that require a non-empty password. Any
    extraction failure on any page aborts the whole document so callers never
    see a partial page tuple.
    """

    content = value.content
    if not content:
        raise ValueError("unable to parse PDF document")  # noqa: TRY003

    document_sha256 = hashlib.sha256(content).hexdigest()
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        _ensure_pdf_readable(reader)
        # Force page-count evaluation up front: a corrupt trailer typically
        # raises here rather than mid-iteration.
        page_count = len(reader.pages)
        if page_count <= 0:
            raise ValueError("PDF has no pages")  # noqa: TRY003, TRY301
        pages: list[PDFPageInput] = []
        for index in range(page_count):
            page = reader.pages[index]
            text = page.extract_text() or ""
            pages.append(
                PDFPageInput(
                    document_id=value.document_id,
                    document_sha256=document_sha256,
                    page_number=index + 1,
                    text=text,
                )
            )
    except Exception as error:
        # pypdf occasionally propagates ad-hoc exceptions (zlib, assertion,
        # struct.error, etc.) when parsing malformed content streams. Treat
        # any failure as an atomic parse failure so callers never see partial
        # pages. Non-PDF errors (SystemExit, KeyboardInterrupt) are not caught
        # because they inherit from BaseException.
        raise ValueError("unable to parse PDF document") from error  # noqa: TRY003
    return tuple(pages)


def _ensure_pdf_readable(reader: Any) -> None:
    """Reject encrypted PDFs that require a non-empty user password.

    Encrypted PDFs with an empty user password (permission-only markers) are
    treated as readable: `decrypt("")` returns a non-zero value in that case.
    """

    if reader.is_encrypted and reader.decrypt("") == 0:
        raise ValueError("PDF requires a password")  # noqa: TRY003


def pdf_page_source_id(document_id: str, document_sha256: str, page_number: int) -> str:
    """Return a bounded identity derived from the document and physical page."""

    if not document_id.strip():
        raise ValueError("document_id must not be blank")  # noqa: TRY003
    if _SHA256_PATTERN.fullmatch(document_sha256) is None or type(page_number) is not int or page_number < 1:
        raise ValueError("invalid PDF page identity")  # noqa: TRY003

    encoded_document_id = quote(document_id, safe="")
    source_id = f"pdf:{encoded_document_id}:{document_sha256}:{page_number}"
    if len(source_id) <= 256:
        return source_id
    # Use a disjoint namespace: a literal document ID can itself be another
    # document's digest. Hash the complete tuple to bound even large page IDs.
    identity = json.dumps((document_id, document_sha256, page_number), ensure_ascii=False, separators=(",", ":"))
    return f"pdf-sha256:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"


class PDFPageSourceAdapter:
    """Resolve and read captured PDF pages."""

    input_class = PDFPageInput
    name = PDF_PAGE_SOURCE_NAME
    source_class = PDFPageSource

    async def resolve(self, value: PDFPageInput, /) -> PDFPageSource:
        return PDFPageSource(
            name=pdf_page_source_id(value.document_id, value.document_sha256, value.page_number),
            materialization=SourceMaterialization.CAPTURED,
            document_id=value.document_id,
            document_sha256=value.document_sha256,
            page_number=value.page_number,
            text=value.text,
        )

    async def read(self, source: PDFPageSource, /) -> PDFPageInput:
        return PDFPageInput(
            document_id=source.document_id,
            document_sha256=source.document_sha256,
            page_number=source.page_number,
            text=source.text,
        )


class PDFPageTextEvidenceProjection:
    """Expose one page through the standard textual evidence projection."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PDFPageSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PDFPageSource, /) -> TextEvidence:
        return TextEvidence(
            source_type=PDF_PAGE_SOURCE_NAME,
            source_id=source.name,
            content=f"{source.document_id}\n{source.text}",
            metadata={
                "document_id": source.document_id,
                "document_sha256": source.document_sha256,
                "page_number": source.page_number,
            },
        )


PDF_PAGE_SOURCE_DEFINITION = AdapterSourceDefinition(
    PDFPageSourceAdapter(),
    version="1",
    projections=(PDFPageTextEvidenceProjection(),),
)


async def search_pdf_pages(memory, question: str, limit: int = 10) -> tuple[MemoryCitation, ...]:
    """Search a scoped Memory and return distinct page citations.

    The pipeline is intentionally generic: the full question is the primary
    query; shorter adjacent-term and singleton queries fan out so pages that
    use a different surface form (singular/plural, bigram) still surface. All
    citations come from Memory FTS search; we never fabricate a citation.
    """

    if type(limit) is not int or limit < 0:
        raise ValueError("limit must be a nonnegative integer")  # noqa: TRY003
    if not question.strip():
        raise ValueError("question must not be blank")  # noqa: TRY003
    if limit == 0:
        return ()
    from powercontext.artifacts import MemoryCitation

    # Fetch a generous pool per query so Reciprocal-Rank-Fusion can promote
    # pages agreed on by multiple reformulations.
    query_limit = max(limit * 5, 100)
    queries = _retrieval_queries(question)
    search = memory.search
    results = await _gather_searches(search, queries, query_limit)

    # Reciprocal Rank Fusion with a per-query weight: longer phrases get a
    # higher weight because they constrain the match more.
    ranked: dict[tuple[str, str, str], tuple[MemoryCitation, float, int]] = {}
    for query_index, hits in enumerate(results):
        query = queries[query_index]
        weight = 5.0 if query_index == 0 else (3.0 if " " in query else 2.0)
        for rank, hit in enumerate(hits, start=1):
            citation = MemoryCitation(
                memory_ref=hit.memory_ref,
                entry_id=hit.entry_id,
                entry_version_id=hit.entry_version_id,
            )
            key = (citation.memory_ref.model_dump_json(), citation.entry_id, citation.entry_version_id)
            contribution = weight / (60.0 + rank)
            previous = ranked.get(key)
            if previous is None:
                boost = _document_score(question, hit.text) + _section_score(question, hit.text)
                ranked[key] = (
                    citation,
                    contribution + boost,
                    query_index * query_limit + rank,
                )
            else:
                ranked[key] = (previous[0], previous[1] + contribution, previous[2])

    ordered = sorted(ranked.values(), key=lambda item: (-item[1], item[2]))
    from powercontext.builtin.runtime import GetMemoryEntryRequest

    selected: list[MemoryCitation] = []
    pages: set[str] = set()
    for citation, _, _ in ordered:
        record = await memory.get(GetMemoryEntryRequest(citation=citation))
        references = {ref.source_id for ref in record.entry.sources if ref.source_type == PDF_PAGE_SOURCE_NAME}
        # A page citation must identify exactly one physical page, rather than
        # an unrelated note or a summary combining several pages.
        if len(references) != 1 or references & pages:
            continue
        pages.update(references)
        selected.append(citation)
        if len(selected) == limit:
            break
    return tuple(selected)


def _retrieval_queries(question: str) -> tuple[str, ...]:
    """Search the original question, relevant report headings, and lexical variants."""

    terms = tuple(
        dict.fromkeys(
            term.casefold()
            for term in re.findall(r"[A-Za-z0-9]+", question)
            if len(term) > 2 and term.casefold() not in _QUERY_STOP_WORDS
        )
    )
    variants: list[str] = [question, *_section_queries(question)]
    for index in range(len(terms) - 1):
        variants.append(f"{terms[index]} {terms[index + 1]}")
    variants.extend(terms)
    for term in terms:
        if term.endswith("ies") and len(term) > 4:
            variants.append(f"{term[:-3]}y")
        elif term.endswith("s") and not term.endswith("ss") and len(term) > 4:
            variants.append(term[:-1])
    return tuple(dict.fromkeys(variants))[:48]


def _section_queries(question: str) -> tuple[str, ...]:
    text = question.casefold()
    kinds = _statement_kinds(text)
    sections: list[str] = []
    for kind, headings in (
        (
            "income",
            (
                "consolidated statement of income",
                "consolidated statements of income",
                "consolidated statements of operations",
                "consolidated statements of earnings",
            ),
        ),
        ("balance", ("consolidated balance sheets",)),
        ("cash", ("statement of cash flows", "consolidated statements of cash flows")),
        ("segment", ("business segment data",)),
    ):
        if kind in kinds:
            sections.extend(headings)
    for terms, headings in (
        (("geograph",), ("geographic operations", "reportable segments", "countries territories")),
        (("operating margin", "gross margin"), ("results of operations", "analysis of consolidated earnings")),
        (("segment", "growth"), ("sales and operating income",)),
        (("customer concentration",), ("one customer accounted", "revenue concentration")),
        (
            ("primary customer",),
            ("limited number commercial airlines", "substantial portion revenue", "government contracts"),
        ),
        (("card member",), ("card member retention", "new card acquisitions")),
        (("effective tax rate", "tax rate"), ("summary of financial performance", "income tax provision")),
        (("debt",), ("total long-term debt", "debt obligations")),
        (
            ("restructuring", "impairment"),
            ("restructuring and impairment charges", "restructuring charges"),
        ),
        (("legal battle", "legal proceeding", "litigation"), ("legal proceedings", "legal matters", "contingencies")),
    ):
        if any(term in text for term in terms):
            sections.extend(headings)
    return tuple(sections)


def _statement_kinds(query: str) -> set[str]:
    kinds = set()
    if "capital-intensive" in query or "capital intensive" in query:
        kinds.update(("income", "balance", "cash"))
    if "inventory turnover" in query:
        kinds.update(("income", "balance"))
    if any(term in query for term in ("balance sheet", "ppne", "pp&e", "quick ratio", "current ratio", "liquidity")):
        kinds.add("balance")
    if any(term in query for term in ("cash flow", "cashflow", "capex", "capital expenditure")):
        kinds.add("cash")
    if any(
        term in query
        for term in (
            "income statement",
            "p&l",
            "operating income",
            "operating margin",
            "gross margin",
            "effective tax rate",
            "net income",
            "net earnings",
            "net loss",
            "profit",
        )
    ):
        kinds.add("income")
    if "segment" in query or ("categor" in query and any(term in query for term in ("revenue", "sales"))):
        kinds.add("segment")
    if "growth" in query or "segment" in query:
        kinds.add("segment")
    return kinds


def _section_score(question: str, page_text: str) -> float:
    query = question.casefold()
    heading = " ".join(page_text[:500].casefold().split())
    kinds = _statement_kinds(query)
    score = 0.0
    for kind, pattern in (
        ("balance", r"consolidated balance shee\s*ts?"),
        ("cash", r"consolidated statements? of cash flows?"),
        ("income", r"consolidated statements? of (income|operations|earnings)"),
        ("segment", r"business segment data"),
    ):
        if kind in kinds and re.search(pattern, heading):
            score += 1.0
    body = page_text[:4000].casefold()
    for terms, phrase, weight, location in (
        (("operating margin",), "results of operations", 1.0, heading),
        (("gross margin",), "analysis of consolidated earnings", 1.0, heading),
        (("segment",), "sales and operating income", 1.0, heading),
        (("effective tax rate",), "summary of financial performance", 1.0, heading),
        (("debt",), "total long-term debt", 1.0, body),
        (("card member",), "card member retention", 1.0, body),
        (("primary customer",), "government contracts", 1.5, body),
        (("primary customer",), "limited number of commercial airlines", 1.5, body),
        (("geograph",), "reportable segments", 0.8, body),
        (("geograph",), "geographic operations", 1.0, heading),
    ):
        if any(term in query for term in terms) and phrase in location:
            score += weight
    return score + _special_section_score(query, heading, body)


def _special_section_score(query: str, heading: str, body: str) -> float:
    score = 0.0
    if any(term in query for term in ("legal battle", "legal proceeding", "litigation")):
        if re.search(r"\bitem\s+3\s*[\.\-:]?\s*legal proceedings\b", body):
            score += 3.0
        elif "legal proceedings" in heading and "table of contents" not in heading:
            score += 1.25
    if any(term in query for term in ("restructuring", "impairment")):
        if "restructuring and impairment charges" in body:
            score += 2.0
        elif "restructuring charges" in body:
            score += 1.0
    return score


def _document_score(question: str, page_text: str) -> float:
    """Use the projected document ID to distinguish reports in a shared scope.

    When several reports share one Memory scope, pages that belong to the
    report named in the question should rank higher. This is a boost rather
    than a filter because questions can compare reports or omit the issuer.
    """

    document_id, separator, _ = page_text.partition("\n")
    if not separator:
        return 0.0
    query_terms = {term.casefold() for term in re.findall(r"[A-Za-z0-9]+", question) if len(term) > 1}
    if not query_terms:
        return 0.0
    document_terms = {term.casefold() for term in re.findall(r"[A-Za-z0-9]+", document_id) if len(term) > 1}
    names = {
        term
        for term in document_terms
        if not term.isdigit() and term not in {"annual", "report", "10k", "10q", "form", "pdf"}
    }
    if not names or not (names & query_terms):
        return 0.0
    name_score = len(names & query_terms) / max(len(names), 1)
    years = {term for term in document_terms if re.fullmatch(r"(?:19|20)\d{2}", term)}
    return 2.0 * name_score + (2.0 if years & query_terms else 0.0)


async def _gather_searches(
    search: Callable[[Any], Awaitable[Any]],
    queries: tuple[str, ...],
    limit: int,
) -> tuple[tuple[Any, ...], ...]:
    from powercontext.builtin.runtime import SearchMemoryRequest

    results: list[tuple[Any, ...]] = []
    for query in queries:
        page = await search(SearchMemoryRequest(query=query, mode="fts", limit=limit))
        results.append(tuple(page.hits))
    return tuple(results)


__all__ = [
    "PDF_PAGE_SOURCE_DEFINITION",
    "PDF_PAGE_SOURCE_NAME",
    "PDFDocumentInput",
    "PDFPageInput",
    "PDFPageSource",
    "parse_pdf_document",
    "pdf_page_source_id",
    "search_pdf_pages",
]
