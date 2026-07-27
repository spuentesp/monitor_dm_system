"""Live end-to-end Forge tests against the running MONITOR backend.

No mocks — drives the actual HTTP API. Covers the two World Forge on-ramps:
  1. Lorebook ingestion: upload a tiny text PDF → job reaches `completed`
     with a ready pack that has extracted entities (T-082/T-086).
  2. Quick world: a one-line seed → a committed, playable universe (T-087).

Gated by the `e2e` marker (run with RUN_E2E=1). Skips cleanly when the live
backend or an LLM provider is unavailable.
"""

from __future__ import annotations

import io
import os
import time

import pytest
import requests

API_URL = os.environ.get("MONITOR_API_URL", "http://localhost:8001/api")


def _require_backend() -> None:
    try:
        requests.get(f"{API_URL}/health", timeout=5).raise_for_status()
    except Exception as exc:
        pytest.skip(f"live backend not available: {exc}")


def _make_tiny_text_pdf() -> bytes:
    """A small PDF with a real text layer (no external fixtures)."""
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "The village of Harrowfen sits in a peat bog. Elder Wreave guards its "
        "secrets. The Pale Lantern is said to lead travelers to their doom. "
        "Iron rusts overnight in Harrowfen — a curse of the bog witch.",
    )
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.mark.e2e
def test_tiny_pdf_ingests_to_ready_pack() -> None:
    _require_backend()
    pdf = _make_tiny_text_pdf()
    title = f"E2E tiny PDF {int(time.time())}"

    resp = requests.post(
        f"{API_URL}/ingest/sources/upload",
        files={"file": ("harrowfen.pdf", pdf, "application/pdf")},
        data={
            "scan_type": "full",
            "analysis_layers": ["entities", "lore", "axioms"],
            "ingest_now": "true",
            "title": title,
        },
        timeout=60,
    )
    assert resp.status_code == 201, resp.text

    # Poll the job to a terminal state (analyze uses an LLM; allow generous time).
    deadline = time.time() + 240
    job = None
    while time.time() < deadline:
        jobs = requests.get(f"{API_URL}/ingest/jobs", timeout=10).json()
        match = [j for j in jobs if (j.get("source_title") or "") == title]
        if match:
            job = match[0]
            if job.get("status") in ("completed", "failed", "error", "cancelled"):
                break
        time.sleep(8)

    assert job is not None, "ingestion job never appeared"
    if job["status"] != "completed":
        # If the LLM provider is down, don't fail the suite — skip with the reason.
        err = (job.get("errors") or [""])[0]
        if (
            "timed out" in err.lower()
            or "connection" in err.lower()
            or "provider" in err.lower()
        ):
            pytest.skip(f"LLM provider unavailable: {err}")
        pytest.fail(f"job did not complete: status={job['status']} error={err}")

    # A ready pack with extracted entities should exist for this source.
    packs = requests.get(f"{API_URL}/ingest/packs", timeout=10).json()
    pack = next((p for p in packs if (p.get("name") or "") == title), None)
    assert pack is not None, "no pack created for the ingested source"
    assert pack.get("status") == "ready"
    assert (pack.get("entity_count") or len(pack.get("entity_archetypes", []))) > 0


@pytest.mark.e2e
def test_quick_world_seed_creates_playable_universe() -> None:
    _require_backend()
    resp = requests.post(
        f"{API_URL}/forge/quick-world",
        json={
            "seed": "A lighthouse at the edge of a sea that remembers every drowning.",
            "genre": "gothic horror",
            "tone": "mysterious",
            "start_playing": True,
        },
        timeout=180,
    )
    if resp.status_code in (502, 503):
        pytest.skip(f"world builder/LLM unavailable: {resp.text}")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["universe_id"]
    assert data["committed"] >= 1, f"nothing committed: {data.get('errors')}"
    assert data["world_name"]
    assert len(data["entities"]) >= 1

    # The universe should now be visible with entities in the graph.
    universes = requests.get(f"{API_URL}/universes/universes", timeout=10).json()
    u = next((x for x in universes if x["id"] == data["universe_id"]), None)
    assert u is not None, "quick-world universe not found in listing"
    assert (u.get("entity_count") or 0) >= 1
