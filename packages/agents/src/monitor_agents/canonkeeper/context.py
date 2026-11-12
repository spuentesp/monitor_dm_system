"""
Canon context assembly for the contradiction checks (G08, phase 2).

The checks used to be handed the whole canon and asked to hold it in their
head alongside a chunk of candidates. On the 2026-11-07 corpus that shape
detected 25% of the contradictions; the per-class corpus
(`recall_corpus.py`) shows the same weakness per class.

This module is the retrieval half of the fix: given one candidate
statement, decide *which* canon belongs in its context. The rules are
explicit and deterministic — no keyword scoring, no model:

1. **Direct hits** — canon facts that mention an entity the candidate
   names, or that are attached to one of those entities.
2. **One hop out** — canon facts attached to an entity a direct hit also
   touches. A fact about Mira Vale's guild is relevant to a claim about
   Mira Vale; a fact about the harbour council is one hop from that.
3. **The timeline** — canon facts that carry a timestamp and touch the same
   entities, because "when" is what a timeline violation turns on.

When nothing matches, the whole canon is used: an empty context cannot
contradict anything, and a false negative is worse than a long prompt.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1 schemas), external libraries
CALLED BY: CanonKeeper's contradiction checks
"""

from __future__ import annotations

from typing import Any


def mentioned_entity_names(statement: str, entity_names: list[str]) -> set[str]:
    """The canonical entity names a statement mentions.

    Matching is case-insensitive and substring-based on the *name*, which is
    what the canon itself stores — the alternative (resolving every noun
    phrase) needs a model and buys nothing the checks need.
    """
    if not statement:
        return set()
    lowered = statement.lower()
    found: set[str] = set()
    for name in entity_names:
        cleaned = str(name).strip()
        if cleaned and cleaned.lower() in lowered:
            found.add(cleaned)
    return found


def _fact_entity_ids(fact: dict[str, Any]) -> set[str]:
    """The entity ids a canon fact is attached to."""
    raw = fact.get("entity_ids") or []
    ids: set[str] = set()
    for item in raw:
        if isinstance(item, str) and item.strip():
            ids.add(item.strip())
        elif item is not None:
            ids.add(str(item))
    return ids


def _fact_text(fact: dict[str, Any]) -> str:
    """Everything a fact says, for name matching."""
    parts = [str(fact.get("statement") or "")]
    properties = fact.get("properties")
    if isinstance(properties, dict):
        for key in ("name", "description", "participant", "participants"):
            value = properties.get(key)
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.extend(str(v) for v in value)
    return " ".join(parts)


def select_relevant_facts(
    statement: str,
    facts: list[dict[str, Any]],
    entity_names: list[str],
) -> list[dict[str, Any]]:
    """The canon facts that bear on one statement.

    Args:
        statement: The candidate statement.
        facts: Every canon fact of the universe.
        entity_names: The universe's entity names, for name matching.

    Returns:
        The selected facts. Empty only when the universe has no canon at all
        or nothing mentions the candidate's entities *and* the universe is
        small enough that everything is context anyway.
    """
    mentioned = mentioned_entity_names(statement, entity_names)
    if not mentioned:
        return list(facts)

    matched_ids: set[str] = set()
    direct: list[dict[str, Any]] = []
    for fact in facts:
        text = _fact_text(fact).lower()
        names_hit = any(name.lower() in text for name in mentioned)
        ids_hit = bool(_fact_entity_ids(fact) & matched_ids)
        if names_hit or ids_hit:
            direct.append(fact)
            matched_ids |= _fact_entity_ids(fact)

    # One hop out: facts attached to an entity a direct hit also touches.
    one_hop = [fact for fact in facts if fact not in direct and _fact_entity_ids(fact) & matched_ids]

    # The timeline: dated facts about the same entities. A candidate can
    # contradict *when* something happened without naming the same people.
    dated = [fact for fact in (*direct, *one_hop) if fact.get("time_ref") or fact.get("properties", {}).get("time_ref")]

    selected = [*direct, *one_hop]
    seen = {id(fact) for fact in selected}
    for fact in dated:
        if id(fact) not in seen:
            selected.append(fact)
            seen.add(id(fact))
    return selected or list(facts)


def render_context_lines(
    facts: list[dict[str, Any]],
    axioms: list[Any] | None = None,
) -> list[str]:
    """Render canon as the context lines the checks consume.

    Axioms first (they are the world's rules), then facts. A fact that
    carries a timestamp shows it: a check that cannot see *when* cannot
    see a timeline violation.
    """
    lines: list[str] = []
    for axiom in axioms or []:
        statement = axiom.get("statement") if isinstance(axiom, dict) else getattr(axiom, "statement", None)
        if statement:
            lines.append(f"Axiom: {statement}")
    for fact in facts:
        statement = str(fact.get("statement") or "").strip()
        if not statement:
            continue
        time_ref = fact.get("time_ref") or (
            fact.get("properties", {}).get("time_ref") if isinstance(fact.get("properties"), dict) else None
        )
        if time_ref:
            lines.append(f"Fact ({time_ref}): {statement}")
        else:
            lines.append(f"Fact: {statement}")
    return lines


def build_focused_context(
    statement: str,
    facts: list[dict[str, Any]],
    axioms: list[Any] | None = None,
    entity_names: list[str] | None = None,
) -> str:
    """The context for one candidate: the canon that bears on it.

    Args:
        statement: The candidate statement.
        facts: Every canon fact of the universe.
        axioms: The universe's axioms.
        entity_names: The universe's entity names.

    Returns:
        The rendered context.
    """
    selected = select_relevant_facts(statement, facts, entity_names or [])
    return "\n".join(render_context_lines(selected, axioms))


__all__ = [
    "build_focused_context",
    "mentioned_entity_names",
    "render_context_lines",
    "select_relevant_facts",
]
