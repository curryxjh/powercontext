---
title: Parse and retrieve PDF pages
description: Capture complete PDF pages and retrieve exact Memory citations within one scope.
---

# Parse and retrieve PDF pages

Install `powercontext[pdf]` alongside the Runtime dependencies. The PDF extra pins `pypdf` to the parser version used
for page extraction. Processing runs locally and requires no online model. Scanned pages require a separate OCR
workflow; this parser only preserves extractable text.

```python
from pathlib import Path

from powercontext.sources import SourceDefinitionRegistry, project_source_for_transport
from powercontext.sources.pdf_pages import (
    PDF_PAGE_SOURCE_DEFINITION,
    PDFDocumentInput,
    parse_pdf_document,
)

pages = parse_pdf_document(
    PDFDocumentInput(document_id="annual-report", content=Path("report.pdf").read_bytes())
)
registry = SourceDefinitionRegistry((PDF_PAGE_SOURCE_DEFINITION,))
```

Parsing returns a tuple of all physical pages, in order, numbered from one. Blank pages remain in the tuple with empty
text. Each page carries the SHA-256 digest of the complete input bytes, including metadata and permissions. Documents
readable with an empty password are supported. Empty files, invalid PDFs, inaccessible encrypted PDFs, and failures on
any page raise `ValueError`; no partial page tuple is returned. Text-bearing streams are checked before extraction,
including compressed data integrity and nested Form syntax, so corruption cannot silently become blank text. Document IDs must be nonblank; significant whitespace
and Unicode are preserved. Physical page numbers must be positive integers.

For each page, resolve the Source with `await registry.resolve(page)` and create an observation with
`project_source_for_transport(registry, source)`. Register `manifest_for_definition(PDF_PAGE_SOURCE_DEFINITION)` through
`runtime.ingestion.register`, then submit each observation using `SubmitSourceObservation` and the desired scope ID.
The definition is named `pdf-page`, version `1`, and uses captured materialization. Its standard text projection contains
`document_id + "\n" + page.text` and exactly three metadata fields: `document_id`, `document_sha256`, and `page_number`.
Use a Source-processing pipeline to preserve that projection as Memory evidence; ingestion alone does not create Memory.

## Retrieve exact evidence

```python
from powercontext.builtin.runtime import GetMemoryEntryRequest
from powercontext.sources.pdf_pages import search_pdf_pages

memory = runtime.memory.for_scope(scope_id)
citations = await search_pdf_pages(memory, "What is net PP&E?", limit=20)
for citation in citations:
    record = await memory.get(GetMemoryEntryRequest(citation=citation))
    # record.entry.sources identifies the persisted PDF page.
```

Search uses only the supplied scoped Memory's public search/get APIs. Bounded lexical query expansion includes common
financial abbreviations, and statement headings contribute to ranking. Matches between the projected document ID
and the question's issuer/year also contribute, so similar statements from other reports do not dominate solely by
heading. This is a ranking boost rather than a hard filter, allowing comparisons across reports. Results are exact citations obtained from Memory,
with at most `limit` distinct PDF Source identities. Entries without a PDF Source or combining several PDF pages are
excluded. Repeated entries for the same page consume one result slot. Different document revisions retain distinct page
identities. Zero limit performs no Memory access; negative or noninteger limits and blank questions are rejected.

Candidate retrieval uses at most 40 query variants, with at least 100 candidates requested per variant. Citation
validation reads candidates in rank order until the requested number of distinct pages is found or candidates are
exhausted. It does not enumerate or rewrite the complete Memory collection. No document-specific answers or evidence
page lists are used. Retrieval quality depends on the corpus and question; successful parsing alone does not establish
an evidence recall score.

## Stored identities and revisions

Source identity depends on the document ID, complete PDF digest, and physical page number, and stays within 256
characters. Short identities retain the `pdf:` encoding. Longer identities use a disjoint `pdf-sha256:` namespace and a
hash of the complete identity tuple. This avoids confusing a literal document ID with another document's digest.

Existing stored Sources and exact citations retain their original names and remain readable. Recapturing a long identity
that used the older ambiguous shortened encoding produces the disjoint identity; existing historical records are not
renamed or merged automatically. Preserve the original PDF bytes indexed by their complete digest so callers can locate
the physical page even after a newer document revision is ingested.
