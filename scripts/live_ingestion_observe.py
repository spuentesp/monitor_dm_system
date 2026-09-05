#!/usr/bin/env python3
"""Controlled real-LLM ingestion observer (heuristic, not a gate).

World Architect / EPIC 2 counterpart of ``live_session_observe.py``. Uploads a
*known* fixture document whose named entities, lore, and axiom are fixed in this
file, runs the real ingestion pipeline (extraction uses an LLM), then reads the
resulting Knowledge Pack back and reports soft quality signals:

  * **recall** — how many planted named entities were extracted (name + aliases)
  * **precision noise** — extracted entities that are NOT in the planted set
    (often generic taxonomy: "Village", "Militia" — arguably intentional)
  * **lore / axiom capture** — counts + whether the planted axiom was found
  * **timing** — wall-clock to a terminal job state, plus failure visibility
  * optional **LLM judge** — coverage / type-accuracy / faithfulness (0-5)

It makes **no assertions**. It writes a human-readable markdown report plus a
JSON summary under ``docs/testing/``.

Usage:
    docker compose --env-file .env -f infra/docker-compose.yml up -d
    uv run python scripts/live_ingestion_observe.py --api-url http://localhost:8001/api
    uv run python scripts/live_ingestion_observe.py --no-judge   # skip the LLM judge

Requires the dockerized stack up + an LLM provider configured for extraction.
The judge needs GOOGLE_API_KEY (or a matching key for --judge-model).
"""

from __future__ import annotations

import argparse
import io
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

# --------------------------------------------------------------------------- #
# The controlled fixture: a short setting with a KNOWN, labelled cast.
# Recall is measured against PLANTED_ENTITIES / PLANTED_AXIOM below.
# --------------------------------------------------------------------------- #
FIXTURE_TEXT = (
    "The Chronicle of Harrowfen\n\n"
    "Harrowfen is a fog-bound village built on a peat bog at the edge of "
    "Mournmere, the black lake. Elder Wreave, the village headman, guards the "
    "old covenants and fears the coming of winter. The Bog Witch dwells beneath "
    "the waters of Mournmere and trades memories for years of life. Captain "
    "Holloway leads the Lantern Wardens, a militia that patrols the causeway "
    "after dusk. The Pale Lantern is a cursed light that lures travelers off the "
    "safe paths into the sucking mud. By ancient law, iron rusts overnight in "
    "Harrowfen, for the bog will not abide worked metal. The Wardens swear the "
    "Oath of Salt each spring to keep the witch bound beneath the lake."
)

# Planted named entities: canonical name -> expected entity_type.
PLANTED_ENTITIES: dict[str, str] = {
    "Harrowfen": "location",
    "Mournmere": "location",
    "The Pale Lantern": "object",
    "Elder Wreave": "character",
    "The Bog Witch": "character",
    "Captain Holloway": "character",
    "The Lantern Wardens": "faction",
}
PLANTED_AXIOM = "iron rusts overnight in Harrowfen"


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).strip()


def _name_matches(planted: str, candidate: str) -> bool:
    """Bidirectional token-substring match, ignoring articles/titles."""
    stop = {"the", "a", "an", "elder", "captain", "of"}
    p = " ".join(t for t in _norm(planted).split() if t not in stop)
    c = " ".join(t for t in _norm(candidate).split() if t not in stop)
    if not p or not c:
        return False
    return p in c or c in p


# --------------------------------------------------------------------------- #
# Pipeline drive + read-back
# --------------------------------------------------------------------------- #
def _make_pdf() -> bytes:
    """Build the fixture as a real text-layer PDF (PyMuPDF)."""
    try:
        # reason: PyMuPDF (fitz) lacks type stubs; suppress until upstream adds py.typed
        import fitz  # type: ignore
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "PyMuPDF (fitz) is required to build the fixture PDF"
        ) from exc
    doc = fitz.open()
    page = doc.new_page()
    # Wrap so the text layer stays on the page.
    y = 72
    for para in FIXTURE_TEXT.split("\n"):
        for chunk in [para[i : i + 90] for i in range(0, len(para), 90)] or [""]:
            page.insert_text((72, y), chunk)
            y += 14
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _upload(http: requests.Session, base_url: str, title: str) -> None:
    pdf = _make_pdf()
    resp = http.post(
        f"{base_url}/ingest/sources/upload",
        files={"file": ("harrowfen.pdf", pdf, "application/pdf")},
        data={
            "scan_type": "full",
            "analysis_layers": ["entities", "lore", "axioms"],
            "ingest_now": "true",
            "title": title,
        },
        timeout=60,
    )
    resp.raise_for_status()


