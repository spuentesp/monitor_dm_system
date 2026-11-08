#!/usr/bin/env python3
"""Build and serve the answer-key sheet (see BOOK_DECOMPOSITION_PLAN.md, Q1).

Local only: the sheet holds book text, so it binds to 127.0.0.1 and never leaves this machine.

    # Pick claims and pre-fill labels. Use a model that isn't a reviewer being scored.
    uv run scripts/answer_key_sheet.py build --out <dir> --claims-from minimax/MiniMax-M3.1-Flash \
        --model mistral/mistral-medium-latest --tuning-pages 153,163

    # Label them. Each click saves to <dir>/answer-key.jsonl.
    uv run scripts/answer_key_sheet.py serve --out <dir>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import structlog
from dotenv import load_dotenv
from monitor_agents.book_decomposition import ExtractionLog, RunGuard, RunStopped
from monitor_agents.book_decomposition.answer_key import (
    Answer,
    append_answer,
    build_rows,
    prefill_rows,
    read_answers,
    read_rows,
    select_sample,
    write_rows,
)
from monitor_agents.book_decomposition.extractor import build_lm
from monitor_agents.book_decomposition.review import build_claims
from monitor_data.schemas.book_graph import BookTree
from pydantic import ValidationError

structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=sys.stderr))

_PAGE = Path(__file__).with_name("answer_key_sheet.html")
_MAX_BODY = 20_000


def _rows_path(out: Path) -> Path:
    return out / "answer-key-rows.json"


def _answers_path(out: Path) -> Path:
    return out / "answer-key.jsonl"


def cmd_build(args: argparse.Namespace) -> int:
    out = Path(args.out)
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    tree = BookTree.model_validate_json((out / "tree.json").read_text(encoding="utf-8"))
    prefix = re.sub(r"[^\w.-]+", "_", args.claims_from) + "-"
    outcomes = [
        o
        for o in ExtractionLog(out / "extraction-log.jsonl").read()
        if o.run_key.startswith(prefix)
    ]
    if not outcomes:
        sys.stderr.write(f"No claims from {args.claims_from} in {out}.\n")
        return 2
    claims = build_claims(tree, outcomes)
    tuning_pages = {int(page) for page in args.tuning_pages.split(",")}
    sample = select_sample(claims, tuning_pages, tuning=args.tuning, test=args.test, seed=args.seed)
    rows = build_rows(tree, sample)
    guard = RunGuard(max_output_tokens=args.max_output_tokens, requests_per_minute=args.rpm)
    filled = 0
    try:
        filled = asyncio.run(prefill_rows(rows, build_lm(args.model), guard))
    except RunStopped:
        filled = sum(row.prefill is not None for row in rows)  # What's blank, a person fills in.
    write_rows(_rows_path(out), rows)
    # Counts only, so nobody reads the test claims by accident.
    sys.stdout.write(
        json.dumps(
            {
                "rows": len(rows),
                "prefilled": filled,
                "stopped_reason": guard.stopped_reason,
                "input_tokens": guard.input_tokens,
                "output_tokens": guard.output_tokens,
            }
        )
        + "\n"
    )
    return 0


def _handler(out: Path, allowed_hosts: set[str]) -> type[BaseHTTPRequestHandler]:
    rows = {row.id: row for row in read_rows(_rows_path(out))}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_: object) -> None:  # Book text and clicks don't belong in a log.
            return

        def _send(self, status: int, body: bytes, content_type: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _host_allowed(self) -> bool:
            # Stops other websites reaching this server through a rebinding DNS name.
            return self.headers.get("Host", "") in allowed_hosts

        def do_GET(self) -> None:  # noqa: N802  # reason: http.server's required name
            if not self._host_allowed():
                self._send(403, b"{}")
            elif self.path == "/":
                self._send(200, _PAGE.read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/data":
                answers = read_answers(_answers_path(out))
                body = {
                    "rows": [
                        row.model_dump(mode="json", exclude={"split"}) for row in rows.values()
                    ],
                    "answers": {k: v.model_dump(mode="json") for k, v in answers.items()},
                }
                self._send(200, json.dumps(body, ensure_ascii=False).encode())
            else:
                self._send(404, b"{}")

        def do_POST(self) -> None:  # noqa: N802  # reason: http.server's required name
            length = int(self.headers.get("Content-Length") or 0)
            is_json = self.headers.get("Content-Type", "").startswith("application/json")
            if self.path != "/answer" or not self._host_allowed() or not is_json:
                self._send(403, b"{}")
                return
            if length > _MAX_BODY:
                self._send(413, b"{}")
                return
            try:
                answer = Answer.model_validate_json(self.rfile.read(length))
            except ValidationError as exc:
                self._send(422, json.dumps({"error": str(exc)[:300]}).encode())
                return
            if answer.id not in rows:
                self._send(404, b"{}")
                return
            append_answer(_answers_path(out), answer)
            self._send(200, b"{}")

    return Handler


def cmd_serve(args: argparse.Namespace) -> int:
    out = Path(args.out)
    hosts = {f"127.0.0.1:{args.port}", f"localhost:{args.port}"}
    server = ThreadingHTTPServer(("127.0.0.1", args.port), _handler(out, hosts))
    sys.stdout.write(f"Open http://localhost:{args.port}  (Ctrl+C to stop; every click is saved)\n")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="Pick claims and pre-fill labels.")
    build.add_argument("--out", required=True)
    build.add_argument("--claims-from", required=True)
    build.add_argument("--model", required=True)
    build.add_argument(
        "--tuning-pages", required=True, help="Pages already inspected, e.g. 153,163"
    )
    build.add_argument("--tuning", type=int, default=30)
    build.add_argument("--test", type=int, default=90)
    build.add_argument("--seed", type=int, default=20261103)
    build.add_argument("--rpm", type=float, default=20)
    build.add_argument("--max-output-tokens", type=int, default=30_000)
    build.set_defaults(func=cmd_build)
    serve = commands.add_parser("serve", help="Label the claims in a browser.")
    serve.add_argument("--out", required=True)
    serve.add_argument("--port", type=int, default=8765)
    serve.set_defaults(func=cmd_serve)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
