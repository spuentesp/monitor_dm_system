"""
Neo4j client for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (neo4j async driver, tenacity)
CALLED BY: neo4j_tools.py

Async Neo4j client using the official ``AsyncGraphDatabase`` driver.
All write operations must be routed through tools with CanonKeeper authority
enforcement — this client is read/write agnostic by design.

Tenacity retry decorators handle transient connectivity failures such as
connection pool exhaustion and short network blips.
"""

import inspect
import logging
import os
import threading
import time
from datetime import datetime
from typing import Any, cast

from neo4j import AsyncDriver, AsyncGraphDatabase
from tenacity import retry

from monitor_data.config import settings
from monitor_data.db._utils import DB_RETRY, run_sync

logger = logging.getLogger(__name__)
_SLOW_QUERY_THRESHOLD_MS = 150.0


# =============================================================================
# QUERY PERFORMANCE TRACKING
# =============================================================================


class QueryPerformanceTracker:
    """Track Neo4j query performance by pattern for optimization insights.

    This singleton tracks query execution times, categorizes them by pattern,
    and provides reports to identify slow queries and optimization opportunities.

    Thread-safe for concurrent access across the data layer.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._query_stats: dict[str, dict[str, Any]] = {}
        self._recent_slow_queries: list[dict[str, Any]] = []
        self._max_recent_slow = 100  # Keep last 100 slow queries
        self._enabled = os.environ.get("NEO4J_PERF_TRACKING", "true").lower() == "true"
        self._start_time = time.time()

    def _normalize_pattern(self, query: str) -> str:
        """Extract a normalized pattern from a query for grouping.

        Examples:
        - "MATCH (e:Entity {id: $id}) RETURN e" → "MATCH (e:Entity {...}) RETURN e"
        - "MATCH (a)-[r:KNOWS]->(b) RETURN a, b" → "MATCH (a)-[r:KNOWS]->(b) RETURN ..."
        """
        # Remove parameter values and normalize whitespace
        normalized = query.strip()
        # Replace parameters with placeholders
        import re

        normalized = re.sub(r"\$\w+", "$param", normalized)
        # Remove excessive whitespace
        normalized = " ".join(normalized.split())
        # Truncate long queries for pattern matching
        if len(normalized) > 200:
            normalized = normalized[:200] + "..."
        return normalized

    def get_stats(self) -> dict[str, Any]:
        """Get overall performance statistics."""
        with self._lock:
            total_queries = sum(s["count"] for s in self._query_stats.values())
            total_time = sum(s["total_ms"] for s in self._query_stats.values())
            slow_queries = sum(s["slow_count"] for s in self._query_stats.values())

            avg_time = (total_time / total_queries) if total_queries > 0 else 0.0
            slow_rate = (slow_queries / total_queries * 100) if total_queries > 0 else 0.0

            return {
                "total_queries": total_queries,
                "total_time_ms": total_time,
                "avg_time_ms": avg_time,
                "slow_queries": slow_queries,
                "slow_query_rate": slow_rate,
                "unique_patterns": len(self._query_stats),
                "uptime_seconds": time.time() - self._start_time,
            }

    def track_query(self, mode: str, query: str, duration_ms: float) -> None:
        """Track a query execution.

        Args:
            mode: "read" or "write"
            query: The Cypher query executed
            duration_ms: Execution time in milliseconds
        """
        if not self._enabled:
            return

        pattern = self._normalize_pattern(query)
        key = f"{mode}:{pattern}"

        with self._lock:
            if key not in self._query_stats:
                self._query_stats[key] = {
                    "count": 0,
                    "total_ms": 0.0,
                    "max_ms": 0.0,
                    "min_ms": float("inf"),
                    "slow_count": 0,  # > 150ms
                    "very_slow_count": 0,  # > 500ms
                    "last_seen": None,
                }

            stats = self._query_stats[key]
            stats["count"] += 1
            stats["total_ms"] += duration_ms
            stats["max_ms"] = max(stats["max_ms"], duration_ms)
            stats["min_ms"] = min(stats["min_ms"], duration_ms)
            stats["last_seen"] = datetime.now().isoformat()

            if duration_ms > _SLOW_QUERY_THRESHOLD_MS:
                stats["slow_count"] += 1
            if duration_ms > 500.0:
                stats["very_slow_count"] += 1

            # Track recent slow queries for immediate insight
            if duration_ms > _SLOW_QUERY_THRESHOLD_MS:
                self._recent_slow_queries.append(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "mode": mode,
                        "pattern": pattern,
                        "duration_ms": round(duration_ms, 2),
                        "query": query[:500],  # Truncate for logging
                    }
                )
                self._recent_slow_queries = self._recent_slow_queries[-self._max_recent_slow :]

    def get_report(self, limit: int | None = 20, sort_by: str = "total_ms") -> dict[str, Any]:
        """Get a performance report for all tracked queries.

        Args:
            limit: Maximum number of query patterns to include in report
            sort_by: Metric to sort by ("total_ms", "avg_time", "count", "max_time")

        Returns:
            Dictionary with performance statistics
        """
        with self._lock:
            # Calculate derived metrics for each pattern
            patterns = []
            for key, stats in self._query_stats.items():
                if stats["count"] > 0:
                    avg_ms = stats["total_ms"] / stats["count"]
                    patterns.append(
                        {
                            "pattern": key,
                            "count": stats["count"],
                            "avg_time_ms": round(avg_ms, 2),
                            "max_time_ms": round(stats["max_ms"], 2),
                            "min_time_ms": round(stats["min_ms"], 2),
                            "total_time_ms": round(stats["total_ms"], 2),
                            "pct_slow": round((stats["slow_count"] / stats["count"]) * 100, 2),
                            "pct_very_slow": round((stats["very_slow_count"] / stats["count"]) * 100, 2),
                            "slow_count": stats["slow_count"],
                            "very_slow_count": stats["very_slow_count"],
                            "last_seen": stats["last_seen"],
                        }
                    )

            if sort_by == "count":
                patterns.sort(key=lambda x: x["count"], reverse=True)
            elif sort_by == "avg_time":
                patterns.sort(key=lambda x: x["avg_time_ms"], reverse=True)
            elif sort_by == "max_time":
                patterns.sort(key=lambda x: x["max_time_ms"], reverse=True)
            else:
                # Sort by total time spent (most expensive first)
                patterns.sort(key=lambda x: x["total_time_ms"], reverse=True)

            patterns_returned = patterns[:limit] if limit is not None else patterns

            return {
                "total_patterns": len(patterns),
                "total_queries": sum(p["count"] for p in patterns),
                "patterns": patterns_returned,
                "by_pattern": patterns_returned,
                "recent_slow_queries": self._recent_slow_queries[-20:],  # Last 20
                "tracking_enabled": self._enabled,
            }

    def get_slow_queries(self, threshold_ms: float = 150.0) -> list[dict[str, Any]]:
        """Get queries that exceed the threshold, sorted by duration.

        Args:
            threshold_ms: Minimum duration to be considered slow

        Returns:
            List of slow query records
        """
        with self._lock:
            return [
                {**q, "is_very_slow": q["duration_ms"] > 500.0}
                for q in self._recent_slow_queries
                if q["duration_ms"] >= threshold_ms
            ]

    def get_top_slow_patterns(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get query patterns with the highest percentage of slow executions.

        Args:
            limit: Maximum number of patterns to return

        Returns:
            List of patterns with slow execution percentages
        """
        with self._lock:
            patterns = []
            for key, stats in self._query_stats.items():
                if stats["count"] >= 5:  # Only patterns with sufficient samples
                    avg_ms = stats["total_ms"] / stats["count"]
                    pct_slow = (stats["slow_count"] / stats["count"]) * 100
                    if pct_slow > 0:  # Only patterns with some slow executions
                        patterns.append(
                            {
                                "pattern": key,
                                "count": stats["count"],
                                "avg_ms": round(avg_ms, 2),
                                "pct_slow": round(pct_slow, 2),
                                "slow_count": stats["slow_count"],
                                "very_slow_count": stats["very_slow_count"],
                            }
                        )

            # Sort by percentage of slow queries (descending)
            patterns.sort(key=lambda x: x["pct_slow"], reverse=True)
            return patterns[:limit]

    def reset(self) -> None:
        """Reset all tracking statistics. Useful for testing or after optimization."""
        with self._lock:
            self._query_stats.clear()
            self._recent_slow_queries.clear()

    def is_enabled(self) -> bool:
        """Check if performance tracking is enabled."""
        return self._enabled


