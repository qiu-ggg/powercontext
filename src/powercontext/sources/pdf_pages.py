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

"""Physical-page PDF Sources with exact page-level retrieval.

Every physical page of an original PDF becomes one ``CAPTURED`` Source. The
identity is derived from the document id, the SHA-256 of the whole input file and
the 1-based physical page number, so a citation resolves to exactly one page of
exactly one revision of the file even after the document is re-issued.

Retrieval is offline: the pages are ranked locally with BM25 over the Memory
entry bodies, boosted by the section headings printed on each page and by
adjacency of query terms, and only real Memory citations are returned.
"""

from __future__ import annotations

import hashlib
import io
import math
import re
from collections import Counter
from urllib.parse import quote

from pydantic import BaseModel, model_validator
from pypdf import PdfReader

from powercontext.artifacts.models import MemoryCitation
from powercontext.sources.definitions import AdapterSourceDefinition, SourceDefinition
from powercontext.sources.models import (
    Source,
    SourceMaterialization,
    _validate_reference_part,
)
from powercontext.sources.projections import TEXT_EVIDENCE_PROJECTION_KEY, TextEvidence

PDF_PAGE_SOURCE_NAME = "pdf-page"
PDF_PAGE_SOURCE_VERSION = "1"
PDF_PAGE_SOURCE_ID_PREFIX = "pdf"

#: ``_validate_reference_part`` refuses longer identities, and the SHA-256 digest
#: already spends 64 characters, so a document id that would overflow is folded.
_MAX_IDENTITY_LENGTH = 256
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")

_WORD_PATTERN = re.compile(r"[a-z]+|\d+")
_FISCAL_YEAR_PATTERN = re.compile(r"\bfy\s?(\d{4})\b")

#: Function words carry no retrieval signal; dropping them keeps a natural-language
#: question from matching a page on grammar alone.
_STOPWORDS = frozenset(
    """
    a about above after again against all am an and any are as at be because been before being
    below between both but by can could did do does doing down during each few for from further
    had has have having he her here hers herself him himself his how i if in into is it its itself
    just me more most my myself no nor not now of off on once only or other our ours ourselves out
    over own same she should so some such than that the their theirs them themselves then there
    these they this those through to too under until up very was we were what when where which
    while who whom why will with would you your yours yourself yourselves
    """.split()
)

#: FinanceBench questions wrap the ask in a task instruction ("Respond to the
#: question by assuming the perspective of an investment analyst ..."). Those words
#: describe the exercise, not the document, and they match nearly every page.
_INSTRUCTION_WORDS = frozenset(
    """
    define defined calculate calculated compute computed please give provide report reported show
    following using use used based response respond answer assuming assume perspective analyst
    investor state explain explanation why relevant useful metric measure like company details
    shown within only cannot can stated above below question let know tell
    """.split()
)

#: A deliberately small suffix set. It has to merge the inflection families that
#: matter for financial prose (``operates``/``operating``/``operations``,
#: ``revenues``/``revenue``, ``primarily``/``primary``) without collapsing words
#: that carry different meaning.
_SUFFIXES = (
    ("ically", ""),
    ("ation", "at"),
    ("ations", "at"),
    ("ingly", ""),
    ("edly", ""),
    ("ies", "y"),
    ("sses", "ss"),
    ("ing", ""),
    ("ly", ""),
    ("ed", ""),
    ("es", ""),
    ("s", ""),
)

_BM25_K1 = 1.2
#: Pages of a 10-K run from a 40-token cover sheet to a 900-token statement, so
#: full length normalisation buries the long narrative pages that hold the answer.
_BM25_B = 0.35
#: Section titles ("Item 3. Legal Proceedings.", "Consolidated Statement of Cash
#: Flows") name the answer far more reliably than the body text around them.
_HEADING_WEIGHT = 1.0
_HEADING_B = 0.4
#: Weight of the trailing instruction clause relative to the primary ask.
_SECONDARY_WEIGHT = 0.3
#: Weight of an adjacent query-term pair that also occurs adjacently on the page.
_PHRASE_WEIGHT = 0.2


class PDFDocumentInput(BaseModel):
    """One complete original PDF plus the document id that names it."""

    document_id: str
    content: bytes


