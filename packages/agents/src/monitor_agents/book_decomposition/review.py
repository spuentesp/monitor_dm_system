"""Review extracted claims: verify, stack duplicates, settle conflicts, and miss nothing.

The ledger is the safety mechanism. Every original claim ends with exactly one recorded
status, and `check_ledger` proves it. A sentence whose only claims were all removed is
reported as orphaned, so a bad deletion can't quietly lose part of the book.

Examples are never deleted: they're kept out of canon and stay linked to their source.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import dspy
import structlog
from monitor_data.schemas.book_graph import (
    AtomKind,
    BookNode,
    BookNodeKind,
    BookTree,
    ClaimCheck,
    ClaimStack,
    ClaimStatus,
    ClaimVerdict,
    CoverageAudit,
    ExtractedAtom,
    LedgerEntry,
    ParagraphGap,
    ReviewedClaim,
    SkipAudit,
    StackDecision,
    StackRelation,
    VerificationBatch,
)
from pydantic import BaseModel, Field, ValidationError

from monitor_agents.book_prompts import apply_fiction_preamble
from monitor_agents.book_decomposition.checks import (
    ClaimFlag,
    check_names,
    check_numbers,
    closely_matches,
    source_states,
    combines_rules,
    describes_the_book,
    is_overstuffed,
    quote_is_in,
    unresolved_flags,
)
from monitor_agents.book_decomposition.extractor import run_metered
from monitor_agents.book_decomposition.pacing import RunGuard, RunStopped
from monitor_agents.book_decomposition.pipeline import ProvenancedAtom, WindowOutcome

log = structlog.get_logger()

DEFAULT_BATCH_SIZE = 12
DEFAULT_MAX_CLUSTER = 12
DEFAULT_CONCURRENCY = 8
_SIMILARITY_THRESHOLD = 0.5
_MIN_SHARED_TOKENS = 2
_QUANTITY = re.compile(r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b", re.IGNORECASE)
_MID_SENTENCE_NAME = re.compile(r"(?<=[a-z,] )[A-Z][a-z]{2,}\b")
_QUANTITY_OVERLAP = 2
_COVERAGE_BATCH = 8
_MAX_SIDEBAR_PAGES = 1
_MIN_NAME_USES = 3
_MAX_NAME_USE_OUTSIDE = 0.4
_MIN_LABELED = 2  # One labeled paragraph in a style could be a coincidence.
_LAYOUT_NOTE = (
    "NOTE: this source continues a worked example, though it has no label. Use verdict=example "
    "unless the claim would still be true and useful with every sample character and scene "
    "removed.\n"
)
_STOPWORDS = frozenset(
    "a an and are as at be by can for from has have if in is it its may must of on one or "
    "that the their they this to when which with you your".split()
)


@dataclass(frozen=True)
class Claim:
    """An extracted claim with a stable ID and its source paragraphs' text."""

    id: str
    atom: ExtractedAtom
    source_node_ids: tuple[str, ...]
    page: int
    source_text: str
    from_example_passage: bool
    example_by_layout: bool = False  # Only its layout marks it, as it has no "Example:" label.
    heading: str = ""
    flags: tuple[ClaimFlag, ...] = ()
    section_text: str = ""  # The whole section, where a name a claim resolved was given.
    cited_text: str = ""
    paragraph_ids: tuple[str, ...] = ()
    sample_names: frozenset[str] = frozenset()


def _claim_id(atom: ProvenancedAtom) -> str:
    source = "|".join([atom.atom.kind.value, atom.atom.statement, *atom.source_node_ids])
    return hashlib.sha256(source.encode()).hexdigest()[:16]


def _starts_example(text: str) -> bool:
    return text.lstrip("@•-– ").casefold().startswith(("example:", "example of", "for example:"))


def _nearest_headings(tree: BookTree) -> dict[str, str]:
    """Map each paragraph to the heading above it, within its division.

    A list can keep its meaning there: "CHALLENGING (DIFFICULTY 2)" above "Overcoming a complex
    lock" holds the number, and the bullet alone doesn't.
    """
    found: dict[str, str] = {}
    current = ""
    division: str | None = None
    for node in tree.nodes:
        if node.kind not in (BookNodeKind.HEADING, BookNodeKind.PARAGRAPH, BookNodeKind.TABLE):
            continue
        if node.parent_id != division:
            division = node.parent_id
            current = ""
        if node.kind == BookNodeKind.HEADING:
            current = node.text
        else:
            found[node.id] = current
    return found


def _heading_path(node: BookNode, by_id: dict[str, BookNode], nearest: dict[str, str]) -> str:
    parts: list[str] = []
    parent = by_id.get(node.parent_id or "")
    paragraph = parent if node.kind == BookNodeKind.SENTENCE and parent else node
    if nearest.get(paragraph.id):
        parts.append(nearest[paragraph.id])
    while parent is not None:
        if parent.kind == BookNodeKind.DIVISION:
            parts.append(parent.text)
        parent = by_id.get(parent.parent_id or "")
    return " > ".join(reversed(parts))


def example_continuations(tree: BookTree) -> set[str]:
    """Find unlabeled paragraphs that continue an example, from the book's own layout.

    A running example labels only its first paragraph, but books tend to set the whole passage
    in one style. So a paragraph counts when it directly follows a labeled example in the same
    style. A style can't mean "example" alone, because books reuse it for quotes and sidebars. The
    result is a hint for the verifier, which can still keep a general rule found in one.
    """
    words: Counter[str] = Counter()
    labeled_styles: Counter[str] = Counter()
    for node in tree.nodes:
        if node.kind == BookNodeKind.PARAGRAPH and node.style:
            words[node.style] += len(node.text.split())
            labeled_styles[node.style] += _starts_example(node.text)
    if not words:
        return set()
    body_style = words.most_common(1)[0][0]
    found: set[str] = set()
    run_style: str | None = None
    run_parent: str | None = None
    run_page = 0
    interrupted = False  # A heading or a new section passed, which usually ends a passage.
    sidebar_passed = False  # But a boxed sidebar can sit in the middle of an example.
    for node in tree.nodes:
        if node.kind in (BookNodeKind.SENTENCE, BookNodeKind.FURNITURE):
            continue
        if node.kind != BookNodeKind.PARAGRAPH:
            interrupted = True
        elif _starts_example(node.text):
            usable = node.style != body_style and labeled_styles[node.style or ""] >= _MIN_LABELED
            run_style = node.style if usable else None
            run_parent, run_page = node.parent_id, node.page_end
            interrupted = sidebar_passed = False
        elif run_style and node.style == run_style:
            same_place = node.parent_id == run_parent and not interrupted
            resumes = sidebar_passed and node.page_start - run_page <= _MAX_SIDEBAR_PAGES
            if same_place or resumes:
                found.add(node.id)
                run_parent, run_page = node.parent_id, node.page_end
                interrupted = sidebar_passed = False
            else:
                run_style = None
        elif node.style == body_style:
            run_style = None  # Back in the main text, so the example is over.
        else:
            sidebar_passed = True
    return found


