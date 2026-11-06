"""Schemas for the book decomposition prototype.

A book becomes a tree (book → division → paragraph/table → sentence). Every extracted
claim cites the units it came from, and every unit ends with a recorded outcome, so
"was the whole book read?" is answerable from the data.

See docs/architecture/BOOK_DECOMPOSITION_PLAN.md.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class BookRecordType(StrEnum):
    """The kinds of progress stored for a book."""

    NODE = "node"
    TREE_META = "tree_meta"
    OUTCOME = "outcome"
    CHECK = "check"
    COVERAGE = "coverage"
    CLAIM = "claim"
    LEDGER = "ledger"
    REPORT = "report"
    GRAPH = "graph"
    DECISION = "decision"  # A person's accept or reject of a claim review held back.


class BookRecord(BaseModel):
    """One stored item of a book's progress. The key is unique within its document and type."""

    key: str
    data: dict[str, Any]


class BookNodeKind(StrEnum):
    """Node types in a decomposed book."""

    BOOK = "book"
    DIVISION = "division"  # A chapter/section from the PDF table of contents.
    PARAGRAPH = "paragraph"
    TABLE = "table"
    HEADING = "heading"
    FURNITURE = "furniture"  # Running headers, footers and page numbers.
    SENTENCE = "sentence"


class BookNode(BaseModel):
    """One node of the tree. `seq` is the global reading order within the book."""

    id: str
    doc_id: str
    kind: BookNodeKind
    parent_id: str | None = None
    seq: int
    text: str = ""
    page_start: int = Field(description="0-indexed first page")
    page_end: int = Field(description="0-indexed last page, inclusive")
    style: str | None = Field(None, description="Main font and color; used to spot example runs")


class DecompositionReport(BaseModel):
    """Measured completeness of a decomposition."""

    pages_total: int = 0
    pages_without_text: int = Field(0, description="Likely scans; their text needs OCR")
    image_blocks: int = 0
    toc_entries: int = 0
    toc_entries_located: int = Field(0, description="Entries whose title was found on its page")
    node_counts: dict[str, int] = Field(default_factory=dict)
    words_total: int = 0
    fragment_paragraphs: int = Field(
        0, description="Paragraphs of 3 words or fewer; a high count suggests broken tables"
    )
    alnum_extracted: int = Field(0, description="Alphanumeric characters on the PDF's pages")
    alnum_in_leaves: int = Field(0, description="Alphanumeric characters in the tree's leaves")
    alnum_in_paragraphs: int = 0
    alnum_in_sentences: int = 0
    alnum_overprint_removed: int = Field(
        0, description="Characters drawn twice at one spot, as in a shadow effect, and kept once"
    )

    @property
    def is_lossless(self) -> bool:
        """True when no extracted text was lost on the way into the tree."""
        return (
            self.alnum_extracted == self.alnum_in_leaves + self.alnum_overprint_removed
            and self.alnum_in_paragraphs == self.alnum_in_sentences
        )


class BookTree(BaseModel):
    """A fully decomposed book, nodes in reading order."""

    doc_id: str
    title: str
    decomposer_version: str
    content_hash: str
    nodes: list[BookNode]
    report: DecompositionReport


class AtomKind(StrEnum):
    """What a claim extracted from the book represents."""

    AXIOM = "axiom"  # A truth about how the world or game works.
    ENTITY = "entity"  # A named thing, or a type of thing.
    FACT = "fact"  # A specific event or state in the setting.
    RULE = "rule"  # A mechanic, procedure or number players apply.
    RELATIONSHIP = "relationship"  # A typed link between two named things.


class SkipReason(StrEnum):
    """Why a unit legitimately produced no atoms."""

    FLAVOR = "flavor"  # In-world fiction or mood that asserts nothing lasting.
    EXAMPLE = "example"  # An illustration of something stated elsewhere.
    NAVIGATION = "navigation"  # "See page 12", tables of contents, indexes.
    CREDITS = "credits"  # Authors, legal text, publisher notes.
    REPETITION = "repetition"  # Restates an earlier unit in this passage.
    OTHER = "other"


class ExtractedAtom(BaseModel):
    """One standalone claim, citing the labelled units that support it."""

    kind: AtomKind
    statement: str = Field(description="One self-contained claim; no unresolved pronouns")
    cites: list[str] = Field(description="Labels of the units supporting this claim, e.g. ['S3']")
    name: str | None = Field(None, description="Required for kind=entity")
    entity_type: str | None = Field(None, description="For kind=entity")
    subject: str | None = Field(None, description="Required for kind=relationship")
    predicate: str | None = Field(None, description="Required for kind=relationship")
    object: str | None = Field(None, description="Required for kind=relationship")
    confidence: float = Field(0.8, ge=0.0, le=1.0)


