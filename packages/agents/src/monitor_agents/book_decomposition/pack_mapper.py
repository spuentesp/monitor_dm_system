"""Turn reviewed claims into a KnowledgePack, so they reach canon by the existing route (I-17).

The pack goes through the usual review, duplicate and contradiction checks, and CanonKeeper. Every
item carries its source sentences as `evidence_refs`. A claim too long for its field is held back
for a person instead of being cut, because cutting could remove a condition.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import UUID

from monitor_data.schemas.base import ProfileEvidenceRef
from monitor_data.schemas.book_graph import AtomKind, BookNode, BookTree, ReviewedClaim
from monitor_data.schemas.game_systems import GameRule, GameRuleType
from monitor_data.schemas.knowledge_packs import (
    EmbeddedGameSystem,
    ExtractedAxiom,
    ExtractedEntityArchetype,
    ExtractedLoreFact,
    KnowledgePackCreate,
    KnowledgePackStatus,
    KnowledgePackType,
)
from pydantic import ValidationError

from monitor_agents.book_decomposition.review import _heading_path, _nearest_headings

_ENTITY_TYPE_NAMES = ("character", "faction", "location", "object", "concept", "organization")
_DEFAULT_ENTITY_TYPE = "concept"
_MAX_SUB_TYPE = 100
# Models write freeform types such as "device" or "Ranged Weapon". Schema types are matched first.
_ENTITY_TYPE_WORDS = {
    "character": ("person", "people", "npc", "individual", "leader", "noble", "human"),
    "faction": ("house", "guild", "order", "school"),
    "location": ("place", "planet", "city", "world", "region", "zone"),
    "object": (
        "asset",
        "item",
        "device",
        "weapon",
        "vehicle",
        "armor",
        "armour",
        "equipment",
        "tool",
        "ornithopter",
        "shield",
        "launcher",
        "gun",
        "knife",
        "technology",
        "variant",
        "unit",
    ),
    "organization": ("group", "company", "military"),
}
_RULE_NAME_WORDS = 10
_MAX_RULE_NAME = 200
_MAX_NOTE = 300
_MAX_SECTION_PATH = 300
_LORE_LIMIT = 1000
_STATEMENT_LIMITS = {
    AtomKind.AXIOM: 500,
    AtomKind.RULE: 2000,
    AtomKind.ENTITY: 1000,
    AtomKind.FACT: _LORE_LIMIT,
    AtomKind.RELATIONSHIP: _LORE_LIMIT,
}


@dataclass
class MappedClaims:
    """What fits in a pack, and what's held back for a person, with the reason."""

    axioms: list[ExtractedAxiom] = field(default_factory=list)
    entities: list[ExtractedEntityArchetype] = field(default_factory=list)
    lore_facts: list[ExtractedLoreFact] = field(default_factory=list)
    rules: list[GameRule] = field(default_factory=list)
    held_back: dict[str, str] = field(default_factory=dict)

    @property
    def mapped_count(self) -> int:
        return len(self.axioms) + len(self.entities) + len(self.lore_facts) + len(self.rules)


def normalize_entity_type(raw: str | None) -> str:
    """Map a model's freeform entity type onto the schema's six. Its wording stays as sub_type."""
    words = set(re.findall(r"[a-z]+", (raw or "").casefold()))
    for name in _ENTITY_TYPE_NAMES:
        if name in words:
            return name
    for name, known in _ENTITY_TYPE_WORDS.items():
        if words & set(known):
            return name
    return _DEFAULT_ENTITY_TYPE


def _evidence(
    claim: ReviewedClaim, book: BookTree, by_id: dict[str, BookNode], nearest: dict[str, str]
) -> list[ProfileEvidenceRef]:
    refs = []
    for node_id in claim.source_node_ids:
        node = by_id[node_id]
        refs.append(
            ProfileEvidenceRef(
                ref=f"{book.doc_id}:{node_id}",
                section_path=_heading_path(node, by_id, nearest)[:_MAX_SECTION_PATH] or None,
                page_hint=node.page_start + 1,
                note=node.text[:_MAX_NOTE] or None,
            )
        )
    return refs


def _rule_name(statement: str) -> str:
    words = statement.split()
    name = " ".join(words[:_RULE_NAME_WORDS])
    return (name + "…" if len(words) > _RULE_NAME_WORDS else name)[:_MAX_RULE_NAME]


def map_claims(claims: Sequence[ReviewedClaim], book: BookTree) -> MappedClaims:
    """Sort reviewed claims into pack items. Every claim ends up mapped or held back."""
    by_id = {node.id: node for node in book.nodes}
    nearest = _nearest_headings(book)
    mapped = MappedClaims()
    for claim in claims:
        # The pack fields silently trim long text, so this has to be checked first.
        limit = _STATEMENT_LIMITS.get(claim.kind, _LORE_LIMIT)
        if len(claim.statement) > limit:
            mapped.held_back[claim.id] = f"Longer than the {limit} characters its pack field holds"
            continue
        evidence = _evidence(claim, book, by_id, nearest)
        ref = evidence[0].ref[:200] if evidence else None
        try:
            if claim.kind == AtomKind.AXIOM:
                mapped.axioms.append(ExtractedAxiom(statement=claim.statement, source_ref=ref, evidence_refs=evidence))
            elif claim.kind == AtomKind.RULE:
                mapped.rules.append(
                    GameRule(
                        name=_rule_name(claim.statement),
                        rule_type=GameRuleType.CUSTOM,
                        description=claim.statement,
                        source_ref=ref,
                        evidence_refs=evidence,
                    )
                )
            elif claim.kind == AtomKind.ENTITY and claim.name:
                mapped.entities.append(
                    ExtractedEntityArchetype(
                        name=claim.name,
                        entity_type=normalize_entity_type(claim.entity_type),
                        sub_type=(claim.entity_type or "")[:_MAX_SUB_TYPE].strip() or None,
                        description=claim.statement,
                        source_ref=ref,
                        evidence_refs=evidence,
                    )
                )
            else:
                is_link = claim.kind == AtomKind.RELATIONSHIP
                names = [claim.subject, claim.object] if is_link else [claim.name]
                mapped.lore_facts.append(
                    ExtractedLoreFact(
                        statement=claim.statement,
                        fact_type="relationship" if is_link else "state",
                        involved_entities=[name for name in names if name],
                        source_ref=ref,
                        evidence_refs=evidence,
                    )
                )
        except ValidationError as exc:
            mapped.held_back[claim.id] = str(exc.errors()[0]["msg"])[:200]
    return mapped


def rules_system(name: str, rules: list[GameRule]) -> EmbeddedGameSystem:
    """The rules-only system a decomposed book's pack carries."""
    return EmbeddedGameSystem(
        name=name[:200],
        description="Rules from book decomposition. This holds rules only, not a full system.",
        rules=rules,
        needs_review=True,
    )


def build_pack(
    mapped: MappedClaims,
    *,
    pack_id: UUID,
    name: str,
    pack_type: KnowledgePackType,
    source_document_id: UUID,
    job_id: UUID,
) -> KnowledgePackCreate:
    """Create a pack that waits for review like any other, and never applies itself."""
    system = rules_system(name, mapped.rules) if mapped.rules else None
    return KnowledgePackCreate(
        pack_id=pack_id,
        name=name[:200],
        pack_type=pack_type,
        status=KnowledgePackStatus.READY,
        source_document_ids=[source_document_id],
        ingestion_job_id=job_id,
        tags=["book_decomposition"],
        axioms=mapped.axioms,
        entity_archetypes=mapped.entities,
        lore_facts=mapped.lore_facts,
        game_system_data=system,
    )