def sample_character_names(tree: BookTree, continuations: set[str]) -> frozenset[str]:
    """Find names that belong to a book's worked examples, using how the book itself uses them.

    A name counts when it's never written in lowercase, as "The" is, and nearly always appears
    inside examples.
    """
    in_examples: Counter[str] = Counter()
    elsewhere: Counter[str] = Counter()
    lowercase: set[str] = set()
    for node in tree.nodes:
        if node.kind != BookNodeKind.PARAGRAPH:
            continue
        is_example = _starts_example(node.text) or node.id in continuations
        for word in re.findall(r"[A-Za-z]{3,}", node.text):
            if word[0].isupper() and word[1:].islower():
                (in_examples if is_example else elsewhere)[word] += 1
            elif word.islower():
                lowercase.add(word)
    return frozenset(
        name
        for name, count in in_examples.items()
        if count >= _MIN_NAME_USES
        and name.casefold() not in lowercase
        and elsewhere[name] <= count * _MAX_NAME_USE_OUTSIDE
    )


def build_claims(tree: BookTree, outcomes: Iterable[WindowOutcome]) -> list[Claim]:
    """Attach full source paragraphs to atoms in reading order, dropping exact repeats."""
    by_id = {node.id: node for node in tree.nodes}
    continuations = example_continuations(tree)
    sample_names = sample_character_names(tree, continuations)
    nearest = _nearest_headings(tree)
    sections: dict[str | None, list[str]] = defaultdict(list)
    for node in tree.nodes:
        if node.kind == BookNodeKind.PARAGRAPH:
            sections[node.parent_id].append(node.text)
    section_text = {parent: " ".join(texts) for parent, texts in sections.items()}
    claims: dict[str, Claim] = {}
    for outcome in outcomes:
        for item in outcome.atoms:
            claim_id = _claim_id(item)
            if claim_id in claims:
                continue
            paragraphs: dict[str, BookNode] = {}
            for node_id in item.source_node_ids:
                node = by_id[node_id]
                parent = by_id.get(node.parent_id or "")
                source = parent if parent and node.kind == BookNodeKind.SENTENCE else node
                paragraphs[source.id] = source
            labeled = any(_starts_example(p.text) for p in paragraphs.values())
            continues_example = any(p.id in continuations for p in paragraphs.values())
            source_text = "\n".join(p.text for p in paragraphs.values())
            heading = _heading_path(by_id[item.source_node_ids[0]], by_id, nearest)
            cited = " ".join(by_id[node_id].text for node_id in item.source_node_ids)
            flags = (*check_numbers(item.atom.statement, f"{source_text} {heading}"),)
            section = next(iter(paragraphs.values())).parent_id
            context = f"{source_text} {section_text.get(section, '')} {heading}"
            flags = (*flags, *check_names(item.atom.statement, context))
            claims[claim_id] = Claim(
                id=claim_id,
                atom=item.atom,
                source_node_ids=tuple(item.source_node_ids),
                page=item.page,
                source_text=source_text,
                from_example_passage=labeled or continues_example,
                example_by_layout=continues_example and not labeled,
                heading=heading,
                flags=flags,
                section_text=context,
                cited_text=cited,
                paragraph_ids=tuple(paragraphs),
                sample_names=sample_names,
            )
    seq = {node.id: node.seq for node in tree.nodes}
    return sorted(claims.values(), key=lambda c: seq[c.source_node_ids[0]])


def restrict_to_pages(tree: BookTree, outcomes: Iterable[WindowOutcome], first: int, last: int) -> list[WindowOutcome]:
    """Keep only the claims and sentences on these 1-indexed pages, to review a small part."""
    pages = {node.id: node.page_start + 1 for node in tree.nodes}

    def wanted(node_id: str) -> bool:
        return first <= pages.get(node_id, 0) <= last

    return [
        outcome.model_copy(
            update={
                "atoms": [a for a in outcome.atoms if first <= a.page + 1 <= last],
                "skipped": {n: why for n, why in outcome.skipped.items() if wanted(n)},
                "cited": [n for n in outcome.cited if wanted(n)],
                "uncovered": [n for n in outcome.uncovered if wanted(n)],
            }
        )
        for outcome in outcomes
    ]


# ---------------------------------------------------------------------------
# Clustering: find candidates cheaply; the LLM decides what they actually are.
# ---------------------------------------------------------------------------


def _tokens(claim: Claim) -> frozenset[str]:
    # Digits are left out so "at most 6" and "at most 8" land together as a possible conflict.
    words = re.findall(r"[a-z]+", claim.atom.statement.casefold())
    return frozenset(word for word in words if word not in _STOPWORDS)


def cluster_claims(claims: Sequence[Claim], max_cluster: int = DEFAULT_MAX_CLUSTER) -> list[list[Claim]]:
    """Group similar claims of one kind. Entities also group by name, whatever the wording."""
    parent = list(range(len(claims)))

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    tokens = [_tokens(claim) for claim in claims]
    names: dict[str, int] = {}
    for i, claim in enumerate(claims):
        name = (claim.atom.name or "").strip().casefold()
        if name:
            if name in names:
                parent[find(i)] = find(names[name])
            else:
                names[name] = i
        for j in range(i):
            shared = len(tokens[i] & tokens[j])
            union = len(tokens[i] | tokens[j])
            if shared >= _MIN_SHARED_TOKENS and union and shared / union >= _SIMILARITY_THRESHOLD:
                parent[find(i)] = find(j)

    groups: dict[int, list[Claim]] = defaultdict(list)
    for i, claim in enumerate(claims):
        groups[find(i)].append(claim)
    clusters: list[list[Claim]] = []
    for group in groups.values():
        for start in range(0, len(group), max_cluster):
            clusters.append(group[start : start + max_cluster])
    return clusters


def _quantity_groups(claims: Sequence[Claim]) -> dict[str, list[Claim]]:
    """Find the claims that give a number for each named game term."""
    # The book's own terms are whatever it capitalizes mid-sentence. They can open a sentence too.
    terms = {name.casefold() for claim in claims for name in _MID_SENTENCE_NAME.findall(claim.atom.statement)}
    by_term: dict[str, list[Claim]] = defaultdict(list)
    for claim in claims:
        if _QUANTITY.search(claim.atom.statement):
            for word in set(re.findall(r"[a-z]+", claim.atom.statement.casefold())) & terms:
                by_term[word].append(claim)
    return by_term


