#!/usr/bin/env python3
"""Playwright smoke test — drives the live web UI with the LLM player.

Uses the same InstructablePlayer as the headless harness, so behavior
matches the canonical session driver.

Assumes:
    - Backend is reachable at http://localhost:8001
    - Frontend is reachable at http://localhost:3000
    - LLM provider is reachable (Gemini 2.5 Flash)

Run from repo root:
    uv run python scripts/vtm_web_smoke.py [turn_count]
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from scripts._shared_vtm import setup_logging  # noqa: E402
from scripts.vtm_embrace_session import (  # noqa: E402
    PLAYER_CONCEPT, PLAYER_GOAL, PLAYER_LANGUAGE,
    PLAYER_MODEL, PLAYER_SEED,
)
from monitor_agents.players import (  # noqa: E402
    InstructablePlayer, InstructedSpec, PlayerContext,
)

SCREENSHOT_DIR = Path("tests/e2e/logs/vtm_embrace")
BACKEND_HEALTH = "http://localhost:8001/api/health"
FRONTEND_URL = "http://localhost:3000"


async def wait_for_health(url: str, label: str, timeout: int = 60) -> None:
    """Poll a URL until it returns <500 or until timeout."""
    deadline = time.time() + timeout
    last_err: str = ""
    async with httpx.AsyncClient() as c:
        while time.time() < deadline:
            try:
                r = await c.get(url, timeout=2)
                if r.status_code < 500:
                    print(f"[smoke] {label} healthy (status={r.status_code})")
                    return
                last_err = f"status={r.status_code}"
            except Exception as exc:  # noqa: BLE001
                last_err = str(exc)[:120]
            await asyncio.sleep(1)
    raise RuntimeError(f"health check timed out for {url}: {last_err}")


async def main(turns: int = 6) -> None:
    setup_logging()
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    # Assumes backend + frontend are already up. If not, raise with a clear message.
    await wait_for_health(BACKEND_HEALTH, "backend")
    try:
        await wait_for_health(FRONTEND_URL, "frontend")
    except RuntimeError:
        print("[smoke] WARNING: frontend health probe failed; continuing anyway.")

    player = InstructablePlayer(
        spec=InstructedSpec(
            model=PLAYER_MODEL, temperature=0.9, max_tokens=180,
        ),
        context=PlayerContext(
            concept=PLAYER_CONCEPT, seed=PLAYER_SEED,
            goal=PLAYER_GOAL, language=PLAYER_LANGUAGE,
        ),
        recent_turns_max=3,
    )

    from playwright.async_api import async_playwright  # imported here to fail fast if missing

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()

        console_errors: list[str] = []
        page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))
        page.on(
            "console",
            lambda m: console_errors.append(f"console.{m.type}: {m.text}")
            if m.type in ("error", "warning")
            else None,
        )

        print(f"[smoke] navigating to {FRONTEND_URL}/play")
        await page.goto(f"{FRONTEND_URL}/play", timeout=30000)
        await page.wait_for_load_state("networkidle", timeout=30000)

        # Try the documented selector first, fall back to any textarea.
        chat_input = None
        try:
            chat_input = page.locator('textarea[aria-label="Send message"]').first
            await chat_input.wait_for(timeout=10000)
            print("[smoke] found composer via aria-label")
        except Exception:
            chat_input = page.locator("textarea").first
            try:
                await chat_input.wait_for(timeout=5000)
                print("[smoke] found composer via fallback textarea selector")
            except Exception as exc:  # noqa: BLE001
                await page.screenshot(path=str(SCREENSHOT_DIR / "ui_no_input_found.png"))
                raise RuntimeError(f"Could not locate chat input: {exc}")

        for turn_idx in range(turns):
            print(f"[smoke] turn {turn_idx + 1}/{turns}")
            try:
                action_text, intent = await player.next()
            except Exception as exc:  # noqa: BLE001
                print(f"[smoke] player.next() failed: {exc}")
                action_text = "I take stock of the situation."
                intent = "fallback (player error)"
            await chat_input.fill(action_text)
            await chat_input.press("Enter")
            # Heuristic wait for the GM response to settle
            await page.wait_for_timeout(3000)
            await page.screenshot(path=str(SCREENSHOT_DIR / f"ui_turn_{turn_idx + 1}.png"))
            player.observe(gm_text="", player_text=action_text, intent=intent)

        await browser.close()

    print(f"\n[smoke] screenshots written to: {SCREENSHOT_DIR}")
    print(f"[smoke] console errors/warnings: {len(console_errors)}")
    for err in console_errors[:8]:
        print(f"  - {err}")


if __name__ == "__main__":
    n_turns = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    asyncio.run(main(n_turns))