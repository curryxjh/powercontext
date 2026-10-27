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
import hashlib
import re
from collections import Counter
from io import BytesIO

import pytest
from pydantic import ValidationError
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from powercontext.sources import SourceDefinitionRegistry, SourceMaterialization, project_source_for_transport
from powercontext.sources.pdf_pages import (
    PDF_PAGE_SOURCE_DEFINITION,
    PDFDocumentInput,
    PDFPageInput,
    PDFPageSource,
    parse_pdf_document,
    pdf_page_source_id,
)
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY, TextEvidence


def make_pdf(
    pages: tuple[str, ...], *, password: str | None = None, algorithm: str | None = None, broken_last_page: bool = False
) -> bytes:
    """Construct known page text, including blank pages, without another parser."""

    writer = PdfWriter()
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    for text in pages:
        page = writer.add_blank_page(width=600, height=800)
        if not text:
            continue
        stream = DecodedStreamObject()
        lines = []
        for line in text.splitlines():
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            lines.append(f"({escaped}) Tj 0 -14 Td")
        stream.set_data(("BT /F1 10 Tf 10 750 Td " + " ".join(lines) + " ET").encode("ascii"))
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        })
        page[NameObject("/Contents")] = stream
    if broken_last_page:
        broken = DecodedStreamObject()
        broken.set_data(b"BT /F1 10 Tf (unterminated string")
        writer.pages[-1][NameObject("/Contents")] = broken
    if password is not None:
        writer.encrypt(user_password=password, owner_password="owner-password", algorithm=algorithm)  # noqa: S106
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_all_physical_pages_keep_their_own_text_numbers_and_blank_boundaries():
    expected = (
        "Quarterly financial statements\nNet revenue 2024 2023\nNorth 123.45 99.01\nSouth (7,654) 6,789",
        "",
        "APPENDIX\nDividend 0.75\nRevenue revenue revenue 42\nShare repurchases 1,234",
    )
    raw = make_pdf(expected)
    result = parse_pdf_document(PDFDocumentInput(document_id="report: /%中文", content=raw))
    assert isinstance(result, tuple)
    assert [page.page_number for page in result] == [1, 2, 3]
    for text, page in zip(expected, result, strict=True):
        assert page.document_id == "report: /%中文"
        assert page.document_sha256 == hashlib.sha256(raw).hexdigest()
        # Known generated text supplies both evidence recall and full-page F1
        # expectations without consulting any benchmark answers or gold files.
        expected_terms = Counter(re.findall(r"[a-z]+|\d+", text.lower()))
        parsed_terms = Counter(re.findall(r"[a-z]+|\d+", page.text.lower()))
        assert parsed_terms == expected_terms
        if not text:
            assert page.text == ""


@pytest.mark.parametrize("password,algorithm", [(None, None), ("", None), ("", "AES-256")])
def test_unencrypted_and_empty_password_documents_preserve_text(password, algorithm):
    raw = make_pdf(("Cash flows 2024 987", ""), password=password, algorithm=algorithm)
    result = parse_pdf_document(PDFDocumentInput(document_id="permissions", content=raw))
    assert len(result) == 2
    assert "Cash flows 2024 987" in result[0].text
    assert result[1].text == ""


def test_nonempty_password_document_is_rejected():
    raw = make_pdf(("Confidential revenue 123",), password="required-password")  # noqa: S106 - synthetic fixture
    with pytest.raises(ValueError):
        parse_pdf_document(PDFDocumentInput(document_id="protected", content=raw))


@pytest.mark.parametrize("raw", [b"", b"plain text", b"%PDF-1.7\ntruncated", b"\x00\x01\x02"])
def test_invalid_pdf_fails_with_value_error(raw):
    with pytest.raises(ValueError):
        parse_pdf_document(PDFDocumentInput(document_id="invalid", content=raw))


def test_failure_on_a_later_page_does_not_return_a_partial_document():
    raw = make_pdf(("Valid first page", "Malformed second page"), broken_last_page=True)
    with pytest.raises(ValueError):
        parse_pdf_document(PDFDocumentInput(document_id="damaged", content=raw))


