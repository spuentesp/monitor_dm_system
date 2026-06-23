"""
Tests for subject-index pre-filtering in contradiction detection (Paso 3).

LAYER: 1 (data-layer)
CRITERIO DE ÉXITO:
  1. _extract_proper_nouns extrae correctamente nombres propios
  2. _build_subject_index indexa correctamente items canónicos
  3. Pre-filtro no produce falsos negativos respecto al algoritmo exhaustivo
  4. Reducción ≥80% de candidatos en datasets diversos

NOTE: Reference implementations are inline to avoid pre-existing circular
import in monitor_data.schemas (game_systems ↔ knowledge_packs).
"""

import re


from monitor_data.tools.ingest_tools.delta_detection import _levenshtein_ratio


# =============================================================================
# Reference implementations (mirrors contradiction_detection.py logic)
# =============================================================================

_PROPER_NOUN_PATTERN = re.compile(r"\b[A-Z][a-z]{2,}\b")
_NEGATION_PREFIXES = ("not ", "is not ", "are not ", "does not ", "cannot ", "never ")
_OPPOSITE_PAIRS: list[tuple[str, str]] = [
    ("mortal", "immortal"),
    ("alive", "dead"),
    ("true", "false"),
    ("good", "evil"),
    ("light", "dark"),
    ("visible", "invisible"),
    ("possible", "impossible"),
    ("open", "closed"),
    ("destroyed", "intact"),
    ("at war", "at peace"),
]


def _extract_proper_nouns(text: str) -> set[str]:
    """Extract capitalized words (3+ chars) that look like proper nouns."""
    return set(_PROPER_NOUN_PATTERN.findall(text))


def _has_negation_conflict_ref(text_a: str, text_b: str) -> bool:
    """Check if one text negates the other (mirrors original logic)."""
    for prefix in _NEGATION_PREFIXES:
        if prefix in text_a and prefix not in text_b:
            stripped = text_a.replace(prefix, "", 1)
            if _levenshtein_ratio(stripped, text_b) > 0.75:
                return True
        if prefix in text_b and prefix not in text_a:
            stripped = text_b.replace(prefix, "", 1)
            if _levenshtein_ratio(stripped, text_a) > 0.75:
                return True
    return False


def _has_opposite_terms_ref(text_a: str, text_b: str) -> str | None:
    """Check for opposite term pairs (reference implementation)."""
    for term1, term2 in _OPPOSITE_PAIRS:
        if (term1 in text_a and term2 in text_b) or (term2 in text_a and term1 in text_b):
            return f"{term1}<->{term2}"
    return None


def _shares_subject_ref(text_a: str, text_b: str) -> bool:
    """Check if two statements share the same subject via proper nouns."""
    nouns_a = _extract_proper_nouns(text_a)
    nouns_b = _extract_proper_nouns(text_b)
    if nouns_a & nouns_b:
        return True
    tokens_a = {w for w in text_a.split() if len(w) >= 5}
    tokens_b = {w for w in text_b.split() if len(w) >= 5}
    return len(tokens_a & tokens_b) >= 2


def _compare_statements_ref(
    new_statement: str,
    existing_statement: str,
    existing_canon_level: str = "canon",
    item_index: int = 0,
) -> dict | None:
    """Reference _compare_statements returning dict instead of Pydantic model."""
    new_lower = new_statement.lower().strip()
    existing_lower = existing_statement.lower().strip()

    similarity = _levenshtein_ratio(new_lower, existing_lower)
    if similarity > 0.92:
        return None

    if _has_negation_conflict_ref(new_lower, existing_lower):
        return {
            "type": "negation",
            "similarity": similarity,
            "explanation": f"Negation: '{new_statement[:100]}' vs '{existing_statement[:100]}'",
        }

    opp = _has_opposite_terms_ref(new_lower, existing_lower)
    if opp and similarity >= 0.65:
        return {
            "type": "opposite",
            "similarity": similarity,
            "explanation": f"Opposite ({opp}): '{new_statement[:100]}' vs '{existing_statement[:100]}'",
        }

    if _shares_subject_ref(new_lower, existing_lower) and 0.65 <= similarity < 0.92:
        return {
            "type": "overlap",
            "similarity": similarity,
            "explanation": f"Similar: '{new_statement[:80]}' vs '{existing_statement[:80]}'",
        }

    return None


# =============================================================================
# Subject index builder
# =============================================================================