def _poll_job(http: requests.Session, base_url: str, title: str, timeout_s: int) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last: dict[str, Any] = {}
    while time.time() < deadline:
        jobs = _api(http, "GET", base_url, "/ingest/jobs")
        match = [j for j in jobs if (j.get("source_title") or "") == title]
        if match:
            last = match[0]
            if last.get("status") in ("completed", "failed", "error", "cancelled"):
                return last
        time.sleep(6)
    return last or {"status": "timeout"}


def _find_pack(http: requests.Session, base_url: str, title: str) -> dict[str, Any] | None:
    packs = _api(http, "GET", base_url, "/ingest/packs")
    summary = next((p for p in packs if (p.get("name") or "") == title), None)
    if not summary:
        return None
    return _api(http, "GET", base_url, f"/ingest/packs/{summary['id']}")


# --------------------------------------------------------------------------- #
# Soft metrics
# --------------------------------------------------------------------------- #
def _score_extraction(pack: dict[str, Any]) -> dict[str, Any]:
    archetypes = pack.get("entity_archetypes") or []
    extracted_names: list[tuple[str, list[str]]] = [
        (str(e.get("name", "")), list(e.get("aliases") or [])) for e in archetypes
    ]

    found: dict[str, str | None] = {}
    matched_extracted: set[str] = set()
    for planted, _etype in PLANTED_ENTITIES.items():
        hit = None
        for name, aliases in extracted_names:
            # Each extracted entity may satisfy at most one planted entity, so a
            # single generic "Lantern" can't be credited to both "Pale Lantern"
            # and "Lantern Wardens" and inflate recall.
            if name in matched_extracted:
                continue
            if any(_name_matches(planted, cand) for cand in [name, *aliases]):
                hit = name
                matched_extracted.add(name)
                break
        found[planted] = hit

    recall_hits = sum(1 for v in found.values() if v)
    # Type accuracy on the entities we did find.
    type_correct = 0
    type_checked = 0
    by_name = {str(e.get("name", "")): e for e in archetypes}
    for planted, etype in PLANTED_ENTITIES.items():
        hit = found[planted]
        if hit and hit in by_name:
            type_checked += 1
            if str(by_name[hit].get("entity_type", "")).lower() == etype:
                type_correct += 1

    extra = [name for name, _ in extracted_names if name not in matched_extracted]
    lore = pack.get("lore_facts") or []
    axioms = pack.get("axioms") or []
    axiom_found = any(
        _norm(PLANTED_AXIOM) in _norm(a.get("statement", "")) or
        ("iron" in _norm(a.get("statement", "")) and "rust" in _norm(a.get("statement", "")))
        for a in axioms
    )
    return {
        "planted_entities": len(PLANTED_ENTITIES),
        "entities_extracted": len(archetypes),
        "recall_hits": recall_hits,
        "recall_pct": round(100 * recall_hits / len(PLANTED_ENTITIES), 1),
        "found_map": found,
        "type_accuracy": f"{type_correct}/{type_checked}" if type_checked else "n/a",
        "precision_noise_count": len(extra),
        "precision_noise_names": extra,
        "lore_facts": len(lore),
        "axiom_count": len(axioms),
        "planted_axiom_found": axiom_found,
    }


