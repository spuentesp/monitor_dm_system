"""Let a person decide on the claims review couldn't settle (I-17).

Review sends some claims to a person: a number its source doesn't have, a contradiction the book
states both ways, a check that didn't finish. Each decision is stored apart from the ledger, so a
resumed run, which writes the ledger again, can't undo it. An accepted claim joins the book's pack,
which still goes through the usual pack review and CanonKeeper before reaching canon.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TypeVar
from uuid import NAMESPACE_URL, UUID, uuid5

import structlog
from monitor_data.schemas.book_graph import (
    BookRecord,
    BookRecordType,
    BookTree,
    ClaimStatus,
    HeldClaimDecision,
    LedgerEntry,
    ReviewedClaim,
)
from monitor_data.schemas.knowledge_packs import KnowledgePackStatus, KnowledgePackUpdate
from monitor_data.tools.mongodb_tools.book_decomposition import (
    mongodb_acquire_book_lease,
    mongodb_list_book_records,
    mongodb_release_book_lease,
    mongodb_upsert_book_records,
)
from monitor_data.tools.mongodb_tools.knowledge_packs import (
    mongodb_get_knowledge_pack,
    mongodb_update_knowledge_pack,
)
from pydantic import BaseModel, Field

from monitor_agents.book_decomposition.pack_mapper import map_claims, rules_system
from monitor_agents.book_decomposition.store import load_tree

log = structlog.get_logger()

T = TypeVar("T", bound=BaseModel)

_LEASE_SECONDS = 60.0
_MAX_STATEMENT = 2000
# Adding to these would never reach the world the pack was applied to.
_CLOSED_PACK_STATUSES = (KnowledgePackStatus.APPLIED, KnowledgePackStatus.ARCHIVED)


class HeldClaimError(Exception):
    """A decision that can't be made. The message says why, in words a person can act on."""


class HeldClaimNotFound(HeldClaimError):
    pass


class HeldClaimConflict(HeldClaimError):
    """Already decided the other way, the book is busy, or the pack can't take it."""


class SourceSentence(BaseModel):
    id: str
    text: str
    page: int = Field(description="1-indexed")


class ConflictingClaim(BaseModel):
    claim_id: str
    statement: str


class HeldClaim(BaseModel):
    """One claim waiting for a person, with what they need to decide."""

    claim_id: str
    kind: str
    statement: str
    original_statement: str
    name: str | None = None
    reason: str
    page: int = Field(description="1-indexed")
    sources: list[SourceSentence]
    conflicts: list[ConflictingClaim] = Field(default_factory=list)
    decision: HeldClaimDecision | None = None


def pack_id_for(doc_id: str) -> UUID:
    """A fixed pack ID per book, so a crash after creating the pack can't create a second one."""
    return uuid5(NAMESPACE_URL, f"book-decomposition:{doc_id}")


def _ledger(doc_id: str) -> dict[str, LedgerEntry]:
    entries = (LedgerEntry.model_validate(r.data) for r in mongodb_list_book_records(doc_id, BookRecordType.LEDGER))
    return {entry.claim_id: entry for entry in entries}


def load_decisions(doc_id: str) -> dict[str, HeldClaimDecision]:
    records = mongodb_list_book_records(doc_id, BookRecordType.DECISION)
    return {r.key: HeldClaimDecision.model_validate(r.data) for r in records}


def _statement(entry: LedgerEntry) -> str:
    return entry.statement or entry.original_statement


def open_count(ledger: list[LedgerEntry] | dict[str, LedgerEntry], decisions: dict[str, HeldClaimDecision]) -> int:
    """Claims still waiting for a person."""
    entries = ledger.values() if isinstance(ledger, dict) else ledger
    return sum(e.status == ClaimStatus.NEEDS_HUMAN and e.claim_id not in decisions for e in entries)


def list_held_claims(doc_id: str) -> list[HeldClaim]:
    """Every claim review sent to a person, in page order, with any decision already made."""
    ledger = _ledger(doc_id)
    decisions = load_decisions(doc_id)
    tree = load_tree(doc_id)
    nodes = {node.id: node for node in tree.nodes} if tree else {}
    held = []
    for entry in ledger.values():
        if entry.status != ClaimStatus.NEEDS_HUMAN:
            continue
        sources = [
            SourceSentence(id=node_id, text=nodes[node_id].text, page=nodes[node_id].page_start + 1)
            for node_id in entry.source_node_ids
            if node_id in nodes
        ]
        conflicts = [
            ConflictingClaim(claim_id=other, statement=_statement(ledger[other]))
            for other in entry.conflicts_with
            if other in ledger
        ]
        held.append(
            HeldClaim(
                claim_id=entry.claim_id,
                kind=entry.kind.value,
                statement=_statement(entry),
                original_statement=entry.original_statement,
                name=entry.name,
                reason=entry.reason,
                page=entry.page + 1,
                sources=sources,
                conflicts=conflicts,
                decision=decisions.get(entry.claim_id),
            )
        )
    held.sort(key=lambda claim: (claim.page, claim.claim_id))
    return held