class PDFPageInput(BaseModel):
    """One physical page of one PDF revision."""

    document_id: str
    document_sha256: str
    page_number: int
    text: str

    @model_validator(mode="after")
    def validate_page(self) -> PDFPageInput:
        _require_non_blank(self.document_id, "document_id")
        if not _SHA256_PATTERN.fullmatch(self.document_sha256):
            raise ValueError("document_sha256 must be 64 lowercase hexadecimal characters")  # noqa: TRY003
        if not isinstance(self.page_number, int) or isinstance(self.page_number, bool) or self.page_number < 1:
            raise ValueError("page_number must be a positive integer")  # noqa: TRY003
        return self


class PDFPageSource(Source):
    """A captured physical page whose name is its stable identity."""

    source_id: str
    document_id: str
    document_sha256: str
    page_number: int
    text: str

    @model_validator(mode="after")
    def validate_identity(self) -> PDFPageSource:
        _validate_reference_part("source_id", self.source_id)
        if self.name != self.source_id:
            raise ValueError("PDF page Source name must equal its identity")  # noqa: TRY003
        return self


def pdf_page_source_id(document_id: str, document_sha256: str, page_number: int) -> str:
    """Return the fixed ``pdf:<document>:<sha256>:<page>`` identity for one page."""

    document = _require_non_blank(document_id, "document_id")
    identity = f"{PDF_PAGE_SOURCE_ID_PREFIX}:{quote(document, safe='')}:{document_sha256}:{page_number}"
    if len(identity) > _MAX_IDENTITY_LENGTH:
        folded = hashlib.sha256(document.encode("utf-8")).hexdigest()
        identity = f"{PDF_PAGE_SOURCE_ID_PREFIX}:{folded}:{document_sha256}:{page_number}"
    _validate_reference_part("source_id", identity)
    return identity


def parse_pdf_document(value: PDFDocumentInput) -> tuple[PDFPageInput, ...]:
    """Parse every physical page of one original PDF.

    Parsing is all-or-nothing: either every page is extracted and returned, or the
    call raises ``ValueError`` without exposing a partial page list.
    """

    document_id = _require_non_blank(value.document_id, "document_id")
    if not isinstance(value.content, (bytes, bytearray)):
        raise ValueError("PDF content must be bytes")  # noqa: TRY003
    content = bytes(value.content)
    if not content:
        raise ValueError("PDF document must not be empty")  # noqa: TRY003

    digest = hashlib.sha256(content).hexdigest()
    texts = _extract_pages(content)
    if not texts:
        raise ValueError("PDF document must contain at least one page")  # noqa: TRY003
    return tuple(
        PDFPageInput(
            document_id=document_id,
            document_sha256=digest,
            page_number=index,
            text=text,
        )
        for index, text in enumerate(texts, start=1)
    )


def _extract_pages(content: bytes) -> list[str]:
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            # An empty user password is a permission marker, not an access barrier:
            # the document opens without asking the caller for a secret.
            if not reader.decrypt(""):
                raise ValueError("PDF document requires a user password")  # noqa: TRY003
        pages = list(reader.pages)
        return [_page_text(page) for page in pages]
    except ValueError:
        raise
    except Exception as error:  # noqa: BLE001 - any parser failure is an invalid document
        raise ValueError(f"PDF document could not be parsed: {error}") from error


def _page_text(page: object) -> str:
    extracted = page.extract_text()  # type: ignore[attr-defined]
    return "" if extracted is None else str(extracted)


