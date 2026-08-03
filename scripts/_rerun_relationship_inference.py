#!/usr/bin/env python3
"""
Re-run relationship inference against the existing VtM knowledge pack and
write the new relationships back to Neo4j directly.

What this does, end-to-end:
  1. Loads the current VtM knowledge pack from MongoDB.
  2. Pulls the 192 entity archetypes out of `entity_archetypes`.
  3. Instantiates the analyzer and calls `_infer_relationships` on the
     same entities, with the patched prompt (no 'none' / no self-refs).
  4. For each new ExtractedRelationship, resolves both endpoints by exact
     name match (using the patched `_resolve_name_to_uuid`) and writes
     the relationship to Neo4j via the MCP tool.

This is the focused re-run for option (1) of the recovery plan after the
first ingest left Beast / Caitiff / Clan / Caine / Lupines / Arcanum etc.
as dead-end nodes with no outgoing SUBTYPE_OF edges. It does NOT re-ingest
the PDF, does NOT re-create entities, and does NOT touch the knowledge
pack's existing axioms / lore / snippets.

Run from the repo root with the dev infra up:

    uv run python scripts/_rerun_relationship_inference.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Make both data-layer and agents importable from the repo root.
sys.path.insert(0, "packages/data-layer/src")
sys.path.insert(0, "packages/agents/src")

# Load .env for provider creds etc.
ENV_PATH = Path(".env")
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from monitor_data.db.mongodb import MongoDBClient  # noqa: E402
from monitor_data.schemas.knowledge_packs import (  # noqa: E402
    ExtractedEntityArchetype,
    ExtractedRelationship,
)
from monitor_agents.analyzer._core import Analyzer  # noqa: E402


async def main(args: "argparse.Namespace | None" = None) -> None:
    """Re-run relationship inference against an existing knowledge pack
    and write the new relationships back to Neo4j directly.

    What this does, end-to-end:
      1. Loads the knowledge pack from MongoDB (by --pack-name or
         --pack-id, defaulting to the legacy "VtM 20th Anniversary
         Corebook" name for backward compatibility).
      2. Pulls the entity archetypes out of `entity_archetypes`.
      3. Instantiates the analyzer and calls `_infer_relationships` on
         the same entities, with the new prompt + alias normaliser.
      4. For each new ExtractedRelationship, resolves both endpoints
         by exact name match and writes the relationship to Neo4j.
    """
    mongo = MongoDBClient()
    await mongo.connect()
    try:
        packs = mongo.get_collection("knowledge_packs")
        # Resolve the pack to use. CLI args take precedence; if neither
        # --pack-name nor --pack-id is given, fall back to the legacy
        # VtM name so existing invocations keep working.
        pack_name = getattr(args, "pack_name", None) if args else None
        pack_id = getattr(args, "pack_id", None) if args else None
        if pack_id:
            pack_doc = packs.find_one({"pack_id": pack_id})
            if not pack_doc:
                print(f"ERROR: Knowledge pack with id {pack_id!r} not found.")
                sys.exit(1)
        elif pack_name:
            pack_doc = packs.find_one({"name": pack_name})
            if not pack_doc:
                print(f"ERROR: Knowledge pack with name {pack_name!r} not found.")
                sys.exit(1)
        else:
            pack_doc = packs.find_one({"name": "VtM 20th Anniversary Corebook"})
            if not pack_doc:
                print(
                    "ERROR: Default pack 'VtM 20th Anniversary Corebook' not found. "
                    "Pass --pack-name or --pack-id to target a different pack."
                )
                sys.exit(1)

        # The 192 entity archetypes already canonized in Mongo. Re-load them
        # as proper Pydantic models so the analyzer is happy.
        raw_entities = pack_doc.get("entity_archetypes", [])
        entities: list[ExtractedEntityArchetype] = [
            ExtractedEntityArchetype(**e) for e in raw_entities
        ]
        # source_name is used only as a label in the LLM call.
        source_name = pack_doc.get("name", "VtM 20th Anniversary Corebook")

        # The pack doesn't store universe_id directly; the source documents do.
        docs = mongo.get_collection("documents")
        universe_id = ""
        for doc_id_str in pack_doc.get("source_document_ids", []):
            d = docs.find_one({"doc_id": str(doc_id_str)})
            if d and d.get("universe_id"):
                universe_id = d["universe_id"]
                break

        print(
            f"Loaded {len(entities)} entities from knowledge pack "
            f"{pack_doc.get('pack_id')}"
        )
        print(f"Universe ID: {universe_id}")
        print()
        print("Running relationship inference (this will make ~63 LLM calls)...")
        print()

        analyzer = Analyzer(agent_id="rerun-rel-inference-1")
        try:
            new_rels: list[ExtractedRelationship] = await analyzer._infer_relationships(
                entities=entities,
                source_name=source_name,
                source_profile_context=(
                    "Vampire: The Masquerade 20th Anniversary corebook. "
                    "Gothic-Punk horror. Focus on VtM-specific ontology: "
                    "Clans, Disciplines, Sects, the Jyhad, the Beast, "
                    "Paths of Enlightenment, Thaumaturgy, etc."
                ),
            )
        finally:
            # The Analyzer BaseAgent holds a few async resources; close cleanly.
            try:
                await analyzer.close()  # type: ignore[attr-defined]
            except Exception:
                pass

        # Drop any self-references and placeholder names that slipped through.
        # (Belt-and-braces — the prompt was patched to forbid both, but a
        # bad LLM response shouldn't be allowed to re-poison the graph.)
        clean: list[ExtractedRelationship] = []
        placeholder = {
            "none", "unknown", "n/a", "na", "unspecified",
            "unnamed", "null", "nil", "tbd", "-", "",
        }
        for r in new_rels:
            f = (r.from_entity or "").strip().lower()
            t = (r.to_entity or "").strip().lower()
            if f in placeholder or t in placeholder:
                print(f"  SKIP placeholder: {r.from_entity!r} -> {r.to_entity!r}")
                continue
            if f == t:
                print(f"  SKIP self-ref:    {r.from_entity!r} -> {r.to_entity!r}")
                continue
            clean.append(r)
        print()
        print(f"Produced {len(clean)} clean relationships.")

        # Persist back to the knowledge pack so the next canonization sees
        # the new ones. Replace the old list (which had 0 in it anyway —
        # all the originals were filtered out as 'X -> none' or self-refs).
        packs.update_one(
            {"pack_id": pack_doc["pack_id"]},
            {
                "$set": {
                    "entity_relationships": [r.model_dump() for r in clean],
                    "updated_at": __import__("datetime").datetime.utcnow(),
                }
            },
        )
        print(f"Updated knowledge_pack.entity_relationships in MongoDB.")

        # Now create the relationships in Neo4j directly via the MCP tool
        # wrapper, using exact-name match for both endpoints.
        from monitor_agents.canonkeeper.agent import CanonKeeper

        keeper = CanonKeeper(agent_id="rerun-rel-canonize-1")
        try:
            from_id = await keeper._resolve_name_to_uuid("__init__", "")  # warm up
        except Exception:
            pass

        committed = 0
        skipped_missing = 0
        skipped_self = 0
        errors = 0
        for r in clean:
            from_id = await keeper._resolve_name_to_uuid(r.from_entity, universe_id or "")
            to_id = await keeper._resolve_name_to_uuid(r.to_entity, universe_id or "")
            if not from_id or not to_id:
                skipped_missing += 1
                print(
                    f"  MISS  {r.from_entity!r} -> {r.to_entity!r}: "
                    f"{'from' if not from_id else 'to'} not in graph"
                )
                continue
            if from_id == to_id:
                skipped_self += 1
                print(f"  SELF  {r.from_entity!r} -> {r.to_entity!r}")
                continue
            rel_type = (r.rel_type or "related_to").strip().lower()
            neo4j_rel_type = keeper._REL_TYPE_MAP.get(rel_type, "RELATED_TO")
            rel_category = keeper._REL_CATEGORY_MAP.get(neo4j_rel_type, "generic")
            result_text = await keeper.call_tool(
                "neo4j_create_relationship",
                {
                    "params": {
                        "from_entity_id": from_id,
                        "to_entity_id": to_id,
                        "rel_type": neo4j_rel_type,
                        "category": rel_category,
                        "properties": {
                            "description": r.description or "",
                            "confidence": float(r.confidence or 0.8),
                            "authority": "source",
                            "canon_level": "proposed",
                        },
                    }
                },
            )
            # call_tool returns a dict; check for the error key.
            if isinstance(result_text, dict) and result_text.get("error"):
                errors += 1
                print(f"  ERR   {r.from_entity!r} -> {r.to_entity!r}: {result_text['error']}")
                continue
            committed += 1
        try:
            await keeper.close()  # type: ignore[attr-defined]
        except Exception:
            pass

        print()
        print(
            f"Committed {committed} relationships, "
            f"skipped {skipped_missing} (target missing) "
            f"+ {skipped_self} (self-ref), {errors} errors"
        )
    finally:
        await mongo.close()


def _cli() -> None:
    """CLI entry point. Allows the rerun to be invoked against any
    knowledge pack by name, not just the hardcoded VtM pack.

    Usage:
        uv run python scripts/_rerun_relationship_inference.py [--pack-name NAME] [--pack-id UUID]

    If neither --pack-name nor --pack-id is given, falls back to the
    legacy "VtM 20th Anniversary Corebook" name for backward
    compatibility.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--pack-name",
        default=None,
        help="Name of the knowledge pack to re-run relationship inference on. "
             "Defaults to 'VtM 20th Anniversary Corebook'.",
    )
    parser.add_argument(
        "--pack-id",
        default=None,
        help="UUID of the knowledge pack. Takes precedence over --pack-name if both are given.",
    )
    args = parser.parse_args()

    # Stash CLI args on the module so main() can read them.
    _cli_args = args  # noqa: F841 (intentional module-level stash)
    globals()["_cli_args"] = args
    asyncio.run(main(_cli_args))


if __name__ == "__main__":
    _cli()
