#!/usr/bin/env python3
"""Controlled real-LLM GM-assistant (co-pilot) observer (heuristic, not a gate).

EPIC 7 / O4 counterpart of ``live_session_observe.py``. Bootstraps a *known*
universe (the deterministic, LLM-free Millhaven demo world), then exercises the
real-LLM co-pilot surfaces and reports soft quality signals for each:

  * **recap** (CF-2)          — length + how many canon names it references
  * **plot hooks** (CF-4)     — count + grounding (fraction naming a canon entity)
  * **contradictions** (CF-5) — count + severities
  * **session prep** (CF-7)   — completeness (recap / threads / hooks / reminders)
  * **handout** (CF-6)        — length + in-character heuristic
  * **threads** (CF-3)        — count + statuses
  * timing per surface + failure visibility
  * optional **LLM judge** — usefulness / grounding / specificity (0-5)

Grounding matters because the standing quality concern (per STATUS.md) is that
hooks were once generic ("Welcome to Millhaven"); this measures whether output
actually names canon entities. It makes **no assertions** — it writes a markdown
report + JSON summary under ``docs/testing/``.

Usage:
    docker compose --env-file .env -f infra/docker-compose.yml up -d
    uv run python scripts/live_copilot_observe.py --api-url http://localhost:8001/api
    uv run python scripts/live_copilot_observe.py --no-judge

Requires the dockerized stack up + an LLM provider (the co-pilot agents use it).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from live_gameplay_smoke import _api  # noqa: E402

try:
    import litellm
except Exception:  # noqa: BLE001
    litellm = None

DEFAULT_API_URL = os.environ.get("MONITOR_API_URL", "http://localhost:8001/api")
DEFAULT_OUTPUT_DIR = Path("docs/testing")
# Words that betray out-of-character / meta prose leaking into a player handout.
META_WORDS = ("the players", "the gm", "the dm", "as a player", "game master", "the party should")


# --------------------------------------------------------------------------- #
# Grounding helpers
# --------------------------------------------------------------------------- #
def _canon_names(http: requests.Session, base_url: str, universe_id: str) -> list[str]:
    try:
        state = _api(http, "GET", base_url, f"/universes/{universe_id}/state")
    except Exception:  # noqa: BLE001
        return []
    names: list[str] = []
    for e in state.get("entities") or []:
        n = e.get("name") if isinstance(e, dict) else None
        if n:
            names.append(str(n))
    return names


def _significant_tokens(names: list[str], exclude: set[str] | None = None) -> set[str]:
    """Distinctive lowercase tokens from canon names (drop common/world-name words).

    ``exclude`` drops the world/universe name tokens — otherwise a generic title
    like "Welcome to Millhaven" would count as grounded purely because the place
    name leaks from locations such as "Millhaven Inn". Grounding should mean the
    output names a *specific* entity, not just the setting.
    """
    stop = {"the", "of", "a", "an", "elder", "old", "inn", "and"} | (exclude or set())
    toks: set[str] = set()
    for n in names:
        for t in re.sub(r"[^a-z0-9 ]+", " ", n.lower()).split():
            if len(t) > 3 and t not in stop:
                toks.add(t)
    return toks


def _references_canon(text: str, tokens: set[str]) -> bool:
    low = (text or "").lower()
    return any(t in low for t in tokens)


# --------------------------------------------------------------------------- #
# Surface drivers — each returns (result_dict, latency_s, error_or_None)
# --------------------------------------------------------------------------- #
def _timed(fn) -> tuple[Any, float, str | None]:
    t0 = time.time()
    try:
        return fn(), round(time.time() - t0, 1), None
    except Exception as exc:  # noqa: BLE001
        return None, round(time.time() - t0, 1), str(exc)


def observe(base_url: str, *, judge_model: str, do_judge: bool) -> dict[str, Any]:
    http = requests.Session()
    health = _api(http, "GET", base_url, "/health")
    if health.get("status") != "ok":
        raise RuntimeError(f"backend unhealthy: {health}")

    demo = _api(http, "POST", base_url, "/forge/demo-world?start_playing=true", json={})
    universe_id = demo.get("universe_id")
    session_id = demo.get("session_id")
    if not universe_id:
        raise RuntimeError(f"demo-world returned no universe_id: {demo}")
    canon = _canon_names(http, base_url, universe_id)
    world_tokens = {
        t for t in re.sub(r"[^a-z0-9 ]+", " ", (demo.get("world_name") or "").lower()).split()
        if len(t) > 3
    }
    tokens = _significant_tokens(canon, exclude=world_tokens)

    # Resolve a story for the universe (session-prep + threads need it).
    story_id = None
    try:
        stories = _api(http, "GET", base_url, "/stories", params={"universe_id": universe_id})
        items = stories.get("stories") if isinstance(stories, dict) else stories
        if items:
            story_id = items[0].get("id")
    except Exception:  # noqa: BLE001
        pass

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "universe_id": universe_id,
        "session_id": session_id,
        "story_id": story_id,
        "canon_entity_count": len(canon),
        "surfaces": {},
    }
    surfaces = report["surfaces"]

    # --- CF-2 recap -------------------------------------------------------- #
    recap, lat, err = _timed(
        lambda: _api(http, "GET", base_url, f"/chat/{session_id}/recap")
    )
    text = (recap or {}).get("recap", "") if recap else ""
    surfaces["recap"] = {
        "latency_s": lat, "error": err, "chars": len(text),
        "canon_refs": sum(1 for t in tokens if t in text.lower()),
    }

    # --- CF-4 hooks -------------------------------------------------------- #
    body = {"universe_id": universe_id, "max_hooks": 5}
    if story_id:
        body["story_id"] = story_id
    hooks_resp, lat, err = _timed(
        lambda: _api(http, "POST", base_url, "/gm/hooks", json=body)
    )
    hooks = (hooks_resp or {}).get("hooks", []) if hooks_resp else []
    grounded = sum(
        1 for h in hooks
        if _references_canon(
            f"{h.get('title','')} {h.get('description','')} {' '.join(h.get('connected_entities') or [])}",
            tokens,
        )
    )
    surfaces["hooks"] = {
        "latency_s": lat, "error": err, "count": len(hooks),
        "grounded": grounded,
        "grounded_pct": round(100 * grounded / len(hooks), 1) if hooks else 0.0,
        "titles": [h.get("title") for h in hooks],
        "urgencies": [h.get("urgency") for h in hooks],
    }

    # --- CF-5 contradictions ---------------------------------------------- #
    contra_resp, lat, err = _timed(
        lambda: _api(http, "POST", base_url, "/gm/contradictions", json={"universe_id": universe_id})
    )
    contradictions = (contra_resp or {}).get("contradictions", []) if contra_resp else []
    surfaces["contradictions"] = {
        "latency_s": lat, "error": err, "count": len(contradictions),
        "severities": [c.get("severity") for c in contradictions],
    }

    # --- CF-7 session prep ------------------------------------------------- #
    if story_id:
        prep_resp, lat, err = _timed(
            lambda: _api(http, "POST", base_url, "/gm/session-prep",
                         json={"universe_id": universe_id, "story_id": story_id})
        )
        prep = (prep_resp or {}).get("prep", {}) if prep_resp else {}
        surfaces["session_prep"] = {
            "latency_s": lat, "error": err,
            "has_recap": bool(prep.get("recap")),
            "open_threads": len(prep.get("open_threads") or []),
            "hooks": len(prep.get("hooks") or []),
            "npc_reminders": len(prep.get("npc_reminders") or []),
        }
    else:
        surfaces["session_prep"] = {"error": "no story_id available", "skipped": True}

    # --- CF-6 handout ------------------------------------------------------ #
    handout_resp, lat, err = _timed(
        lambda: _api(http, "POST", base_url, "/gm/handouts",
                     json={"universe_id": universe_id, "handout_type": "letter",
                           "tone": "ominous", "spoiler_level": "safe"})
    )
    handout = (handout_resp or {}).get("handout", {}) if handout_resp else {}
    content = handout.get("content", "") if handout else ""
    surfaces["handout"] = {
        "latency_s": lat, "error": err, "chars": len(content),
        "has_title": bool(handout.get("title")),
        "in_character": not any(w in content.lower() for w in META_WORDS),
        "canon_refs": sum(1 for t in tokens if t in content.lower()),
    }

    # --- CF-3 threads ------------------------------------------------------ #
    if story_id:
        threads_resp, lat, err = _timed(
            lambda: _api(http, "GET", base_url, f"/stories/{story_id}/threads")
        )
        threads = threads_resp or []
        surfaces["threads"] = {
            "latency_s": lat, "error": err,
            "count": len(threads) if isinstance(threads, list) else 0,
            "statuses": [t.get("status") for t in threads] if isinstance(threads, list) else [],
        }
    else:
        surfaces["threads"] = {"error": "no story_id available", "skipped": True}

    if do_judge:
        report["judge"] = _judge(report, hooks, content, judge_model)
    return report


def _judge(report: dict[str, Any], hooks: list[dict], handout: str, model: str) -> dict[str, Any]:
    if litellm is None:
        return {"error": "litellm not installed"}
    rubric = {
        "usefulness": "Would these outputs actually help a GM run the next session?",
        "grounding": "Do hooks/handout reference the world's real named entities, not generic filler?",
        "specificity": "Are they concrete and distinctive rather than vague boilerplate?",
    }
    hook_lines = "\n".join(f"- {h.get('title')}: {h.get('description','')[:120]}" for h in hooks)
    prompt = (
        "You are a strict GM-assistant evaluator. Score the co-pilot output 0-5 per "
        "dimension; be critical.\n\n"
        "RUBRIC:\n" + "\n".join(f"- {k}: {v}" for k, v in rubric.items()) + "\n\n"
        f"PLOT HOOKS:\n{hook_lines}\n\n"
        f"HANDOUT (excerpt):\n{handout[:800]}\n\n"
        'Respond with ONLY JSON: {"scores": {"usefulness": int, "grounding": int, '
        '"specificity": int}, "justification": "2-3 sentences"}.'
    )
    try:
        resp = litellm.completion(
            model=model, messages=[{"role": "user", "content": prompt}],
            api_key=os.getenv("GOOGLE_API_KEY"), temperature=0.0,
        )
        text = resp["choices"][0]["message"]["content"].strip()
        start, end = text.find("{"), text.rfind("}")
        out = json.loads(text[start : end + 1])
        out["rubric"] = rubric
        return out
    except Exception as exc:  # noqa: BLE001
        return {"error": f"judge failed: {exc}"}


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    s = report["surfaces"]
    L = [
        "# GM Co-Pilot Observation",
        "",
        f"- **Universe**: `{report['universe_id']}` ({report['canon_entity_count']} canon entities)",
        f"- **Story**: `{report['story_id']}`  ·  **Session**: `{report['session_id']}`",
        "",
        "## Surfaces",
        "",
        "| Surface | Latency | Signal |",
        "|---------|---------|--------|",
        f"| CF-2 recap | {s['recap'].get('latency_s')}s | {s['recap'].get('chars')} chars, "
        f"{s['recap'].get('canon_refs')} canon refs |",
        f"| CF-4 hooks | {s['hooks'].get('latency_s')}s | {s['hooks'].get('count')} hooks, "
        f"**{s['hooks'].get('grounded_pct')}% grounded** |",
        f"| CF-5 contradictions | {s['contradictions'].get('latency_s')}s | "
        f"{s['contradictions'].get('count')} found {s['contradictions'].get('severities')} |",
        f"| CF-7 session-prep | {s['session_prep'].get('latency_s')}s | "
        f"recap={s['session_prep'].get('has_recap')}, threads={s['session_prep'].get('open_threads')}, "
        f"hooks={s['session_prep'].get('hooks')}, reminders={s['session_prep'].get('npc_reminders')} |",
        f"| CF-6 handout | {s['handout'].get('latency_s')}s | {s['handout'].get('chars')} chars, "
        f"in-character={s['handout'].get('in_character')}, {s['handout'].get('canon_refs')} canon refs |",
        f"| CF-3 threads | {s['threads'].get('latency_s')}s | {s['threads'].get('count')} threads |",
    ]
    errs = {k: v.get("error") for k, v in s.items() if v.get("error")}
    if errs:
        L += ["", "## Errors", ""]
        L += [f"- **{k}**: {v}" for k, v in errs.items()]
    if s["hooks"].get("titles"):
        L += ["", "## Hook titles", ""]
        L += [f"- {t}" for t in s["hooks"]["titles"]]
    judge = report.get("judge") or {}
    if judge.get("scores"):
        js = judge["scores"]
        avg = round(sum(js.values()) / len(js), 2)
        L += ["", "## Judge", "", f"**Average: {avg}/5**", ""]
        L += [f"- {k}: **{v}/5**" for k, v in js.items()]
        if judge.get("justification"):
            L += ["", f"> {judge['justification']}"]
    path.write_text("\n".join(L), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api-url", default=DEFAULT_API_URL)
    ap.add_argument("--judge-model", default=os.getenv("GM_EVAL_JUDGE", "gemini/gemini-2.5-flash"))
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = ap.parse_args()

    report = observe(args.api_url, judge_model=args.judge_model, do_judge=not args.no_judge)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    md_path = out_dir / f"observe_copilot_{stamp}.md"
    json_path = out_dir / f"observe_copilot_{stamp}.json"
    write_markdown(md_path, report)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    s = report["surfaces"]
    print(f"recap:          {s['recap'].get('chars')} chars, {s['recap'].get('canon_refs')} canon refs")
    print(f"hooks:          {s['hooks'].get('count')} ({s['hooks'].get('grounded_pct')}% grounded)")
    print(f"contradictions: {s['contradictions'].get('count')} {s['contradictions'].get('severities')}")
    print(f"handout:        {s['handout'].get('chars')} chars, in-character={s['handout'].get('in_character')}")
    print(f"threads:        {s['threads'].get('count')}")
    if (report.get("judge") or {}).get("scores"):
        js = report["judge"]["scores"]
        print(f"judge avg:      {round(sum(js.values())/len(js), 2)}/5")
    print(f"log:            {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