# Module-level singleton tracker
_perf_tracker: QueryPerformanceTracker | None = None
_tracker_lock = threading.Lock()


def get_perf_tracker() -> QueryPerformanceTracker:
    """Get the singleton performance tracker instance."""
    global _perf_tracker
    with _tracker_lock:
        if _perf_tracker is None:
            _perf_tracker = QueryPerformanceTracker()
    return _perf_tracker


_SCHEMA_BOOTSTRAP_QUERIES = (
    "CREATE CONSTRAINT universe_id_unique IF NOT EXISTS FOR (u:Universe) REQUIRE u.id IS UNIQUE",
    "CREATE CONSTRAINT source_id_unique IF NOT EXISTS FOR (s:Source) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT story_id_unique IF NOT EXISTS FOR (s:Story) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT scene_id_unique IF NOT EXISTS FOR (s:Scene) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT fact_id_unique IF NOT EXISTS FOR (f:Fact) REQUIRE f.id IS UNIQUE",
    "CREATE CONSTRAINT axiom_id_unique IF NOT EXISTS FOR (a:Axiom) REQUIRE a.id IS UNIQUE",
    "CREATE CONSTRAINT event_id_unique IF NOT EXISTS FOR (e:Event) REQUIRE e.id IS UNIQUE",
    "CREATE CONSTRAINT plot_thread_id_unique IF NOT EXISTS FOR (t:PlotThread) REQUIRE t.id IS UNIQUE",
    "CREATE CONSTRAINT party_id_unique IF NOT EXISTS FOR (p:Party) REQUIRE p.id IS UNIQUE",
    # === Sub-plan 1: Sub-hierarchy labels for groups and places ===
    # :Group is the universal collective — clan, sect, organization,
    # species, faction, party, etc. all carry the :Entity label AND
    # a :Group label so graph queries can match any collective
    # generically.
    # :World, :Region, :Place, :Structure form the location
    # sub-hierarchy used by spatial scaling (cosmic / planetary /
    # regional / city / building).
    "CREATE CONSTRAINT group_id_unique IF NOT EXISTS FOR (n:Group) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT world_id_unique IF NOT EXISTS FOR (n:World) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT region_id_unique IF NOT EXISTS FOR (n:Region) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT place_id_unique IF NOT EXISTS FOR (n:Place) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT structure_id_unique IF NOT EXISTS FOR (n:Structure) REQUIRE n.id IS UNIQUE",
    # :KnowledgeTree is the Source → concept hierarchy root referenced
    # in packages/data-layer/src/monitor_data/schemas/rpg_ontology/
    # topology.py. Sub-plan 1 of the coverage plan reifies it as a
    # first-class Neo4j node (was previously documented but not
    # writable).
    "CREATE CONSTRAINT knowledge_tree_id_unique IF NOT EXISTS FOR (n:KnowledgeTree) REQUIRE n.id IS UNIQUE",
    "CREATE INDEX entity_universe_idx IF NOT EXISTS FOR (e:Entity) ON (e.universe_id)",
    "CREATE INDEX entity_type_idx IF NOT EXISTS FOR (e:Entity) ON (e.entity_type)",
    # === Sub-plan 1: Sub-type indexes for the new group/place taxonomy ===
    "CREATE INDEX entity_group_type_idx IF NOT EXISTS FOR (e:Entity) ON (e.group_type)",
    "CREATE INDEX entity_place_type_idx IF NOT EXISTS FOR (e:Entity) ON (e.place_type)",
    "CREATE INDEX entity_sub_type_idx IF NOT EXISTS FOR (e:Entity) ON (e.sub_type)",
    "CREATE INDEX fact_universe_idx IF NOT EXISTS FOR (f:Fact) ON (f.universe_id)",
    "CREATE INDEX story_universe_idx IF NOT EXISTS FOR (s:Story) ON (s.universe_id)",
    "CREATE INDEX scene_story_idx IF NOT EXISTS FOR (s:Scene) ON (s.story_id)",
    "CREATE FULLTEXT INDEX entity_text_idx IF NOT EXISTS FOR (e:Entity) ON EACH [e.name, e.description]",
    "CREATE FULLTEXT INDEX fact_statement_idx IF NOT EXISTS FOR (f:Fact) ON EACH [f.statement]",
    # Relationship property indexes (Neo4j requires a typed relationship
    # pattern; untyped ()-[r]->() indexes are invalid Cypher)
    "CREATE INDEX relates_to_category_idx IF NOT EXISTS FOR ()-[r:RELATES_TO]-() ON (r.category)",
    "CREATE INDEX relates_to_created_idx IF NOT EXISTS FOR ()-[r:RELATES_TO]-() ON (r.created_at)",
)


