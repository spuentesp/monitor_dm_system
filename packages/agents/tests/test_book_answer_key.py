"""Tests for the answer key: sampling, labels and saving (book decomposition, Q1, I-17)."""

import json
import threading
import urllib.error
import urllib.request
import importlib.util
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from monitor_agents.book_decomposition import RunGuard
from monitor_agents.book_decomposition.answer_key import (
    Answer,
    Authority,
    Force,
    Scope,
    Support,
    KeyRow,
    Labels,
    append_answer,
    build_rows,
    format_for_prefill,
    prefill_rows,
    read_answers,
    read_rows,
    select_sample,
    write_rows,
)
from monitor_agents.book_decomposition.pipeline import ProvenancedAtom, WindowOutcome
from monitor_agents.book_decomposition.review import build_claims
from monitor_data.schemas.book_graph import (
    AtomKind,
    BookNode,
    BookNodeKind,
    BookTree,
    DecompositionReport,
    ExtractedAtom,
)

LABELS = {
    "support": "quoted",
    "scope": "general_rule",
    "force": "may",
    "authority": "core_rule",
    "dropped_condition": False,
    "canon": True,
}


def _tree(texts: list[str]) -> BookTree:
    nodes = [BookNode(id="root", doc_id="d", kind=BookNodeKind.BOOK, seq=0, page_start=0, page_end=0)]
    nodes.append(
        BookNode(
            id="div",
            doc_id="d",
            kind=BookNodeKind.DIVISION,
            parent_id="root",
            seq=1,
            text="Rules",
            page_start=0,
            page_end=0,
        )
    )
    for i, text in enumerate(texts):
        nodes.append(
            BookNode(
                id=f"p{i}",
                doc_id="d",
                kind=BookNodeKind.PARAGRAPH,
                parent_id="div",
                seq=len(nodes),
                text=text,
                page_start=i,
                page_end=i,
            )
        )
        nodes.append(
            BookNode(
                id=f"s{i}",
                doc_id="d",
                kind=BookNodeKind.SENTENCE,
                parent_id=f"p{i}",
                seq=len(nodes),
                text=text,
                page_start=i,
                page_end=i,
            )
        )
    return BookTree(
        doc_id="d", title="T", decomposer_version="1", content_hash="x", nodes=nodes, report=DecompositionReport()
    )


def _claims(tree: BookTree, count: int, kind: AtomKind = AtomKind.RULE):
    atoms = [
        ProvenancedAtom(
            atom=ExtractedAtom(kind=kind, statement=f"Claim {i}.", cites=["S1"]), source_node_ids=[f"s{i}"], page=i
        )
        for i in range(count)
    ]
    return build_claims(tree, [WindowOutcome(window_id="w", atoms=atoms)])


@pytest.mark.unit
def test_sample_keeps_splits_apart_with_the_requested_sizes():
    tree = _tree(["x"] * 40)
    sample = select_sample(_claims(tree, 40), {1, 2, 3, 4, 5, 6}, tuning=4, test=20, seed=1)
    tuning = [c for split, c in sample if split == "tuning"]
    test = [c for split, c in sample if split == "test"]
    assert (len(tuning), len(test)) == (4, 20)
    assert all(c.page + 1 <= 6 for c in tuning)
    assert all(c.page + 1 > 6 for c in test)
    assert len({c.id for _, c in sample}) == 24


@pytest.mark.unit
def test_sample_is_repeatable():
    tree = _tree(["x"] * 30)
    claims = _claims(tree, 30)
    pick = lambda seed: [c.id for _, c in select_sample(claims, {1}, tuning=1, test=10, seed=seed)]  # noqa: E731
    assert pick(5) == pick(5)
    assert pick(5) != pick(6)


@pytest.mark.unit
def test_sample_includes_limiting_sources_even_when_rare():
    texts = ["Plain text."] * 30
    texts[17] = "You may do it, unless you are tired."
    tree = _tree(texts)
    sample = select_sample(_claims(tree, 30), set(), tuning=0, test=3, seed=2)
    assert any(c.source_node_ids == ("s17",) for _, c in sample)


@pytest.mark.unit
def test_sample_smaller_pool_returns_everything_without_hanging():
    tree = _tree(["x"] * 3)
    assert len(select_sample(_claims(tree, 3), set(), tuning=0, test=50, seed=1)) == 3


@pytest.mark.unit
def test_rows_carry_heading_and_neighboring_paragraphs():
    tree = _tree(["First.", "Second.", "Third."])
    sample = [("test", c) for c in _claims(tree, 3)]
    rows = {row.statement: row for row in build_rows(tree, sample)}
    assert rows["Claim 1."].before == "First."
    assert rows["Claim 1."].after == "Third."
    assert rows["Claim 1."].heading == "Rules"
    assert rows["Claim 1."].page == 2
    assert rows["Claim 0."].before == ""
    assert rows["Claim 2."].after == ""


@pytest.mark.unit
def test_prefill_prompt_shows_the_surrounding_text():
    row = KeyRow(
        id="a", split="test", page=1, kind="rule", statement="S", heading="H", source="SRC", before="BEF", after="AFT"
    )
    prompt = format_for_prefill([row])
    assert all(text in prompt for text in ("BEF", "SRC", "AFT", "[C1]"))


class _FailingLm:
    pass


