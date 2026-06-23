"""
Canon contradiction detection (EPIC 2).

LAYER: 1 (data-layer)

Before a KnowledgePack is applied to a multiverse, this module compares
its extracted items against the existing canon stored in Neo4j/MongoDB.
It detects semantic contradictions where a new statement directly opposes
an already-committed canonical fact or axiom.

Detection strategies:
  1. NEGATION_PATTERN — Lexical heuristics: "X is NOT Y" vs "X is Y"
  2. OPPOSITE_TERMS   — Known antonym pairs: mortal/immortal, alive/dead, etc.
  3. FUZZY_SIMILARITY — Levenshtein ratio on statements (same subject, different predicate)

The module is designed to run AFTER deduplication but BEFORE canon application.
It produces a ContradictionResult that the UI can present to the user for
resolution before the ProposedChanges are committed.

Usage::

    from monitor_data.tools.ingest_tools.contradiction_detection import detect_contradictions
    from monitor_data.tools.ingest_tools.delta_detection import _levenshtein_ratio

    result = detect_contradictions(
        new_pack=pack_response,
        canon_axioms=[{"statement": "Elves are immortal", ...}],
        canon_facts=[{"statement": "The Sundering happened 1000 years ago", ...}],
        multiverse_id=multiverse_id,
    )
    if result.high_severity_count > 0:
        # Present to user for resolution before applying
        ...
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from monitor_data.schemas.contradiction import (
    ContradictionFact,
    ContradictionMatch,
    ContradictionResolution,
    ContradictionResult,
    ContradictionSeverity,
    ContradictionType,
)
from monitor_data.schemas.knowledge_packs import (
    ExtractedAxiom,
    ExtractedLoreFact,
    KnowledgePackResponse,
)
from monitor_data.tools._shared import levenshtein_ratio as _levenshtein_ratio

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Negation patterns — pairs of (positive, negative) word patterns
# ---------------------------------------------------------------------------

_NEGATION_PREFIXES = (
    "not ",
    "is not ",
    "are not ",
    "does not ",
    "cannot ",
    "never ",
    "no longer ",
    "ceased to ",
    "fail to ",
)
_OPPOSITE_PAIRS: List[tuple[str, str]] = [
    ("mortal", "immortal"),
    ("alive", "dead"),
    ("mortal", "undying"),
    ("finite", "infinite"),
    ("mortal", "deathless"),
    ("true", "false"),
    ("real", "fake"),
    ("real", "illusory"),
    ("good", "evil"),
    ("light", "dark"),
    ("lawful", "chaotic"),
    ("permanent", "temporary"),
    ("immutable", "mutable"),
    ("visible", "invisible"),
    ("possible", "impossible"),
    ("legal", "illegal"),
    ("banned", "permitted"),
    ("forbidden", "allowed"),
    ("destroyed", "intact"),
    ("extinct", "thriving"),
    ("at war", "at peace"),
    ("allied", "enemy"),
    ("friendly", "hostile"),
    ("open", "closed"),
    ("locked", "unlocked"),
    ("active", "dormant"),
    ("present", "absent"),
    ("required", "optional"),
    ("mandatory", "voluntary"),
    ("known", "unknown"),
    ("revealed", "hidden"),
    ("stolen", "returned"),
    ("lost", "found"),
    ("winner", "loser"),
    ("victory", "defeat"),
    ("success", "failure"),
]

# Similarity threshold — above this, two statements with the same subject
# but different content are flagged as potential contradictions.
_SIMILARITY_THRESHOLD = 0.65
# Higher threshold for strong contradiction confidence
_HIGH_SIMILARITY_THRESHOLD = 0.80


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def detect_contradictions(
    new_pack: KnowledgePackResponse,
    canon_axioms: Sequence[Dict[str, Any]],
    canon_facts: Sequence[Dict[str, Any]],
    multiverse_id: Optional[UUID] = None,
    universe_id: Optional[UUID] = None,
) -> ContradictionResult:
    """
    Check a KnowledgePack's extracted items against existing canon.

    Args:
        new_pack: The KnowledgePack being applied.
        canon_axioms: Existing axiom dicts from Neo4j (must have 'statement').
        canon_facts: Existing fact dicts from Neo4j/MongoDB (must have 'statement').
        multiverse_id: Target multiverse for provenance.
        universe_id: Target universe for provenance.

    Returns:
        ContradictionResult with all detected contradictions.
    """
    axiom_matches = _check_axioms(new_pack.axioms, canon_axioms)
    lore_matches = _check_lore_facts(new_pack.lore_facts, canon_facts)
    entity_matches = _check_entity_names(new_pack, canon_facts)

    result = ContradictionResult(
        checked_against_multiverse=multiverse_id,
        checked_against_universe=universe_id,
        axiom_contradictions=axiom_matches,
        lore_contradictions=lore_matches,
        entity_contradictions=entity_matches,
    )
    result.compute_totals()
    return result


# ---------------------------------------------------------------------------
# Axiom contradiction checks
# ---------------------------------------------------------------------------


def _check_axioms(
    new_axioms: Sequence[ExtractedAxiom],
    canon_axioms: Sequence[Dict[str, Any]],
) -> List[ContradictionMatch]:
    """Check new axioms against existing canonical axioms."""
    matches: List[ContradictionMatch] = []

    for idx, axiom in enumerate(new_axioms):
        for canon_idx, canon in enumerate(canon_axioms):
            canon_stmt = canon.get("statement", "")
            if not canon_stmt:
                continue

            match = _compare_statements(
                new_statement=axiom.statement,
                existing_statement=canon_stmt,
                new_source=axiom.source_ref,
                existing_source=canon.get("source_ref"),
                existing_canon_level=canon.get("canon_level", "canon"),
                category="axioms",
                item_index=idx,
            )
            if match is not None:
                match.new_fact.fact_type = "axiom"
                match.existing_fact.fact_type = "axiom"
                # Axiom contradictions are always at least HIGH severity
                if match.severity == ContradictionSeverity.MEDIUM:
                    match.severity = ContradictionSeverity.HIGH
                matches.append(match)

    return matches


# ---------------------------------------------------------------------------
# Lore fact contradiction checks
# ---------------------------------------------------------------------------


def _check_lore_facts(
    new_facts: Sequence[ExtractedLoreFact],
    canon_facts: Sequence[Dict[str, Any]],
) -> List[ContradictionMatch]:
    """Check new lore facts against existing canonical facts."""
    matches: List[ContradictionMatch] = []

    for idx, fact in enumerate(new_facts):
        # Skip rumors and character beliefs — they are expected to contradict
        knowledge_scope = getattr(fact, "knowledge_scope", None)
        if knowledge_scope and knowledge_scope.value != "world":
            continue

        for canon_idx, canon in enumerate(canon_facts):
            canon_stmt = canon.get("statement", "")
            if not canon_stmt:
                continue

            match = _compare_statements(
                new_statement=fact.statement,
                existing_statement=canon_stmt,
                new_source=fact.source_ref,
                existing_source=canon.get("source_ref"),
                existing_canon_level=canon.get("canon_level", "canon"),
                category="lore_facts",
                item_index=idx,
            )
            if match is not None:
                matches.append(match)

    return matches


# ---------------------------------------------------------------------------
# Entity name contradiction checks (entity_archetypes vs canon facts)
# ---------------------------------------------------------------------------


def _check_entity_names(
    new_pack: KnowledgePackResponse,
    canon_facts: Sequence[Dict[str, Any]],
) -> List[ContradictionMatch]:
    """Check if entity descriptions contradict established canon about those entities."""
    matches: List[ContradictionMatch] = []

    for idx, entity in enumerate(new_pack.entity_archetypes):
        entity_name_lower = entity.name.lower()
        relevant_facts = [
            f for f in canon_facts if entity_name_lower in f.get("statement", "").lower()
        ]
        # Only flag if the entity description directly opposes a canon fact
        for canon in relevant_facts:
            canon_stmt = canon.get("statement", "")
            similarity = _levenshtein_ratio(entity.description.lower(), canon_stmt.lower())
            if similarity < _SIMILARITY_THRESHOLD:
                # Very different statements about the same entity — could be a contradiction
                has_negation = _has_negation_conflict(entity.description, canon_stmt)
                if has_negation:
                    severity = ContradictionSeverity.MEDIUM
                    ctype = ContradictionType.SEMANTIC_OPPOSITE
                else:
                    continue  # Not clearly contradictory, just different info

                matches.append(
                    ContradictionMatch(
                        contradiction_id=f"contra:entities:{idx}:{canon.get('id', 'unknown')}",
                        contradiction_type=ctype,
                        severity=severity,
                        new_fact=ContradictionFact(
                            statement=entity.description[:2000],
                            source_name=entity.source_ref,
                            canon_level="proposed",
                            confidence=entity.confidence,
                            fact_type="entity",
                        ),
                        existing_fact=ContradictionFact(
                            statement=canon_stmt[:2000],
                            source_name=canon.get("source_ref"),
                            source_id=_safe_uuid(canon.get("source_id")),
                            canon_level=canon.get("canon_level", "canon"),
                            confidence=float(canon.get("confidence", 0.9)),
                            fact_type="fact",
                        ),
                        similarity_score=similarity,
                        explanation=(
                            f"Entity '{entity.name}' description may contradict "
                            f"established canon: '{canon_stmt[:100]}'"
                        ),
                        recommended_resolution=ContradictionResolution.REVIEW,
                        category="entity_archetypes",
                        item_index=idx,
                    )
                )

    return matches


# ---------------------------------------------------------------------------
# Core comparison logic
# ---------------------------------------------------------------------------


def _compare_statements(
    new_statement: str,
    existing_statement: str,
    new_source: Optional[str] = None,
    existing_source: Optional[str] = None,
    existing_canon_level: str = "canon",
    category: str = "lore_facts",
    item_index: int = 0,
) -> Optional[ContradictionMatch]:
    """
    Compare two statements and detect if they contradict each other.

    Returns None if no contradiction is detected, otherwise a ContradictionMatch.
    """
    new_lower = new_statement.lower().strip()
    existing_lower = existing_statement.lower().strip()

    # Skip identical or near-identical statements (handled by dedup)
    similarity = _levenshtein_ratio(new_lower, existing_lower)
    if similarity > 0.92:
        return None

    # Check for negation-based contradiction
    if _has_negation_conflict(new_lower, existing_lower):
        severity = _classify_severity(similarity, existing_canon_level)
        ctype = ContradictionType.SEMANTIC_OPPOSITE
        explanation = (
            f"Negation conflict: '{new_statement[:100]}' vs canon: '{existing_statement[:100]}'"
        )
        return ContradictionMatch(
            contradiction_id=f"contra:{category}:{item_index}:{hash(existing_statement) % 10000}",
            contradiction_type=ctype,
            severity=severity,
            new_fact=ContradictionFact(
                statement=new_statement[:2000],
                source_name=new_source,
                canon_level="proposed",
                confidence=0.8,
                fact_type=category.rstrip("s"),  # axioms → axiom
            ),
            existing_fact=ContradictionFact(
                statement=existing_statement[:2000],
                source_name=existing_source,
                canon_level=existing_canon_level,
                confidence=0.9,
                fact_type=category.rstrip("s"),
            ),
            similarity_score=similarity,
            explanation=explanation,
            recommended_resolution=ContradictionResolution.REVIEW,
            category=category,
            item_index=item_index,
        )

    # Check for opposite term pairs — only meaningful when both statements
    # talk about the same subject ("Elves are immortal" does not contradict
    # "Dwarves are mortal"). Subject check uses the original casing so the
    # proper-noun heuristic can see capitalized names.
    opposite_match = _has_opposite_terms(new_lower, existing_lower)
    if (
        opposite_match
        and similarity >= _SIMILARITY_THRESHOLD
        and _shares_subject(new_statement, existing_statement)
    ):
        severity = _classify_severity(similarity, existing_canon_level)
        explanation = (
            f"Opposing terms ({opposite_match}): "
            f"'{new_statement[:100]}' vs canon: '{existing_statement[:100]}'"
        )
        return ContradictionMatch(
            contradiction_id=f"contra:{category}:{item_index}:{hash(existing_statement) % 10000}",
            contradiction_type=ContradictionType.SEMANTIC_OPPOSITE,
            severity=severity,
            new_fact=ContradictionFact(
                statement=new_statement[:2000],
                source_name=new_source,
                canon_level="proposed",
                confidence=0.8,
                fact_type=category.rstrip("s"),
            ),
            existing_fact=ContradictionFact(
                statement=existing_statement[:2000],
                source_name=existing_source,
                canon_level=existing_canon_level,
                confidence=0.9,
                fact_type=category.rstrip("s"),
            ),
            similarity_score=similarity,
            explanation=explanation,
            recommended_resolution=ContradictionResolution.REVIEW,
            category=category,
            item_index=item_index,
        )

    # High-similarity but different content — potential partial overlap
    if _SIMILARITY_THRESHOLD <= similarity < 0.92:
        # Check if they share the same subject (entity names, proper nouns)
        if _shares_subject(new_lower, existing_lower):
            severity = ContradictionSeverity.LOW
            explanation = (
                f"Similar statements about the same subject: "
                f"'{new_statement[:80]}' vs canon: '{existing_statement[:80]}'"
            )
            return ContradictionMatch(
                contradiction_id=f"contra:{category}:{item_index}:{hash(existing_statement) % 10000}",
                contradiction_type=ContradictionType.PARTIAL_OVERLAP,
                severity=severity,
                new_fact=ContradictionFact(
                    statement=new_statement[:2000],
                    source_name=new_source,
                    canon_level="proposed",
                    confidence=0.8,
                    fact_type=category.rstrip("s"),
                ),
                existing_fact=ContradictionFact(
                    statement=existing_statement[:2000],
                    source_name=existing_source,
                    canon_level=existing_canon_level,
                    confidence=0.9,
                    fact_type=category.rstrip("s"),
                ),
                similarity_score=similarity,
                explanation=explanation,
                recommended_resolution=ContradictionResolution.MERGE,
                category=category,
                item_index=item_index,
            )

    return None


# ---------------------------------------------------------------------------
# Heuristic helpers
# ---------------------------------------------------------------------------


def _has_negation_conflict(text_a: str, text_b: str) -> bool:
    """Check if one text negates the other.

    E.g. "X is Y" vs "X is not Y" → True
         "X can do Z" vs "X cannot do Z" → True
    """
    # Check if adding/removing negation makes them more similar
    for prefix in _NEGATION_PREFIXES:
        # If A has the negation and B doesn't
        if prefix in text_a and prefix not in text_b:
            stripped = text_a.replace(prefix, "", 1)
            if _levenshtein_ratio(stripped, text_b) > 0.75:
                return True
        # If B has the negation and A doesn't
        if prefix in text_b and prefix not in text_a:
            stripped = text_b.replace(prefix, "", 1)
            if _levenshtein_ratio(stripped, text_a) > 0.75:
                return True
    return False


def _has_opposite_terms(text_a: str, text_b: str) -> Optional[str]:
    """Check if the two texts contain known opposite term pairs.

    Whole-word matching only — substring checks would make "immortal"
    contain "mortal" and flag every mortality statement as conflicting.

    Returns the pair found (e.g. "mortal/immortal") or None.
    """
    import re

    def has_word(word: str, text: str) -> bool:
        return re.search(rf"\b{re.escape(word)}\b", text) is not None

    for word_a, word_b in _OPPOSITE_PAIRS:
        if (has_word(word_a, text_a) and has_word(word_b, text_b)) or (
            has_word(word_b, text_a) and has_word(word_a, text_b)
        ):
            return f"{word_a}/{word_b}"
    return None


def _shares_subject(text_a: str, text_b: str) -> bool:
    """Heuristic: do two statements share the same subject?

    Looks for capitalized words (proper nouns) or quoted entity names
    that appear in both statements.
    """
    import re

    # Extract words that look like proper nouns (capitalized, 3+ chars)
    proper_noun_pattern = re.compile(r"\b[A-Z][a-z]{2,}\b")
    nouns_a = set(proper_noun_pattern.findall(text_a))
    nouns_b = set(proper_noun_pattern.findall(text_b))
    overlap = nouns_a & nouns_b

    # Need at least one shared proper noun
    if overlap:
        return True

    # Fallback: check for shared long tokens (5+ chars)
    tokens_a = {w for w in text_a.split() if len(w) >= 5}
    tokens_b = {w for w in text_b.split() if len(w) >= 5}
    token_overlap = tokens_a & tokens_b
    return len(token_overlap) >= 2


def _classify_severity(
    similarity: float,
    existing_canon_level: str,
) -> ContradictionSeverity:
    """Classify how severe a contradiction is."""
    if existing_canon_level == "canon":
        # Contradicting established canon is always serious
        if similarity >= _HIGH_SIMILARITY_THRESHOLD:
            return ContradictionSeverity.HIGH
        return ContradictionSeverity.MEDIUM
    if existing_canon_level in ("proposed", "rumor", "character_belief"):
        # Less serious — the existing fact isn't canon yet
        return ContradictionSeverity.LOW
    return ContradictionSeverity.MEDIUM


def _safe_uuid(value: Any) -> Optional[UUID]:
    """Safely convert a value to UUID."""
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None