def _nearest_neighbor_order(group: Sequence[Claim]) -> list[Claim]:
    """Order claims so each is followed by the remaining claim most like it."""
    tokens = {claim.id: _tokens(claim) for claim in group}

    def likeness(first: Claim, second: Claim) -> float:
        union = tokens[first.id] | tokens[second.id]
        return len(tokens[first.id] & tokens[second.id]) / len(union) if union else 0.0

    remaining = list(group)
    ordered = [remaining.pop(0)]
    while remaining:
        following = max(remaining, key=lambda claim: likeness(ordered[-1], claim))
        remaining.remove(following)
        ordered.append(following)
    return ordered


def quantity_clusters(claims: Sequence[Claim], max_cluster: int = DEFAULT_MAX_CLUSTER) -> list[list[Claim]]:
    """Group claims that give a number for the same named game term.

    "The pool holds at most 6 Momentum" and "A group can never save more than 8 Momentum" share
    too few words for `cluster_claims`, yet they can't both be true. This only finds candidates:
    the LLM decides whether they conflict.

    A very common term won't fit in one call. Its claims are ordered so similar ones share a
    cluster, and neighboring clusters overlap. Other pairs still go uncompared, which
    `terms_not_fully_compared` reports.
    """
    clusters: list[list[Claim]] = []
    seen: set[frozenset[str]] = set()
    step = max(1, max_cluster - _QUANTITY_OVERLAP)
    for _, group in sorted(_quantity_groups(claims).items()):
        ordered = group if len(group) <= max_cluster else _nearest_neighbor_order(group)
        for start in range(0, max(1, len(ordered) - _QUANTITY_OVERLAP), step):
            chunk = ordered[start : start + max_cluster]
            ids = frozenset(claim.id for claim in chunk)
            if len(chunk) > 1 and ids not in seen:
                seen.add(ids)
                clusters.append(chunk)
    return clusters


def terms_not_fully_compared(claims: Sequence[Claim], max_cluster: int = DEFAULT_MAX_CLUSTER) -> list[str]:
    """Name the terms with too many numeric claims to compare every pair."""
    return sorted(term for term, group in _quantity_groups(claims).items() if len(group) > max_cluster)


# ---------------------------------------------------------------------------
# LLM steps
# ---------------------------------------------------------------------------


class ClaimVerificationSignature(dspy.Signature):  # type: ignore[misc]
    """Check claims extracted from a tabletop RPG or setting book against their source text.

    Return one check per claim label. Judge each claim only by its own source.

    Verdicts:
    - supported: the source says this, with all of its conditions and exceptions.
    - corrected: the claim is close, but the meaning is off, or it drops a condition,
      exception or limit that the source states. Put the fixed claim in corrected_statement.
      Preserve every number exactly. Example: "Knights may ride any horse" is corrected when
      the source adds "unless it is wounded".
    - example: it comes from a worked example or sample of play. It describes what one
      illustrative character did instead of something generally true. Named sample characters
      doing things in a rules explanation are the usual sign. A claim marked
      from_example_passage=true is nearly always this, unless it states a general rule.
    - filler: true but gives a reader nothing to use, or it has an unresolved reference
      ("Some days are better than others").
    - unsupported: the source doesn't say this.
    """

    claims: str = dspy.InputField(desc="Each claim with its label, kind, flags and source text")
    result: VerificationBatch = dspy.OutputField()


apply_fiction_preamble(ClaimVerificationSignature)


class ClaimStackingSignature(dspy.Signature):  # type: ignore[misc]
    """Decide how similar claims from one book relate. Most will simply be different claims.

    Return a stack only for claims that truly relate. Leave everything else out.

    - relation=same: they state one rule or fact in different words. canonical_statement must keep
      every condition and number from all of them, and add nothing else. Claims about different
      actions are different claims, even when they share a number or an effect, so never gather
      them into a list.
    - relation=contradiction: they can't all be true. Read the quoted sources:
      - If each claim is what its own source says, the book disagrees with itself: set
        settled_by_source=false, even if one source looks more detailed.
      - If a source shows that a claim misread it, set settled_by_source=true, list the
        misreadings in wrong_labels and give the correct canonical_statement.
      - If the book itself gives conflicting statements, or it could be a general rule and
        an exception, set settled_by_source=false. Never guess: a person will decide.

    Claims about different subjects that use similar wording are not related. A rule and its
    exception are two separate claims rather than a contradiction, unless they truly conflict.
    """

    claims: str = dspy.InputField(desc="Similar claims, each with its label and source text")
    result: StackDecision = dspy.OutputField()


apply_fiction_preamble(ClaimStackingSignature)


class SkipAuditSignature(dspy.Signature):  # type: ignore[misc]
    """Find usable claims an extractor missed in sentences it chose to skip.

    Each sentence has the reason it was skipped. Most skips are right, so return nothing for
    those. Return a claim only when a sentence states a lasting truth, rule or number a reader
    would need, and it isn't merely illustrating a sample character. Each claim cites its
    sentence label. Use only this text.

    Atom kinds: axiom, entity, fact, rule, relationship. An entity needs a name. A relationship
    needs subject, predicate and object.
    """

    sentences: str = dspy.InputField(desc="Skipped sentences with labels and skip reasons")
    result: SkipAudit = dspy.OutputField()


apply_fiction_preamble(SkipAuditSignature)


class ParagraphCoverageSignature(dspy.Signature):  # type: ignore[misc]
    """Find what each paragraph of a tabletop RPG book says that its claims leave out.

    Read all of a paragraph's claims together. Report a gap only for a distinct rule, fact, limit,
    number or definition that the paragraph states and none of the claims covers, even combined.
    Most paragraphs have no gaps, so report nothing for those.

    Don't report different wording, a detail that's only an illustration, mood or flavor, or a
    pointer to another section. Quote the paragraph's exact words for each gap.
    """

    paragraphs: str = dspy.InputField(desc="Each paragraph with its label and its claims")
    result: CoverageAudit = dspy.OutputField()


apply_fiction_preamble(ParagraphCoverageSignature)


class ReviewModel(Protocol):
    """The LLM calls review depends on. Tests supply a scripted version."""

    async def verify(self, prompt: str) -> VerificationBatch: ...

    async def stack(self, prompt: str) -> StackDecision: ...

    async def audit_skips(self, prompt: str) -> SkipAudit: ...

    async def find_gaps(self, prompt: str) -> CoverageAudit: ...


