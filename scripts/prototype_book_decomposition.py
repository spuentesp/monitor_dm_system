#!/usr/bin/env python3
"""Book decomposition prototype. Writes files only; touches no database.

See docs/architecture/BOOK_DECOMPOSITION_PLAN.md.

    # Free, no LLM: check the structure first.
    uv run scripts/prototype_book_decomposition.py decompose WtWf-VtM20th.pdf --out out/vtm

    # List the divisions, to choose what to extract.
    uv run scripts/prototype_book_decomposition.py divisions --out out/vtm

    # One chapter through a real model. Reads API keys from .env or the environment.
    # Use a LiteLLM model name, or minimax/<model> with MINIMAX_API_KEY.
    uv run scripts/prototype_book_decomposition.py extract --out out/dune \
        --division "Chapter 5" --model mistral/mistral-medium-latest \
        --expect tests/fixtures/ingestion/dune_ch5_rules_expect.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

from collections.abc import Callable
from typing import Any

import structlog
from pydantic import BaseModel
from pydantic import ValidationError
from dotenv import load_dotenv
from monitor_agents.book_decomposition import (
    DspyWindowExtractor,
    ExtractionLog,
    IngestStatus,
    LogBusy,
    RunGuard,
    RunStopped,
    Window,
    build_windows,
    run_until_settled,
)
from monitor_agents.book_decomposition.extractor import build_lm, prompt_fingerprint
from monitor_agents.book_decomposition.pipeline import WindowOutcome
from monitor_agents.book_decomposition.kimi_cli import (
    DEFAULT_MAX_CALLS,
    KimiAnswerError,
    KimiClient,
    KimiCoverageModel,
    final_json,
)
from monitor_agents.book_decomposition.knowledge_graph import (
    ANSWER_SHAPE as GRAPH_ANSWER_SHAPE,
    GRAPH_INSTRUCTIONS,
    MERGE_INSTRUCTIONS,
    GraphBatch,
    GraphLog,
    GraphReport,
    KnowledgeGraph,
    MergeAnswer,
    apply_merges,
    assemble_graph,
    build_domain_tree,
    claim_domains,
    format_claims,
    graph_fingerprint,
    graph_search,
    keyword_search,
)
from monitor_agents.book_decomposition.review import (
    CheckLog,
    CoverageLog,
    coverage_fingerprint,
    ParagraphCoverageSignature,
    DspyReviewModel,
    ReviewResult,
    build_claims,
    restrict_to_pages,
    review_claims,
    verification_fingerprint,
)
from monitor_data.schemas.book_graph import BookNodeKind, BookTree, ClaimStatus, ReviewedClaim
from monitor_data.tools.ingest_tools.book_tree import decompose_pdf


# Logs go to stderr, so stdout holds only the JSON report and can be piped to other tools.
structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=sys.stderr))


def _emit(payload: object) -> None:
    sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n")


def _load_tree(out: Path) -> BookTree:
    return BookTree.model_validate_json((out / "tree.json").read_text(encoding="utf-8"))


def _select_windows(tree: BookTree, windows: list[Window], query: str | None) -> list[Window]:
    """Select windows in any division whose path contains the query, including nested ones."""
    if not query:
        return windows
    needle = query.casefold()
    return [w for w in windows if any(needle in part.casefold() for part in w.heading_path)]


def cmd_decompose(args: argparse.Namespace) -> int:
    data = Path(args.pdf).read_bytes()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    doc_id = hashlib.sha256(data).hexdigest()[:32]
    tree = decompose_pdf(data, doc_id=doc_id, title=args.title or Path(args.pdf).stem)
    temporary = out / "tree.json.tmp"
    temporary.write_text(tree.model_dump_json(), encoding="utf-8")
    temporary.replace(out / "tree.json")  # Atomic, so a crash can't leave half a tree.
    windows = build_windows(tree, max_words=args.max_words)
    report = tree.report.model_dump()
    report["is_lossless"] = tree.report.is_lossless
    report["alnum_lost"] = tree.report.alnum_extracted - tree.report.alnum_in_leaves
    report["windows"] = len(windows)
    report["units"] = sum(len(w.units) for w in windows)
    _emit(report)
    return 0 if tree.report.is_lossless else 1


def cmd_divisions(args: argparse.Namespace) -> int:
    tree = _load_tree(Path(args.out))
    by_id = {node.id: node for node in tree.nodes}
    words: dict[str, int] = {}
    for node in tree.nodes:
        if node.kind == BookNodeKind.PARAGRAPH and node.parent_id:
            words[node.parent_id] = words.get(node.parent_id, 0) + len(node.text.split())
    rows = []
    for node in tree.nodes:
        if node.kind != BookNodeKind.DIVISION:
            continue
        depth = 0
        parent = by_id.get(node.parent_id or "")
        while parent is not None and parent.kind == BookNodeKind.DIVISION:
            depth += 1
            parent = by_id.get(parent.parent_id or "")
        rows.append(
            f"p{node.page_start + 1:>4} {words.get(node.id, 0):>7}w  {'  ' * depth}{node.text}"
        )
    sys.stdout.write("\n".join(rows) + "\n")
    return 0


log = structlog.get_logger()

_DEFAULT_COVERAGE_BATCH = 8
_KIMI_COVERAGE_BATCH = 20  # Each kimi call starts a whole session, so calls are kept few.


def _guard_from(args: argparse.Namespace) -> RunGuard:
    return RunGuard(
        max_output_tokens=args.max_output_tokens or None,
        requests_per_minute=args.rpm or None,
    )


def _reasoning_effort(args: argparse.Namespace) -> str | None:
    return None if args.reasoning_effort == "default" else args.reasoning_effort


def _usage(guard: RunGuard) -> dict[str, object]:
    return {
        "stopped_reason": guard.stopped_reason,
        "budget_output_tokens": guard.max_output_tokens,
        "this_run": {
            "requests": guard.requests,
            "input_tokens": guard.input_tokens,
            "output_tokens": guard.output_tokens,
            "rate_limit_pauses": guard.rate_limit_pauses,
        },
    }


def _log_path(out: Path) -> Path:
    return out / "extraction-log.jsonl"


def _model_prefix(model: str | None) -> str:
    return re.sub(r"[^\w.-]+", "_", model or "registry")


def _parse_pages(spec: str | None) -> tuple[int, int] | None:
    """Parse '150-170' or '150' as 1-indexed inclusive pages."""
    if not spec:
        return None
    first, _, last = spec.partition("-")
    return int(first), int(last or first)


def _check_expectations(path: str, statements: list[str]) -> dict[str, object]:
    expected = json.loads(Path(path).read_text(encoding="utf-8"))
    found = {
        item["name"]: any(re.search(item["pattern"], s, re.IGNORECASE) for s in statements)
        for item in expected
    }
    return {"matched": sum(found.values()), "total": len(found), "detail": found}


def cmd_extract(args: argparse.Namespace) -> int:
    out = Path(args.out)
    tree = _load_tree(out)
    all_windows = build_windows(tree, max_words=args.max_words)
    windows = _select_windows(tree, all_windows, args.division)
    pages = _parse_pages(args.pages)
    if pages:
        windows = [w for w in windows if pages[0] <= w.units[0].page + 1 <= pages[1]]
    if not windows:
        sys.stderr.write("No windows match that selection.\n")
        return 2
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    lm = build_lm(args.model, _reasoning_effort(args)) if args.model else None
    prefix = _model_prefix(args.model)
    run_key = f"{prefix}-{prompt_fingerprint()}"

    def accept(key: str) -> bool:
        # Work from an older prompt is kept unless asked otherwise, because redoing it costs quota.
        return key == run_key or (not args.redo_older_prompts and key.startswith(prefix + "-"))

    extraction_log = ExtractionLog(_log_path(out))
    guard = _guard_from(args)
    try:
        with extraction_log.exclusive():
            result = asyncio.run(
                run_until_settled(
                    windows,
                    DspyWindowExtractor(lm=lm),
                    extraction_log,
                    guard,
                    run_key=run_key,
                    accept_run=accept,
                    concurrency=args.concurrency,
                    wait_for_quota_seconds=args.wait_for_quota_hours * 3600,
                    retry_quarantined=args.retry_quarantined,
                )
            )
    except LogBusy as exc:
        sys.stderr.write(f"{exc}\n")
        return 4
    outcomes = [o for o in extraction_log.read() if accept(o.run_key)]
    selected = {u.node_id for w in windows for u in w.units}
    claims = build_claims(tree, outcomes)
    with (out / f"atoms-{prefix}.jsonl").open("w", encoding="utf-8") as handle:
        for claim in claims:
            if set(claim.source_node_ids) & selected:
                handle.write(claim.atom.model_dump_json() + "\n")
    by_id = {node.id: node for node in tree.nodes}
    summary: dict[str, object] = {
        "status": result.status.value,
        "pause_reason": result.pause_reason,
        "rounds": result.rounds,
        "units": {
            "selected": len(selected),
            "done": len(result.states.done),
            "pending": len(result.states.pending),
            "quarantined": len(result.states.quarantined),
        },
        "coverage": round(len(result.states.done) / len(selected), 4),
        "outcomes_by_prompt": Counter(o.run_key for o in outcomes),
        "quarantined_sentences": [by_id[n].text[:200] for n in sorted(result.states.quarantined)],
        **_usage(guard),
        "claims": len(claims),
        "atoms_by_kind": Counter(c.atom.kind.value for c in claims),
    }
    if args.expect:
        summary["expectations"] = _check_expectations(
            args.expect, [c.atom.statement for c in claims]
        )
    _emit(summary)
    if result.status == IngestStatus.PAUSED:
        sys.stderr.write(
            "Paused. All finished work is saved; rerun the same command to continue.\n"
        )
        return 3
    return 0


def _latest_outcomes(out: Path, model: str) -> list[WindowOutcome]:
    """Load everything this model has produced for the book."""
    prefix = _model_prefix(model) + "-"
    outcomes = [o for o in ExtractionLog(_log_path(out)).read() if o.run_key.startswith(prefix)]
    if not outcomes:
        raise SystemExit(f"No outcomes for {model} in {out}. Run extract first.")
    return outcomes


def _write_review_markdown(path: Path, result: ReviewResult, tree: BookTree) -> None:
    """Write the part a person actually has to read."""
    sections: dict[ClaimStatus, list[str]] = {}
    for entry in result.ledger:
        if entry.status in (ClaimStatus.ACCEPTED, ClaimStatus.MERGED):
            continue
        line = f"- p{entry.page + 1} **{entry.kind.value}**: {entry.original_statement}"
        if entry.reason:
            line += f"\n  - why: {entry.reason}"
        if entry.status == ClaimStatus.CORRECTED:
            fixed = next(c.statement for c in result.claims if c.id == entry.claim_id)
            line += f"\n  - now: {fixed}"
        sections.setdefault(entry.status, []).append(line)
    parts = [f"# Claim review\n\n{json.dumps(result.report.by_status)}"]
    for status in (
        ClaimStatus.NEEDS_HUMAN,
        ClaimStatus.CORRECTED,
        ClaimStatus.REJECTED,
        ClaimStatus.EXAMPLE,
    ):
        lines = sections.get(status, [])
        parts.append(f"## {status.value} ({len(lines)})\n\n" + "\n".join(lines))
    by_id = {node.id: node for node in tree.nodes}
    orphans = [
        f"- p{by_id[node_id].page_start + 1}: {by_id[node_id].text}"
        for node_id in result.report.orphaned_sentences
    ]

    def listed(node_ids: list[str]) -> str:
        return "\n".join(f"- p{by_id[n].page_start + 1}: {by_id[n].text}" for n in node_ids)

    terms = result.report.terms_not_fully_compared
    never = result.report.sentences_never_extracted
    not_rechecked = result.report.sentences_not_rechecked
    parts[1:1] = [
        f"## Never extracted: no claims exist for these ({len(never)})\n\n"
        "Extraction never finished them, so this review says nothing about them.\n\n"
        + listed(never),
        f"## Orphaned sentences: no claim left ({len(orphans)})\n\n"
        "Every claim citing these was removed. Check nothing important went with them.\n\n"
        + "\n".join(orphans),
        f"## Skipped and not rechecked ({len(not_rechecked)})\n\n"
        "Extraction skipped these and the second look failed, so a person should read them.\n\n"
        + listed(not_rechecked),
        f"## Terms not fully compared ({len(terms)})\n\n"
        "These have too many numeric claims to compare every pair, so a contradiction could "
        "remain.\n\n" + "\n".join(f"- {term}" for term in terms),
    ]
    path.write_text("\n\n".join(parts) + "\n", encoding="utf-8")


def cmd_review(args: argparse.Namespace) -> int:
    out = Path(args.out)
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    tree = _load_tree(out)
    # A different model makes a better reviewer: it's less likely to share the extractor's mistakes.
    outcomes = _latest_outcomes(out, args.claims_from or args.model)
    pages = _parse_pages(args.pages)
    if pages:
        outcomes = restrict_to_pages(tree, outcomes, *pages)
    guard = _guard_from(args)
    model = DspyReviewModel(build_lm(args.model, _reasoning_effort(args)), guard=guard)
    check_log = CheckLog(
        out / f"review-checks-{_model_prefix(args.model)}-{verification_fingerprint()}.jsonl"
    )
    coverage_model = None
    coverage_batch = _DEFAULT_COVERAGE_BATCH
    coverage_prefix = _model_prefix(args.model)
    if args.coverage_model:
        coverage_model = KimiCoverageModel(
            args.coverage_model,
            ParagraphCoverageSignature.instructions,
            guard=RunGuard(requests_per_minute=args.rpm or None),
            max_calls=args.coverage_max_calls,
        )
        coverage_batch = _KIMI_COVERAGE_BATCH
        coverage_prefix = _model_prefix(args.coverage_model)
    coverage_log = CoverageLog(
        out / f"coverage-log-{coverage_prefix}-{coverage_fingerprint()}.jsonl"
    )
    try:
        result = asyncio.run(
            review_claims(
                tree,
                outcomes,
                model,
                concurrency=args.concurrency,
                check_log=check_log,
                coverage_model=coverage_model,
                coverage_batch_size=coverage_batch,
                coverage_log=coverage_log,
            )
        )
    except RunStopped as exc:
        _emit({**_usage(guard), "stopped_reason": str(exc)})
        sys.stderr.write(
            "Review stopped early, so there's no report yet. Finished checks are saved. "
            "Rerun the same command to continue.\n"
        )
        return 3
    stem = _model_prefix(args.model) + (f"-p{args.pages}" if pages else "")
    (out / f"reviewed-{stem}.jsonl").write_text(
        "".join(claim.model_dump_json() + "\n" for claim in result.claims), encoding="utf-8"
    )
    (out / f"ledger-{stem}.jsonl").write_text(
        "".join(entry.model_dump_json() + "\n" for entry in result.ledger), encoding="utf-8"
    )
    (out / f"coverage-gaps-{stem}.jsonl").write_text(
        "".join(gap.model_dump_json() + "\n" for gap in result.report.paragraph_gaps),
        encoding="utf-8",
    )
    _write_review_markdown(out / f"review-{stem}.md", result, tree)
    report = {**_usage(guard), **result.report.model_dump()}
    for field in (
        "orphaned_sentences",
        "sentences_never_extracted",
        "sentences_not_rechecked",
        "paragraph_gaps",
    ):
        report[field] = len(report[field])
    if args.expect:
        report["expectations"] = _check_expectations(
            args.expect, [claim.statement for claim in result.claims]
        )
    _emit(report)
    return 0 if not result.report.ledger_problems else 1


def _add_pacing_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--rpm", type=float, default=20, help="Requests per minute; 0 for no limit")
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=200_000,
        help="Stop after this many output tokens in this run, failed calls included; 0 for no limit",
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=["minimal", "low", "medium", "high", "default"],
        default="low",
        help="MiniMax only. Reasoning was 92%% of output tokens at the model's default",
    )


def _load_reviewed(out: Path, reviewed_by: str, pages: str) -> list[ReviewedClaim]:
    claims: dict[str, ReviewedClaim] = {}
    for part in pages.split(","):
        path = out / f"reviewed-{_model_prefix(reviewed_by)}-p{part.strip()}.jsonl"
        if not path.exists():
            raise SystemExit(f"{path} doesn't exist. Run review first.")
        for line in path.read_text(encoding="utf-8").splitlines():
            claim = ReviewedClaim.model_validate_json(line)
            claims[claim.id] = claim
    return list(claims.values())


def _parser_for(model: type[BaseModel]) -> Callable[[str], Any]:
    def parse(stdout: str) -> Any:
        try:
            return model.model_validate(final_json(stdout))
        except ValidationError as exc:
            raise KimiAnswerError(f"Kimi's answer doesn't fit: {exc}") from exc

    return parse


def cmd_graph(args: argparse.Namespace) -> int:
    out = Path(args.out)
    claims = _load_reviewed(out, args.reviewed_by, args.pages)
    book = _load_tree(out)
    client = KimiClient(
        args.model, guard=RunGuard(requests_per_minute=args.rpm or None), max_calls=args.max_calls
    )
    prefix = _model_prefix(args.model)
    graph_log = GraphLog(out / f"graph-log-{prefix}-{graph_fingerprint()}.jsonl")
    batches = [claims[i : i + args.batch] for i in range(0, len(claims), args.batch)]
    failed = [0]
    reused = [0]
    merge_failures = [0]

    async def run() -> list[tuple[list[ReviewedClaim], GraphBatch]]:
        saved = graph_log.read()
        semaphore = asyncio.Semaphore(args.concurrency)

        async def one(batch: list[ReviewedClaim]) -> tuple[list[ReviewedClaim], GraphBatch] | None:
            body = format_claims(batch)
            key = hashlib.sha256(body.encode()).hexdigest()[:16]
            if key in saved:
                reused[0] += 1
                return batch, saved[key]
            if args.saved_only:
                failed[0] += 1
                return None
            try:
                async with semaphore:
                    answer = await client.ask(
                        f"{GRAPH_INSTRUCTIONS}\n\n{GRAPH_ANSWER_SHAPE}\n\n{body}",
                        _parser_for(GraphBatch),
                    )
            except RunStopped:
                raise
            except Exception as exc:  # noqa: BLE001  # reason: counted in the report; rerunning retries the batch
                log.warning("graph_batch_failed", error=f"{type(exc).__name__}: {exc}"[:300])
                failed[0] += 1
                return None
            graph_log.append(key, answer)
            return batch, answer

        results = await asyncio.gather(*(one(b) for b in batches), return_exceptions=True)
        finished = []
        for result in results:
            if isinstance(result, BaseException):
                raise result
            if result is not None:
                finished.append(result)
        return finished

    async def merged(graph: KnowledgeGraph) -> KnowledgeGraph:
        if args.saved_only:
            return graph
        names = "\n".join(node.name for node in graph.nodes)
        try:
            answer = await client.ask(f"{MERGE_INSTRUCTIONS}\n\n{names}", _parser_for(MergeAnswer))
        except RunStopped:
            raise
        except Exception as exc:  # noqa: BLE001  # reason: the graph is usable unmerged, and the report says so
            log.warning("graph_merge_failed", error=f"{type(exc).__name__}: {exc}"[:300])
            merge_failures[0] += 1
            return graph
        return apply_merges(graph, answer.groups)

    try:
        answers = asyncio.run(run())
        domains = claim_domains(claims, answers)
        graphs = {}
        for domain in ("rules", "lore"):
            graph = assemble_graph(
                answers, GraphReport(claims=len(claims), batches=len(batches)), domain
            )
            graphs[domain] = asyncio.run(merged(graph)) if graph.nodes else graph
    except RunStopped as exc:
        _emit({"stopped_reason": str(exc), "kimi_calls": client.calls})
        sys.stderr.write("Stopped early. Finished batches are saved; rerun to continue.\n")
        return 3
    folder = out / "graph-run"
    folder.mkdir(exist_ok=True)
    summary: dict[str, object] = {
        "kimi_calls": client.calls,
        "batches": len(batches),
        "batches_reused": reused[0],
        "batches_failed": failed[0],
        "merge_failures": merge_failures[0],
        "claims": len(claims),
        "claims_by_domain": Counter(domains.values()),
    }
    for domain, graph in graphs.items():
        (folder / f"graph-{domain}.json").write_text(
            graph.model_dump_json(indent=1), encoding="utf-8"
        )
        tree = build_domain_tree(book, claims, domains, domain)
        (folder / f"tree-{domain}.json").write_text(
            tree.model_dump_json(indent=1), encoding="utf-8"
        )
        summary[domain] = {
            "nodes": len(graph.nodes),
            "edges": len(graph.edges),
            **graph.report.model_dump(
                exclude={"claims", "batches", "batches_reused", "batches_failed"}
            ),
        }
    (folder / "claim-domains.json").write_text(json.dumps(domains), encoding="utf-8")
    _emit(summary)
    return 0


def cmd_graph_questions(args: argparse.Namespace) -> int:
    out = Path(args.out)
    claims = _load_reviewed(out, args.reviewed_by, args.pages)
    by_id = {claim.id: claim for claim in claims}
    graphs = [
        KnowledgeGraph.model_validate_json(
            (out / "graph-run" / f"graph-{d}.json").read_text(encoding="utf-8")
        )
        for d in ("rules", "lore")
    ]
    rows = []
    for item in json.loads(Path(args.questions).read_text(encoding="utf-8")):

        def hit(ids: list[str]) -> bool:
            return any(re.search(item["pattern"], by_id[i].statement, re.IGNORECASE) for i in ids)

        rows.append(
            {
                "question": item["question"],
                "graph": hit(graph_search(item["question"], graphs, claims, args.limit)),
                "keywords": hit(keyword_search(item["question"], claims, args.limit)),
            }
        )
    _emit(
        {
            "questions": len(rows),
            "limit": args.limit,
            "graph_found": sum(row["graph"] for row in rows),
            "keywords_found": sum(row["keywords"] for row in rows),
            "rows": rows,
        }
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    decompose = commands.add_parser("decompose", help="PDF to tree. No LLM, no cost.")
    decompose.add_argument("pdf")
    decompose.add_argument("--out", required=True)
    decompose.add_argument("--title")
    decompose.add_argument("--max-words", type=int, default=600)
    decompose.set_defaults(func=cmd_decompose)
    divisions = commands.add_parser("divisions", help="List divisions with word counts.")
    divisions.add_argument("--out", required=True)
    divisions.set_defaults(func=cmd_divisions)
    extract = commands.add_parser("extract", help="Tree to atoms, using a real LLM.")
    extract.add_argument("--out", required=True)
    extract.add_argument("--division", help="Only divisions whose path contains this text")
    extract.add_argument(
        "--model", help="LiteLLM model, or minimax/<model>. Default: the registry."
    )
    extract.add_argument("--pages", help="Only this part of the book, e.g. 150-170")
    extract.add_argument(
        "--wait-for-quota-hours",
        type=float,
        default=0,
        help="On quota errors, keep waiting and retrying for this long instead of pausing",
    )
    extract.add_argument("--redo-older-prompts", action="store_true")
    extract.add_argument("--retry-quarantined", action="store_true")
    extract.add_argument("--max-words", type=int, default=600)
    _add_pacing_arguments(extract)
    extract.add_argument("--expect", help="JSON file of facts the atoms should contain")
    extract.set_defaults(func=cmd_extract)
    review = commands.add_parser("review", help="Verify, stack and ledger extracted claims.")
    review.add_argument("--out", required=True)
    review.add_argument("--model", required=True)
    review.add_argument("--claims-from", help="Review claims extracted by this model instead")
    review.add_argument("--pages", help="Only claims on these pages, e.g. 153 or 150-170")
    review.add_argument(
        "--coverage-model",
        help="Run the paragraph check through the kimi command, e.g. kimi-code/k3.1-pro",
    )
    review.add_argument(
        "--coverage-max-calls",
        type=int,
        default=DEFAULT_MAX_CALLS,
        help="Stop after this many kimi calls; Kimi reports no tokens to budget by",
    )
    _add_pacing_arguments(review)
    review.add_argument("--expect", help="JSON file of facts the reviewed claims should contain")
    review.set_defaults(func=cmd_review)
    graph = commands.add_parser("graph", help="Build a knowledge graph from reviewed claims.")
    graph.add_argument("--out", required=True)
    graph.add_argument("--model", required=True, help="kimi model, e.g. kimi-code/k3.1-pro")
    graph.add_argument("--reviewed-by", required=True, help="The model that reviewed the claims")
    graph.add_argument("--pages", required=True, help="Reviewed ranges, e.g. 168-180,181-197")
    graph.add_argument("--batch", type=int, default=25)
    graph.add_argument("--max-calls", type=int, default=12)
    graph.add_argument(
        "--saved-only",
        action="store_true",
        help="Build from saved answers with no new calls: missing batches and merging are skipped",
    )
    graph.add_argument("--concurrency", type=int, default=4)
    graph.add_argument("--rpm", type=float, default=20)
    graph.set_defaults(func=cmd_graph)
    questions = commands.add_parser("graph-questions", help="Test the graph on real questions.")
    questions.add_argument("--out", required=True)
    questions.add_argument("--reviewed-by", required=True)
    questions.add_argument("--pages", required=True)
    questions.add_argument("--questions", required=True, help="JSON list of question and pattern")
    questions.add_argument("--limit", type=int, default=8)
    questions.set_defaults(func=cmd_graph_questions)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