def _build_subject_index(
    canon_items: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    """Build proper_noun -> list of canon items."""
    index: dict[str, list[dict[str, str]]] = {}
    for item in canon_items:
        stmt = item.get("statement", "")
        nouns = _extract_proper_nouns(stmt)
        if not nouns:
            index.setdefault("_all", []).append(item)
        else:
            for noun in nouns:
                index.setdefault(noun.lower(), []).append(item)
    return index


def _get_subject_candidates(
    new_statement: str,
    subject_index: dict[str, list[dict[str, str]]],
) -> list[dict[str, str]]:
    """Get canon items sharing at least one proper noun with new_statement."""
    nouns = _extract_proper_nouns(new_statement)
    seen_ids: set[int] = set()
    candidates: list[dict[str, str]] = []

    for item in subject_index.get("_all", []):
        item_id = id(item)
        if item_id not in seen_ids:
            seen_ids.add(item_id)
            candidates.append(item)

    if not nouns:
        for items in subject_index.values():
            for item in items:
                item_id = id(item)
                if item_id not in seen_ids:
                    seen_ids.add(item_id)
                    candidates.append(item)
        return candidates

    for noun in nouns:
        for item in subject_index.get(noun.lower(), []):
            item_id = id(item)
            if item_id not in seen_ids:
                seen_ids.add(item_id)
                candidates.append(item)

    return candidates


# =============================================================================
# Pre-filtered vs exhaustive comparison
# =============================================================================


def _check_axioms_prefiltered(
    new_axioms: list,
    canon_axioms: list[dict[str, str]],
) -> list[dict]:
    subject_index = _build_subject_index(canon_axioms)
    matches: list[dict] = []
    for idx, axiom in enumerate(new_axioms):
        candidates = _get_subject_candidates(axiom.statement, subject_index)
        for canon in candidates:
            canon_stmt = canon.get("statement", "")
            if not canon_stmt:
                continue
            match = _compare_statements_ref(
                new_statement=axiom.statement,
                existing_statement=canon_stmt,
                existing_canon_level=canon.get("canon_level", "canon"),
                item_index=idx,
            )
            if match is not None:
                matches.append(match)
    return matches


def _check_axioms_original(
    new_axioms: list,
    canon_axioms: list[dict[str, str]],
) -> list[dict]:
    matches: list[dict] = []
    for idx, axiom in enumerate(new_axioms):
        for canon in canon_axioms:
            canon_stmt = canon.get("statement", "")
            if not canon_stmt:
                continue
            match = _compare_statements_ref(
                new_statement=axiom.statement,
                existing_statement=canon_stmt,
                existing_canon_level=canon.get("canon_level", "canon"),
                item_index=idx,
            )
            if match is not None:
                matches.append(match)
    return matches


# =============================================================================
# Test factories
# =============================================================================


def _make_axiom(statement: str) -> object:
    from types import SimpleNamespace

    return SimpleNamespace(statement=statement, source_ref=None, confidence=0.8)


def _make_canon_axiom(statement: str) -> dict[str, str]:
    return {"statement": statement, "canon_level": "canon"}


# =============================================================================
# Tests
# =============================================================================


class TestProperNounExtraction:
    def test_simple_proper_noun(self) -> None:
        nouns = _extract_proper_nouns("Gandalf went to Mordor")
        assert "Gandalf" in nouns
        assert "Mordor" in nouns

    def test_no_proper_nouns(self) -> None:
        assert _extract_proper_nouns("the cat sat on the mat") == set()

    def test_short_capitalized_ignored(self) -> None:
        nouns = _extract_proper_nouns("An Elf went To the Shire")
        assert "An" not in nouns
        assert "To" not in nouns
        assert "Elf" in nouns
        assert "Shire" in nouns


class TestSubjectIndex:
    def test_empty(self) -> None:
        assert _build_subject_index([]) == {}

    def test_items_with_proper_nouns(self) -> None:
        items = [
            _make_canon_axiom("Gandalf is a wizard"),
            _make_canon_axiom("Frodo is a hobbit"),
        ]
        index = _build_subject_index(items)
        assert "gandalf" in index
        assert index["gandalf"][0]["statement"] == "Gandalf is a wizard"

    def test_items_without_proper_nouns(self) -> None:
        items = [
            _make_canon_axiom("magic is real"),
            _make_canon_axiom("the world is round"),
        ]
        index = _build_subject_index(items)
        assert "_all" in index
        assert len(index["_all"]) == 2


class TestZeroFalseNegatives:
    def test_same_results_small(self) -> None:
        new_axioms = [
            _make_axiom("Elves are immortal"),
            _make_axiom("Dwarves live underground"),
        ]
        canon = [
            _make_canon_axiom("Elves are mortal"),
            _make_canon_axiom("Dwarves are great miners"),
            _make_canon_axiom("Magic is fading from the world"),
        ]
        original = _check_axioms_original(new_axioms, canon)
        prefiltered = _check_axioms_prefiltered(new_axioms, canon)
        assert len(original) == len(prefiltered)

    def test_same_results_with_proper_nouns(self) -> None:
        new_axioms = [_make_axiom("Gandalf is not the strongest wizard")]
        canon = [
            _make_canon_axiom("Gandalf is the strongest wizard"),
            _make_canon_axiom("Saruman is a powerful wizard"),
            _make_canon_axiom("The Shire is peaceful"),
            _make_canon_axiom("Mordor is dangerous"),
            _make_canon_axiom("Elves are immortal"),
        ]
        original = _check_axioms_original(new_axioms, canon)
        prefiltered = _check_axioms_prefiltered(new_axioms, canon)
        assert len(original) == len(prefiltered)

    def test_no_proper_nouns_fallback(self) -> None:
        new_axioms = [_make_axiom("Magic is real and powerful")]
        canon = [
            _make_canon_axiom("Magic is an illusion"),
            _make_canon_axiom("The world is flat"),
            _make_canon_axiom("Dragons exist"),
        ]
        original = _check_axioms_original(new_axioms, canon)
        prefiltered = _check_axioms_prefiltered(new_axioms, canon)
        assert len(original) == len(prefiltered)

    def test_candidate_reduction(self) -> None:
        subjects = [
            "Gandalf",
            "Frodo",
            "Aragorn",
            "Sauron",
            "Galadriel",
            "Elrond",
            "Gimli",
            "Legolas",
            "Boromir",
            "Saruman",
        ]
        canon = [
            _make_canon_axiom(f"{subjects[i % 10]} fact {i} about Middle Earth") for i in range(100)
        ]
        subject_index = _build_subject_index(canon)
        candidates = _get_subject_candidates("Gandalf is very powerful", subject_index)
        reduction = len(candidates) / len(canon)
        assert reduction <= 0.20, (
            f"{len(candidates)}/{len(canon)} ({reduction:.1%}) candidates, expected <=20%"
        )