class DspyReviewModel:
    """Runs the review signatures through DSPy with a given LM."""

    def __init__(self, lm: Any, guard: RunGuard | None = None) -> None:
        self._lm = lm
        self._guard = guard
        self._verify = dspy.Predict(ClaimVerificationSignature)
        self._stack = dspy.Predict(ClaimStackingSignature)
        self._audit = dspy.Predict(SkipAuditSignature)
        self._gaps = dspy.Predict(ParagraphCoverageSignature)

    async def _run(self, module: Any, **kwargs: str) -> Any:
        usage = [0, 0]

        def call() -> Any:
            prediction, usage[0], usage[1] = run_metered(self._lm, lambda: module(**kwargs))
            return prediction.result

        async def make_call() -> Any:
            return await asyncio.to_thread(call)

        if self._guard is None:
            return await make_call()
        result = await self._guard.call(make_call)
        self._guard.record(usage[0], usage[1])
        return result

    async def verify(self, prompt: str) -> VerificationBatch:
        return VerificationBatch.model_validate(await self._run(self._verify, claims=prompt))

    async def stack(self, prompt: str) -> StackDecision:
        return StackDecision.model_validate(await self._run(self._stack, claims=prompt))

    async def audit_skips(self, prompt: str) -> SkipAudit:
        return SkipAudit.model_validate(await self._run(self._audit, sentences=prompt))

    async def find_gaps(self, prompt: str) -> CoverageAudit:
        return CoverageAudit.model_validate(await self._run(self._gaps, paragraphs=prompt))


def _claim_notes(claim: Claim) -> str:
    return _LAYOUT_NOTE if claim.example_by_layout else ""


def format_for_verification(batch: Sequence[Claim]) -> str:
    return "\n\n".join(
        f"[C{i}] kind={claim.atom.kind.value} from_example_passage="
        f"{str(claim.from_example_passage).lower()}\n"
        f"{_claim_notes(claim)}"
        f"CLAIM: {claim.atom.statement}\nHEADING: {claim.heading}\nSOURCE: {claim.source_text}"
        for i, claim in enumerate(batch, 1)
    )


def verification_fingerprint() -> str:
    """Identify the verification prompt and schema, so saved checks from another never apply."""
    source = ClaimVerificationSignature.instructions + json.dumps(ClaimCheck.model_json_schema(), sort_keys=True)
    return hashlib.sha256(source.encode()).hexdigest()[:12]


def _check_key(claim: Claim) -> str:
    """Name a saved check. Notes are part of what was asked, so new notes mean a new check."""
    notes = _claim_notes(claim)
    if not notes:
        return claim.id
    return f"{claim.id}:{hashlib.sha256(notes.encode()).hexdigest()[:8]}"


class CheckStore(Protocol):
    """Where finished verifier checks are kept. The review works with any backend."""

    def read(self) -> dict[str, ClaimCheck]: ...

    def append(self, checks: dict[str, ClaimCheck]) -> None: ...