@pytest.mark.unit
async def test_failed_prefill_leaves_claims_blank_for_a_person(monkeypatch):
    import monitor_agents.book_decomposition.answer_key as module

    def boom(*_args, **_kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(module, "run_metered", boom)
    row = KeyRow(id="a", split="test", page=1, kind="rule", statement="S", heading="H", source="SRC")
    filled = await prefill_rows([row], _FailingLm(), RunGuard())
    assert filled == 0
    assert row.prefill is None


@pytest.mark.unit
async def test_prefill_stops_on_quota_and_keeps_the_rest_blank(monkeypatch):
    import monitor_agents.book_decomposition.answer_key as module

    def quota(*_args, **_kwargs):
        raise RuntimeError("usage limit reached (2056)")

    monkeypatch.setattr(module, "run_metered", quota)
    rows = [
        KeyRow(id=str(i), split="test", page=1, kind="rule", statement="S", heading="H", source="SRC")
        for i in range(25)
    ]
    guard = RunGuard()
    with pytest.raises(Exception, match="usage limit"):
        await prefill_rows(rows, _FailingLm(), guard)
    assert guard.stopped


@pytest.mark.unit
def test_rows_survive_a_round_trip(tmp_path):
    row = KeyRow(
        id="a", split="test", page=1, kind="rule", statement="S", heading="H", source="SRC", prefill=Labels(**LABELS)
    )
    path = tmp_path / "rows.json"
    write_rows(path, [row])
    assert read_rows(path) == [row]


@pytest.mark.unit
def test_the_last_answer_wins_and_a_torn_line_is_ignored(tmp_path):
    path = tmp_path / "answers.jsonl"
    append_answer(path, Answer(id="a", labels=Labels(**LABELS)))
    append_answer(path, Answer(id="a", labels=Labels(**{**LABELS, "canon": False}), note="changed"))
    with path.open("a") as handle:
        handle.write('{"id":"b","lab')
    answers = read_answers(path)
    assert list(answers) == ["a"]
    assert answers["a"].labels.canon is False
    assert answers["a"].note == "changed"


@pytest.mark.unit
def test_no_answers_file_means_no_answers(tmp_path):
    assert read_answers(tmp_path / "none.jsonl") == {}


def _load_script():
    path = Path(__file__).parents[3] / "scripts" / "answer_key_sheet.py"
    spec = importlib.util.spec_from_file_location("answer_key_sheet", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def sheet(tmp_path):
    script = _load_script()
    row = KeyRow(id="a", split="test", page=1, kind="rule", statement="S", heading="H", source="SRC")
    write_rows(script._rows_path(tmp_path), [row])
    server = ThreadingHTTPServer(("127.0.0.1", 0), None)
    port = server.server_address[1]
    server.RequestHandlerClass = script._handler(tmp_path, {f"127.0.0.1:{port}"})
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}", tmp_path, script
    server.shutdown()
    server.server_close()


def _post(url, body, **headers):
    request = urllib.request.Request(
        url + "/answer", data=json.dumps(body).encode(), headers={"Content-Type": "application/json", **headers}
    )
    return urllib.request.urlopen(request, timeout=5).status


@pytest.mark.unit
@pytest.mark.enable_socket
def test_sheet_serves_the_page_and_hides_which_claims_are_the_test_set(sheet):
    url, _, _ = sheet
    assert b"Claim Answer Key" in urllib.request.urlopen(url + "/", timeout=5).read()
    data = json.load(urllib.request.urlopen(url + "/data", timeout=5))
    assert data["rows"][0]["statement"] == "S"
    assert "split" not in data["rows"][0]


@pytest.mark.unit
@pytest.mark.enable_socket
def test_sheet_saves_an_answer_to_disk_immediately(sheet):
    url, path, script = sheet
    assert _post(url, {"id": "a", "labels": LABELS, "note": "n"}) == 200
    assert read_answers(script._answers_path(path))["a"].note == "n"
    data = json.load(urllib.request.urlopen(url + "/data", timeout=5))
    assert data["answers"]["a"]["note"] == "n"


@pytest.mark.unit
@pytest.mark.enable_socket
@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"id": "a", "labels": {**LABELS, "support": "nonsense"}}, 422),
        ({"id": "a"}, 422),
        ({"id": "unknown", "labels": LABELS}, 404),
    ],
)
def test_sheet_rejects_bad_answers_without_saving(sheet, body, code):
    url, path, script = sheet
    with pytest.raises(urllib.error.HTTPError) as caught:
        _post(url, body)
    assert caught.value.code == code
    assert not script._answers_path(path).exists()


@pytest.mark.unit
@pytest.mark.enable_socket
def test_sheet_rejects_requests_from_another_host_name(sheet):
    url, path, script = sheet
    with pytest.raises(urllib.error.HTTPError) as caught:
        _post(url, {"id": "a", "labels": LABELS}, Host="evil.example")
    assert caught.value.code == 403
    assert not script._answers_path(path).exists()


@pytest.mark.unit
def test_canon_if_corrected_survives_the_answer_file_and_defaults_to_unset(tmp_path):
    path = tmp_path / "answers.jsonl"
    labels = Labels(**{**LABELS, "dropped_condition": True, "canon": False})
    append_answer(path, Answer(id="a", labels=labels, canon_if_corrected=True))
    append_answer(path, Answer(id="b", labels=labels))
    answers = read_answers(path)
    assert answers["a"].canon_if_corrected is True
    assert answers["b"].canon_if_corrected is None


@pytest.mark.unit
def test_sheet_explains_every_label_value():
    page = (Path(__file__).parents[3] / "scripts" / "answer_key_sheet.html").read_text(encoding="utf-8")
    help_text = page[page.index("const HELP=") : page.index("const NAMES=")]
    for labels in (Support, Scope, Force, Authority):
        for value in labels:
            assert f"{value.value}:[" in help_text
    assert "true:[" in help_text and "false:[" in help_text
