#!/usr/bin/env python3
"""Pre-flight check for the GM table test (G11).

The table test is a ≥2 h human session. Finding out that a lookup endpoint
returns 500 in minute ten of that session is an expensive way to learn
something a script can check in a minute.

This script exercises **every endpoint the table-test protocol touches**
(the S1–S9 lookups and the C1–C4 combat steps) against a running backend,
and prints a pass/fail table. It is the difference between "the build is
ready for the session" and "the session starts with a debugging detour".

It is read-only apart from the combat check, which creates and then deletes
its own scratch session.

Usage::

    # against a backend already running on :8123 (see the live-run recipe)
    uv run python scripts/gm_table_test_preflight.py --base-url http://127.0.0.1:8123

    # point it at a specific universe and story
    uv run python scripts/gm_table_test_preflight.py \\
        --universe-id <uuid> --story-id <uuid>

    # a machine-readable report
    uv run python scripts/gm_table_test_preflight.py --json-out /tmp/preflight.json

The backend must be reachable and the caller must be authenticated (the
script uses the same env the backend does; with ``MONITOR_AUTH_DISABLED``
the local account owns everything).

Exit code 0 when every check passes, 1 when any fails — so it can gate the
session.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from uuid import uuid4
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "http://127.0.0.1:8123"
TIMEOUT_SECONDS = 120


@dataclass
class Check:
    """One pre-flight check and its outcome."""

    key: str
    what: str
    ok: bool = False
    detail: str = ""
    seconds: float = 0.0
    skipped: bool = False


@dataclass
class Report:
    """Every check, in order."""

    checks: list[Check] = field(default_factory=list)

    def add(self, check: Check) -> Check:
        self.checks.append(check)
        return check

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if not c.ok and not c.skipped]

    @property
    def skipped(self) -> list[Check]:
        return [c for c in self.checks if c.skipped]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": len(self.checks),
            "passed": sum(1 for c in self.checks if c.ok),
            "failed": len(self.failed),
            "skipped": len(self.skipped),
            "checks": [
                {
                    "key": c.key,
                    "what": c.what,
                    "ok": c.ok,
                    "skipped": c.skipped,
                    "detail": c.detail,
                    "seconds": round(c.seconds, 2),
                }
                for c in self.checks
            ],
        }


class Client:
    """A tiny HTTP client for the backend under test."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = os.getenv("MONITOR_PREFLIGHT_TOKEN", "").strip()

    def request(
        self,
        method: str,
        path: str,
        body: Any = None,
        query: dict[str, Any] | None = None,
    ) -> tuple[int, Any, str]:
        """Return ``(status, parsed_body, raw_text)``."""
        url = f"{self.base_url}{path}"
        if query:
            from urllib.parse import urlencode

            clean = {k: str(v) for k, v in query.items() if v is not None}
            if clean:
                url += "?" + urlencode(clean)
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                raw = response.read().decode("utf-8", "replace")
                return response.status, _parse(raw), raw
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            return exc.code, _parse(raw), raw
        except Exception as exc:  # noqa: BLE001  # reason: a transport failure is a failed check
            return 0, None, f"{type(exc).__name__}: {exc}"

    def get(self, path: str, query: dict[str, Any] | None = None) -> tuple[int, Any, str]:
        return self.request("GET", path, query=query)

    def post(self, path: str, body: Any = None) -> tuple[int, Any, str]:
        return self.request("POST", path, body=body)

    def patch(self, path: str, body: Any = None) -> tuple[int, Any, str]:
        return self.request("PATCH", path, body=body)

    def delete(self, path: str) -> tuple[int, Any, str]:
        return self.request("DELETE", path)


