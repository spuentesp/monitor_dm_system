"""Mapping reviewed claims to a pack: every claim is accounted for, with evidence (I-17)."""

from uuid import uuid4

import pytest
from monitor_agents.book_decomposition.pack_mapper import build_pack, map_claims
from monitor_data.schemas.book_graph import (
    AtomKind,
    BookNode,
    BookNodeKind,
    BookTree,
    DecompositionReport,
    ReviewedClaim,
)
from monitor_data.schemas.knowledge_packs import KnowledgePackStatus, KnowledgePackType


def _book() -> BookTree:
    nodes = [
        BookNode(id="root", doc_id="d", kind=BookNodeKind.BOOK, seq=0, page_start=0, page_end=0),
        BookNode(id="ch", doc_id="d", kind=BookNodeKind.DIVISION, parent_id="root", seq=1, text="Chapter 6", page_start=4, page_end=4),
        BookNode(id="p", doc_id="d", kind=BookNodeKind.PARAGRAPH, parent_id="ch", seq=2, text="Source text.", page_start=4, page_end=4),
        BookNode(id="s", doc_id="d", kind=BookNodeKind.SENTENCE, parent_id="p", seq=3, text="Source text.", page_start=4, page_end=4),
    ]
    return BookTree(doc_id="doc", title="T", decomposer_version="4", content_hash="x", nodes=nodes, report=DecompositionReport())


def _claim(kind: AtomKind, statement: str = "A statement.", **fields) -> ReviewedClaim:
    return ReviewedClaim(id=str(uuid4()), kind=kind, statement=statement, source_node_ids=["s"], pages=[4], merged_from=[], **fields)


@pytest.mark.unit
def test_each_kind_goes_to_its_pack_field_with_evidence():
    mapped = map_claims(
        [
            _claim(AtomKind.AXIOM),
            _claim(AtomKind.RULE, "Spend 2 points to run further."),
            _claim(AtomKind.FACT),
            _claim(AtomKind.RELATIONSHIP, subject="Guild", predicate="controls", object="travel"),
            _claim(AtomKind.ENTITY, name="Spacing Guild", entity_type="faction"),
        ],
        _book(),
    )
    assert (len(mapped.axioms), len(mapped.rules), len(mapped.lore_facts), len(mapped.entities)) == (1, 1, 2, 1)
    assert mapped.rules[0].description == "Spend 2 points to run further."
    evidence = mapped.axioms[0].evidence_refs[0]
    assert evidence.ref == "doc:s" and evidence.section_path == "Chapter 6" and evidence.page_hint == 5
    assert evidence.note == "Source text."
    relationship = next(f for f in mapped.lore_facts if f.fact_type == "relationship")
    assert relationship.involved_entities == ["Guild", "travel"]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("faction", "faction"),
        ("Asset", "object"),
        ("Ranged Weapon", "object"),
        ("ornithopter variant", "object"),
        ("organization", "organization"),
        ("planet", "location"),
        ("Keyword", "concept"),
        (None, "concept"),
    ],
)
def test_freeform_entity_types_map_to_the_schema_and_keep_their_wording(raw, expected):
    mapped = map_claims([_claim(AtomKind.ENTITY, name="Thing", entity_type=raw)], _book())
    assert mapped.lore_facts == []
    entity = mapped.entities[0]
    assert entity.entity_type == expected
    assert entity.sub_type == raw


@pytest.mark.unit
def test_entity_without_a_name_is_kept_as_a_fact():
    mapped = map_claims([_claim(AtomKind.ENTITY, entity_type="object")], _book())
    assert mapped.entities == [] and len(mapped.lore_facts) == 1


@pytest.mark.unit
def test_claim_too_long_for_its_field_is_held_back_and_not_cut():
    claim = _claim(AtomKind.AXIOM, "word " * 200)
    mapped = map_claims([claim], _book())
    assert mapped.axioms == [] and claim.id in mapped.held_back
    assert "500" in mapped.held_back[claim.id]


@pytest.mark.unit
def test_claim_exactly_at_the_limit_is_kept_whole():
    statement = "w" * 500
    assert map_claims([_claim(AtomKind.AXIOM, statement)], _book()).axioms[0].statement == statement


@pytest.mark.unit
def test_every_claim_is_mapped_or_held_back():
    claims = [_claim(AtomKind.AXIOM), _claim(AtomKind.AXIOM, "word " * 200), _claim(AtomKind.RULE)]
    mapped = map_claims(claims, _book())
    assert mapped.mapped_count + len(mapped.held_back) == len(claims)


@pytest.mark.unit
def test_long_rule_gets_a_short_name_and_keeps_its_full_text():
    statement = " ".join(f"word{i}" for i in range(30))
    rule = map_claims([_claim(AtomKind.RULE, statement)], _book()).rules[0]
    assert rule.description == statement and rule.name.endswith("…") and len(rule.name.split()) == 10


@pytest.mark.unit
def test_pack_waits_for_review_and_holds_rules_in_the_game_system():
    mapped = map_claims([_claim(AtomKind.RULE), _claim(AtomKind.AXIOM)], _book())
    pack_id, doc, job = uuid4(), uuid4(), uuid4()
    pack = build_pack(mapped, pack_id=pack_id, name="Dune", pack_type=KnowledgePackType.RULEBOOK, source_document_id=doc, job_id=job)
    assert pack.pack_id == pack_id and pack.status == KnowledgePackStatus.READY
    assert pack.game_system_data is not None and pack.game_system_data.needs_review
    assert len(pack.game_system_data.rules) == 1
    assert pack.source_document_ids == [doc] and pack.ingestion_job_id == job


@pytest.mark.unit
def test_pack_with_no_rules_has_no_game_system():
    mapped = map_claims([_claim(AtomKind.AXIOM)], _book())
    pack = build_pack(mapped, pack_id=uuid4(), name="L", pack_type=KnowledgePackType.MISC, source_document_id=uuid4(), job_id=uuid4())
    assert pack.game_system_data is None