class CheckLog:
    """Finished verification checks, saved per claim as they arrive.

    DSPy's cache matches a whole batch. New claims shift every later batch, which would pay for
    checks already done, so finished work is kept by claim instead. Append-only: a process killed
    mid-write leaves at most one torn line, which is ignored and redone.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> dict[str, ClaimCheck]:
        checks: dict[str, ClaimCheck] = {}
        if not self.path.exists():
            return checks
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                checks[row["claim_id"]] = ClaimCheck.model_validate(row["check"])
            except (ValueError, KeyError, TypeError, ValidationError):
                log.warning("check_log_torn_line", path=str(self.path))
        return checks

    def append(self, checks: dict[str, ClaimCheck]) -> None:
        if not checks:
            return
        with self.path.open("a", encoding="utf-8") as handle:
            for claim_id, check in checks.items():
                row = {"claim_id": claim_id, "check": check.model_dump(mode="json")}
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


async def verify_claims(
    claims: Sequence[Claim],
    model: ReviewModel,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    concurrency: int = DEFAULT_CONCURRENCY,
    on_checks: Callable[[dict[str, ClaimCheck]], None] | None = None,
) -> dict[str, ClaimCheck]:
    """Check claims against sources. A claim with no valid check stays out of the result.

    `on_checks` receives each batch's checks as soon as they arrive, so stopping loses none.
    """
    semaphore = asyncio.Semaphore(concurrency)

    async def run(batch: Sequence[Claim], attempts: int = 2) -> dict[str, ClaimCheck]:
        results: dict[str, ClaimCheck] = {}
        pending = list(batch)
        for _ in range(attempts):
            labels = {f"C{i}": claim for i, claim in enumerate(pending, 1)}
            fresh: dict[str, ClaimCheck] = {}
            try:
                async with semaphore:
                    answer = await model.verify(format_for_verification(pending))
            except RunStopped:
                raise
            # A failed batch leaves its claims unchecked, and they go to a person.
            except Exception as exc:  # noqa: BLE001  # reason: unchecked claims are routed to human review, never approved
                log.warning("claim_verification_failed", error=str(exc)[:300])
                continue
            for check in answer.checks:
                claim = labels.get(check.label)
                is_valid = check.verdict != ClaimVerdict.CORRECTED or bool(
                    check.corrected_statement and check.corrected_statement.strip()
                )
                if claim is not None and is_valid:
                    results[claim.id] = check
                    fresh[claim.id] = check
            if on_checks is not None:
                on_checks(fresh)
            pending = [claim for claim in pending if claim.id not in results]
            if not pending:
                break
        return results

    batches = [claims[i : i + batch_size] for i in range(0, len(claims), batch_size)]
    merged: dict[str, ClaimCheck] = {}
    for result in await asyncio.gather(*(run(batch) for batch in batches)):
        merged.update(result)
    return merged


def format_for_stacking(cluster: Sequence[Claim], statements: dict[str, str]) -> str:
    return "\n\n".join(
        f"[C{i}] CLAIM: {statements[claim.id]}\nHEADING: {claim.heading}\nSOURCE: {claim.source_text}"
        for i, claim in enumerate(cluster, 1)
    )


async def audit_skipped_units(
    tree: BookTree,
    outcomes: Iterable[WindowOutcome],
    model: ReviewModel,
    *,
    batch_size: int = 25,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> list[WindowOutcome]:
    """Re-read every skipped sentence and return any claims it should have produced."""
    by_id = {node.id: node for node in tree.nodes}
    skipped = [(nid, why) for outcome in outcomes for nid, why in outcome.skipped.items()]
    semaphore = asyncio.Semaphore(concurrency)

    async def run(batch: list[tuple[str, str]]) -> WindowOutcome:
        labels = {f"S{i}": nid for i, (nid, _) in enumerate(batch, 1)}
        prompt = "\n".join(f"[S{i}] (skipped as {why}) {by_id[nid].text}" for i, (nid, why) in enumerate(batch, 1))
        rescued = WindowOutcome(window_id=f"skip-audit:{batch[0][0]}")
        try:
            async with semaphore:
                answer = await model.audit_skips(prompt)
        except RunStopped:
            raise
        # The sentences keep their skip status, and the error is on the outcome.
        except Exception as exc:  # noqa: BLE001  # reason: recorded on the outcome and shown in the report
            log.warning("skip_audit_failed", error=str(exc)[:300])
            rescued.errors.append(f"{type(exc).__name__}: {exc}"[:300])
            rescued.uncovered = [nid for nid, _ in batch]
            return rescued
        for atom in answer.atoms:
            node_ids = [labels[label] for label in atom.cites if label in labels]
            if not node_ids or len(node_ids) != len(atom.cites):
                rescued.dropped_atoms += 1
                continue
            page = by_id[node_ids[0]].page_start
            rescued.atoms.append(ProvenancedAtom(atom=atom, source_node_ids=node_ids, page=page))
        return rescued

    batches = [skipped[i : i + batch_size] for i in range(0, len(skipped), batch_size)]
    return list(await asyncio.gather(*(run(batch) for batch in batches)))


# ---------------------------------------------------------------------------
# The ledger
# ---------------------------------------------------------------------------


@dataclass
class _Working:
    """Mutable state as a claim moves through review."""

    claim: Claim
    statement: str
    status: ClaimStatus
    reason: str = ""
    canonical: str | None = None
    conflicts_with: list[str] = field(default_factory=list)


class ReviewReport(BaseModel):
    """Outcome counts plus everything a person needs to look at."""

    claims_in: int = 0
    claims_out: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    by_kind_out: dict[str, int] = Field(default_factory=dict)
    contradictions_settled: int = 0
    contradictions_for_human: int = 0
    claims_unchecked: int = 0
    rescued_from_skips: int = 0
    skip_audit_failures: int = 0
    stacking_failures: int = 0
    paragraphs_audited: int = 0
    paragraph_gaps: list[ParagraphGap] = Field(
        default_factory=list, description="What paragraphs say that their claims leave out"
    )
    coverage_gaps_unverified: int = Field(0, description="Gaps dropped: quote not in the paragraph")
    coverage_check_failures: int = 0
    claims_from_gaps: int = Field(0, description="New claims made from verified paragraph gaps")
    coverage_reused: int = Field(0, description="Paragraphs whose saved check cost nothing")
    merges_refused: int = Field(0, description="Merges that would have combined separate rules")
    checks_reused: int = Field(0, description="Claims whose saved check cost nothing this run")
    terms_not_fully_compared: list[str] = Field(
        default_factory=list, description="Too many numeric claims to compare every pair"
    )
    sentences_never_extracted: list[str] = Field(
        default_factory=list, description="No outcome at extraction, so no claim could cover them"
    )
    sentences_not_rechecked: list[str] = Field(
        default_factory=list, description="Skipped sentences whose second look failed"
    )
    orphaned_sentences: list[str] = Field(
        default_factory=list, description="Sentences that were cited, but now support nothing"
    )
    ledger_problems: list[str] = Field(default_factory=list)


@dataclass
class ReviewResult:
    claims: list[ReviewedClaim] = field(default_factory=list)
    ledger: list[LedgerEntry] = field(default_factory=list)
    report: ReviewReport = field(default_factory=ReviewReport)


def paragraphs_to_audit(tree: BookTree, working: dict[str, _Working]) -> list[tuple[BookNode, list[str]]]:
    """Pair each paragraph that kept a claim with the statements covering it.

    Claims a person will decide count as coverage, and so do claims merged elsewhere, through the
    claim they became. Worked examples are left out, because they're not meant to be covered.
    """
    by_id = {node.id: node for node in tree.nodes}
    covers = (ClaimStatus.ACCEPTED, ClaimStatus.CORRECTED, ClaimStatus.NEEDS_HUMAN)
    statements: dict[str, dict[str, None]] = defaultdict(dict)
    examples: set[str] = set()
    for state in working.values():
        target = working.get(state.canonical or "") if state.status == ClaimStatus.MERGED else state
        if state.status == ClaimStatus.EXAMPLE or state.claim.from_example_passage:
            examples.update(state.claim.paragraph_ids)
        elif target is not None and target.status in covers:
            for paragraph_id in state.claim.paragraph_ids:
                statements[paragraph_id][target.statement] = None
    return [
        (by_id[paragraph_id], list(found)) for paragraph_id, found in statements.items() if paragraph_id not in examples
    ]


def format_for_coverage(batch: Sequence[tuple[BookNode, list[str]]]) -> str:
    return "\n\n".join(
        f"[P{i}] PARAGRAPH: {paragraph.text}\nCLAIMS:\n" + "\n".join(f"- {statement}" for statement in statements)
        for i, (paragraph, statements) in enumerate(batch, 1)
    )


class CoverageModel(Protocol):
    """Finds what paragraphs say that their claims leave out."""

    async def find_gaps(self, prompt: str) -> CoverageAudit: ...


class CoverageStore(Protocol):
    """Where finished paragraph checks are kept."""

    def read(self) -> dict[str, list[ParagraphGap]]: ...

    def append(self, finished: dict[str, list[ParagraphGap]]) -> None: ...


class CoverageLog:
    """Finished paragraph checks, saved as they arrive. A torn last line is ignored and redone."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @staticmethod
    def key(paragraph: BookNode, statements: Sequence[str]) -> str:
        source = "\n".join([paragraph.id, *sorted(statements)])
        return hashlib.sha256(source.encode()).hexdigest()[:16]

    def read(self) -> dict[str, list[ParagraphGap]]:
        saved: dict[str, list[ParagraphGap]] = {}
        if not self.path.exists():
            return saved
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                saved[row["key"]] = [ParagraphGap.model_validate(gap) for gap in row["gaps"]]
            except (ValueError, KeyError, TypeError, ValidationError):
                log.warning("coverage_log_torn_line", path=str(self.path))
        return saved

    def append(self, finished: dict[str, list[ParagraphGap]]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            for key, gaps in finished.items():
                row = {"key": key, "gaps": [gap.model_dump(mode="json") for gap in gaps]}
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())


