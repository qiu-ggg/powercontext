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

Retrieval is offline. Pages are ranked locally with BM25 over the Memory entry
bodies, widened by the financial vocabulary the question's concepts imply
(:mod:`powercontext.sources.pdf_concepts`), boosted by the section titles printed
on each page and by adjacency of query terms, with a small prior toward pages
that print a primary financial statement. Only real Memory citations are
returned.
"""

from __future__ import annotations

import hashlib
import io
import math
import re
from collections import Counter
from collections.abc import Sequence
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
from powercontext.sources.pdf_concepts import CONCEPT_SOURCE
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
_BM25_B = 0.45
#: Section titles ("Item 3. Legal Proceedings.", "Consolidated Statement of Cash
#: Flows") name the answer far more reliably than the body text around them.
_HEADING_WEIGHT = 1.0
_HEADING_B = 0.4
#: Weight of the trailing instruction clause relative to the primary ask.
_SECONDARY_WEIGHT = 0.3
#: Weight of an adjacent query-term pair that also occurs adjacently on the page.
_PHRASE_WEIGHT = 0.2
#: Weight of a concept expansion term relative to a term the question actually
#: used. It has to be well below 1.0: the expansion is a guess about vocabulary,
#: the question is not.
_CONCEPT_WEIGHT = 0.45
#: A question that asks for a financial metric is answered by a primary
#: statement far more often than by a narrative page, so pages carrying a
#: statement title receive a fraction of the top page score as a bonus.
_STATEMENT_WEIGHT = 0.2

#: A metric question is often answered by a statement page that hardly repeats
#: the question's own wording ("operating margin" -> the income statement), so
#: the statement named by the question gets its own ranking pass and a decisive
#: position bonus instead of competing on wording alone.
_FACET_WEIGHT = 2.0
_FACET_DEPTH = 4
#: Rank-fusion damping. Every pass contributes through the position it reaches,
#: so passes with incomparable score scales stay comparable.
_FUSION_DAMPING = 40
#: How deep the wording pass feeds the fusion. Only the result window matters,
#: and a generous depth keeps the pass transparent to its own ordering.
_FUSION_DEPTH = 200
#: Weight of the term-coverage pass. It is a different question from "how often
#: does a term repeat", so it gets its own pass instead of a score tweak.
_COVERAGE_WEIGHT = 1.5
_COVERAGE_DEPTH = 6
#: Only a handful of pages print a primary statement, and they are the ones that
#: carry the numbers, so the facet pass looks at the densest of them first.
_STATEMENT_FACETS = (
    (
        r"operating margin|gross margin|margin|operating income|operating profit|operating loss|"
        r"net income|earnings|revenue|revenues|sales|profit|segment|segments|p&l|income statement|"
        r"ebitda|effective tax|per share|expense|expenses|cost|costs|growth|drag",
        (
            r"consolidated statements? of (income|operations|earnings|profit)",
            r"consolidated (income|earnings) statement",
            r"statements? of (income|operations|earnings)",
            r"consolidated statements? of comprehensive income",
        ),
    ),
    (
        r"cash flow|capex|capital expenditure|depreciation|amortization|liquidity|dividend",
        (r"consolidated statements? of cash flows?", r"consolidated cash flow statement"),
    ),
    (
        r"balance sheet|financial position|debt|liabilit|asset|assets|capital.intens|"
        r"current ratio|quick ratio|working capital|return on|roa|roe|inventory turn|leverage",
        (r"consolidated balance sheets?", r"consolidated statements? of financial position"),
    ),
)

_STATEMENT_PATTERN = re.compile(
    r"consolidated\s+(statement|balance|statements)\s+of\s+"
    r"(income|operation|earning|cash|financial|comprehensive|shareholder|stockholder|change)",
    re.IGNORECASE,
)


def _concept_index() -> dict[str, frozenset[str]]:
    """Flatten the lexicon into ``trigger token -> expansion tokens``."""

    index: dict[str, set[str]] = {}
    for triggers, expansions in CONCEPT_SOURCE.items():
        terms = {
            token
            for token in _tokenize(expansions)
            if token not in _STOPWORDS and token not in _INSTRUCTION_WORDS
        }
        if not terms:
            continue
        for trigger in triggers.split():
            index.setdefault(_stem(trigger), set()).update(terms)
    return {trigger: frozenset(terms) for trigger, terms in index.items()}


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


_CONCEPTS = _concept_index()


def _concept_terms(term: str) -> frozenset[str]:
    """Return the expansion for one question term.

    The lexicon is keyed by stemmed trigger words, but a stemmer cannot make
    ``retirees`` and ``retirement`` land on the same key, so a prefix match of at
    least four characters is accepted as well. Short words are excluded because
    a four-letter prefix is already the point where finance vocabulary stops
    being ambiguous.
    """

    exact = _CONCEPTS.get(term)
    if exact is not None:
        return exact
    if len(term) < 4:
        return frozenset()
    merged: set[str] = set()
    for trigger, terms in _CONCEPTS.items():
        if len(trigger) < 4:
            continue
        if trigger.startswith(term):
            merged |= terms
    return frozenset(merged)


def _expand(
    weights: dict[str, float],
    counters: Sequence[Counter] = (),
) -> dict[str, float]:
    """Add the accounting vocabulary that the question's concepts imply.

    The expansion never overrides a term the question already used: a question
    that says "revenue" keeps weight 1.0 even if "revenue" is also an expansion
    term for "gross".

    How hard a trigger pulls is scaled by how rare it is across the pages at
    hand. A stem such as ``operat`` is a verb in most questions and a margin
    term in a few; if nearly every page prints it, it cannot be what the
    question meant, so its expansion is scaled down instead of flooding the
    query with statements vocabulary and dragging every question onto the
    financial pages.
    """

    if not _CONCEPTS:
        return dict(weights)
    expanded = dict(weights)
    ceiling = _idf(1, max(len(counters), 1)) or 1.0
    for term, weight in weights.items():
        extras = _concept_terms(term)
        if not extras:
            continue
        reach = _CONCEPT_WEIGHT
        if counters:
            document_frequency = sum(1 for counter in counters if counter.get(term))
            if document_frequency:
                reach *= min(1.0, _idf(document_frequency, len(counters)) / ceiling)
        for extra in extras:
            expanded[extra] = max(expanded.get(extra, 0.0), reach * weight)
    return expanded


def _is_statement_page(title: str) -> bool:
    """True when the page prints one of the four primary statements."""

    lowered = title.lower()
    return bool(_STATEMENT_PATTERN.search(lowered)) or "consolidated balance sheet" in lowered


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


def _strip_document_ids(texts: Sequence[str]) -> list[str]:
    """Drop the leading document id line the text projection prepends.

    The projection writes ``DOCUMENT_ID\\nPAGE_TEXT``, so every page of a filing
    repeats the same id on its first line. Left in place it shifts the collection
    statistics and the heading of every page, which is enough to push a correct
    page out of the result window. Only a line that repeats and carries no space
    is removed: real page text almost never starts that way, and a single-page
    document keeps its text verbatim.
    """

    counts: Counter[str] = Counter()
    for text in texts:
        line = text.split("\n", 1)[0].strip()
        if line and not any(character.isspace() for character in line):
            counts[line] += 1
    repeated = {line for line, count in counts.items() if count > 1}
    if not repeated:
        return list(texts)
    stripped = []
    for text in texts:
        head, separator, tail = text.partition("\n")
        stripped.append(tail if separator and head.strip() in repeated else text)
    return stripped


def _numeric_density(text: str) -> float:
    """Share of tokens that are digits: primary statements are dense, prose is not."""

    tokens = _WORD_PATTERN.findall(text.lower())
    if not tokens:
        return 0.0
    return sum(token.isdigit() or token.replace(",", "").replace(".", "").isdigit() for token in tokens) / len(tokens)


def _coverage_order(
    weights: dict[str, float],
    bodies: Sequence[Counter],
    texts: Sequence[str],
) -> list[int]:
    """Order pages by how many distinct question terms they actually contain.

    Relevance is not only about how often a term repeats: the page that answers
    a question tends to touch more of its terms than the page that merely
    discusses one of them at length. Numeric density breaks the ties, because the
    terms of a metric question meet on a table more often than in prose.
    """

    keys = [term for term in weights if not term.isdigit()]
    if not keys:
        return []
    scored: list[tuple[float, int]] = []
    for index, counter in enumerate(bodies):
        covered = sum(1 for term in keys if counter.get(term))
        if covered:
            scored.append((covered / len(keys) * (1.0 + _numeric_density(texts[index])), index))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [index for _, index in scored]


def _statement_facets(question: str) -> tuple[tuple[str, ...], ...]:
    return tuple(patterns for trigger, patterns in _STATEMENT_FACETS if re.search(trigger, question, re.I))


def _facet_order(texts: Sequence[str], titles: Sequence[str], patterns: Sequence[str]) -> list[int]:
    """Order the pages that print the statement the question's metric implies."""

    selected: list[tuple[float, int]] = []
    for index, title in enumerate(titles):
        haystack = title.lower() or texts[index][:300].lower()
        if any(re.search(pattern, haystack) for pattern in patterns):
            selected.append((_numeric_density(texts[index]), index))
    selected.sort(key=lambda item: (-item[0], item[1]))
    return [index for _, index in selected]


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

    Four signals are combined, because no single one is enough on a 10-K: the
    page body, the section titles printed on the page, adjacency of query terms,
    and whether the page prints a primary financial statement. The body score
    dominates; the other three break the ties that a bag of words cannot.
    """

    fused, _, _ = _rank_parts(texts, question)
    return _ordered(fused)


def _rank_parts(
    texts: tuple[str, ...],
    question: str,
) -> tuple[dict[int, float], tuple[str, ...], list[str]]:
    """Return the fused score per entry together with the texts it was built from."""

    if not texts:
        return {}, (), []
        return []
    texts = tuple(_strip_document_ids(texts))
    bodies = [Counter(_tokenize(text)) for text in texts]
    weights = _expand(_query_weights(question), bodies)
    if not weights:
        return {}, texts, [_headings(text) for text in texts]

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
    scores = [
        body + _HEADING_WEIGHT * heading
        for body, heading in zip(scores, heading_scores, strict=True)
    ]

    pairs = _query_phrases(question)
    if pairs:
        page_pairs = [_bigrams(_tokenize(text)) for text in texts]
        every_pair = [pair for pairs_on_page in page_pairs for pair in pairs_on_page]
        pair_idf = [_idf(every_pair.count(pair), len(every_pair)) for pair in pairs]
        for index, pairs_on_page in enumerate(page_pairs):
            bonus = sum(
                weight
                for pair, weight in zip(pairs, pair_idf, strict=True)
                if pair in pairs_on_page
            )
            if bonus:
                scores[index] += _PHRASE_WEIGHT * bonus

    ordered = [(score, index) for index, score in enumerate(scores) if score > 0.0]
    if ordered and _STATEMENT_WEIGHT:
        bonus = _STATEMENT_WEIGHT * max(score for score, _ in ordered)
        ordered = [
            (score + bonus if _is_statement_page(titles[index]) else score, index)
            for score, index in ordered
        ]
    ordered.sort(key=lambda item: (-item[0], item[1]))

    # Every pass contributes through the position it reaches, so the wording
    # ranking and the statement passes stay comparable even though their score
    # scales differ. A single pass keeps its own order under this fusion.
    return _rank_scores(ordered, texts, titles, question, weights, bodies), texts, titles


def _rank_scores(
    ordered: list[tuple[float, int]],
    texts: Sequence[str],
    titles: Sequence[str],
    question: str,
    weights: dict[str, float] | None = None,
    bodies: Sequence[Counter] | None = None,
) -> dict[int, float]:
    fused: dict[int, float] = {}
    for rank, (_, index) in enumerate(ordered[:_FUSION_DEPTH], 1):
        fused[index] = 1.0 / (_FUSION_DAMPING + rank)
    for patterns in _statement_facets(question):
        for rank, index in enumerate(_facet_order(texts, titles, patterns)[:_FACET_DEPTH], 1):
            fused[index] = fused.get(index, 0.0) + _FACET_WEIGHT / (_FUSION_DAMPING + rank)
    if _COVERAGE_WEIGHT and weights and bodies is not None:
        for rank, index in enumerate(
            _coverage_order(weights, bodies, texts)[:_COVERAGE_DEPTH], 1
        ):
            fused[index] = fused.get(index, 0.0) + _COVERAGE_WEIGHT / (_FUSION_DAMPING + rank)
    return fused


def _ordered(fused: dict[int, float]) -> list[int]:
    # Ties fall back to page order, which keeps the result deterministic.
    return [index for index, _ in sorted(fused.items(), key=lambda item: (-item[1], item[0]))]


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

    fused, _, _ = _rank_parts(tuple(record.entry.text for record in records), query)

    citations: list[MemoryCitation] = []
    for index in _ordered(fused):
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
