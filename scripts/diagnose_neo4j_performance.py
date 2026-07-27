#!/usr/bin/env python3
"""
Neo4j Performance Diagnostic Script

LAYER: 1 (data-layer)
DEPENDENCIES: monitor_data, neo4j

This script performs comprehensive performance diagnostics on the Neo4j database,
including query profiling, index analysis, and relationship query testing.

Run with:
    python scripts/diagnose_neo4j_performance.py

Environment variables:
    RUN_INTEGRATION=1  # Required to run actual queries
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from monitor_data.db.neo4j import (
    _SLOW_QUERY_THRESHOLD_MS,
    Neo4jClient,
    get_neo4j_client,
    get_perf_tracker,
)


class Neo4jPerformanceDiagnostics:
    """Comprehensive Neo4j performance diagnostics."""

    def __init__(self) -> None:
        self.client: Neo4jClient | None = None
        self.results: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "database_status": {},
            "index_analysis": {},
            "query_profiles": {},
            "relationship_query_tests": {},
            "recommendations": [],
        }

    async def setup(self) -> None:
        """Initialize Neo4j client connection."""
        if os.environ.get("RUN_INTEGRATION") != "1":
            print("⚠️  Skipping integration tests (RUN_INTEGRATION not set)")
            print("To run actual diagnostics, set: export RUN_INTEGRATION=1")
            return

        print("🔌 Connecting to Neo4j...")
        self.client = get_neo4j_client()
        await self.client.connect()
        print("✅ Connected to Neo4j")

        # Reset performance tracker for clean measurements
        get_perf_tracker().reset()

    async def check_database_status(self) -> None:
        """Check database connectivity and basic status."""
        print("\n📊 Checking database status...")

        if not self.client:
            print("⚠️  Skipping (not connected)")
            return

        try:
            is_healthy = await self.client.verify_connectivity()
            self.results["database_status"]["healthy"] = is_healthy

            # Get basic stats
            stats_queries = [
                ("node_count", "MATCH (n) RETURN count(n) as count"),
                ("relationship_count", "MATCH ()-[r]->() RETURN count(r) as count"),
                ("entity_count", "MATCH (e:Entity) RETURN count(e) as count"),
                (
                    "relationship_types",
                    "MATCH ()-[r]->() RETURN DISTINCT type(r) as type",
                ),
                (
                    "entity_types",
                    "MATCH (e:Entity) RETURN DISTINCT e.entity_type as type",
                ),
            ]

            for name, query in stats_queries:
                try:
                    start = time.perf_counter()
                    result = self.client.execute_read(query)
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    self.results["database_status"][name] = {
                        "value": result[0] if result else None,
                        "query_time_ms": round(elapsed_ms, 2),
                    }
                except Exception as exc:  # noqa: BLE001
                    self.results["database_status"][name] = {"error": str(exc)}

            print("✅ Database status collected")

        except Exception as exc:  # noqa: BLE001
            print(f"❌ Error checking database status: {exc}")
            self.results["database_status"]["error"] = str(exc)

    async def analyze_indexes(self) -> None:
        """Analyze existing indexes and their usage."""
        print("\n🔍 Analyzing indexes...")

        if not self.client:
            print("⚠️  Skipping (not connected)")
            return

        try:
            # Get all indexes
            indexes_query = "SHOW INDEXES"
            start = time.perf_counter()
            indexes = self.client.execute_read(indexes_query)
            elapsed_ms = (time.perf_counter() - start) * 1000

            self.results["index_analysis"] = {
                "total_indexes": len(indexes),
                "query_time_ms": round(elapsed_ms, 2),
                "indexes": indexes,
            }

            # Check for missing critical indexes
            existing_index_names = {idx.get("name") for idx in indexes}
            critical_indexes = [
                "entity_universe_idx",
                "entity_type_idx",
                "fact_universe_idx",
                "story_universe_idx",
                "scene_story_idx",
                # New indexes we want to add
                "rel_type_idx",
                "rel_category_idx",
                "rel_created_at_idx",
            ]

            missing_indexes = [
                idx for idx in critical_indexes if idx not in existing_index_names
            ]

            if missing_indexes:
                self.results["recommendations"].append(
                    {
                        "type": "missing_indexes",
                        "priority": "high",
                        "message": f"Missing {len(missing_indexes)} critical indexes",
                        "details": missing_indexes,
                    }
                )

            print(f"✅ Found {len(indexes)} indexes")
            if missing_indexes:
                print(f"⚠️  Missing {len(missing_indexes)} recommended indexes")

        except Exception as exc:  # noqa: BLE001
            print(f"❌ Error analyzing indexes: {exc}")
            self.results["index_analysis"]["error"] = str(exc)

    async def profile_common_queries(self) -> None:
        """Profile common query patterns used in the application."""
        print("\n⚡ Profiling common queries...")

        if not self.client:
            print("⚠️  Skipping (not connected)")
            return

        # Common query patterns from the codebase
        test_queries = [
            {
                "name": "get_entity_by_id",
                "query": "MATCH (e:Entity {id: $id}) RETURN e",
                "params": {"id": "test-entity-1"},
            },
            {
                "name": "get_entity_neighborhood",
                "query": "MATCH (e:Entity {id: $id})-[r]-(other) RETURN e, r, other LIMIT 50",
                "params": {"id": "test-entity-1"},
            },
            {
                "name": "get_relationships_by_type",
                "query": "MATCH ()-[r:KNOWS]->() RETURN r LIMIT 100",
                "params": {},
            },
            {
                "name": "get_facts_by_universe",
                "query": "MATCH (f:Fact {universe_id: $universe_id}) RETURN f LIMIT 100",
                "params": {"universe_id": "test-universe"},
            },
            {
                "name": "traverse_paths",
                "query": "MATCH path = (e:Entity {id: $id})-[*1..3]-(other) RETURN path LIMIT 20",
                "params": {"id": "test-entity-1"},
            },
            {
                "name": "fulltext_search",
                "query": "CALL db.index.fulltext.queryNodes('entity_text_idx', $search) YIELD node RETURN node LIMIT 10",
                "params": {"search": "test"},
            },
        ]

        for test in test_queries:
            name = test["name"]
            query = test["query"]
            params = test["params"]

            try:
                # Warm up (ignore first run)
                try:
                    self.client.execute_read(query, params)
                except Exception:  # noqa: BLE001
                    pass

                # Profile with multiple runs
                times = []
                for _ in range(3):
                    start = time.perf_counter()
                    try:
                        self.client.execute_read(query, params)
                    except Exception:  # noqa: BLE001
                        pass
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    times.append(elapsed_ms)

                avg_time = sum(times) / len(times)
                max_time = max(times)
                min_time = min(times)

                self.results["query_profiles"][name] = {
                    "query": query[:200],
                    "avg_time_ms": round(avg_time, 2),
                    "max_time_ms": round(max_time, 2),
                    "min_time_ms": round(min_time, 2),
                    "runs": len(times),
                    "is_slow": avg_time > _SLOW_QUERY_THRESHOLD_MS,
                }

                status = "⚠️  SLOW" if avg_time > _SLOW_QUERY_THRESHOLD_MS else "✅"
                print(f"{status} {name}: {avg_time:.2f}ms avg")

                if avg_time > _SLOW_QUERY_THRESHOLD_MS:
                    self.results["recommendations"].append(
                        {
                            "type": "slow_query",
                            "priority": "high" if avg_time > 500 else "medium",
                            "message": f"Query '{name}' is slow ({avg_time:.2f}ms avg)",
                            "details": {"query": query, "avg_time_ms": avg_time},
                        }
                    )

            except Exception as exc:  # noqa: BLE001
                print(f"❌ Error profiling {name}: {exc}")
                self.results["query_profiles"][name] = {"error": str(exc)}

        print("✅ Query profiling complete")

    async def test_relationship_queries(self) -> None:
        """Test relationship query patterns, especially those with toUpper() issues."""
        print("\n🔗 Testing relationship queries...")

        if not self.client:
            print("⚠️  Skipping (not connected)")
            return

        # Test different relationship query patterns
        relationship_tests = [
            {
                "name": "filter_by_type_direct",
                "query": "MATCH ()-[r:KNOWS]->() RETURN count(r)",
                "params": {},
                "issue": "Should use index on relationship type",
            },
            {
                "name": "filter_by_type_toUpper",
                "query": "MATCH ()-[r]->() WHERE toUpper(type(r)) = 'KNOWS' RETURN count(r)",
                "params": {},
                "issue": "toUpper() prevents index usage",
            },
            {
                "name": "filter_by_type_case_sensitive",
                "query": "MATCH ()-[r]->() WHERE type(r) = 'KNOWS' RETURN count(r)",
                "params": {},
                "issue": "Case sensitivity may miss results",
            },
            {
                "name": "filter_multiple_types",
                "query": "MATCH ()-[r]->() WHERE type(r) IN ['KNOWS', 'LIKES', 'HATES'] RETURN count(r)",
                "params": {},
                "issue": "IN clause may not use index efficiently",
            },
            {
                "name": "traverse_with_type_filter",
                "query": "MATCH (e:Entity {id: $id})-[r:KNOWS]-(other) RETURN other LIMIT 50",
                "params": {"id": "test-entity-1"},
                "issue": "Should use relationship type index",
            },
        ]

        for test in relationship_tests:
            name = test["name"]
            query = test["query"]
            params = test["params"]

            try:
                start = time.perf_counter()
                try:
                    result = self.client.execute_read(query, params)
                    success = True
                    count = result[0].get("count(r)", 0) if result else 0
                except Exception:  # noqa: BLE001
                    success = False
                    count = 0
                elapsed_ms = (time.perf_counter() - start) * 1000

                self.results["relationship_query_tests"][name] = {
                    "query": query,
                    "time_ms": round(elapsed_ms, 2),
                    "success": success,
                    "result_count": count,
                    "issue": test["issue"],
                    "is_slow": elapsed_ms > _SLOW_QUERY_THRESHOLD_MS,
                }

                status = "⚠️  SLOW" if elapsed_ms > _SLOW_QUERY_THRESHOLD_MS else "✅"
                print(f"{status} {name}: {elapsed_ms:.2f}ms")

                if elapsed_ms > _SLOW_QUERY_THRESHOLD_MS:
                    self.results["recommendations"].append(
                        {
                            "type": "relationship_query_issue",
                            "priority": "medium",
                            "message": f"Relationship query '{name}' is slow",
                            "details": {"issue": test["issue"], "time_ms": elapsed_ms},
                        }
                    )

            except Exception as exc:  # noqa: BLE001
                print(f"❌ Error testing {name}: {exc}")
                self.results["relationship_query_tests"][name] = {"error": str(exc)}

        print("✅ Relationship query tests complete")

    async def collect_performance_report(self) -> None:
        """Collect performance tracker report."""
        print("\n📈 Collecting performance tracker report...")

        report = get_perf_tracker().get_report(limit=50)
        self.results["performance_tracker"] = report

        print(
            f"✅ Tracked {report['total_queries']} queries across {report['total_patterns']} patterns"
        )

        # Get slow queries
        slow_queries = get_perf_tracker().get_slow_queries()
        if slow_queries:
            print(f"⚠️  Found {len(slow_queries)} slow queries")
            self.results["recommendations"].append(
                {
                    "type": "slow_queries_detected",
                    "priority": "high",
                    "message": f"Found {len(slow_queries)} slow queries during diagnostics",
                    "details": {"count": len(slow_queries)},
                }
            )

        # Get top slow patterns
        slow_patterns = get_perf_tracker().get_top_slow_patterns(limit=10)
        if slow_patterns:
            print(f"⚠️  Top {len(slow_patterns)} slow patterns identified")
            self.results["performance_tracker"]["top_slow_patterns"] = slow_patterns

    async def generate_recommendations(self) -> None:
        """Generate actionable recommendations based on diagnostics."""
        print("\n💡 Generating recommendations...")

        # Check for common issues
        if not self.results["database_status"].get("healthy"):
            self.results["recommendations"].append(
                {
                    "type": "connectivity",
                    "priority": "critical",
                    "message": "Neo4j database is not healthy - check connectivity",
                }
            )

        # Check relationship type usage
        if self.results["database_status"].get("relationship_types"):
            rel_types = self.results["database_status"]["relationship_types"].get(
                "value", []
            )
            if rel_types and len(rel_types) > 10:
                self.results["recommendations"].append(
                    {
                        "type": "relationship_taxonomy",
                        "priority": "medium",
                        "message": f"Found {len(rel_types)} relationship types - consider hierarchical taxonomy",
                        "details": {"current_types": rel_types},
                    }
                )

        # Check for toUpper() usage patterns
        for name, test in self.results["relationship_query_tests"].items():
            if test.get("is_slow") and "toUpper" in test.get("query", ""):
                self.results["recommendations"].append(
                    {
                        "type": "toUpper_usage",
                        "priority": "high",
                        "message": f"Query '{name}' uses toUpper() - prevents index usage",
                        "details": {
                            "query": test["query"],
                            "recommendation": "Use uppercase values at write time instead",
                        },
                    }
                )

        print(f"✅ Generated {len(self.results['recommendations'])} recommendations")

    def save_report(self, output_path: str = "neo4j_performance_report.json") -> None:
        """Save diagnostic report to JSON file."""
        report_path = Path(output_path)
        report_path.write_text(json.dumps(self.results, indent=2, default=str))
        print(f"\n📄 Report saved to {report_path.absolute()}")

    def print_summary(self) -> None:
        """Print a summary of diagnostic results."""
        print("\n" + "=" * 60)
        print("📊 NEO4J PERFORMANCE DIAGNOSTIC SUMMARY")
        print("=" * 60)

        # Database status
        if "healthy" in self.results["database_status"]:
            status = (
                "✅ Healthy"
                if self.results["database_status"]["healthy"]
                else "❌ Unhealthy"
            )
            print(f"\nDatabase: {status}")

        if "node_count" in self.results["database_status"]:
            node_count = self.results["database_status"]["node_count"].get("value", 0)
            rel_count = self.results["database_status"]["relationship_count"].get(
                "value", 0
            )
            print(f"Nodes: {node_count}")
            print(f"Relationships: {rel_count}")

        # Indexes
        if "total_indexes" in self.results["index_analysis"]:
            print(f"\nIndexes: {self.results['index_analysis']['total_indexes']}")

        # Query profiles
        slow_queries = [
            name
            for name, profile in self.results["query_profiles"].items()
            if profile.get("is_slow")
        ]
        if slow_queries:
            print(f"\n⚠️  Slow queries: {len(slow_queries)}")
            for name in slow_queries[:5]:
                time_ms = self.results["query_profiles"][name].get("avg_time_ms", 0)
                print(f"  - {name}: {time_ms:.2f}ms")

        # Recommendations
        if self.results["recommendations"]:
            print(f"\n💡 Recommendations: {len(self.results['recommendations'])}")
            for rec in self.results["recommendations"][:5]:
                priority = rec.get("priority", "info").upper()
                msg = rec.get("message", "")
                print(f"  [{priority}] {msg}")

        print("=" * 60)


async def run_diagnostics() -> None:
    """Run the complete diagnostic suite."""
    print("🚀 Starting Neo4j Performance Diagnostics")
    print("=" * 60)

    diagnostics = Neo4jPerformanceDiagnostics()

    try:
        await diagnostics.setup()
        await diagnostics.check_database_status()
        await diagnostics.analyze_indexes()
        await diagnostics.profile_common_queries()
        await diagnostics.test_relationship_queries()
        await diagnostics.collect_performance_report()
        await diagnostics.generate_recommendations()

        diagnostics.print_summary()
        diagnostics.save_report()

    except KeyboardInterrupt:
        print("\n\n⚠️  Diagnostics interrupted by user")
    except Exception as exc:  # noqa: BLE001
        print(f"\n\n❌ Error during diagnostics: {exc}")
        raise
    finally:
        if diagnostics.client:
            await diagnostics.client.close()
            print("\n🔌 Disconnected from Neo4j")


if __name__ == "__main__":
    asyncio.run(run_diagnostics())
