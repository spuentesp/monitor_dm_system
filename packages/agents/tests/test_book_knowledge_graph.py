"""Tests for the knowledge graph: only what traces back to claims is kept (prototype, I-17)."""

from pathlib import Path

import pytest
from monitor_agents.book_decomposition.knowledge_graph import (
    GRAPH_INSTRUCTIONS,
    LORE_PREDICATES,
    RULE_PREDICATES,
    GraphBatch,
    GraphEdge,
    GraphLog,
    GraphNode,
    GraphReport,
    KnowledgeGraph,
    apply_merges,
    assemble_graph,
    build_domain_tree,
    claim_domains,
    format_claims,
    graph_search,
    keyword_search,
)
from monitor_data.schemas.book_graph import (
    AtomKind,
    BookNode,
    BookNodeKind,
    BookTree,
    DecompositionReport,
    ReviewedClaim,
)


def _claim(claim_id: str, statement: str) -> ReviewedClaim:
    return ReviewedClaim(id=claim_id, kind=AtomKind.RULE, statement=statement, source_node_ids=[f"s-{claim_id}"], pages=[0], merged_from=[])


CLAIMS = [_claim("a", "Momentum is spent on skill tests."), _claim("b", "Threat opposes Momentum.")]


def _build(relationships, entities=()):
    answer = GraphBatch.model_validate({"entities": list(entities), "relationships": relationships})
    return assemble_graph([(CLAIMS, answer)], GraphReport())


def _rel(subject="Momentum", predicate="used_in", target="skill test", cites=("C1",)):
    return {"subject": subject, "predicate": predicate, "object": target, "cites": list(cites)}


@pytest.mark.unit
def test_relationship_keeps_its_claim_as_evidence():
    graph = _build([_rel()], [{"name": "Momentum", "type": "mechanic"}])
    assert [(e.subject, e.predicate, e.object, e.claim_ids) for e in graph.edges] == [("momentum", "used_in", "skill test", ["a"])]
    momentum = next(n for n in graph.nodes if n.id == "momentum")
    assert momentum.type == "mechanic" and momentum.claim_ids == ["a"]
    assert graph.report.claims_cited == 1


@pytest.mark.unit
@pytest.mark.parametrize("cites", [(), ("C9",), ("C1", "C9")])
def test_relationship_with_a_missing_or_invented_citation_is_dropped(cites):
    graph = _build([_rel(cites=cites)])
    assert graph.edges == [] and graph.nodes == []
    assert graph.report.dropped_bad_citation == 1


@pytest.mark.unit
def test_relationship_naming_something_its_claim_does_not_is_dropped():
    graph = _build([_rel(target="Spacing Guild")])
    assert graph.edges == []
    assert graph.report.dropped_name_not_in_claim == 1


@pytest.mark.unit
def test_entity_with_no_relationship_does_not_become_a_node():
    assert _build([], [{"name": "Dragon", "type": "item"}]).nodes == []


@pytest.mark.unit
def test_names_merge_across_case_articles_and_plurals():
    claims = [_claim("a", "The Assets are used in a conflict."), _claim("b", "An asset is used in a Conflict.")]
    answer = GraphBatch.model_validate({"relationships": [_rel("The Assets", "used_in", "conflict", ("C1",)), _rel("asset", "Used In", "Conflict", ("C2",))]})
    graph = assemble_graph([(claims, answer)], GraphReport())
    assert [n.id for n in graph.nodes] == ["asset", "conflict"]
    assert [(e.predicate, e.claim_ids) for e in graph.edges] == [("used_in", ["a", "b"])]


@pytest.mark.unit
def test_self_link_is_dropped():
    graph = _build([_rel("Momentum", "is", "Momentums")])
    assert graph.edges == [] and graph.report.dropped_self_link == 1


@pytest.mark.unit
def test_format_claims_labels_each_claim():
    assert format_claims(CLAIMS).splitlines()[1] == "[C2] (rule) Threat opposes Momentum."


@pytest.mark.unit
def test_graph_log_survives_a_torn_line(tmp_path: Path):
    log = GraphLog(tmp_path / "graph.jsonl")
    log.append("k", GraphBatch())
    with log.path.open("a", encoding="utf-8") as handle:
        handle.write('{"key": "torn')
    assert list(log.read()) == ["k"]


@pytest.mark.unit
def test_singular_words_ending_in_s_are_not_cut_short():
    claims = [_claim("a", "A focus is used on Arrakis.")]
    answer = GraphBatch.model_validate({"relationships": [_rel("Focus", "used_in", "Arrakis", ("C1",))]})
    graph = assemble_graph([(claims, answer)], GraphReport())
    assert [n.id for n in graph.nodes] == ["arrakis", "focus"]


def _rels(*rels):
    return GraphBatch.model_validate({"relationships": list(rels)})


LORE_CLAIMS = [_claim("a", "The Spacing Guild controls space travel."), _claim("b", "Momentum is used in a skill test.")]
MIXED = _rels(
    {"domain": "lore", "subject": "Spacing Guild", "predicate": "controls", "object": "space travel", "cites": ["C1"]},
    {"domain": "rules", "subject": "Momentum", "predicate": "used_in", "object": "skill test", "cites": ["C2"]},
)


@pytest.mark.unit
def test_rules_and_lore_become_separate_graphs():
    rules = assemble_graph([(LORE_CLAIMS, MIXED)], GraphReport(), "rules")
    lore = assemble_graph([(LORE_CLAIMS, MIXED)], GraphReport(), "lore")
    assert [e.subject for e in rules.edges] == ["momentum"]
    assert [e.subject for e in lore.edges] == ["spacing guild"]


