#!/usr/bin/env python3
"""Render a transcript from already-persisted scene/turn data.

Useful when the live run was killed by rate limits but partial data
already landed in MongoDB. Takes story_id and (optionally) actor_id,
prints a markdown transcript to stdout.

Usage:
    uv run python scripts/vtm_render_persisted.py <story_id> [actor_id]
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from scripts._shared_vtm import format_dice_highlight  # noqa: E402


async def render(story_id: str, actor_id: str | None) -> Path:
    client = AsyncIOMotorClient(
        "mongodb://monitor:changeme-mongodb@localhost:27017/monitor?authSource=admin"
    )
    try:
        scenes = [s async for s in client.monitor.scenes.find({"story_id": story_id})]
        scenes.sort(key=lambda s: s.get("narrative_order") or 0)

        # Pull resolutions for dice highlights
        scene_ids = [s.get("scene_id") for s in scenes if s.get("scene_id")]
        resolutions = []
        async for r in client.monitor.resolutions.find({"scene_id": {"$in": scene_ids}}):
            resolutions.append(r)
        res_by_turn = {r.get("turn_id"): r for r in resolutions if r.get("turn_id")}

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = Path("tests/e2e/logs/vtm_embrace")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"vtm_embrace_persisted_{ts}.md"

        lines: list[str] = []
        lines.append(f"# VtM Embrace — Persisted Transcript")
        lines.append("")
        lines.append(f"_Rendered at {ts} UTC from MongoDB scenes for story_id={story_id}_")
        if actor_id:
            lines.append(f"_Actor ID: {actor_id}_")
        lines.append("")
        lines.append(f"_Scenes: {len(scenes)}; total turns: {sum(len(s.get('turns', [])) for s in scenes)}_")
        lines.append("")

        for scene_idx, scene in enumerate(scenes, 1):
            title = scene.get("title", f"Scene {scene_idx}")
            lines.append(f"## Scene {scene_idx}: {title}")
            lines.append("")
            turns = scene.get("turns", []) or []
            if not turns:
                lines.append("_(no turns in this scene)_")
                lines.append("")
                continue
            for t in turns:
                speaker = str(getattr(t.get("speaker"), "value", t.get("speaker")))
                text = (t.get("text") or "").strip()
                lines.append(f"**{speaker}:** {text}")
                lines.append("")
                # Dice highlight if this turn triggered a resolution
                res = res_by_turn.get(str(t.get("turn_id")))
                if res:
                    dice = (res.get("mechanics") or {}).get("dice_results")
                    if dice:
                        dice_line = format_dice_highlight(f"turn {t.get('turn_id', '?')[:8]}", dice)
                        if dice_line:
                            lines.append(f"_{dice_line}_")
                            lines.append("")
            lines.append("---")
            lines.append("")

        out_path.write_text("\n".join(lines))
        return out_path
    finally:
        client.close()


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: vtm_render_persisted.py <story_id> [actor_id]")
        sys.exit(1)
    story_id = sys.argv[1]
    actor_id = sys.argv[2] if len(sys.argv) > 2 else None
    out = await render(story_id, actor_id)
    print(f"Rendered transcript: {out}")


if __name__ == "__main__":
    asyncio.run(main())