def coverage_fingerprint() -> str:
    """Identify the coverage prompt, so saved checks from another prompt never apply."""
    return hashlib.sha256(ParagraphCoverageSignature.instructions.encode()).hexdigest()[:12]


async def audit_coverage(
    tree: BookTree,
    working: dict[str, _Working],
    model: CoverageModel,
    report: ReviewReport,
    *,
    batch_size: int = _COVERAGE_BATCH,
    concurrency: int = DEFAULT_CONCURRENCY,
    coverage_log: CoverageStore | None = None,
) -> None:
    """Ask what each paragraph says that all of its claims together don't.

    This only reports, for a person. A gap's quote must really be in the paragraph, so an invented
    gap is dropped and counted.
    """
    items = paragraphs_to_audit(tree, working)
    saved = coverage_log.read() if coverage_log else {}
    keys = {paragraph.id: CoverageLog.key(paragraph, found) for paragraph, found in items}
    report.paragraphs_audited = len(items)
    pending = []
    for paragraph, found in items:
        if keys[paragraph.id] in saved:
            report.coverage_reused += 1
            report.paragraph_gaps.extend(saved[keys[paragraph.id]])
        else:
            pending.append((paragraph, found))
    semaphore = asyncio.Semaphore(concurrency)

    async def run(batch: list[tuple[BookNode, list[str]]]) -> None:
        try:
            async with semaphore:
                answer = await model.find_gaps(format_for_coverage(batch))
        except RunStopped:
            raise
        except Exception as exc:  # noqa: BLE001  # reason: counted in the report, so the gap in checking is visible
            log.warning("coverage_audit_failed", error=str(exc)[:300])
            report.coverage_check_failures += 1
            return
        labels = {f"P{i}": paragraph for i, (paragraph, _) in enumerate(batch, 1)}
        finished: dict[str, list[ParagraphGap]] = {keys[p.id]: [] for p, _ in batch}
        for gap in answer.gaps:
            paragraph = labels.get(gap.label)
            if paragraph is None or not quote_is_in(gap.quote, paragraph.text):
                report.coverage_gaps_unverified += 1
                continue
            found_gap = ParagraphGap(
                paragraph_id=paragraph.id,
                page=paragraph.page_start,
                kind=gap.kind,
                missing=gap.missing,
                quote=gap.quote,
            )
            finished[keys[paragraph.id]].append(found_gap)
            report.paragraph_gaps.append(found_gap)
        if coverage_log:
            coverage_log.append(finished)

    batches = [pending[i : i + batch_size] for i in range(0, len(pending), batch_size)]
    # Let calls in progress finish when one stops the run, so answers already paid for are saved.
    outcomes = await asyncio.gather(*(run(batch) for batch in batches), return_exceptions=True)
    for outcome in outcomes:
        if isinstance(outcome, BaseException):
            raise outcome
    report.paragraph_gaps.sort(key=lambda gap: gap.page)


def claims_from_gaps(tree: BookTree, gaps: Sequence[ParagraphGap]) -> list[Claim]:
    """Turn verified gaps into claims, citing the sentences that hold each quote."""
    by_id = {node.id: node for node in tree.nodes}
    sentences: dict[str, list[BookNode]] = defaultdict(list)
    for node in tree.nodes:
        if node.kind == BookNodeKind.SENTENCE and node.parent_id:
            sentences[node.parent_id].append(node)
    nearest = _nearest_headings(tree)
    claims: dict[str, Claim] = {}
    for gap in gaps:
        if describes_the_book(gap.missing):
            continue
        paragraph = by_id[gap.paragraph_id]
        children = sentences[paragraph.id]
        holding = [s for s in children if quote_is_in(s.text, gap.quote)]
        cited = holding or [s for s in children if quote_is_in(gap.quote, s.text)] or children
        kind = gap.kind if gap.kind in (AtomKind.RULE, AtomKind.AXIOM, AtomKind.FACT) else AtomKind.FACT
        atom = ExtractedAtom(kind=kind, statement=gap.missing, cites=[], confidence=0.5)
        source_ids = tuple(s.id for s in cited) or (paragraph.id,)
        item = ProvenancedAtom(atom=atom, source_node_ids=list(source_ids), page=gap.page)
        heading = _heading_path(paragraph, by_id, nearest)
        claim_id = _claim_id(item)
        claims[claim_id] = Claim(
            id=claim_id,
            atom=atom,
            source_node_ids=source_ids,
            page=gap.page,
            source_text=paragraph.text,
            from_example_passage=False,
            heading=heading,
            section_text=f"{paragraph.text} {heading}",
            cited_text=" ".join(s.text for s in cited),
            paragraph_ids=(paragraph.id,),
        )
    return list(claims.values())


def _kept(claim: Claim, statement: str, status: ClaimStatus, reason: str) -> _Working:
    """Keep a claim, unless it still states a number or name that its source doesn't have.

    A model's approval can't outrank this, and neither can its correction. So a person decides.
    """
    if describes_the_book(statement):
        return _Working(claim, statement, ClaimStatus.REJECTED, "filler: describes the book, not the game")
    source = f"{claim.source_text} {claim.heading}"
    doubts = unresolved_flags(statement, source, claim.section_text or source)
    if doubts:
        details = ", ".join(item.detail for item in doubts)
        return _Working(claim, statement, ClaimStatus.NEEDS_HUMAN, f"Not in the source: {details}. {reason}")
    names = set(re.findall(r"[A-Za-z]{3,}", statement)) & claim.sample_names
    if names:
        return _Working(
            claim,
            statement,
            ClaimStatus.NEEDS_HUMAN,
            f"Names a sample character from the book's examples: {', '.join(sorted(names))}. {reason}",
        )
    if is_overstuffed(claim.atom.statement, statement):
        return _Working(
            claim,
            statement,
            ClaimStatus.NEEDS_HUMAN,
            f"The correction adds far more than it fixes, so it may combine rules. {reason}",
        )
    return _Working(claim, statement, status, "" if status == ClaimStatus.ACCEPTED else reason)