def _judge_extraction(pack: dict[str, Any], model: str) -> dict[str, Any]:
    if litellm is None:
        return {"error": "litellm not installed"}
    entities = [
        f"- {e.get('name')} ({e.get('entity_type')}): {e.get('description', '')[:80]}"
        for e in (pack.get("entity_archetypes") or [])
    ]
    lore = [f"- {f.get('statement')}" for f in (pack.get("lore_facts") or [])]
    rubric = {
        "coverage": "Were the source's key named entities all captured?",
        "type_accuracy": "Are entity types (character/location/faction/object) correct?",
        "faithfulness": "Is everything grounded in the source with no invented facts?",
        "lore_quality": "Are the lore facts accurate, specific, and useful?",
    }
    prompt = (
        "You are a strict knowledge-extraction evaluator. Below is a SOURCE TEXT "
        "and the ENTITIES + LORE a system extracted from it. Score 0-5 per "
        "dimension; be critical.\n\n"
        "RUBRIC:\n" + "\n".join(f"- {k}: {v}" for k, v in rubric.items()) + "\n\n"
        f"SOURCE TEXT:\n{FIXTURE_TEXT}\n\n"
        f"EXTRACTED ENTITIES:\n" + "\n".join(entities) + "\n\n"
        "EXTRACTED LORE:\n" + "\n".join(lore) + "\n\n"
        'Respond with ONLY JSON: {"scores": {"coverage": int, "type_accuracy": int, '
        '"faithfulness": int, "lore_quality": int}, "justification": "2-3 sentences"}.'
    )
    try:
        resp = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0.0,
        )
        text = resp["choices"][0]["message"]["content"].strip()
        start, end = text.find("{"), text.rfind("}")
        out = json.loads(text[start : end + 1])
        out["rubric"] = rubric
        return out
    except Exception as exc:  # noqa: BLE001
        return {"error": f"judge failed: {exc}"}


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def write_markdown(path: Path, report: dict[str, Any]) -> None:
    s = report["scores"]
    L = [
        "# Ingestion Observation",
        "",
        f"- **Title**: `{report['title']}`",
        f"- **Job status**: `{report['job_status']}`  ·  **wall**: `{report['wall_s']}s`",
        f"- **Pack status**: `{report.get('pack_status')}`  ·  **pack id**: `{report.get('pack_id')}`",
        "",
        "## Recall (planted named entities)",
        "",
        f"**{s['recall_hits']}/{s['planted_entities']} = {s['recall_pct']}%**  ·  "
        f"type accuracy {s['type_accuracy']}",
        "",
    ]
    for planted, hit in s["found_map"].items():
        mark = "✅" if hit else "❌"
        L.append(f"- {mark} **{planted}** {'→ `' + hit + '`' if hit else '— MISSING'}")
    L += [
        "",
        "## Other signals",
        "",
        f"- Entities extracted total: {s['entities_extracted']} "
        f"(precision noise: {s['precision_noise_count']})",
        f"- Lore facts: {s['lore_facts']}  ·  Axioms: {s['axiom_count']}  ·  "
        f"planted axiom found: {s['planted_axiom_found']}",
    ]
    if s["precision_noise_names"]:
        L.append(f"- Noise names: `{s['precision_noise_names']}`")
    if report.get("job_errors"):
        L += ["", "## Job errors", "", f"```\n{report['job_errors']}\n```"]
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
    ap.add_argument("--timeout", type=int, default=300, help="Max seconds to await the job")
    ap.add_argument("--judge-model", default=os.getenv("GM_EVAL_JUDGE", "gemini/gemini-2.5-flash"))
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = ap.parse_args()

    http = requests.Session()
    health = _api(http, "GET", args.api_url, "/health")
    if health.get("status") != "ok":
        print(f"backend unhealthy: {health}", file=sys.stderr)
        return 1

    title = f"observe-ingest Harrowfen {int(time.time())}"
    print(f"uploading fixture: {title}")
    t0 = time.time()
    _upload(http, args.api_url, title)
    job = _poll_job(http, args.api_url, title, args.timeout)
    wall = round(time.time() - t0, 1)
    status = job.get("status", "unknown")
    print(f"  job status: {status} ({wall}s)")

    pack = _find_pack(http, args.api_url, title) if status == "completed" else None
    if pack is None:
        scores = {
            "planted_entities": len(PLANTED_ENTITIES), "entities_extracted": 0,
            "recall_hits": 0, "recall_pct": 0.0,
            "found_map": {k: None for k in PLANTED_ENTITIES},
            "type_accuracy": "n/a", "precision_noise_count": 0,
            "precision_noise_names": [], "lore_facts": 0, "axiom_count": 0,
            "planted_axiom_found": False,
        }
    else:
        scores = _score_extraction(pack)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "job_status": status,
        "job_errors": (job.get("errors") or [None])[0] if isinstance(job.get("errors"), list) else job.get("errors"),
        "wall_s": wall,
        "pack_id": pack.get("id") if pack else None,
        "pack_status": pack.get("status") if pack else None,
        "scores": scores,
        "judge": {},
    }
    if pack and not args.no_judge:
        print("  judging extraction...")
        report["judge"] = _judge_extraction(pack, args.judge_model)

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    md_path = out_dir / f"observe_ingest_{stamp}.md"
    json_path = out_dir / f"observe_ingest_{stamp}.json"
    write_markdown(md_path, report)
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"  recall:    {scores['recall_hits']}/{scores['planted_entities']} ({scores['recall_pct']}%)")
    print(f"  lore/axiom: {scores['lore_facts']} lore, {scores['axiom_count']} axioms "
          f"(planted axiom found: {scores['planted_axiom_found']})")
    print(f"  noise:     {scores['precision_noise_count']} extra entities")
    if report["judge"].get("scores"):
        js = report["judge"]["scores"]
        print(f"  judge avg: {round(sum(js.values())/len(js), 2)}/5")
    print(f"  log:       {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