class UnitSkip(BaseModel):
    """An explicit decision that a unit yields no atoms."""

    label: str
    reason: SkipReason


class WindowExtraction(BaseModel):
    """The model's answer for one passage. Every unit must be cited or skipped."""

    atoms: list[ExtractedAtom] = Field(default_factory=list)
    skips: list[UnitSkip] = Field(default_factory=list)


class ClaimVerdict(StrEnum):
    """What checking a claim against its source text found."""

    SUPPORTED = "supported"
    CORRECTED = "corrected"  # Meaning was off or a condition was dropped; statement rewritten.
    EXAMPLE = "example"  # Comes from a worked example or sample play, not a general truth.
    FILLER = "filler"  # True but carries no usable information.
    UNSUPPORTED = "unsupported"  # The source doesn't say this.


class ClaimCheck(BaseModel):
    """The verifier's decision on one claim."""

    label: str
    verdict: ClaimVerdict
    corrected_statement: str | None = Field(None, description="Required when verdict=corrected")
    reason: str = ""


class VerificationBatch(BaseModel):
    """The verifier's answer. Must contain one check per claim."""

    checks: list[ClaimCheck] = Field(default_factory=list)


class StackRelation(StrEnum):
    """How a group of similar claims relate to each other."""

    SAME = "same"  # They state one claim; merge them.
    CONTRADICTION = "contradiction"  # They can't all be true.


class ClaimStack(BaseModel):
    """A group of claims from one cluster, with what to do about them."""

    labels: list[str]
    relation: StackRelation
    canonical_statement: str | None = Field(
        None, description="The merged claim, or the correct one if the sources settle a conflict"
    )
    settled_by_source: bool = Field(
        False, description="For contradictions: the quoted source text decides which is right"
    )
    wrong_labels: list[str] = Field(
        default_factory=list, description="For settled contradictions: claims the source refutes"
    )
    reason: str = ""


class StackDecision(BaseModel):
    """The adjudicator's answer for one cluster. Unlisted claims stay separate."""

    stacks: list[ClaimStack] = Field(default_factory=list)


class CoverageGap(BaseModel):
    """Something a paragraph says that none of its claims cover."""

    label: str
    kind: AtomKind = AtomKind.RULE
    missing: str = Field(description="What the claims leave out, as one standalone statement")
    quote: str = Field(description="The paragraph's exact words that say it")


class CoverageAudit(BaseModel):
    """The answer for a batch of paragraphs. Most paragraphs have no gaps."""

    gaps: list[CoverageGap] = Field(default_factory=list)


class ParagraphGap(BaseModel):
    """A verified gap, tied to its paragraph."""

    paragraph_id: str
    page: int
    kind: AtomKind = AtomKind.RULE
    missing: str
    quote: str


class SkipAudit(BaseModel):
    """Claims found in sentences the extractor skipped."""

    atoms: list[ExtractedAtom] = Field(default_factory=list)


class ClaimStatus(StrEnum):
    """The final outcome of one original claim. Every claim gets exactly one."""

    ACCEPTED = "accepted"
    CORRECTED = "corrected"
    MERGED = "merged"  # Folded into another claim, which inherits its citations.
    EXAMPLE = "example"  # Kept out of canon, retained and linked to its source.
    REJECTED = "rejected"
    NEEDS_HUMAN = "needs_human"


class LedgerEntry(BaseModel):
    """What happened to one original claim, and why."""

    claim_id: str
    kind: AtomKind
    original_statement: str
    status: ClaimStatus
    reason: str = ""
    canonical_id: str | None = Field(None, description="The reviewed claim this now lives in")
    source_node_ids: list[str] = Field(default_factory=list)
    page: int = 0
    # Older ledgers lack these. The statement then falls back to the original one.
    statement: str | None = Field(None, description="The wording after review, which can differ")
    name: str | None = None
    entity_type: str | None = None
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    conflicts_with: list[str] = Field(
        default_factory=list, description="For contradictions: the other claims in the conflict"
    )


class HeldClaimDecision(BaseModel):
    """A person's decision on a claim review sent to them.

    It's stored apart from the ledger, so running the review again can't undo it.
    """

    claim_id: str
    accepted: bool
    statement: str = Field(description="The wording accepted, or the wording when it was rejected")
    decided_at: datetime


class ReviewedClaim(BaseModel):
    """A claim that survived review, with the citations of everything merged into it."""

    id: str
    kind: AtomKind
    statement: str
    name: str | None = None
    entity_type: str | None = None
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    source_node_ids: list[str]
    pages: list[int]
    merged_from: list[str]
    domain: str = Field("lore", description="rules or lore; each gets its own tree and graph")
    paragraph_ids: list[str] = Field(default_factory=list)
    linked_claim_ids: list[str] = Field(
        default_factory=list, description="Claims from the same paragraphs; read them together"
    )