def _apply_checks(claims: Sequence[Claim], checks: dict[str, ClaimCheck]) -> dict[str, _Working]:
    working: dict[str, _Working] = {}
    for claim in claims:
        check = checks.get(claim.id)
        if check is None:
            working[claim.id] = _Working(
                claim, claim.atom.statement, ClaimStatus.NEEDS_HUMAN, "Verification didn't complete"
            )
        elif check.verdict == ClaimVerdict.SUPPORTED:
            working[claim.id] = _kept(claim, claim.atom.statement, ClaimStatus.ACCEPTED, check.reason)
        elif check.verdict == ClaimVerdict.CORRECTED:
            working[claim.id] = _kept(
                claim, str(check.corrected_statement).strip(), ClaimStatus.CORRECTED, check.reason
            )
        elif check.verdict == ClaimVerdict.EXAMPLE:
            working[claim.id] = _Working(claim, claim.atom.statement, ClaimStatus.EXAMPLE, check.reason)
        else:
            # A model rejecting close to the source's own words is more likely wrong than the claim.
            status = (
                ClaimStatus.NEEDS_HUMAN
                if closely_matches(claim.atom.statement, claim.cited_text)
                else ClaimStatus.REJECTED
            )
            working[claim.id] = _Working(claim, claim.atom.statement, status, f"{check.verdict.value}: {check.reason}")
    return working


def _apply_stack(
    stack: ClaimStack, cluster: Sequence[Claim], working: dict[str, _Working], report: ReviewReport
) -> None:
    labels = {f"C{i}": claim for i, claim in enumerate(cluster, 1)}
    members = [labels[label] for label in dict.fromkeys(stack.labels) if label in labels]
    # A claim can sit in more than one cluster. One already settled elsewhere stays settled.
    active = (ClaimStatus.ACCEPTED, ClaimStatus.CORRECTED)
    members = [member for member in members if working[member.id].status in active]
    if len(members) < 2:
        return
    if stack.relation == StackRelation.SAME:
        keeper = members[0]
        canonical = (stack.canonical_statement or "").strip()
        longest = max((working[m.id].statement for m in members), key=lambda s: len(s.split()))
        if canonical and combines_rules(longest, canonical):
            report.merges_refused += 1
            return
        if stack.canonical_statement and stack.canonical_statement.strip():
            working[keeper.id].statement = stack.canonical_statement.strip()
        for other in members[1:]:
            state = working[other.id]
            state.status = ClaimStatus.MERGED
            state.canonical = keeper.id
            state.reason = stack.reason
        return
    wrong = {labels[label].id for label in stack.wrong_labels if label in labels}
    right = [member for member in members if member.id not in wrong]
    # When the book states both versions, it disagrees with itself, and a person has to decide.
    book_states_both = any(source_states(m.atom.statement, m.cited_text) for m in members if m.id in wrong)
    if stack.settled_by_source and wrong and right and stack.canonical_statement and not book_states_both:
        report.contradictions_settled += 1
        working[right[0].id].statement = stack.canonical_statement.strip()
        for member in members:
            if member.id in wrong:
                working[member.id].status = ClaimStatus.REJECTED
                working[member.id].reason = f"Refuted by source: {stack.reason}"
        return
    report.contradictions_for_human += 1
    for member in members:
        working[member.id].status = ClaimStatus.NEEDS_HUMAN
        working[member.id].reason = f"Unresolved contradiction: {stack.reason}"
        working[member.id].conflicts_with = [other.id for other in members if other.id != member.id]


async def stack_claims(
    working: dict[str, _Working],
    model: ReviewModel,
    report: ReviewReport,
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
) -> None:
    """Within each kind, cluster the surviving claims and merge or flag related ones."""
    survivors: dict[AtomKind, list[Claim]] = defaultdict(list)
    for state in working.values():
        if state.status in (ClaimStatus.ACCEPTED, ClaimStatus.CORRECTED):
            survivors[state.claim.atom.kind].append(state.claim)
    report.terms_not_fully_compared = sorted(
        {term for claims in survivors.values() for term in terms_not_fully_compared(claims)}
    )

    clusters: list[list[Claim]] = []
    covered: list[frozenset[str]] = []
    for claims in survivors.values():
        for cluster in cluster_claims(claims):
            if len(cluster) > 1:
                clusters.append(cluster)
                covered.append(frozenset(claim.id for claim in cluster))
        for cluster in quantity_clusters(claims):
            ids = frozenset(claim.id for claim in cluster)
            if not any(ids <= other for other in covered):
                clusters.append(cluster)
    statements = {claim_id: state.statement for claim_id, state in working.items()}
    semaphore = asyncio.Semaphore(concurrency)

    async def run(cluster: list[Claim]) -> tuple[list[Claim], StackDecision | None]:
        try:
            async with semaphore:
                return cluster, await model.stack(format_for_stacking(cluster, statements))
        except RunStopped:
            raise
        # Nothing is merged, and a person checks them, since a contradiction may have gone unseen.
        except Exception as exc:  # noqa: BLE001  # reason: counted in the report; claims stay unmerged rather than lost
            log.warning("claim_stacking_failed", error=str(exc)[:300])
            return cluster, None

    for cluster, decision in await asyncio.gather(*(run(c) for c in clusters)):
        if decision is None:
            report.stacking_failures += 1
            for claim in cluster:
                state = working[claim.id]
                if state.status in (ClaimStatus.ACCEPTED, ClaimStatus.CORRECTED):
                    state.status = ClaimStatus.NEEDS_HUMAN
                    state.reason = "Duplicate and contradiction check didn't complete"
            continue
        for stack in decision.stacks:
            _apply_stack(stack, cluster, working, report)


