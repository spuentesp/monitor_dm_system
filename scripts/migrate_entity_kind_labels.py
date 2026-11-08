#!/usr/bin/env python3
"""Give existing Entity nodes their kind label (EntityArchetype / EntityInstance).

neo4j_create_entity only ever created `:Entity` nodes, while parties, agendas,
story lookups and the memory entity check match `:EntityInstance` or
`:EntityArchetype`. Entities created before the fix are invisible to all of
them until this runs. Idempotent: only nodes missing their kind label change.
EntityTemplate nodes are neither kind and are left alone.

Run with:
    python scripts/migrate_entity_kind_labels.py            # apply
    python scripts/migrate_entity_kind_labels.py --dry-run  # count only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "packages" / "data-layer" / "src"))

_COUNT = """
MATCH (e:Entity) WHERE NOT e:EntityTemplate
RETURN count(CASE WHEN e.is_archetype = true AND NOT e:EntityArchetype THEN 1 END) AS archetypes,
       count(CASE WHEN coalesce(e.is_archetype, false) = false AND NOT e:EntityInstance THEN 1 END) AS instances
"""

_LABEL_ARCHETYPES = """
MATCH (e:Entity) WHERE NOT e:EntityTemplate AND e.is_archetype = true AND NOT e:EntityArchetype
SET e:EntityArchetype
RETURN count(e) AS labelled
"""

_LABEL_INSTANCES = """
MATCH (e:Entity) WHERE NOT e:EntityTemplate AND coalesce(e.is_archetype, false) = false AND NOT e:EntityInstance
SET e:EntityInstance
RETURN count(e) AS labelled
"""


def migrate(client: Any, *, dry_run: bool) -> dict[str, int]:
    """Label entities missing their kind. Returns how many needed each label."""
    row = (client.execute_read(_COUNT, {}) or [{}])[0]
    counts = {"archetypes": int(row.get("archetypes") or 0), "instances": int(row.get("instances") or 0)}
    if not dry_run:
        client.execute_write(_LABEL_ARCHETYPES, {})
        client.execute_write(_LABEL_INSTANCES, {})
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Count the entities that need a label; change nothing.")
    args = parser.parse_args()

    from monitor_data.db.neo4j import get_neo4j_client

    counts = migrate(get_neo4j_client(), dry_run=args.dry_run)
    verb = "need" if args.dry_run else "labelled"
    print(f"Archetypes {verb}: {counts['archetypes']}\nInstances {verb}: {counts['instances']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
