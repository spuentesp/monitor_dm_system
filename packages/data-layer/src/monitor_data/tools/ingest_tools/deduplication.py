"""
Cross-pack deduplication logic (P2-7).

LAYER: 1 (data-layer)

Before a KnowledgePack is applied to the multiverse, checks its items against
all previously-applied packs in the target universe/multiverse to detect
duplicate or near-duplicate content. Duplicates are flagged for review or
auto-resolved based on strategy.

KEY CONCEPTS:
- EXACT: identical identity field value (case-insensitive)
- SEMANTIC: fuzzy match above threshold (0.75) — similar but not identical
- CONFLICTING: same identity, different content — needs manual resolution
- SUBSUMED: one item is a more specific version of another

The first item in each DuplicateGroup is always the NEW candidate.
"""

from __future__ import annotations

import hashlib
from typing import Any

from monitor_data.schemas.deduplication import (
    DeduplicationResult,
    DeduplicationStrategy,
    DuplicateCategory,
    DuplicateGroup,
    DuplicateItemRef,
)
from monitor_data.schemas.knowledge_packs import KnowledgePackResponse
from monitor_data.tools._shared import pydantic_to_dict as _pydantic_to_dict
from monitor_data.tools.ingest_tools.delta_detection import (  # type: ignore
    _levenshtein_ratio,
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_deduplication(
    new_pack: KnowledgePackResponse,
    existing_packs: list[KnowledgePackResponse],
    multiverse_id: str,
    universe_id: str | None = None,
    semantic_threshold: float = 0.75,
) -> DeduplicationResult:
    """
    Check a new KnowledgePack for duplicates against existing packs.

    Args:
        new_pack: The KnowledgePack being applied
        existing_packs: Previously-applied packs in the target universe/multiverse
        multiverse_id: Multiverse being applied to
        universe_id: Optional specific universe
        semantic_threshold: Minimum Levenshtein ratio for SEMANTIC detection (default 0.75)

    Returns:
        DeduplicationResult with all duplicate groups and auto-resolution counts
    """
    duplicate_groups: list[DuplicateGroup] = []

    all_existing_by_field = _build_all_identity_maps(existing_packs)

    # Process each item category
    for category, identity_field in _ITEM_CATEGORIES:
        new_items = _get_items(new_pack, category)
        if not new_items:
            continue

        existing_by_identity = all_existing_by_field.get(category, {})

        for _idx, item in enumerate(new_items):
            identity = _get_item_identity(item, identity_field)
            if not identity:
                continue

            identity_lower = identity.lower()
            content_hash = _compute_content_hash(item)
            item_snapshot = _pydantic_to_dict(item)

            # Check for exact match first
            exact_match = _find_exact_match(identity_lower, existing_by_identity)

            if exact_match is not None:
                # EXACT or CONFLICTING duplicate
                old_item, old_pack_id, old_hash = exact_match
                old_snapshot = _pydantic_to_dict(old_item)
                old_content_hash = _compute_content_hash(old_item)
                old_identity_value = _get_item_identity(old_item, identity_field) or ""

                if content_hash == old_content_hash:
                    # EXACT duplicate — same content
                    category_type = DuplicateCategory.EXACT
                    strategy, reason = _recommend_strategy(category_type, item, old_item, identity_field)
                    duplicate_groups.append(
                        _build_duplicate_group(
                            duplicate_id=_make_duplicate_id(category, identity_lower),
                            category_type=category_type,
                            field_name=category,
                            identity_field=identity_field,
                            strategy=strategy,
                            strategy_reason=reason,
                            similarity_score=1.0,
                            new_item=item,
                            new_pack_id=new_pack.id,
                            new_identity=identity,
                            new_confidence=_get_confidence(item),
                            new_content_hash=content_hash,
                            new_snapshot=item_snapshot,
                            old_item=old_item,
                            old_pack_id=old_pack_id,
                            old_identity=old_identity_value,
                            old_confidence=_get_confidence(old_item),
                            old_content_hash=old_content_hash,
                            old_snapshot=old_snapshot,
                        )
                    )
                else:
                    # CONFLICTING — same identity, different content
                    # Check if this is a negation-style conflict (semantic but opposing)
                    ratio = _levenshtein_ratio(identity_lower, old_identity_value.lower())
                    is_negation_conflict = _is_likely_negation_conflict(identity_lower, old_identity_value.lower())
                    if is_negation_conflict:
                        strategy = DeduplicationStrategy.REVIEW
                        reason = (
                            f"Conflicting content for '{identity}': new source says "
                            f"'{identity}', existing canon says '{old_identity_value}'. "
                            f"Manual resolution required."
                        )
                        category_type = DuplicateCategory.CONFLICTING
                    else:
                        strategy = DeduplicationStrategy.REVIEW
                        reason = (
                            f"Content differs for identity '{identity_lower}': "
                            f"new={identity!r} vs existing={old_identity_value!r}. "
                            f"Manual review recommended."
                        )
                        category_type = DuplicateCategory.CONFLICTING
                    duplicate_groups.append(
                        _build_duplicate_group(
                            duplicate_id=_make_duplicate_id(category, identity_lower),
                            category_type=category_type,
                            field_name=category,
                            identity_field=identity_field,
                            strategy=strategy,
                            strategy_reason=reason,
                            similarity_score=ratio,
                            new_item=item,
                            new_pack_id=new_pack.id,
                            new_identity=identity,
                            new_confidence=_get_confidence(item),
                            new_content_hash=content_hash,
                            new_snapshot=item_snapshot,
                            old_item=old_item,
                            old_pack_id=old_pack_id,
                            old_identity=old_identity_value,
                            old_confidence=_get_confidence(old_item),
                            old_content_hash=old_content_hash,
                            old_snapshot=old_snapshot,
                        )
                    )
            else:
                # No exact match — check for negation-style conflict before semantic match.
                # Two items with very similar text but opposing assertions are CONFLICTING
                # not merely semantic variants.
                negation_conflict = _find_negation_conflict(identity, existing_by_identity, identity_field)
                if negation_conflict is not None:
                    old_item, old_pack_id, old_identity_value, ratio = negation_conflict
                    old_snapshot = _pydantic_to_dict(old_item)
                    old_content_hash = _compute_content_hash(old_item)
                    duplicate_groups.append(
                        _build_duplicate_group(
                            duplicate_id=_make_duplicate_id(category, identity_lower),
                            category_type=DuplicateCategory.CONFLICTING,
                            field_name=category,
                            identity_field=identity_field,
                            strategy=DeduplicationStrategy.REVIEW,
                            strategy_reason=(
                                f"Conflicting content for '{identity}': new says '{identity}', "
                                f"existing canon says '{old_identity_value}'. "
                                f"Manual resolution required."
                            ),
                            similarity_score=ratio,
                            new_item=item,
                            new_pack_id=new_pack.id,
                            new_identity=identity,
                            new_confidence=_get_confidence(item),
                            new_content_hash=content_hash,
                            new_snapshot=item_snapshot,
                            old_item=old_item,
                            old_pack_id=old_pack_id,
                            old_identity=old_identity_value,
                            old_confidence=_get_confidence(old_item),
                            old_content_hash=old_content_hash,
                            old_snapshot=old_snapshot,
                        )
                    )
                else:
                    # No exact match — check semantic similarity at lower threshold
                    semantic_match = _find_semantic_match(identity, existing_by_identity, threshold=0.70)
                    if semantic_match is not None:
                        old_item, old_pack_id, ratio = semantic_match
                        old_snapshot = _pydantic_to_dict(old_item)
                        old_content_hash = _compute_content_hash(old_item)
                        old_identity_value = _get_item_identity(old_item, identity_field) or ""
                        strategy, reason = _recommend_strategy(
                            DuplicateCategory.SEMANTIC, item, old_item, identity_field
                        )
                        duplicate_groups.append(
                            _build_duplicate_group(
                                duplicate_id=_make_duplicate_id(category, identity_lower),
                                category_type=DuplicateCategory.SEMANTIC,
                                field_name=category,
                                identity_field=identity_field,
                                strategy=strategy,
                                strategy_reason=reason,
                                similarity_score=ratio,
                                new_item=item,
                                new_pack_id=new_pack.id,
                                new_identity=identity,
                                new_confidence=_get_confidence(item),
                                new_content_hash=content_hash,
                                new_snapshot=item_snapshot,
                                old_item=old_item,
                                old_pack_id=old_pack_id,
                                old_identity=old_identity_value,
                                old_confidence=_get_confidence(old_item),
                                old_content_hash=old_content_hash,
                                old_snapshot=old_snapshot,
                            )
                        )

    auto_resolvable = sum(1 for g in duplicate_groups if g.strategy != DeduplicationStrategy.REVIEW)
    review_required = len(duplicate_groups) - auto_resolvable

    return DeduplicationResult(
        new_pack_id=new_pack.id,
        universe_id=universe_id,
        multiverse_id=multiverse_id,
        duplicate_groups=duplicate_groups,
        auto_resolvable_count=auto_resolvable,
        review_required_count=review_required,
        total_items_checked=sum(len(_get_items(new_pack, cat)) for cat, _ in _ITEM_CATEGORIES),
    )


# ---------------------------------------------------------------------------
# Per-category identity maps
# ---------------------------------------------------------------------------

# (field_name, identity_field) for each category
_ITEM_CATEGORIES = [
    ("axioms", "statement"),
    ("entity_archetypes", "name"),
    ("lore_facts", "statement"),
    ("entity_relationships", "rel_type"),  # key is from_entity|rel_type|to_entity
    ("random_tables", "name"),
    ("agendas", "title"),
    ("topologies", "connection_type"),  # key is from_location|to_location|connection_type
    ("tone_profiles", "name"),
    ("character_profiles", "name"),
    ("generation_templates", "name"),
    ("plot_threads", "title"),
]


def _build_all_identity_maps(
    existing_packs: list[KnowledgePackResponse],
) -> dict[str, dict[str, tuple[Any, str | None, str]]]:
    """
    Build a unified identity→(item, pack_id, content_hash) map across all existing packs.

    Structure: { field_name: { identity_lower: (item, pack_id, hash) } }
    """
    result: dict[str, dict[str, tuple[Any, str | None, str]]] = {}

    for pack in existing_packs:
        for field_name, identity_field in _ITEM_CATEGORIES:
            if field_name not in result:
                result[field_name] = {}

            items = _get_items(pack, field_name)
            for item in items:
                identity = _get_item_identity(item, identity_field)
                if not identity:
                    continue
                identity_lower = identity.lower()
                content_hash = _compute_content_hash(item)

                # Don't overwrite an existing entry (first-seen wins)
                if identity_lower not in result[field_name]:
                    result[field_name][identity_lower] = (item, str(pack.id) if pack.id else None, content_hash)

    return result


def _get_items(pack: KnowledgePackResponse, field_name: str) -> list[Any]:
    """Get the item list for a given field name from a KnowledgePack."""
    return getattr(pack, field_name, []) or []


def _get_item_identity(item: Any, identity_field: str) -> str | None:
    """Get the identity field value from an item."""
    try:
        return getattr(item, identity_field, None) or None
    except (TypeError, AttributeError):
        return None


def _get_confidence(item: Any) -> float:
    try:
        return float(getattr(item, "confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _get_source_ref(item: Any) -> str | None:
    try:
        return getattr(item, "source_ref", None)
    except (TypeError, AttributeError):
        return None


def _compute_content_hash(item: Any) -> str:
    """Compute MD5 hex digest of the canonical JSON representation of an item."""
    try:
        data = _pydantic_to_dict(item)
        # Remove fields that vary between extractions
        for excl in ("source_ref", "confidence", "updated_at"):
            data.pop(excl, None)
        canonical = "|".join(f"{k}={data[k]}" for k in sorted(data.keys()) if data[k] is not None)
        return hashlib.md5(canonical.encode()).hexdigest()
    except Exception:
        return hashlib.md5(repr(item).encode()).hexdigest()


# ---------------------------------------------------------------------------
# DuplicateGroup builder helper
# ---------------------------------------------------------------------------


def _build_duplicate_group(
    duplicate_id: str,
    category_type: DuplicateCategory,
    field_name: str,
    identity_field: str,
    strategy: DeduplicationStrategy,
    strategy_reason: str,
    similarity_score: float,
    new_item: Any,
    new_pack_id: Any,
    new_identity: str,
    new_confidence: float,
    new_content_hash: str,
    new_snapshot: dict[str, Any],
    old_item: Any,
    old_pack_id: Any,
    old_identity: str,
    old_confidence: float,
    old_content_hash: str,
    old_snapshot: dict[str, Any],
) -> DuplicateGroup:
    """Construct a DuplicateGroup from known values."""
    return DuplicateGroup(
        duplicate_id=duplicate_id,
        category=category_type,
        field_name=field_name,
        identity_field=identity_field,
        strategy=strategy,
        strategy_reason=strategy_reason,
        similarity_score=similarity_score,
        items=[
            DuplicateItemRef(
                item_index=0,
                pack_id=new_pack_id,
                identity_value=new_identity,
                confidence=new_confidence,
                content_hash=new_content_hash,
                item_snapshot=new_snapshot,
                source_ref=_get_source_ref(new_item),
            ),
            DuplicateItemRef(
                item_index=0,
                pack_id=old_pack_id,
                identity_value=old_identity,
                confidence=old_confidence,
                content_hash=old_content_hash,
                item_snapshot=old_snapshot,
                source_ref=_get_source_ref(old_item),
            ),
        ],
    )


def _is_likely_negation_conflict(new_identity: str, old_identity: str) -> bool:
    """
    Detect negation-style conflicts where two strings are semantically
    opposites (e.g., 'Magic is real' vs 'Magic is NOT real').

    Returns True if the strings are similar but one contains negation markers.
    """
    negation_words = {"not", "no", "never", "cannot", "doesn't", "isnt", "dont", "wont", "cant"}
    new_lower = new_identity.lower()
    old_lower = old_identity.lower()
    new_words = set(new_lower.split())
    old_words = set(old_lower.split())
    new_has_negation = bool(new_words & negation_words)
    old_has_negation = bool(old_words & negation_words)
    if new_has_negation != old_has_negation:
        # One has negation, one doesn't — check how similar they are
        ratio = _levenshtein_ratio(new_lower, old_lower)
        return ratio >= 0.70
    return False


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------


def _find_exact_match(
    identity_lower: str,
    existing_by_identity: dict[str, tuple[Any, str | None, str]],
) -> tuple[Any, str | None, str] | None:
    """Return (item, pack_id, content_hash) if an exact identity match exists."""
    return existing_by_identity.get(identity_lower)


def _find_negation_conflict(
    new_identity: str,
    existing_by_identity: dict[str, tuple[Any, str | None, str]],
    identity_field: str = "statement",
) -> tuple[Any, str | None, str, float] | None:
    """
    Detect a negation-style conflict: new and existing are similar text but one
    contains negation while the other doesn't (e.g., 'Magic is real' vs 'Magic is NOT real').

    Returns (old_item, old_pack_id, old_identity_value, ratio) or None.
    """
    negation_words = {"not", "no", "never", "cannot", "doesnt", "isnt", "dont", "wont", "cant"}
    new_words = set(new_identity.lower().split())
    new_has_negation = bool(new_words & negation_words)
    new_lower = new_identity.lower()

    for key, (item, pack_id, _content_hash) in existing_by_identity.items():
        old_identity_value = _get_item_identity(item, identity_field) or ""
        old_words = set(old_identity_value.lower().split())
        old_has_negation = bool(old_words & negation_words)

        if new_has_negation != old_has_negation:
            ratio = _levenshtein_ratio(new_lower, key)
            if ratio >= 0.70:
                return (item, pack_id, old_identity_value, ratio)

    return None


def _find_semantic_match(
    new_identity: str,
    existing_by_identity: dict[str, tuple[Any, str | None, str]],
    threshold: float = 0.75,
) -> tuple[Any, str | None, float] | None:
    """
    Find the best semantic match above the threshold.

    Returns (item, pack_id, similarity_ratio) or None.
    """
    new_lower = new_identity.lower()
    best: tuple[Any, str | None, float] | None = None
    best_ratio = 0.0

    for key, (item, pack_id, _content_hash) in existing_by_identity.items():
        ratio = _levenshtein_ratio(new_lower, key)
        if ratio >= threshold and ratio > best_ratio:
            best_ratio = ratio
            best = (item, pack_id, ratio)

    return best


# ---------------------------------------------------------------------------
# Strategy recommendation
# ---------------------------------------------------------------------------


def _recommend_strategy(
    category: DuplicateCategory,
    new_item: Any,
    existing_item: Any,
    identity_field: str,
) -> tuple[DeduplicationStrategy, str]:
    """
    Recommend a deduplication strategy for a duplicate group.

    Heuristics:
    - EXACT + same confidence → KEEP_NEW (newer source wins)
    - EXACT + existing higher confidence → KEEP_EXISTING (more confident source wins)
    - SEMANTIC + new higher confidence → KEEP_NEW
    - SEMANTIC + existing higher confidence → KEEP_EXISTING
    - SEMANTIC + new item is more specific (longer identity) → KEEP_NEW (more detail wins)
    - CONFLICTING → REVIEW always
    """
    new_conf = _get_confidence(new_item)
    existing_conf = _get_confidence(existing_item)

    if category == DuplicateCategory.CONFLICTING:
        return DeduplicationStrategy.REVIEW, ("Conflicting content detected. Manual review required.")

    if category == DuplicateCategory.EXACT:
        if existing_conf >= new_conf:
            return (
                DeduplicationStrategy.KEEP_EXISTING,
                f"Existing item has equal or higher confidence ({existing_conf:.2f} vs {new_conf:.2f}). "
                f"Canon authority preserved.",
            )
        return (
            DeduplicationStrategy.KEEP_NEW,
            f"New item has higher confidence ({new_conf:.2f} vs {existing_conf:.2f}). Newer source supersedes.",
        )

    # SEMANTIC
    new_identity = _get_item_identity(new_item, identity_field) or ""
    existing_identity = _get_item_identity(existing_item, identity_field) or ""

    if len(new_identity) > len(existing_identity):
        return (
            DeduplicationStrategy.KEEP_NEW,
            f"New item is more specific ({len(new_identity)} chars vs {len(existing_identity)}). "
            f"More detailed description wins.",
        )
    if existing_conf > new_conf + 0.1:
        return (
            DeduplicationStrategy.KEEP_EXISTING,
            f"Existing item significantly more confident ({existing_conf:.2f} vs {new_conf:.2f}). "
            f"Canon authority preserved.",
        )
    return (
        DeduplicationStrategy.KEEP_NEW,
        f"New item has similar or better confidence ({new_conf:.2f} vs {existing_conf:.2f}). Newer source wins.",
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _make_duplicate_id(field_name: str, identity_lower: str) -> str:
    """Create a stable ID for a duplicate group."""
    raw = f"{field_name}:{identity_lower}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]