@pytest.mark.unit
def test_predicate_outside_the_domains_list_is_kept_visible_as_related_to():
    answer = _rels(_rel("Momentum", "can_trigger_often", "skill test"))
    graph = assemble_graph([(CLAIMS, answer)], GraphReport(), "rules")
    assert graph.edges[0].predicate == "related_to"
    assert graph.report.predicates_unlisted == 1


@pytest.mark.unit
def test_prompt_lists_every_predicate_for_both_domains():
    for predicate in RULE_PREDICATES | LORE_PREDICATES:
        assert predicate in GRAPH_INSTRUCTIONS


def _two_node_graph() -> KnowledgeGraph:
    return KnowledgeGraph(
        nodes=[
            GraphNode(id="extended task", name="extended task", type="mechanic", claim_ids=["a", "b"]),
            GraphNode(id="extended test", name="extended test", type="mechanic", claim_ids=["c"]),
            GraphNode(id="zone", name="zone", type="concept", claim_ids=["a"]),
        ],
        edges=[
            GraphEdge(subject="extended task", predicate="used_in", object="zone", claim_ids=["a"]),
            GraphEdge(subject="extended test", predicate="used_in", object="zone", claim_ids=["c"]),
            GraphEdge(subject="extended test", predicate="is_a", object="extended task", claim_ids=["b"]),
        ],
    )


@pytest.mark.unit
def test_merge_keeps_old_names_and_all_citations_and_drops_the_self_link():
    graph = apply_merges(_two_node_graph(), [["Extended Task", "extended test"]])
    assert [n.id for n in graph.nodes] == ["extended task", "zone"]
    assert graph.nodes[0].aliases == ["extended test"]
    assert set(graph.nodes[0].claim_ids) == {"a", "b", "c"}
    assert [(e.subject, e.predicate, e.object, e.claim_ids) for e in graph.edges] == [("extended task", "used_in", "zone", ["a", "c"])]


@pytest.mark.unit
@pytest.mark.parametrize("group", [["extended task", "dragon"], ["zone"], ["extended task", "extended test", "a", "b", "c", "d", "e"]])
def test_unsafe_merge_groups_are_refused(group):
    graph = apply_merges(_two_node_graph(), [group])
    assert len(graph.nodes) == 3
    assert graph.report.merge_groups_refused == 1


@pytest.mark.unit
def test_claim_with_no_valid_domain_label_goes_by_its_kind():
    fact = ReviewedClaim(id="f", kind=AtomKind.FACT, statement="The Guild exists.", source_node_ids=["s"], pages=[0], merged_from=[])
    rule = _claim("r", "Roll two dice.")
    answer = GraphBatch(claim_domains={"C1": "lore", "C2": "nonsense"})
    assert claim_domains([rule, fact], [([rule, fact], answer)]) == {"r": "lore", "f": "lore"}
    assert claim_domains([rule, fact], []) == {"r": "rules", "f": "lore"}


@pytest.mark.unit
def test_each_domain_tree_nests_only_its_claims_under_the_books_headings():
    nodes = [
        BookNode(id="root", doc_id="d", kind=BookNodeKind.BOOK, seq=0, page_start=0, page_end=0),
        BookNode(id="ch", doc_id="d", kind=BookNodeKind.DIVISION, parent_id="root", seq=1, text="Chapter 6: Conflict", page_start=0, page_end=0),
        BookNode(id="h", doc_id="d", kind=BookNodeKind.HEADING, parent_id="ch", seq=2, text="ZONES", page_start=0, page_end=0),
        BookNode(id="p", doc_id="d", kind=BookNodeKind.PARAGRAPH, parent_id="ch", seq=3, text="Text.", page_start=0, page_end=0),
        BookNode(id="s", doc_id="d", kind=BookNodeKind.SENTENCE, parent_id="p", seq=4, text="Text.", page_start=0, page_end=0),
    ]
    book = BookTree(doc_id="d", title="T", decomposer_version="4", content_hash="x", nodes=nodes, report=DecompositionReport())
    claims = [ReviewedClaim(id=i, kind=AtomKind.RULE, statement=i, source_node_ids=["s"], pages=[0], merged_from=[]) for i in ("r", "l")]
    tree = build_domain_tree(book, claims, {"r": "rules", "l": "lore"}, "rules")
    assert tree.children[0].name == "Chapter 6: Conflict"
    assert tree.children[0].children[0].name == "ZONES"
    assert tree.children[0].children[0].claim_ids == ["r"]


@pytest.mark.unit
def test_graph_search_finds_a_linked_claim_keyword_search_can_miss():
    cost = _claim("cost", "It takes 1 token.")
    named = _claim("named", "Players may choose to Fight On.")
    named.linked_claim_ids = ["cost"]
    graph = KnowledgeGraph(
        nodes=[GraphNode(id="resist defeat", name="Resist Defeat", type="mechanic"), GraphNode(id="player", name="player", type="concept")],
        edges=[GraphEdge(subject="player", predicate="used_in", object="resist defeat", claim_ids=["named"])],
    )
    found = graph_search("What is the price to Resist Defeat?", [graph], [cost, named], limit=8)
    assert "cost" in found
    assert "cost" not in keyword_search("What is the price to Resist Defeat?", [cost, named], limit=8)


@pytest.mark.unit
def test_graph_search_returns_nothing_when_the_question_names_no_node():
    graph = KnowledgeGraph(nodes=[GraphNode(id="zone", name="zone", type="concept")])
    assert graph_search("How do dragons fly?", [graph], CLAIMS, limit=8) == []


@pytest.mark.unit
def test_keyword_search_ranks_by_shared_words():
    assert keyword_search("What opposes Momentum?", CLAIMS, limit=1) == ["b"]