def test_digest_includes_metadata_and_document_revision_identity():
    raw = make_pdf(("Same page text",))
    # A complete revised byte stream can retain identical extracted text.
    revised = raw + b"\n% revision metadata\n"
    old = parse_pdf_document(PDFDocumentInput(document_id="revised", content=raw))[0]
    new = parse_pdf_document(PDFDocumentInput(document_id="revised", content=revised))[0]
    assert old.text == new.text
    assert old.document_sha256 != new.document_sha256
    assert pdf_page_source_id(old.document_id, old.document_sha256, 1) != pdf_page_source_id(
        new.document_id, new.document_sha256, 1
    )


def test_source_roundtrip_projection_and_bounded_distinct_identity():
    async def scenario():
        definition = PDF_PAGE_SOURCE_DEFINITION
        registry = SourceDefinitionRegistry((definition,))
        assert definition.name == "pdf-page" and definition.version == "1"
        ids = set()
        for document in ("report", " report ", "a/b:c%", "中文" * 300):
            for revision in ("a" * 64, "b" * 64):
                for number in (1, 2):
                    value = PDFPageInput(
                        document_id=document, document_sha256=revision, page_number=number, text="Revenue 100"
                    )
                    source = await registry.resolve(value)
                    assert source.materialization is SourceMaterialization.CAPTURED
                    assert source.name == (await registry.resolve(value)).name
                    assert 0 < len(source.name) <= 256
                    assert source.name not in ids
                    ids.add(source.name)
                    assert await registry.read(source) == value
                    assert PDFPageSource.model_validate_json(source.model_dump_json()) == source
                    observation = project_source_for_transport(registry, source)
                    assert observation.projection(TEXT_EVIDENCE_PROJECTION_KEY) == {
                        "source_type": "pdf-page",
                        "source_id": source.name,
                        "content": f"{document}\nRevenue 100",
                        "metadata": {"document_id": document, "document_sha256": revision, "page_number": number},
                    }

    asyncio.run(scenario())


def test_existing_long_document_source_names_remain_readable():
    async def scenario():
        document = "legacy" * 60
        digest = "b" * 64
        legacy_name = f"pdf:{hashlib.sha256(document.encode()).hexdigest()}:{digest}:1"
        old = PDFPageSource(
            name=legacy_name,
            materialization=SourceMaterialization.CAPTURED,
            document_id=document,
            document_sha256=digest,
            page_number=1,
            text="Original revenue 42",
        )
        registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
        value = await registry.read(PDFPageSource.model_validate_json(old.model_dump_json()))
        assert value == PDFPageInput(
            document_id=document, document_sha256=digest, page_number=1, text="Original revenue 42"
        )
        projected = TextEvidence.model_validate(
            project_source_for_transport(registry, old).projection(TEXT_EVIDENCE_PROJECTION_KEY)
        )
        assert projected.source_id == legacy_name
        assert projected.metadata["document_sha256"] == digest

    asyncio.run(scenario())


@pytest.mark.parametrize("document_id", ["", " ", "\n\t"])
def test_blank_document_identity_is_rejected(document_id):
    with pytest.raises(ValidationError):
        PDFDocumentInput(document_id=document_id, content=b"pdf")
    with pytest.raises(ValidationError):
        PDFPageInput(document_id=document_id, document_sha256="a" * 64, page_number=1, text="")


@pytest.mark.parametrize("digest", ["", "A" * 64, "a" * 63, "g" * 64, "a" * 64 + "\n"])
def test_invalid_document_digest_is_rejected(digest):
    with pytest.raises(ValidationError):
        PDFPageInput(document_id="report", document_sha256=digest, page_number=1, text="")


@pytest.mark.parametrize("number", [0, -1, True, 1.5, "1"])
def test_physical_page_number_requires_a_positive_integer(number):
    with pytest.raises(ValidationError):
        PDFPageInput(document_id="report", document_sha256="a" * 64, page_number=number, text="")
    with pytest.raises(ValueError):
        pdf_page_source_id("report", "a" * 64, number)