def as_reviewed_claim(entry: LedgerEntry, statement: str, tree: BookTree) -> ReviewedClaim:
    """Rebuild a pack-ready claim from its ledger entry and the wording the person accepted."""
    known = {node.id for node in tree.nodes}
    pages = sorted({node.page_start for node in tree.nodes if node.id in entry.source_node_ids}) or [entry.page]
    return ReviewedClaim(
        id=entry.claim_id,
        kind=entry.kind,
        statement=statement,
        name=entry.name,
        entity_type=entry.entity_type,
        subject=entry.subject,
        predicate=entry.predicate,
        object=entry.object,
        source_node_ids=[node_id for node_id in entry.source_node_ids if node_id in known],
        pages=pages,
        merged_from=[],
    )


def accepted_claims(
    ledger: list[LedgerEntry], decisions: dict[str, HeldClaimDecision], tree: BookTree
) -> list[ReviewedClaim]:
    """Claims a person accepted that review still holds, so a rebuilt pack keeps them."""
    return [
        as_reviewed_claim(entry, decisions[entry.claim_id].statement, tree)
        for entry in ledger
        if entry.status == ClaimStatus.NEEDS_HUMAN
        and entry.claim_id in decisions
        and decisions[entry.claim_id].accepted
    ]


@contextmanager
def _book_lease(doc_id: str) -> Iterator[None]:
    owner = f"held-claims-{uuid.uuid4().hex}"
    if not mongodb_acquire_book_lease(doc_id, owner, _LEASE_SECONDS):
        raise HeldClaimConflict("This book is being decomposed right now. Try again when the run finishes.")
    try:
        yield
    finally:
        mongodb_release_book_lease(doc_id, owner)


def _add_to_pack(doc_id: str, claim: ReviewedClaim, tree: BookTree) -> None:
    mapped = map_claims([claim], tree)
    if mapped.held_back:
        raise HeldClaimConflict(f"This claim can't go in the pack: {mapped.held_back[claim.id]}")
    pack = mongodb_get_knowledge_pack(pack_id_for(doc_id))
    if pack is None:
        # The run hasn't made the pack yet. It reads the decision when it does.
        return
    if pack.status in _CLOSED_PACK_STATUSES:
        raise HeldClaimConflict(f"The pack is {pack.status.value}, so a new claim wouldn't reach the world it went to.")

    # Items already there are skipped. After a crash between this write and the decision's, a retry adds nothing.
    def new(existing: Sequence[T], items: Sequence[T]) -> list[T] | None:
        fresh = [item for item in items if item not in existing]
        return [*existing, *fresh] if fresh else None

    system = pack.game_system_data
    rules = new(system.rules if system else [], mapped.rules)
    update = KnowledgePackUpdate(
        axioms=new(pack.axioms, mapped.axioms),
        entity_archetypes=new(pack.entity_archetypes, mapped.entities),
        lore_facts=new(pack.lore_facts, mapped.lore_facts),
    )
    if rules is not None:
        update.game_system_data = (
            rules_system(pack.name, rules) if system is None else system.model_copy(update={"rules": rules})
        )
    if update.model_dump(exclude_none=True):
        mongodb_update_knowledge_pack(pack.id, update)


def decide_held_claim(doc_id: str, claim_id: str, *, accept: bool, statement: str | None = None) -> HeldClaimDecision:
    """Accept or reject one held claim. Accepting adds it to the pack. Repeating a decision is safe."""
    wording = (statement or "").strip()
    if len(wording) > _MAX_STATEMENT:
        raise HeldClaimConflict(f"The wording is longer than {_MAX_STATEMENT} characters.")
    with _book_lease(doc_id):
        entry = _ledger(doc_id).get(claim_id)
        if entry is None or entry.status != ClaimStatus.NEEDS_HUMAN:
            raise HeldClaimNotFound(f"No claim {claim_id} is waiting for a person in this book.")
        previous = load_decisions(doc_id).get(claim_id)
        if previous is not None:
            # A second click, or a retry after a lost reply. Doing it again would add a duplicate.
            if previous.accepted == accept:
                return previous
            raise HeldClaimConflict("This claim was already decided the other way.")
        decision = HeldClaimDecision(
            claim_id=claim_id,
            accepted=accept,
            statement=wording or _statement(entry),
            decided_at=datetime.now(UTC),
        )
        if accept:
            tree = load_tree(doc_id)
            if tree is None:
                raise HeldClaimConflict("The book's text isn't stored, so the claim can't cite it.")
            _add_to_pack(doc_id, as_reviewed_claim(entry, decision.statement, tree), tree)
        mongodb_upsert_book_records(
            doc_id,
            BookRecordType.DECISION,
            [BookRecord(key=claim_id, data=decision.model_dump(mode="json"))],
        )
    log.info("held_claim_decided", doc_id=doc_id, claim_id=claim_id, accepted=accept)
    return decision


def open_review_count(doc_id: str) -> int:
    return open_count(_ledger(doc_id), load_decisions(doc_id))
