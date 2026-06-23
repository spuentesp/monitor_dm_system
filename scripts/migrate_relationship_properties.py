#!/usr/bin/env python3
"""
Migration script to add category, subcategory, tags, and created_at properties
to existing Neo4j relationships.

LAYER: 1 (data-layer)
DEPENDENCIES: monitor_data, neo4j

This script migrates existing relationships to include the new contextual properties
added in Phase 3 of the Neo4j performance optimization plan.

Run with:
    python scripts/migrate_relationship_properties.py

Environment variables:
    RUN_INTEGRATION=1  # Required to run actual migration
    DRY_RUN=1          # Set to preview changes without applying them
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from monitor_data.db.neo4j import Neo4jClient, get_neo4j_client
from monitor_data.schemas.relationships import (
    RelationshipCategory,
    RelationshipSubcategory,
    RelationshipType,
)

# =============================================================================
# TYPE TO CATEGORY/SUBCATEGORY MAPPINGS
# =============================================================================

# Mapping of RelationshipType to default category and subcategory
RELATIONSHIP_TYPE_MAPPING: Dict[
    RelationshipType, Tuple[RelationshipCategory, RelationshipSubcategory]
] = {
    # Social relationships
    RelationshipType.KNOWS: (
        RelationshipCategory.SOCIAL,
        RelationshipSubcategory.PERSONAL,
    ),
    RelationshipType.ALLIED_WITH: (
        RelationshipCategory.SOCIAL,
        RelationshipSubcategory.ALLIANCE,
    ),
    RelationshipType.HOSTILE_TO: (
        RelationshipCategory.SOCIAL,
        RelationshipSubcategory.ANTAGONISM,
    ),
    RelationshipType.REVERES: (
        RelationshipCategory.SOCIAL,
        RelationshipSubcategory.EMOTIONAL,
    ),
    # Membership relationships
    RelationshipType.MEMBER_OF: (
        RelationshipCategory.MEMBERSHIP,
        RelationshipSubcategory.ORGANIZATIONAL,
    ),
    RelationshipType.SUBGROUP_OF: (
        RelationshipCategory.MEMBERSHIP,
        RelationshipSubcategory.FACTION,
    ),
    RelationshipType.AFFILIATED_WITH: (
        RelationshipCategory.MEMBERSHIP,
        RelationshipSubcategory.AFFILIATION,
    ),
    # Ownership relationships
    RelationshipType.OWNS: (
        RelationshipCategory.OWNERSHIP,
        RelationshipSubcategory.POSSESSION,
    ),
    RelationshipType.CONTROLS: (
        RelationshipCategory.OWNERSHIP,
        RelationshipSubcategory.DOMINATION,
    ),
    RelationshipType.CONTROLLED_BY: (
        RelationshipCategory.OWNERSHIP,
        RelationshipSubcategory.SUBMISSION,
    ),
    # Spatial relationships
    RelationshipType.LOCATED_IN: (
        RelationshipCategory.SPATIAL,
        RelationshipSubcategory.LOCATION,
    ),
    RelationshipType.CONTAINS: (
        RelationshipCategory.SPATIAL,
        RelationshipSubcategory.CONTAINMENT,
    ),
    # Temporal relationships
    RelationshipType.PARTICIPATES_IN: (
        RelationshipCategory.TEMPORAL,
        RelationshipSubcategory.GENERAL,
    ),
    # Taxonomic relationships
    RelationshipType.SUBTYPE_OF: (
        RelationshipCategory.TAXONOMIC,
        RelationshipSubcategory.CLASSIFICATION,
    ),
    RelationshipType.INSTANCE_OF: (
        RelationshipCategory.TAXONOMIC,
        RelationshipSubcategory.INSTANTIATION,
    ),
    RelationshipType.DERIVES_FROM: (
        RelationshipCategory.TAXONOMIC,
        RelationshipSubcategory.DERIVATION,
    ),
    # Power relationships
    RelationshipType.LEADS: (
        RelationshipCategory.POWER,
        RelationshipSubcategory.LEADERSHIP,
    ),
    # Generic relationships
    RelationshipType.RELATED_TO: (
        RelationshipCategory.GENERIC,
        RelationshipSubcategory.GENERAL,
    ),
    # Special cases
    RelationshipType.PART_OF: (
        RelationshipCategory.TAXONOMIC,
        RelationshipSubcategory.CLASSIFICATION,
    ),
    RelationshipType.WORKS_FOR: (
        RelationshipCategory.MEMBERSHIP,
        RelationshipSubcategory.ORGANIZATIONAL,
    ),
}


def infer_default_tags(
    rel_type: RelationshipType, properties: Dict[str, Any]
) -> List[str]:
    """Infer default tags based on relationship type and existing properties."""
    tags = []

    # Add relationship type as a tag
    tags.append(rel_type.lower())

    # Infer tags from properties
    if "strength" in properties:
        strength = properties["strength"]
        if isinstance(strength, (int, float)):
            if strength >= 0.8:
                tags.append("strong")
            elif strength <= 0.3:
                tags.append("weak")

    if "since" in properties:
        tags.append("historical")

    if "notes" in properties and "family" in properties["notes"].lower():
        tags.append("familial")

    if "notes" in properties and "romantic" in properties["notes"].lower():
        tags.append("romantic")

    return tags


class RelationshipMigration:
    """Migrate existing relationships to include new properties."""

    def __init__(self) -> None:
        self.client: Optional[Neo4jClient] = None
        self.dry_run = os.environ.get("DRY_RUN", "0") == "1"
        self.stats = {
            "total_relationships": 0,
            "migrated_relationships": 0,
            "already_migrated": 0,
            "errors": 0,
            "by_category": {},
        }

    async def setup(self) -> None:
        """Initialize Neo4j client connection."""
        if os.environ.get("RUN_INTEGRATION") != "1":
            print("⚠️  Skipping migration (RUN_INTEGRATION not set)")
            print("To run migration, set: export RUN_INTEGRATION=1")
            return

        print("🔌 Connecting to Neo4j...")
        self.client = get_neo4j_client()
        await self.client.connect()
        print("✅ Connected to Neo4j")

        if self.dry_run:
            print("🔍 DRY RUN MODE - No changes will be applied")

    async def count_relationships(self) -> int:
        """Count total relationships in the database."""
        if not self.client:
            return 0

        result = self.client.execute_read("MATCH ()-[r]->() RETURN count(r) as count")
        return result[0]["count"] if result else 0

    async def get_unmigrated_relationships(
        self, limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Get relationships that don't have the new properties yet."""
        if not self.client:
            return []

        query = """
        MATCH ()-[r]->()
        WHERE r.category IS NULL
        RETURN id(r) as rel_id, type(r) as rel_type, properties(r) as props
        LIMIT $limit
        """
        result = self.client.execute_read(query, {"limit": limit})
        return result if result else []

    async def migrate_relationship(
        self,
        rel_id: int,
        rel_type_str: str,
        properties: Dict[str, Any],
    ) -> bool:
        """Migrate a single relationship to include new properties."""
        if not self.client:
            return False

        try:
            # Parse relationship type
            rel_type = RelationshipType(rel_type_str)

            # Get category and subcategory from mapping
            category, subcategory = RELATIONSHIP_TYPE_MAPPING.get(
                rel_type,
                (RelationshipCategory.GENERIC, RelationshipSubcategory.GENERAL),
            )

            # Infer default tags
            tags = infer_default_tags(rel_type, properties)

            # Build update query
            query = """
            MATCH ()-[r]->()
            WHERE id(r) = $rel_id
            SET r.category = $category,
                r.subcategory = $subcategory,
                r.tags = $tags,
                r.created_at = CASE WHEN r.created_at IS NULL THEN $created_at ELSE r.created_at END
            RETURN id(r) as updated_id
            """

            params = {
                "rel_id": rel_id,
                "category": category.value,
                "subcategory": subcategory.value,
                "tags": tags,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }

            if not self.dry_run:
                result = self.client.execute_write(query, params)
                return bool(result)
            else:
                # In dry run mode, just print what would be done
                print(f"  Would migrate relationship {rel_id} ({rel_type})")
                print(f"    Category: {category}, Subcategory: {subcategory}")
                print(f"    Tags: {tags}")
                return True

        except Exception as exc:  # noqa: BLE001
            print(f"❌ Error migrating relationship {rel_id}: {exc}")
            return False

    async def run_migration(self, batch_size: int = 100) -> None:
        """Run the full migration."""
        if not self.client:
            return

        print("\n📊 Starting migration...")

        # Count total relationships
        total = await self.count_relationships()
        self.stats["total_relationships"] = total
        print(f"Total relationships in database: {total}")

        # Migrate in batches
        migrated = 0
        while True:
            relationships = await self.get_unmigrated_relationships(batch_size)

            if not relationships:
                break

            print(f"\nProcessing batch of {len(relationships)} relationships...")

            for rel in relationships:
                rel_id = rel["rel_id"]
                rel_type_str = rel["rel_type"]
                props = rel["props"] or {}

                success = await self.migrate_relationship(rel_id, rel_type_str, props)

                if success:
                    migrated += 1
                    self.stats["migrated_relationships"] += 1

                    # Track by category
                    rel_type = RelationshipType(rel_type_str)
                    category, _ = RELATIONSHIP_TYPE_MAPPING.get(
                        rel_type,
                        (RelationshipCategory.GENERIC, RelationshipSubcategory.GENERAL),
                    )
                    cat_key = category.value
                    self.stats["by_category"][cat_key] = (
                        self.stats["by_category"].get(cat_key, 0) + 1
                    )
                else:
                    self.stats["errors"] += 1

            print(f"Progress: {migrated}/{total} relationships migrated")

            # Stop if we've processed all relationships in this batch
            if len(relationships) < batch_size:
                break

        self.stats["already_migrated"] = total - migrated

    def print_summary(self) -> None:
        """Print migration summary."""
        print("\n" + "=" * 60)
        print("📈 MIGRATION SUMMARY")
        print("=" * 60)
        print(f"Total relationships in database: {self.stats['total_relationships']}")
        print(f"Relationships migrated: {self.stats['migrated_relationships']}")
        print(f"Already had properties: {self.stats['already_migrated']}")
        print(f"Errors encountered: {self.stats['errors']}")

        if self.stats["by_category"]:
            print("\n📊 By Category:")
            for category, count in sorted(self.stats["by_category"].items()):
                print(f"  {category}: {count}")

        print("=" * 60)

        if self.dry_run:
            print("🔍 DRY RUN COMPLETE - No changes were applied")
            print("To apply changes, run without DRY_RUN=1")
        else:
            print("✅ MIGRATION COMPLETE")


async def main() -> None:
    """Main entry point."""
    migration = RelationshipMigration()
    await migration.setup()

    if migration.client:
        await migration.run_migration()
        migration.print_summary()
    else:
        print("⚠️  Migration skipped (no connection)")


if __name__ == "__main__":
    asyncio.run(main())