class Neo4jClient:
    """
    Async Neo4j database client for canonical graph operations.

    All write operations should be called ONLY through tools with
    CanonKeeper authority enforcement.
    """

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        self._uri: str = uri or settings.neo4j_uri
        self._user: str = user or settings.neo4j_user
        _pw = password or os.environ.get("NEO4J_PASSWORD")
        if not _pw:
            raise ValueError("Neo4j password is required")
        self.password: str = _pw
        self._driver: AsyncDriver | None = None
        self._schema_initialized = False

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the async Neo4j driver (idempotent) and ensure hot indexes exist."""
        if self._driver is None:
            self._driver = AsyncGraphDatabase.driver(self._uri, auth=(self._user, self.password))

        if not self._schema_initialized:
            await self._initialize_schema()
            self._schema_initialized = True

    async def close(self) -> None:
        """Close the Neo4j driver and release connections."""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    async def __aenter__(self) -> "Neo4jClient":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def _initialize_schema(self) -> None:
        """Create the core constraints and indexes used by hot graph queries."""
        driver = self._guard()

        try:
            session_factory = driver.session()
            if inspect.isawaitable(session_factory):
                session_factory = await session_factory
            async with session_factory as session:
                for statement in _SCHEMA_BOOTSTRAP_QUERIES:
                    # One statement per write so a single bad statement cannot
                    # abort the whole bootstrap (constraints are idempotent).
                    try:
                        await session.execute_write(lambda tx, stmt=statement: tx.run(stmt))  # type: ignore
                    except Exception as exc:
                        logger.warning(
                            "Neo4j schema statement failed (%s...): %s",
                            statement[:60],
                            exc,
                        )
        except Exception as exc:
            logger.warning("Neo4j schema bootstrap skipped: %s", exc)

    def _log_query_timing(self, mode: str, query: str, started_at: float) -> None:
        elapsed_ms = (time.perf_counter() - started_at) * 1000

        # Track query performance
        get_perf_tracker().track_query(mode, query, elapsed_ms)

        # Check for slow query alerts (Phase 5)
        try:
            from monitor_data.db.neo4j_alerts import get_alert_manager

            alert_manager = get_alert_manager()
            pattern = get_perf_tracker()._normalize_pattern(query)
            alert_manager.check_slow_query(pattern, elapsed_ms, query)
        except Exception as exc:
            # Don't fail the query if alerting has issues
            logger.debug("Failed to check for slow query alerts: %s", exc)

        # Log slow queries (existing behavior)
        if elapsed_ms < _SLOW_QUERY_THRESHOLD_MS:
            return
        compact_query = " ".join(query.split())
        if len(compact_query) > 240:
            compact_query = compact_query[:237] + "..."
        logger.info("Slow Neo4j %s (%.1f ms): %s", mode, elapsed_ms, compact_query)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    @retry(**DB_RETRY)
    async def verify_connectivity(self) -> bool:
        """Verify Neo4j connection is healthy."""
        try:
            if self._driver is None:
                return False
            await self._driver.verify_connectivity()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    def _guard(self) -> AsyncDriver:
        """Return the driver or raise if not connected (auto-connects)."""
        if self._driver is None:
            # We use run_sync here because this is often called from sync tool functions
            run_sync(self.connect())
        assert self._driver is not None
        return self._driver

    async def _ensure_driver(self) -> AsyncDriver:
        """Return the driver from inside async execution without re-entering run_sync."""
        if self._driver is None:
            await self.connect()
        assert self._driver is not None
        return self._driver

    @retry(**DB_RETRY)
    async def _execute_read_async(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Async internal: execute a read transaction."""
        driver = await self._ensure_driver()
        params = parameters or {}
        started_at = time.perf_counter()

        async def _work(tx: Any) -> list[dict[str, Any]]:
            result = await tx.run(query, params)
            return [dict(record) async for record in result]

        try:
            async with driver.session() as session:
                return cast(list[dict[str, Any]], await session.execute_read(_work))
        finally:
            self._log_query_timing("read", query, started_at)

    @retry(**DB_RETRY)
    async def _execute_write_async(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Async internal: execute a write transaction."""
        driver = await self._ensure_driver()
        params = parameters or {}
        started_at = time.perf_counter()

        async def _work(tx: Any) -> list[dict[str, Any]]:
            result = await tx.run(query, params)
            return [dict(record) async for record in result]

        try:
            async with driver.session() as session:
                return cast(list[dict[str, Any]], await session.execute_write(_work))
        finally:
            self._log_query_timing("write", query, started_at)

    def execute_read(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a read transaction synchronously (safe in any context)."""
        return cast(list[dict[str, Any]], run_sync(self._execute_read_async(query, parameters)))

    def execute_write(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a write transaction synchronously (safe in any context)."""
        return cast(list[dict[str, Any]], run_sync(self._execute_write_async(query, parameters)))


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================

_neo4j_client_instance: Neo4jClient | None = None
_client_lock = threading.Lock()


def get_neo4j_client() -> Neo4jClient:
    """Return (and lazily initialise) the module-level Neo4jClient singleton.

    Synchronous — safe to call from any context including async FastAPI handlers.
    The underlying async driver runs on a dedicated background thread loop.
    """
    global _neo4j_client_instance
    with _client_lock:
        if _neo4j_client_instance is None:
            _neo4j_client_instance = Neo4jClient(password=settings.neo4j_password)
    return _neo4j_client_instance


def reset_neo4j_client() -> None:
    """Close and discard the singleton. Used in tests for clean state."""
    global _neo4j_client_instance
    with _client_lock:
        if _neo4j_client_instance is not None:
            run_sync(_neo4j_client_instance.close())
            _neo4j_client_instance = None
