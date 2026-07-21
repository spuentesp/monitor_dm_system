"""
Entity promotion gate — extract & tag transient entities from narration.

The Narrator tags every newly-introduced entity with one of two intents
(``[Name](entity:anchor)`` for structurally-important entities that should
earn a permanent Neo4j UUID, or ``[Name](entity:flavor)`` for disposable
set dressing). This module:

  1. Parses those tags out of the narrator's prose (regex).
  2. Builds ProposedChange records carrying the intent metadata.
  3. Increments ``interaction_count`` on existing proposals when the same
     tagged name reappears in later turns (in-memory counter; flushed to
     MongoDB by callers).
  4. Detects when a tagged name shows up in a mechanical payload
     (combat / state_change / inventory) and marks
     ``is_mechanically_bound = True`` so the entity survives the
     promotion gate even if it was tagged as flavor.

This module is intentionally pure (no DB writes, no LLM calls). Callers
thread the parsed proposals and update counters into the scene loop's
``pending_proposals`` state; CanonKeeper.apply_entity_promotion_rules()
later consults ``promotion_intent`` / ``interaction_count`` /
``is_mechanically_bound`` at scene end to decide acceptance.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Regex
# ---------------------------------------------------------------------------

# Matches `[Name](entity:anchor)` or `[Name](entity:flavor)`. Name may include
# spaces, hyphens, apostrophes (e.g. "Rust Nail", "Ostensible", "Kael Draven",
# "D'Angelo"). Excludes `]` and `(` inside the bracketed name.
_ENTITY_TAG_RE = re.compile(
    r"\[(?P<name>[^\]\(]+?)\]\(entity:(?P<intent>anchor|flavor)\)"
)


def parse_entity_tags(narrative_text: str) -> List[Tuple[str, str]]:
    """
    Extract ``(name, intent)`` tuples from narrator prose.

    Returns an empty list when no tags are present. Order matches the
    order tags appear in the text; duplicates are NOT collapsed here
    (callers may want to count repeated references).
    """
    if not narrative_text:
        return []
    out: List[Tuple[str, str]] = []
    for match in _ENTITY_TAG_RE.finditer(narrative_text):
        name = match.group("name").strip()
        intent = match.group("intent").strip().lower()
        if name and intent in {"anchor", "flavor"}:
            out.append((name, intent))
    return out


# ---------------------------------------------------------------------------
# Proposal construction
# ---------------------------------------------------------------------------


def _proposal_key(proposal: Dict[str, Any]) -> str:
    """Return a stable lookup key for an entity proposal (case-insensitive name)."""
    content = proposal.get("content") or {}
    name = (content.get("name") or "").strip().lower()
    return name


def merge_tagged_intents(
    llm_proposals: List[Dict[str, Any]],
    tagged: Iterable[Tuple[str, str]],
) -> List[Dict[str, Any]]:
    """
    Merge tagged (name, intent) pairs into existing entity proposals.

    For each (name, intent) tag:
      - If a proposal with that name already exists in ``llm_proposals``,
        stamp ``promotion_intent`` on it (overwriting any prior value).
      - Otherwise, append a minimal proposal carrying only ``name`` and
        ``promotion_intent`` so CanonKeeper can evaluate the tag alone.

    The narrator's LLM-extracted proposals (``llm_proposals``) keep their
    richer content (description, entity_type, confidence); the tag is the
    only thing this function adds.
    """
    merged = list(llm_proposals)
    index = {
        _proposal_key(p): i for i, p in enumerate(merged) if _proposal_key(p)
    }
    for name, intent in tagged:
        key = name.strip().lower()
        if not key:
            continue
        if key in index:
            merged[index[key]]["promotion_intent"] = intent
            merged[index[key]].setdefault("interaction_count", 1)
            continue
        merged.append(
            {
                "proposal_type": "ENTITY",
                "content": {"name": name.strip()},
                "summary": f"Entity tagged in narration: {name} ({intent})",
                "confidence": 1.0,
                "authority": "SYSTEM",
                "proposer": "narrator_entity_tag",
                "promotion_intent": intent,
                "interaction_count": 1,
                "is_mechanically_bound": False,
            }
        )
        index[key] = len(merged) - 1
    return merged


# ---------------------------------------------------------------------------
# Interaction counter
# ---------------------------------------------------------------------------


def bump_interaction_counts(
    proposals: List[Dict[str, Any]],
    tagged: Iterable[Tuple[str, str]],
) -> List[Dict[str, Any]]:
    """
    Increment ``interaction_count`` for each proposal whose name reappears
    in ``tagged``. Does NOT create new proposals. Existing proposal wins.

    Mutates the proposals list in place and also returns it for chaining.
    """
    by_name = {_proposal_key(p): p for p in proposals if _proposal_key(p)}
    seen_this_turn: set[str] = set()
    for name, _intent in tagged:
        key = name.strip().lower()
        if not key or key in seen_this_turn:
            continue
        seen_this_turn.add(key)
        proposal = by_name.get(key)
        if proposal is not None:
            proposal["interaction_count"] = int(proposal.get("interaction_count", 1)) + 1
    return proposals


# ---------------------------------------------------------------------------
# Mechanical binding
# ---------------------------------------------------------------------------


def _collect_names_from_payload(payload: Any) -> List[str]:
    """Recursively pull name strings out of a mechanical payload dict.

    Looks at common fields where NPC / item names land in state_change,
    inventory, and combat proposals: ``name``, ``target_name``,
    ``actor_name``, ``from_entity``, ``to_entity``, ``entity_name``.
    Also accepts ``entity_id`` / ``target_entity_id`` / ``actor_id``
    (mechanical payloads frequently carry the entity name there).
    """
    if not isinstance(payload, dict):
        return []
    names: List[str] = []
    name_fields = (
        "name",
        "target_name",
        "actor_name",
        "from_entity",
        "to_entity",
        "entity_name",
    )
    for f in name_fields:
        v = payload.get(f)
        if isinstance(v, str) and v.strip():
            names.append(v.strip())
    # Mechanical-payload entity references — accept name-shaped strings
    # only (skip UUIDs, they don't match name-keyed proposals).
    id_fields = ("entity_id", "target_entity_id", "actor_id")
    for f in id_fields:
        v = payload.get(f)
        if isinstance(v, str) and v.strip() and "-" not in v:
            names.append(v.strip())
    # nested ``content`` / ``payload`` (proposal shape)
    for nested_key in ("content", "payload"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            names.extend(_collect_names_from_payload(nested))
    return names


def detect_mechanically_bound(
    proposals: List[Dict[str, Any]],
    mechanical_payloads: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Set ``is_mechanically_bound = True`` on any proposal whose name
    appears in any mechanical payload (state_change, event, inventory).

    A "flavor" entity that gets referenced by a state-change or combat
    payload is structurally required for graph integrity — we promote
    it to anchor-equivalent regardless of interaction count.
    """
    referenced: set[str] = set()
    for payload in mechanical_payloads:
        for n in _collect_names_from_payload(payload):
            referenced.add(n.strip().lower())

    if not referenced:
        return proposals

    for proposal in proposals:
        name = _proposal_key(proposal)
        if name and name in referenced:
            proposal["is_mechanically_bound"] = True
    return proposals


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------


def annotate_proposals(
    base_proposals: List[Dict[str, Any]],
    narrative_text: Optional[str],
    mechanical_payloads: Optional[Iterable[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Apply all three passes in one call:

      1. Parse ``[Name](entity:anchor|flavor)`` tags from ``narrative_text``.
      2. Merge tag intent onto any matching base proposal (or append a
         minimal proposal when the LLM extractor missed it).
      3. Bump ``interaction_count`` for reappearing names.
      4. Stamp ``is_mechanically_bound`` for any name referenced by a
         mechanical payload.

    Returns the new list of proposals (does not mutate the input).
    """
    proposals = list(base_proposals)
    tagged = parse_entity_tags(narrative_text or "")
    if tagged:
        proposals = merge_tagged_intents(proposals, tagged)
        proposals = bump_interaction_counts(proposals, tagged)
    if mechanical_payloads:
        proposals = detect_mechanically_bound(proposals, mechanical_payloads)
    return proposals