def _require_non_blank(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")  # noqa: TRY003
    return value


def _stem(word: str) -> str:
    if len(word) <= 3:
        return word
    for suffix, replacement in _SUFFIXES:
        if not word.endswith(suffix):
            continue
        if len(word) - len(suffix) < 3:
            continue
        if suffix == "s" and word.endswith("ss"):
            continue
        if suffix == "es" and word.endswith("ses"):
            continue
        base = word[: -len(suffix)] + replacement
        if suffix == "s" and base.endswith(("u", "i")):
            continue
        return base
    return word


def _normalize(text: str) -> str:
    """Lower-case the text and fold ``FY2022`` onto the bare year."""

    return _FISCAL_YEAR_PATTERN.sub(r"\1", text.lower())


def _tokenize(text: str) -> list[str]:
    return [_stem(token) for token in _WORD_PATTERN.findall(_normalize(text))]


def _bigrams(tokens: list[str]) -> set[tuple[str, str]]:
    return set(zip(tokens, tokens[1:], strict=False))


_HEADING_PATTERNS = (
    re.compile(r"^item\s+\d+[a-z]?\.?"),
    re.compile(r"^note\s+\d+\s*[—–-]"),
    re.compile(r"^consolidated\s+(statement|balance|statements)"),
    re.compile(r"^part\s+[ivx]+\b"),
)


def _is_heading(line: str) -> bool:
    """True when a line looks like a section title rather than prose or a table row."""

    if not line or len(line) > 90 or len(line.split()) > 12:
        return False
    if line.lower() == "table of contents":
        return False
    lowered = line.lower()
    if any(pattern.match(lowered) for pattern in _HEADING_PATTERNS):
        return True
    if len(line.split()) > 8 or "," in line or "$" in line or "—" in line:
        return False
    numeric = [token for token in _WORD_PATTERN.findall(lowered) if token.isdigit()]
    if len(numeric) >= 3 or any(len(token) >= 3 for token in numeric):
        return False
    if line.endswith((".", ",", ";", ":", "%", ")", "’")):
        return False
    return line[0].isupper()


def _headings(text: str) -> str:
    return "\n".join(line.strip() for line in text.splitlines() if _is_heading(line.strip()))


def _split_question(question: str) -> tuple[str, str]:
    """Split the raw question into its primary ask and the trailing instruction."""

    index = question.find("?")
    if index >= 0:
        return question[: index + 1], question[index + 1 :]
    index = question.find(". ")
    if index >= 0:
        return question[: index + 1], question[index + 1 :]
    return question, ""


def _query_weights(question: str) -> dict[str, float]:
    """Return ``term -> weight`` for one question, ignoring grammar and instructions."""

    primary, secondary = _split_question(question)
    weights: dict[str, float] = {}
    for text, weight in ((primary, 1.0), (secondary, _SECONDARY_WEIGHT)):
        for term in _tokenize(text):
            if term in _STOPWORDS or term in _INSTRUCTION_WORDS:
                continue
            weights[term] = max(weights.get(term, 0.0), weight)
    if weights:
        return weights
    for term in _tokenize(question):
        if term not in _STOPWORDS:
            weights[term] = 1.0
    return weights


def _query_phrases(question: str) -> list[tuple[str, str]]:
    primary, _ = _split_question(question)
    sequence = _tokenize(primary)
    pairs = [
        (left, right)
        for left, right in zip(sequence, sequence[1:], strict=False)
        if left not in _STOPWORDS
        and right not in _STOPWORDS
        and left not in _INSTRUCTION_WORDS
        and right not in _INSTRUCTION_WORDS
    ]
    return list(dict.fromkeys(pairs))


def _idf(document_frequency: int, total: int) -> float:
    return math.log(1.0 + (total - document_frequency + 0.5) / (document_frequency + 0.5))


def _bm25(
    weights: dict[str, float],
    counters: list[Counter],
    lengths: list[int],
    average: float,
    b: float,
) -> list[float]:
    total = len(counters)
    idf = {}
    for term in weights:
        document_frequency = sum(1 for counter in counters if counter.get(term))
        idf[term] = _idf(document_frequency, total)
    scores = [0.0] * total
    for index, counter in enumerate(counters):
        norm = _BM25_K1 * (1.0 - b + b * (lengths[index] / average if average else 0.0))
        score = 0.0
        for term, weight in weights.items():
            frequency = counter.get(term, 0)
            if frequency:
                score += weight * idf[term] * frequency * (_BM25_K1 + 1.0) / (frequency + norm)
        scores[index] = score
    return scores


def _rank(
    texts: tuple[str, ...],
    question: str,
) -> list[int]:
    """Return entry positions ordered by relevance to the question.

    Three lexical signals are combined, because no single one is enough on a
    10-K: the page body, the section headings printed on the page, and adjacency
    of query terms. Scores are only compared inside one signal family, so the
    body score dominates and the heading and phrase terms act as tie-breakers.
    """

    if not texts:
        return []
    weights = _query_weights(question)
    if not weights:
        return []

    bodies = [Counter(_tokenize(text)) for text in texts]
    body_lengths = [sum(counter.values()) for counter in bodies]
    body_average = sum(body_lengths) / len(body_lengths)
    scores = _bm25(weights, bodies, body_lengths, body_average, _BM25_B)

    titles = [_headings(text) for text in texts]
    heading_counters = [Counter(_tokenize(title)) for title in titles]
    heading_lengths = [sum(counter.values()) for counter in heading_counters]
    heading_average = (sum(heading_lengths) / len(heading_lengths)) or 1.0
    heading_scores = _bm25(
        weights, heading_counters, heading_lengths, heading_average, _HEADING_B
    )
    scores = [body + _HEADING_WEIGHT * heading for body, heading in zip(scores, heading_scores, strict=True)]

    pairs = _query_phrases(question)
    if pairs:
        page_pairs = [_bigrams(_tokenize(text)) for text in texts]
        every_pair = [pair for pairs_on_page in page_pairs for pair in pairs_on_page]
        pair_idf = [
            _idf(every_pair.count(pair), len(every_pair)) for pair in pairs
        ]
        for index, pairs_on_page in enumerate(page_pairs):
            bonus = sum(
                weight for pair, weight in zip(pairs, pair_idf, strict=True) if pair in pairs_on_page
            )
            if bonus:
                scores[index] += _PHRASE_WEIGHT * bonus

    ordered = [(score, index) for index, score in enumerate(scores) if score > 0.0]
    # Ties fall back to page order, which keeps the result deterministic.
    ordered.sort(key=lambda item: (-item[0], item[1]))
    return [index for _, index in ordered]


async def search_pdf_pages(
    memory,
    question: str,
    limit: int = 10,
) -> tuple[MemoryCitation, ...]:
    """Return up to ``limit`` exact page citations for one natural-language question."""

    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError("limit must be a positive integer")  # noqa: TRY003
    query = _require_non_blank(question, "question")

    page = await memory.list()
    records = page.entries
    if not records:
        return ()

    ordered = _rank(tuple(record.entry.text for record in records), query)
    citations: list[MemoryCitation] = []
    for index in ordered:
        citation = records[index].citation
        if citation in citations:
            continue
        citations.append(citation)
        if len(citations) >= limit:
            break
    return tuple(citations)


class _PDFPageSourceAdapter:
    """Resolve and read the physical-page PDF Source."""

    input_class = PDFPageInput
    name = PDF_PAGE_SOURCE_NAME
    source_class = PDFPageSource

    async def resolve(self, value: PDFPageInput, /) -> PDFPageSource:
        source_id = pdf_page_source_id(value.document_id, value.document_sha256, value.page_number)
        return PDFPageSource(
            name=source_id,
            source_id=source_id,
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


class _PDFPageTextEvidenceProjection:
    """Expose one physical page as standard textual Artifact evidence."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PDFPageSource
    output_class: type[BaseModel] = TextEvidence

    def project(self, source: PDFPageSource, /) -> TextEvidence:
        return TextEvidence(
            source_type=PDF_PAGE_SOURCE_NAME,
            source_id=source.source_id,
            content=f"{source.document_id}\n{source.text}",
            metadata={
                "document_id": source.document_id,
                "document_sha256": source.document_sha256,
                "page_number": source.page_number,
            },
        )


PDF_PAGE_SOURCE_DEFINITION: SourceDefinition[PDFPageInput, PDFPageSource, PDFPageInput] = AdapterSourceDefinition(
    _PDFPageSourceAdapter(),
    version=PDF_PAGE_SOURCE_VERSION,
    projections=(_PDFPageTextEvidenceProjection(),),
)


__all__ = [
    "PDF_PAGE_SOURCE_DEFINITION",
    "PDF_PAGE_SOURCE_NAME",
    "PDF_PAGE_SOURCE_VERSION",
    "PDFDocumentInput",
    "PDFPageInput",
    "PDFPageSource",
    "parse_pdf_document",
    "pdf_page_source_id",
    "search_pdf_pages",
]
