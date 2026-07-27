#!/usr/bin/env python3
"""Verify the harness actually persisted everything it claimed to.

For every transcript in tests/e2e/logs/full_loop/, query Mongo + Neo4j
directly and report whether the persisted state matches the JSON claims.
"""
from __future__ import annotations

import json
from pathlib import Path

LOG_DIR = Path("tests/e2e/logs/full_loop")


def main() -> None:
    from monitor_data.db.mongodb import get_mongodb_client
    from monitor_data.db.neo4j import get_neo4j_client

    mongo = get_mongodb_client()
    neo = get_neo4j_client()

    print(f"{'run':<55} {'story_id':<10} {'claimed':>7} {'actual':>7} {'match':>6} {'actor_persisted':>17}")
    print("-" * 110)

    for p in sorted(LOG_DIR.glob("*.json")):
        data = json.loads(p.read_text())
        story_id = data.get("story_id")
        if not story_id or story_id == "?":
            print(f"  {p.stem:<55} (no story_id)")
            continue

        # JSON claim: scenes × turns.
        if "scene_runs" in data:
            scenes_claim = data.get("scene_runs") or []
        else:
            scenes_claim = [{"scene_id": data.get("scene_id"), "turns": data.get("turns", [])}]
        claimed_scenes = {s.get("scene_id") for s in scenes_claim if s.get("scene_id")}

        # Mongo reality.
        mongo_scenes = list(mongo["scenes"].find({"story_id": story_id}))
        actual_scenes = {s["scene_id"] for s in mongo_scenes}
        match = "✓" if claimed_scenes == actual_scenes else f"diff={claimed_scenes ^ actual_scenes}"

        # Actor persistence check. Character identity (name, description)
        # lives on the Neo4j Entity, NOT the MongoDB CharacterSheet —
        # CharacterSheetCreate has no universe_id field by design (see
        # character_sheets.py module docstring). Query Neo4j for the most
        # recent character Entity in this story's universe, then confirm
        # a sheet exists for it via entity_id (a field the sheet DOES have).
        actor_persisted = ""
        uni_rows = neo.execute_read(
            "MATCH (s:Story {id: $sid}) RETURN s.universe_id AS uid",
            {"sid": story_id},
        )
        if uni_rows:
            uid = uni_rows[0]["uid"]
            entity_rows = neo.execute_read(
                "MATCH (e:Entity {universe_id: $uid, entity_type: 'character'}) "
                "RETURN e.id AS id, e.name AS name "
                "ORDER BY e.created_at DESC LIMIT 1",
                {"uid": str(uid)},
            )
            if entity_rows:
                entity_id = entity_rows[0]["id"]
                has_sheet = mongo["character_sheets"].find_one({"entity_id": entity_id}) is not None
                marker = "" if has_sheet else " (no sheet!)"
                actor_persisted = f"{entity_id[:8]}{marker}"

        print(
            f"  {p.stem:<55} {story_id[:8]}..  {len(claimed_scenes):>7} {len(actual_scenes):>7}   "
            f"{match:>5}   {actor_persisted or '-':>17}"
        )


if __name__ == "__main__":
    main()
