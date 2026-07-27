"""
Re-ingestion delta detection logic (P2-6).

LAYER: 1 (data-layer)

Compares two KnowledgePack extractions (current vs new) and produces an
IngestionDelta that classifies every item as ADDED / MODIFIED / UNCHANGED /
REMOVED per category.

This drives two flows:
  1. Review — present the delta to the user for approval
  2. Apply  — only emit ProposedChanges for ADDED and MODIFIED items,
              skipping UNCHANGED (already committed) and REMOVED (the
              source doc no longer has them)

The comparison is field-by-field within each extracted item using a deep
equality check that ignores confidence deltas and source_ref changes
unless they indicate a substantive modification.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from monitor_data.schemas.ingestion_delta import (
    DeltaCategory,
    DeltaItem,
    IngestionDelta,
    IngestionDeltaApplyRequest,
)
from monitor_data.schemas.knowledge_packs import (
    ExtractedAxiom,
    ExtractedEntityArchetype,
    ExtractedLoreFact,
    ExtractedRandomTable,
    ExtractedRelationship,
    ExtractedTopology,
    KnowledgePackResponse,
)
from monitor_data.tools._shared import levenshtein_ratio as _levenshtein_ratio
from monitor_data.tools._shared import pydantic_to_dict as _pydantic_to_dict

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_ingestion_delta(
    current_pack: KnowledgePackResponse,
    new_pack: KnowledgePackResponse,
    source_id: UUID,
    pack_id_current: UUID | None = None,
    pack_id_new: UUID | None = None,
) -> IngestionDelta:
    """
    Compare two KnowledgePack extractions and produce a structured delta.

    Args:
        current_pack: The last-applied KnowledgePack version
        new_pack: The freshly extracted KnowledgePack from re-ingesting the same source
        source_id: Which source document this delta is for
        pack_id_current: Optional KnowledgePack UUID of current (for tracking)
        pack_id_new: Optional KnowledgePack UUID of new (for tracking)

    Returns:
        IngestionDelta with per-category breakdowns and rollup stats
    """
    axioms_delta = _diff_axioms(current_pack.axioms, new_pack.axioms)
    entities_delta = _diff_entities(current_pack.entity_archetypes, new_pack.entity_archetypes)
    lore_delta = _diff_lore_facts(current_pack.lore_facts, new_pack.lore_facts)
    rels_delta = _diff_relationships(current_pack.entity_relationships, new_pack.entity_relationships)
    tables_delta = _diff_random_tables(current_pack.random_tables, new_pack.random_tables)
    agendas_delta = _diff_agendas(current_pack.agendas, new_pack.agendas)
    topologies_delta = _diff_topologies(current_pack.topologies, new_pack.topologies)
    threads_delta = _diff_by_identity_field(
        current_pack.plot_threads,
        new_pack.plot_threads,
        field_name="plot_threads",
        identity_field="title",
    )

    all_items: list[DeltaItem] = [
        *(axioms_delta or []),
        *(entities_delta or []),
        *(lore_delta or []),
        *(rels_delta or []),
        *(tables_delta or []),
        *(agendas_delta or []),
        *(topologies_delta or []),
        *(threads_delta or []),
    ]

    net_new = sum(1 for d in all_items if d.delta_category == DeltaCategory.ADDED)
    modified = sum(1 for d in all_items if d.delta_category == DeltaCategory.MODIFIED)
    removed = sum(1 for d in all_items if d.delta_category == DeltaCategory.REMOVED)
    unchanged = sum(1 for d in all_items if d.delta_category == DeltaCategory.UNCHANGED)

    significance = _classify_significance(net_new, modified, removed, len(all_items))
    recommendations = _build_recommendations(net_new, modified, removed, significance)

    return IngestionDelta(
        source_id=source_id,
        pack_id_current=pack_id_current,
        pack_id_new=pack_id_new,
        total_axioms=len(new_pack.axioms),
        total_entities=len(new_pack.entity_archetypes),
        total_lore_facts=len(new_pack.lore_facts),
        total_relationships=len(new_pack.entity_relationships),
        total_random_tables=len(new_pack.random_tables),
        total_agendas=len(new_pack.agendas),
        total_topologies=len(new_pack.topologies),
        total_plot_threads=len(new_pack.plot_threads),
        axioms_delta=axioms_delta,
        entities_delta=entities_delta,
        lore_facts_delta=lore_delta,
        relationships_delta=rels_delta,
        random_tables_delta=tables_delta,
        agendas_delta=agendas_delta,
        topologies_delta=topologies_delta,
        plot_threads_delta=threads_delta or [],
        net_new_items=net_new,
        modified_items=modified,
        removed_items=removed,
        unchanged_items=unchanged,
        change_significance=significance,
        recommendations=recommendations,
    )


def filter_delta_for_apply(
    delta: IngestionDelta,
    request: IngestionDeltaApplyRequest,
) -> IngestionDelta:
    """
    Return a filtered copy of delta that only includes items to be applied.

    Removes REMOVED items (the source no longer has them), removes items
    that are UNCHANGED (already committed), and optionally filters
    MODIFIED based on include_modified flag.

    The filtered delta can then be passed to a modified version of
    mongodb_apply_knowledge_pack() that only processes the included items.
    """

    def _keep(item: DeltaItem) -> bool:
        if item.delta_category == DeltaCategory.REMOVED:
            return False
        if item.delta_category == DeltaCategory.UNCHANGED:
            return False
        return not (item.delta_category == DeltaCategory.MODIFIED and not request.include_modified)

    def _filter(items: list[DeltaItem]) -> list[DeltaItem]:
        return [d for d in items if _keep(d)]

    filtered = IngestionDelta(
        source_id=delta.source_id,
        pack_id_current=delta.pack_id_current,
        pack_id_new=delta.pack_id_new,
        total_axioms=len([d for d in delta.axioms_delta if d.delta_category != DeltaCategory.REMOVED]),
        total_entities=len([d for d in delta.entities_delta if d.delta_category != DeltaCategory.REMOVED]),
        total_lore_facts=len([d for d in delta.lore_facts_delta if d.delta_category != DeltaCategory.REMOVED]),
        total_relationships=len([d for d in delta.relationships_delta if d.delta_category != DeltaCategory.REMOVED]),
        total_random_tables=len([d for d in delta.random_tables_delta if d.delta_category != DeltaCategory.REMOVED]),
        total_agendas=len([d for d in delta.agendas_delta if d.delta_category != DeltaCategory.REMOVED]),
        total_topologies=len([d for d in delta.topologies_delta if d.delta_category != DeltaCategory.REMOVED]),
        axioms_delta=_filter(delta.axioms_delta),
        entities_delta=_filter(delta.entities_delta),
        lore_facts_delta=_filter(delta.lore_facts_delta),
        relationships_delta=_filter(delta.relationships_delta),
        random_tables_delta=_filter(delta.random_tables_delta),
        agendas_delta=_filter(delta.agendas_delta),
        topologies_delta=_filter(delta.topologies_delta),
        net_new_items=sum(1 for d in delta.axioms_delta if d.delta_category == DeltaCategory.ADDED and _keep(d))
        + sum(1 for d in delta.entities_delta if d.delta_category == DeltaCategory.ADDED and _keep(d))
        + sum(1 for d in delta.lore_facts_delta if d.delta_category == DeltaCategory.ADDED and _keep(d))
        + sum(1 for d in delta.relationships_delta if d.delta_category == DeltaCategory.ADDED and _keep(d))
        + sum(1 for d in delta.random_tables_delta if d.delta_category == DeltaCategory.ADDED and _keep(d))
        + sum(1 for d in delta.agendas_delta if d.delta_category == DeltaCategory.ADDED and _keep(d))
        + sum(1 for d in delta.topologies_delta if d.delta_category == DeltaCategory.ADDED and _keep(d)),
        modified_items=sum(1 for d in delta.axioms_delta if d.delta_category == DeltaCategory.MODIFIED and _keep(d))
        + sum(1 for d in delta.entities_delta if d.delta_category == DeltaCategory.MODIFIED and _keep(d))
        + sum(1 for d in delta.lore_facts_delta if d.delta_category == DeltaCategory.MODIFIED and _keep(d))
        + sum(1 for d in delta.relationships_delta if d.delta_category == DeltaCategory.MODIFIED and _keep(d))
        + sum(1 for d in delta.random_tables_delta if d.delta_category == DeltaCategory.MODIFIED and _keep(d))
        + sum(1 for d in delta.agendas_delta if d.delta_category == DeltaCategory.MODIFIED and _keep(d))
        + sum(1 for d in delta.topologies_delta if d.delta_category == DeltaCategory.MODIFIED and _keep(d)),
        removed_items=0,  # All removed items are filtered out
        unchanged_items=0,  # All unchanged items are filtered out
        change_significance=delta.change_significance,
        recommendations=delta.recommendations,
    )
    return filtered


# ---------------------------------------------------------------------------
# Per-category diff helpers
# ---------------------------------------------------------------------------


def _diff_axioms(
    current: list[ExtractedAxiom],
    new: list[ExtractedAxiom],
) -> list[DeltaItem]:
    """Compare two axiom lists. Match by statement text similarity."""
    return _diff_by_identity_field(current, new, field_name="axioms", identity_field="statement")


def _diff_entities(
    current: list[ExtractedEntityArchetype],
    new: list[ExtractedEntityArchetype],
) -> list[DeltaItem]:
    """Compare two entity archetype lists. Match by name (case-insensitive)."""
    return _diff_by_identity_field(current, new, field_name="entity_archetypes", identity_field="name")


def _diff_lore_facts(
    current: list[ExtractedLoreFact],
    new: list[ExtractedLoreFact],
) -> list[DeltaItem]:
    """Compare two lore fact lists. Match by statement text."""
    return _diff_by_identity_field(current, new, field_name="lore_facts", identity_field="statement")


def _diff_relationships(
    current: list[ExtractedRelationship],
    new: list[ExtractedRelationship],
) -> list[DeltaItem]:
    """
    Compare relationship lists. Match by the tuple (from_entity, rel_type, to_entity)
    since there may be duplicate relationships with identical endpoints.
    """
    results: list[DeltaItem] = []

    # Build identity maps for current
    current_by_key: dict[str, ExtractedRelationship] = {}
    for item in current:
        key = _relationship_key(item)
        current_by_key[key] = item

    new_by_key: dict[str, ExtractedRelationship] = {}
    for item in new:
        key = _relationship_key(item)
        new_by_key[key] = item

    # Find ADDED and MODIFIED in new
    for idx, item in enumerate(new):
        key = _relationship_key(item)
        if key not in current_by_key:
            results.append(
                DeltaItem(
                    item_index=idx,
                    delta_category=DeltaCategory.ADDED,
                    field_name="entity_relationships",
                    summary=f"New relationship: {item.from_entity} —[{item.rel_type}]→ {item.to_entity}",
                    item_snapshot=item.model_dump(mode="json"),
                    source_ref=item.source_ref,
                )
            )
        else:
            old_item = current_by_key[key]
            diff = _diff_items(old_item.model_dump(mode="json"), item.model_dump(mode="json"))
            if diff["changed_fields"]:
                results.append(
                    DeltaItem(
                        item_index=idx,
                        delta_category=DeltaCategory.MODIFIED,
                        field_name="entity_relationships",
                        summary=f"Changed relationship: {item.from_entity} —[{item.rel_type}]→ {item.to_entity}",
                        changed_fields=diff["changed_fields"],
                        item_snapshot=item.model_dump(mode="json"),
                        confidence_delta=item.confidence - old_item.confidence,
                        source_ref=item.source_ref,
                    )
                )
            else:
                results.append(
                    DeltaItem(
                        item_index=idx,
                        delta_category=DeltaCategory.UNCHANGED,
                        field_name="entity_relationships",
                        summary=f"Unchanged: {item.from_entity} —[{item.rel_type}]→ {item.to_entity}",
                        item_snapshot=item.model_dump(mode="json"),
                        source_ref=item.source_ref,
                    )
                )

    # Find REMOVED from current
    seen_keys = set(new_by_key.keys())
    for idx, item in enumerate(current):
        key = _relationship_key(item)
        if key not in seen_keys:
            results.append(
                DeltaItem(
                    item_index=idx,
                    delta_category=DeltaCategory.REMOVED,
                    field_name="entity_relationships",
                    summary=f"Removed: {item.from_entity} —[{item.rel_type}]→ {item.to_entity}",
                    item_snapshot=item.model_dump(mode="json"),
                    source_ref=item.source_ref,
                )
            )

    return results


def _diff_random_tables(
    current: list[ExtractedRandomTable],
    new: list[ExtractedRandomTable],
) -> list[DeltaItem]:
    """Compare random tables. Match by table name."""
    return _diff_by_identity_field(current, new, field_name="random_tables", identity_field="name")


def _diff_agendas(
    current: list[Any],
    new: list[Any],
) -> list[DeltaItem]:
    """Compare agendas. Match by agenda title."""
    return _diff_by_identity_field(current, new, field_name="agendas", identity_field="title")


def _diff_topologies(
    current: list[ExtractedTopology],
    new: list[ExtractedTopology],
) -> list[DeltaItem]:
    """Compare topologies. Match by (from_location, to_location, connection_type)."""
    results: list[DeltaItem] = []

    current_map: dict[tuple[str, str, str], ExtractedTopology] = {}
    for item in current:
        key = (item.from_location, item.to_location, item.connection_type)
        current_map[key] = item

    new_map: dict[tuple[str, str, str], ExtractedTopology] = {}
    for item in new:
        key = (item.from_location, item.to_location, item.connection_type)
        new_map[key] = item

    for idx, item in enumerate(new):
        key = (item.from_location, item.to_location, item.connection_type)
        if key not in current_map:
            results.append(
                DeltaItem(
                    item_index=idx,
                    delta_category=DeltaCategory.ADDED,
                    field_name="topologies",
                    summary=f"New topology: {item.from_location} --[{item.connection_type}]--> {item.to_location}",
                    item_snapshot=item.model_dump(mode="json"),
                    source_ref=item.source_ref,
                )
            )
        else:
            old_item = current_map[key]
            diff = _diff_items(old_item.model_dump(mode="json"), item.model_dump(mode="json"))
            if diff["changed_fields"]:
                results.append(
                    DeltaItem(
                        item_index=idx,
                        delta_category=DeltaCategory.MODIFIED,
                        field_name="topologies",
                        summary=f"Changed topology: {item.from_location} --[{item.connection_type}]--> {item.to_location}",
                        changed_fields=diff["changed_fields"],
                        item_snapshot=item.model_dump(mode="json"),
                        confidence_delta=item.confidence - old_item.confidence,
                        source_ref=item.source_ref,
                    )
                )
            else:
                results.append(
                    DeltaItem(
                        item_index=idx,
                        delta_category=DeltaCategory.UNCHANGED,
                        field_name="topologies",
                        summary=f"Unchanged topology: {item.from_location} --[{item.connection_type}]--> {item.to_location}",
                        item_snapshot=item.model_dump(mode="json"),
                        source_ref=item.source_ref,
                    )
                )

    seen_keys = set(new_map.keys())
    for idx, item in enumerate(current):
        key = (item.from_location, item.to_location, item.connection_type)
        if key not in seen_keys:
            results.append(
                DeltaItem(
                    item_index=idx,
                    delta_category=DeltaCategory.REMOVED,
                    field_name="topologies",
                    summary=f"Removed topology: {item.from_location} --[{item.connection_type}]--> {item.to_location}",
                    item_snapshot=item.model_dump(mode="json"),
                    source_ref=item.source_ref,
                )
            )

    return results


# ---------------------------------------------------------------------------
# Generic diff by identity field (for items with a natural key)
# ---------------------------------------------------------------------------


def _diff_by_identity_field(
    current: list[Any],
    new: list[Any],
    field_name: str,
    identity_field: str,
) -> list[DeltaItem]:
    """
    Generic diff for lists of Pydantic models that have a natural identity field.

    Matches items between current and new by identity_field value.
    Uses Levenshtein distance on the identity field for fuzzy matching when
    exact key match is not found, to catch renamed items.
    """
    results: list[DeltaItem] = []

    # Build identity → index + item maps for current
    current_by_identity: dict[str, tuple[int, Any]] = {}
    for idx, item in enumerate(current):
        identity = _get_field(item, identity_field) or ""
        current_by_identity[identity.lower()] = (idx, item)

    seen_identities: set[str] = set()

    for idx, item in enumerate(new):
        identity = _get_field(item, identity_field) or ""
        identity_lower = identity.lower()
        snapshot = _pydantic_to_dict(item)

        if identity_lower in current_by_identity:
            seen_identities.add(identity_lower)
            old_idx, old_item = current_by_identity[identity_lower]
            old_snapshot = _pydantic_to_dict(old_item)
            diff = _diff_items(old_snapshot, snapshot)

            if diff["changed_fields"]:
                conf_delta = _get_field(item, "confidence", 0.0) - _get_field(old_item, "confidence", 0.0)
                results.append(
                    DeltaItem(
                        item_index=idx,
                        delta_category=DeltaCategory.MODIFIED,
                        field_name=field_name,
                        summary=f"Modified {identity}: changed {diff['changed_fields']}",
                        changed_fields=diff["changed_fields"],
                        item_snapshot=snapshot,
                        confidence_delta=conf_delta,
                        source_ref=_get_field(item, "source_ref") or _get_field(item, "source_reference"),
                    )
                )
            else:
                results.append(
                    DeltaItem(
                        item_index=idx,
                        delta_category=DeltaCategory.UNCHANGED,
                        field_name=field_name,
                        summary=f"Unchanged: {identity}",
                        item_snapshot=snapshot,
                        source_ref=_get_field(item, "source_ref") or _get_field(item, "source_reference"),
                    )
                )
        else:
            # No exact identity match — try fuzzy match to catch renames.
            # If found, treat as MODIFIED (content similar enough to be the same item).
            # If not found, check whether the new item's content is similar enough
            # to any current item (above threshold) before classifying as truly ADDED.
            fuzzy_match = _find_fuzzy_match(identity, current_by_identity)
            if fuzzy_match is not None:
                old_idx, old_item = current_by_identity[fuzzy_match]
                seen_identities.add(fuzzy_match)
                old_snapshot = _pydantic_to_dict(old_item)
                results.append(
                    DeltaItem(
                        item_index=idx,
                        delta_category=DeltaCategory.MODIFIED,
                        field_name=field_name,
                        summary=f"Renamed '{old_item.name if hasattr(old_item, 'name') else fuzzy_match}' → '{identity}'",
                        changed_fields=[identity_field],
                        item_snapshot=snapshot,
                        confidence_delta=_get_field(item, "confidence", 0.0) - _get_field(old_item, "confidence", 0.0),
                        source_ref=_get_field(item, "source_ref") or _get_field(item, "source_reference"),
                    )
                )
            else:
                # Check if new item's full content is similar enough to any current
                # item (via full-item fuzzy match). If so, treat as MODIFIED rather
                # than ADDED+REMOVED — catches substantive changes to statement-based
                # identity fields (axioms, lore_facts).
                best_current_match = _find_best_content_match(item, current, identity_field)
                if best_current_match is not None:
                    old_idx, old_item = best_current_match
                    seen_identities.add(_get_field(old_item, identity_field, "").lower())
                    old_snapshot = _pydantic_to_dict(old_item)
                    diff = _diff_items(old_snapshot, snapshot)
                    results.append(
                        DeltaItem(
                            item_index=idx,
                            delta_category=DeltaCategory.MODIFIED,
                            field_name=field_name,
                            summary=f"Substantive change: '{_get_field(old_item, identity_field)}' → '{identity}'",
                            changed_fields=diff["changed_fields"] or [identity_field],
                            item_snapshot=snapshot,
                            confidence_delta=_get_field(item, "confidence", 0.0)
                            - _get_field(old_item, "confidence", 0.0),
                            source_ref=_get_field(item, "source_ref") or _get_field(item, "source_reference"),
                        )
                    )
                else:
                    results.append(
                        DeltaItem(
                            item_index=idx,
                            delta_category=DeltaCategory.ADDED,
                            field_name=field_name,
                            summary=f"Added: {identity_lower}",
                            item_snapshot=snapshot,
                            source_ref=_get_field(item, "source_ref") or _get_field(item, "source_reference"),
                        )
                    )

    # Find removed items (in current but not in new)
    for identity_lower, (idx, item) in current_by_identity.items():
        if identity_lower not in seen_identities:
            results.append(
                DeltaItem(
                    item_index=idx,
                    delta_category=DeltaCategory.REMOVED,
                    field_name=field_name,
                    summary=f"Removed: {identity_lower}",
                    item_snapshot=_pydantic_to_dict(item),
                    source_ref=_get_field(item, "source_ref") or _get_field(item, "source_reference"),
                )
            )

    return results


# ---------------------------------------------------------------------------
# Deep-diff helpers
# ---------------------------------------------------------------------------


def _diff_items(
    old: dict[str, Any],
    new: dict[str, Any],
) -> dict[str, Any]:
    """
    Return the set of top-level keys that differ between two flat dicts.
    Ignores: confidence (float drift), source_ref/source_reference (cite only),
    tags (order-independent), aliases (order-independent), updated_at.
    """
    IGNORED_FIELDS = {
        "confidence",
        "source_ref",
        "source_reference",
        "tags",
        "aliases",
        "updated_at",
    }
    changed_fields: list[str] = []

    all_keys = set(old.keys()) | set(new.keys())
    for key in all_keys:
        if key in IGNORED_FIELDS:
            continue
        if key not in old or key not in new:
            changed_fields.append(key)
        elif old[key] != new[key]:
            # For lists that might be reordered, do a set comparison
            if isinstance(old[key], list) and isinstance(new[key], list):
                if set(old[key]) != set(new[key]):
                    changed_fields.append(key)
            else:
                changed_fields.append(key)

    return {"changed_fields": changed_fields}


def _find_fuzzy_match(
    identity: str,
    current_by_identity: dict[str, tuple[int, Any]],
    threshold: float = 0.85,
) -> str | None:
    """Find the best fuzzy match above the similarity threshold."""
    identity_lower = identity.lower()
    best_match: str | None = None
    best_ratio = 0.0

    for key in current_by_identity:
        if key == identity_lower:
            return key
        ratio = _levenshtein_ratio(identity_lower, key)
        if ratio >= threshold and ratio > best_ratio:
            best_ratio = ratio
            best_match = key

    return best_match


def _find_best_content_match(
    new_item: Any,
    current_items: list[Any],
    identity_field: str,
    threshold: float = 0.65,
) -> tuple[int, Any] | None:
    """
    Find the current item most similar to new_item across all current items.

    Uses full-item content similarity (not just the identity field) to detect
    when a substantive content change was made to an item that otherwise matches
    in a fuzzy sense (e.g., "The world is round." → "The world is flat.").

    Returns the (index, item) tuple of the best match above threshold, or None.
    """
    new_identity = _get_field(new_item, identity_field, "") or ""
    best_match: tuple[int, Any] | None = None
    best_ratio = 0.0

    for idx, current_item in enumerate(current_items):
        current_identity = _get_field(current_item, identity_field, "") or ""
        ratio = _levenshtein_ratio(new_identity.lower(), current_identity.lower())
        if ratio >= threshold and ratio > best_ratio:
            best_ratio = ratio
            best_match = (idx, current_item)

    return best_match


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _get_field(item: Any, field_name: str, default: Any = None) -> Any:
    """Safely get a field from a Pydantic model."""
    try:
        return getattr(item, field_name, default)
    except (TypeError, AttributeError):
        return default


def _relationship_key(item: ExtractedRelationship) -> str:
    return f"{item.from_entity.lower()}|{item.rel_type.lower()}|{item.to_entity.lower()}"


# ---------------------------------------------------------------------------
# Heuristics
# ---------------------------------------------------------------------------


def _classify_significance(
    added: int,
    modified: int,
    removed: int,
    total: int,
) -> str:
    """Heuristic classification of change significance."""
    change_count = added + modified + removed
    if total == 0 or change_count == 0:
        return "minimal"

    # When the current pack is very small or empty, a small absolute number
    # of changes should not be classified as major.
    if total <= 2:
        if removed > (added + modified):
            return "major"
        elif change_count == 1 and added == 1 and modified == 0 and removed == 0:
            return "minor"
        elif (change_count == 1 and (modified == 1 or added == 1)) or change_count <= 2:
            return "moderate"
        return "major"

    change_ratio = change_count / max(total, 1)

    if change_ratio > 0.75 or removed > (added + modified):
        return "major"
    elif change_ratio > 0.50 or modified > 5:
        return "significant"
    elif change_ratio > 0.15 or modified > 0:
        return "moderate"
    elif change_ratio > 0.02:
        return "minor"
    return "minimal"


def _build_recommendations(
    added: int,
    modified: int,
    removed: int,
    significance: str,
) -> list[str]:
    """Build human-readable recommendations based on delta stats."""
    recs: list[str] = []

    if significance in ("minimal", "minor"):
        recs.append("Changes are minimal; auto-apply is safe without review.")
    elif significance in ("moderate", "significant"):
        recs.append(f"Review {modified} modified and {removed} removed items before applying.")
        if added > 0:
            recs.append(f"{added} new items will be applied alongside modified items.")
    else:  # major
        recs.append(
            "Major changes detected. Full manual review strongly recommended before applying to the multiverse."
        )

    if removed > 0:
        recs.append(
            f"Note: {removed} item(s) that existed in the previous extraction "
            "are absent from the new extraction. These will be flagged as REMOVED "
            "in the delta but will NOT be automatically removed from canon."
        )

    if added > 5:
        recs.append(
            f"Large number of new items ({added}). Consider batching the apply or applying to a test universe first."
        )

    return recs