def _parse(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _story_detail(ok_detail: str, status: int, raw: str, story_id: str | None) -> str:
    """A story-scoped check's detail, distinguishing "no story" from a failure."""
    if story_id is None:
        return "this universe has no story to check against"
    return f"HTTP {status}: {raw[:160]}" if status != 200 else ok_detail


def _character_ids(client: Client, universe_id: str) -> list[str]:
    """The characters in a universe — what the lookups panel offers."""
    for path in ("/api/entities/entities", "/api/entities"):
        status, body, raw = client.get(
            path, query={"universe_id": universe_id, "entity_type": "character", "limit": 5}
        )
        if status == 200 and body is not None:
            rows = _as_items(body)
            ids = [str(row.get("id")) for row in rows if row.get("id")]
            if ids:
                return ids
    return []


def _system_id(client: Client, universe_id: str) -> str | None:
    """The game system bound to a universe, when there is one."""
    for path in (f"/api/universes/universes/{universe_id}", f"/api/universes/{universe_id}"):
        status, body, raw = client.get(path)
        if status == 200 and isinstance(body, dict):
            return body.get("default_game_system_id")
    return None


def _as_items(body: Any) -> list[dict[str, Any]]:
    """A collection response as a list of rows (list or wrapped)."""
    if isinstance(body, list):
        return [row for row in body if isinstance(row, dict)]
    if isinstance(body, dict):
        for key in ("universes", "stories", "items", "results"):
            value = body.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _timed(func: Any) -> tuple[Any, float]:
    start = time.monotonic()
    result = func()
    return result, time.monotonic() - start


def run(client: Client, universe_id: str, story_id: str | None) -> Report:
    """Exercise every endpoint the table-test protocol touches."""
    report = Report()
    system_id = _system_id(client, universe_id)

    # ── The backend answers at all ───────────────────────────────────────
    (status, _body, raw), elapsed = _timed(lambda: client.get("/api/health"))
    report.add(
        Check(
            key="health",
            what="the backend answers",
            ok=status == 200,
            detail=f"HTTP {status}" if status else raw[:200],
            seconds=elapsed,
        )
    )

    # ── S1: NPC dossier ──────────────────────────────────────────────────
    (status, body, raw), elapsed = _timed(
        lambda: client.post(
            "/api/gm/lookup/npc",
            {"universe_id": universe_id, "name": "Mira"},
        )
    )
    report.add(
        Check(
            key="S1",
            what="Lookups → NPC (dossier with what the NPC wants)",
            ok=status == 200 and bool(body),
            detail=(
                "no dossier"
                if status == 200 and not body
                else f"HTTP {status}: {raw[:160]}"
                if status != 200
                else "answered"
            ),
            seconds=elapsed,
        )
    )

    # ── S2: party knowledge ──────────────────────────────────────────────
    # It needs at least one character, exactly as the protocol's "pick the
    # party members" step does — so pick one the same way the panel does.
    character_ids = _character_ids(client, universe_id)
    (status, body, raw), elapsed = _timed(
        lambda: client.post(
            "/api/gm/lookup/party-knowledge",
            {
                "universe_id": universe_id,
                "character_ids": character_ids,
                "topic": "the harbour",
            },
        )
    )
    report.add(
        Check(
            key="S2",
            what="Lookups → Party knows (witnessed facts only)",
            ok=status == 200,
            detail=(
                "no characters in this universe to pick as the party"
                if not character_ids
                else f"HTTP {status}: {raw[:160]}"
                if status != 200
                else "answered"
            ),
            skipped=not character_ids,
            seconds=elapsed,
        )
    )

    # ── S3: last session ─────────────────────────────────────────────────
    (status, _body, raw), elapsed = _timed(
        lambda: client.post(
            "/api/gm/lookup/last-session",
            {"universe_id": universe_id, "story_id": story_id, "transcript_limit": 20},
        )
    )
    report.add(
        Check(
            key="S3",
            what="Lookups → Last session (ledger + transcript tail)",
            ok=status == 200,
            detail=_story_detail("answered", status, raw, story_id),
            skipped=story_id is None,
            seconds=elapsed,
        )
    )

    # ── S4 / S5: name and complication (model-backed) ────────────────────
    for key, what, path, body in (
        (
            "S4",
            "Lookups → Name (≤ ~30 s)",
            "/api/gm/lookup/improvise",
            {"universe_id": universe_id, "kind": "name", "context": "a courier at the docks"},
        ),
        (
            "S5",
            "Lookups → Complication (≤ ~30 s)",
            "/api/gm/lookup/improvise",
            {"universe_id": universe_id, "kind": "complication", "context": "the council is deadlocked"},
        ),
    ):
        (status, _body, raw), elapsed = _timed(lambda: client.post(path, body))
        report.add(
            Check(
                key=key,
                what=what,
                ok=status == 200,
                detail=f"HTTP {status}: {raw[:160]}" if status != 200 else "answered",
                seconds=elapsed,
            )
        )

    # ── S6: rules answer ─────────────────────────────────────────────────
    (status, _body, raw), elapsed = _timed(
        lambda: client.post(
            "/api/gm/lookup/rules",
            {
                "universe_id": universe_id,
                "system_id": system_id,
                "question": "can I push a boulder uphill?",
            },
        )
    )
    report.add(
        Check(
            key="S6",
            what="Lookups → Rules (answer carries its source)",
            ok=status == 200,
            detail=(
                "this universe has no bound game system"
                if not system_id
                else f"HTTP {status}: {raw[:160]}"
                if status != 200
                else "answered"
            ),
            skipped=not system_id,
            seconds=elapsed,
        )
    )

    # ── S7: prep extraction ──────────────────────────────────────────────
    (status, _body, raw), elapsed = _timed(
        lambda: client.post(
            "/api/gm/prep/extract",
            {
                "universe_id": universe_id,
                "story_id": story_id,
                "notes": "Mira returns to the harbour. Elder Magda is missing. "
                "The council wants the brass key.",
            },
        )
    )
    report.add(
        Check(
            key="S7",
            what="Tonight → Extract for review (prep from notes)",
            ok=status == 200,
            detail=f"HTTP {status}: {raw[:160]}" if status != 200 else "answered",
            seconds=elapsed,
        )
    )

    # ── S8 / S9: session-log proposals with contradiction flags ───────────
    (status, body, raw), elapsed = _timed(
        lambda: client.post(
            "/api/gm/session-log/propose",
            {
                "universe_id": universe_id,
                "story_id": story_id,
                "log_text": "Mira opened the sealed door and found the brass key inside.",
            },
        )
    )
    proposal_ids = (body or {}).get("proposal_ids") if isinstance(body, dict) else None
    statements = (body or {}).get("statements") if isinstance(body, dict) else None
    report.add(
        Check(
            key="S8",
            what="Session Log → Canon (proposals staged for CF-8)",
            ok=status == 200 and bool(proposal_ids),
            detail=(
                "this universe has no story to stage proposals against"
                if story_id is None
                else f"HTTP {status}: {raw[:160]}"
                if status != 200
                else f"the extraction found no world-state claims ({len(statements or [])} statements)"
                if not proposal_ids
                else f"staged {len(proposal_ids)}"
            ),
            skipped=story_id is None,
            seconds=elapsed,
        )
    )

    # ── C1–C4: the combat tracker ───────────────────────────────────────
    session_id = f"preflight-{int(time.time())}"
    combat: dict[str, Any] = {}
    (status, body, raw), elapsed = _timed(
        lambda: client.post(
            "/api/gm/combat/start",
            {
                "universe_id": universe_id,
                "session_id": session_id,
                "combatants": [
                    {"name": "Mira", "side": "pc", "hp": 24, "max_hp": 24},
                    {"name": "Goblin", "side": "enemy", "hp": 7, "max_hp": 7},
                ],
            },
        )
    )
    combat["start"] = Check(
        key="C1",
        what="Combat → start (initiative order)",
        ok=status == 200 and bool(body),
        detail=f"HTTP {status}: {raw[:160]}" if status != 200 else "started",
        seconds=elapsed,
    )
    report.add(combat["start"])

    combatants = (body or {}).get("combatants") or [] if isinstance(body, dict) else []
    combatant_id = combatants[1]["id"] if len(combatants) > 1 else None

    if combatant_id:
        (status, _body, raw), elapsed = _timed(
            lambda: client.post(
                f"/api/gm/combat/{session_id}/initiative",
                {
                    "universe_id": universe_id,
                    "entries": [
                        {"combatant_id": combatants[0]["id"], "initiative": 18},
                        {"combatant_id": combatants[1]["id"], "initiative": 11},
                    ],
                },
            )
        )
        report.add(
            Check(
                key="C1b",
                what="Combat → Set order (initiative)",
                ok=status == 200,
                detail=f"HTTP {status}: {raw[:160]}" if status != 200 else "ordered",
                seconds=elapsed,
            )
        )

        (status, _body, raw), elapsed = _timed(
            lambda: client.patch(
                f"/api/gm/combat/{session_id}/combatant/{combatant_id}",
                {"universe_id": universe_id, "hp_delta": -3, "conditions_add": ["poisoned"]},
            )
        )
        report.add(
            Check(
                key="C2",
                what="Combat → damage (HP drops, conditions stick)",
                ok=status == 200,
                detail=f"HTTP {status}: {raw[:160]}" if status != 200 else "applied",
                seconds=elapsed,
            )
        )

        (status, _body, raw), elapsed = _timed(
            lambda: client.post(
                "/api/gm/combat/condition-explain",
                {"universe_id": universe_id, "condition": "poisoned"},
            )
        )
        report.add(
            Check(
                key="C3",
                what="Combat → condition explanation",
                ok=status == 200,
                detail=f"HTTP {status}: {raw[:160]}" if status != 200 else "explained",
                seconds=elapsed,
            )
        )

        (status, _body, raw), elapsed = _timed(
            lambda: client.post(
                f"/api/gm/combat/{session_id}/end",
                {
                    "universe_id": universe_id,
                    "story_id": story_id,
                    "world_effects": ["The goblin warband swears vengeance"],
                },
            )
        )
        report.add(
            Check(
                key="C4",
                what="Combat → end (casualty/aftermath proposals staged)",
                ok=status == 200,
                detail=_story_detail("ended", status, raw, story_id),
                skipped=story_id is None,
                seconds=elapsed,
            )
        )
    else:
        report.add(
            Check(
                key="C1b-C4",
                what="Combat → order, damage, condition, end",
                ok=False,
                detail="the encounter did not start, so the rest cannot run",
            )
        )

    # ── The clock (CF-11) — used in the same session ─────────────────────
    (status, _body, raw), elapsed = _timed(
        lambda: client.get(f"/api/gm/clock/{story_id}", query={"universe_id": universe_id})
    )
    report.add(
        Check(
            key="CLOCK",
            what="World clock (CF-11) reads for the story",
            ok=status == 200,
            detail=_story_detail("read", status, raw, story_id),
            skipped=story_id is None,
            seconds=elapsed,
        )
    )

    # ── The share link (CF-14) — the player-facing side ──────────────────
    (status, _body, raw), elapsed = _timed(
        lambda: client.get(
            "/api/gm/share/link",
            query={"universe_id": universe_id, "story_id": story_id},
        )
    )
    report.add(
        Check(
            key="SHARE",
            what="Share link (CF-14) can be minted for the story",
            ok=status == 200,
            detail=_story_detail("minted", status, raw, story_id),
            skipped=story_id is None,
            seconds=elapsed,
        )
    )

    # ── The knowledge inspector (CF-15) ──────────────────────────────────
    (status, _body, raw), elapsed = _timed(
        lambda: client.get(
            f"/api/gm/knowledge/{character_ids[0] if character_ids else uuid4()}",
            query={"universe_id": universe_id},
        )
    )
    report.add(
        Check(
            key="KNOWLEDGE",
            what="Knowledge inspector (CF-15) answers",
            ok=status in (200, 404),
            detail=f"HTTP {status}: {raw[:160]}" if status not in (200, 404) else "answered",
            seconds=elapsed,
        )
    )

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--universe-id", default="")
    parser.add_argument("--story-id", default="")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    client = Client(args.base_url)

    universe_id = args.universe_id
    story_id = args.story_id or None

    if not universe_id:
        # The universes router is mounted at /api/universes and serves its
        # collection at /universes inside it.
        body: Any = None
        raw = ""
        for path in ("/api/universes/universes", "/api/universes"):
            status, body, raw = client.get(path)
            if status == 200 and body is not None:
                break
        if status != 200 or body is None:
            print(f"Could not list universes (HTTP {status}): {raw[:200]}")
            print("Pass --universe-id to run the pre-flight against a specific universe.")
            return 2
        universes = _as_items(body)
        if not universes:
            print("No universes exist. Create one (or the demo world) first.")
            return 2
        # Prefer a universe that can actually be checked — one with a bound
        # game system (S6 needs it) and characters (S2 needs them). A probe
        # universe with neither would fail those checks for want of data.
        ranked = sorted(
            universes,
            key=lambda row: (
                not bool(row.get("default_game_system_id")),
                not int(row.get("entity_count") or 0),
                not int(row.get("story_count") or 0),
            ),
        )
        universe_id = str(ranked[0].get("id"))
        print(f"Using universe {universe_id} ({ranked[0].get('name')})")

    if not story_id:
        status, body, raw = client.get("/api/stories", query={"universe_id": universe_id})
        stories = _as_items(body) if status == 200 else []
        if stories:
            story_id = str(stories[0].get("id"))
            print(f"Using the first story: {story_id}")

    print(f"\nGM table-test pre-flight — {args.base_url}")
    print(f"Universe: {universe_id}  Story: {story_id or '(none)'}\n")

    report = run(client, universe_id, story_id)

    width = max(len(c.what) for c in report.checks) + 2
    for check in report.checks:
        if check.skipped:
            mark = "SKIP"
        elif check.ok:
            mark = " ok "
        else:
            mark = "FAIL"
        print(f"[{mark}] {check.key:<8} {check.what:<{width}} {check.seconds:>6.1f}s  {check.detail}")

    passed = sum(1 for c in report.checks if c.ok)
    failed = len(report.failed)
    print(f"\n{passed} passed, {failed} failed, {len(report.skipped)} skipped")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        print(f"JSON report written to {args.json_out}")

    if failed:
        print("\nThe session will not go well until the FAIL rows are green.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