def _finalize(working: dict[str, _Working], report: ReviewReport) -> ReviewResult:
    result = ReviewResult(report=report)
    merged_into: dict[str, list[_Working]] = defaultdict(list)
    for state in working.values():
        if state.status == ClaimStatus.MERGED and state.canonical:
            merged_into[state.canonical].append(state)

    # Follow merge chains, so a claim merged into a later-rejected claim isn't stranded.
    for state in working.values():
        if state.status not in (ClaimStatus.ACCEPTED, ClaimStatus.CORRECTED):
            continue
        members = [state, *merged_into.get(state.claim.id, [])]
        for member in members[1:]:
            member.canonical = state.claim.id
        atom = state.claim.atom
        result.claims.append(
            ReviewedClaim(
                id=state.claim.id,
                kind=atom.kind,
                statement=state.statement,
                name=atom.name,
                entity_type=atom.entity_type,
                subject=atom.subject,
                predicate=atom.predicate,
                object=atom.object,
                source_node_ids=list(dict.fromkeys(n for m in members for n in m.claim.source_node_ids)),
                pages=sorted({m.claim.page for m in members}),
                merged_from=[m.claim.id for m in members[1:]],
                domain="rules" if atom.kind == AtomKind.RULE else "lore",
                paragraph_ids=list(dict.fromkeys(p for m in members for p in m.claim.paragraph_ids)),
            )
        )
    _link_claims(result.claims)
    for state in working.values():
        target = working.get(state.canonical or "")
        needs_rescue = state.status == ClaimStatus.MERGED and (
            target is None or target.status not in (ClaimStatus.ACCEPTED, ClaimStatus.CORRECTED)
        )
        if needs_rescue:
            # What it merged into was removed afterward, so a person must decide.
            state.status = ClaimStatus.NEEDS_HUMAN
            state.reason = "Merged into a claim that was later removed"
            state.canonical = None
        result.ledger.append(
            LedgerEntry(
                claim_id=state.claim.id,
                kind=state.claim.atom.kind,
                original_statement=state.claim.atom.statement,
                status=state.status,
                reason=state.reason,
                canonical_id=state.canonical,
                source_node_ids=list(state.claim.source_node_ids),
                page=state.claim.page,
                statement=state.statement,
                name=state.claim.atom.name,
                entity_type=state.claim.atom.entity_type,
                subject=state.claim.atom.subject,
                predicate=state.claim.atom.predicate,
                object=state.claim.atom.object,
                conflicts_with=state.conflicts_with,
            )
        )
    report.claims_in = len(working)
    report.claims_out = len(result.claims)
    report.by_status = dict(Counter(entry.status.value for entry in result.ledger))
    report.by_kind_out = dict(Counter(claim.kind.value for claim in result.claims))
    report.claims_unchecked = sum(state.reason == "Verification didn't complete" for state in working.values())
    report.orphaned_sentences = _orphaned_sentences(result)
    report.ledger_problems = check_ledger(result, set(working))
    return result


def _link_claims(claims: Sequence[ReviewedClaim]) -> None:
    """Link claims from the same paragraph. A limit can sit in the next claim, not in this one."""
    in_paragraph: dict[str, list[str]] = defaultdict(list)
    for claim in claims:
        for paragraph_id in claim.paragraph_ids:
            in_paragraph[paragraph_id].append(claim.id)
    for claim in claims:
        linked = (i for p in claim.paragraph_ids for i in in_paragraph[p] if i != claim.id)
        claim.linked_claim_ids = list(dict.fromkeys(linked))


def _orphaned_sentences(result: ReviewResult) -> list[str]:
    """Find sentences that were cited, but support no accepted claim, example or open item."""
    cited = {node for entry in result.ledger for node in entry.source_node_ids}
    live = {node for claim in result.claims for node in claim.source_node_ids}
    for entry in result.ledger:
        if entry.status in (ClaimStatus.EXAMPLE, ClaimStatus.NEEDS_HUMAN):
            live.update(entry.source_node_ids)
    return sorted(cited - live)


def check_ledger(result: ReviewResult, expected_ids: set[str]) -> list[str]:
    """Prove the review lost nothing. Returns a description of each violation."""
    problems: list[str] = []
    ids = [entry.claim_id for entry in result.ledger]
    if len(ids) != len(set(ids)):
        problems.append("A claim appears in the ledger more than once")
    if missing := expected_ids - set(ids):
        problems.append(f"{len(missing)} claims have no ledger entry")
    claim_ids = {claim.id for claim in result.claims}
    for entry in result.ledger:
        if entry.status == ClaimStatus.MERGED and entry.canonical_id not in claim_ids:
            problems.append(f"Claim {entry.claim_id} merged into a missing claim")
        if entry.status in (ClaimStatus.ACCEPTED, ClaimStatus.CORRECTED):
            if entry.claim_id not in claim_ids:
                problems.append(f"Accepted claim {entry.claim_id} isn't in the output")
    citations = {node for claim in result.claims for node in claim.source_node_ids}
    for entry in result.ledger:
        if entry.status == ClaimStatus.MERGED and not set(entry.source_node_ids) <= citations:
            problems.append(f"Merged claim {entry.claim_id} lost its citations")
    return problems


async def review_claims(
    tree: BookTree,
    outcomes: Sequence[WindowOutcome],
    model: ReviewModel,
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
    check_log: CheckStore | None = None,
    check_coverage: bool = True,
    coverage_model: CoverageModel | None = None,
    coverage_batch_size: int = _COVERAGE_BATCH,
    coverage_log: CoverageStore | None = None,
) -> ReviewResult:
    """Run the full review: audit skips, verify every claim, stack, then build the ledger."""
    report = ReviewReport()
    rescued = await audit_skipped_units(tree, outcomes, model, concurrency=concurrency)
    report.rescued_from_skips = sum(len(item.atoms) for item in rescued)
    report.skip_audit_failures = sum(bool(item.errors) for item in rescued)
    report.sentences_not_rechecked = sorted({nid for item in rescued for nid in item.uncovered})
    accounted = {nid for outcome in outcomes for nid in [*outcome.cited, *outcome.skipped]}
    report.sentences_never_extracted = sorted({nid for outcome in outcomes for nid in outcome.uncovered} - accounted)
    claims = build_claims(tree, [*outcomes, *rescued])
    saved = check_log.read() if check_log else {}
    # A check made before layout flagged a claim saw different input, so it can't be reused.
    keys = {claim.id: _check_key(claim) for claim in claims}
    reused = {claim.id: saved[keys[claim.id]] for claim in claims if keys[claim.id] in saved}
    report.checks_reused = len(reused)
    checks = await verify_claims(
        [claim for claim in claims if claim.id not in reused],
        model,
        concurrency=concurrency,
        on_checks=((lambda fresh: check_log.append({keys[cid]: c for cid, c in fresh.items()})) if check_log else None),
    )
    checks.update(reused)
    working = _apply_checks(claims, checks)
    await stack_claims(working, model, report, concurrency=concurrency)
    if check_coverage:
        await audit_coverage(
            tree,
            working,
            coverage_model or model,
            report,
            batch_size=coverage_batch_size,
            concurrency=concurrency,
            coverage_log=coverage_log,
        )
        new_claims = [c for c in claims_from_gaps(tree, report.paragraph_gaps) if c.id not in working]
        # A gap is one model's reading, so it goes through the same verifier as any other claim.
        for claim in new_claims:
            keys[claim.id] = _check_key(claim)
        known = {c.id: saved[keys[c.id]] for c in new_claims if keys[c.id] in saved}
        fresh = await verify_claims(
            [c for c in new_claims if c.id not in known],
            model,
            concurrency=concurrency,
            on_checks=(
                (lambda found: check_log.append({keys[cid]: c for cid, c in found.items()})) if check_log else None
            ),
        )
        working.update(_apply_checks(new_claims, {**known, **fresh}))
        report.claims_from_gaps = len(new_claims)
    return _finalize(working, report)
