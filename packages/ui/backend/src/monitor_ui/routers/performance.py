"""
Performance router — Neo4j query performance metrics and monitoring.

Provides real-time access to QueryPerformanceTracker statistics for
monitoring Neo4j query performance, identifying slow queries, and
analyzing query patterns.

This router is part of Phase 5 of the Neo4j performance optimization plan.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class QueryPatternMetrics(BaseModel):
    """Metrics for a single query pattern."""

    pattern: str = Field(..., description="Normalized query pattern (truncated)")
    count: int = Field(..., description="Number of times this query was executed")
    total_time_ms: float = Field(..., description="Total execution time (milliseconds)")
    avg_time_ms: float = Field(..., description="Average execution time (milliseconds)")
    min_time_ms: float = Field(..., description="Fastest execution time (milliseconds)")
    max_time_ms: float = Field(..., description="Slowest execution time (milliseconds)")
    p95_time_ms: float | None = Field(None, description="95th percentile execution time (milliseconds)")
    p99_time_ms: float | None = Field(None, description="99th percentile execution time (milliseconds)")
    slow_count: int = Field(..., description="Number of slow queries (>150ms)")
    last_executed: str | None = Field(None, description="ISO timestamp of last execution")


class PerformanceOverview(BaseModel):
    """High-level performance metrics."""

    total_queries: int = Field(..., description="Total number of queries executed")
    total_time_ms: float = Field(..., description="Total execution time (milliseconds)")
    avg_time_ms: float = Field(..., description="Average query execution time (milliseconds)")
    slow_queries: int = Field(..., description="Number of slow queries (>150ms)")
    slow_query_rate: float = Field(..., description="Percentage of queries that are slow (0-100)")
    unique_patterns: int = Field(..., description="Number of unique query patterns")
    uptime_seconds: float | None = Field(None, description="Time since tracker started (seconds)")


class SlowQueryInfo(BaseModel):
    """Information about a slow query."""

    pattern: str = Field(..., description="Normalized query pattern")
    execution_time_ms: float = Field(..., description="Execution time (milliseconds)")
    timestamp: str = Field(..., description="ISO timestamp of execution")
    sample_query: str | None = Field(None, description="Sample query (first 200 chars)")


class PerformanceReport(BaseModel):
    """Complete performance report."""

    overview: PerformanceOverview = Field(..., description="High-level metrics")
    top_patterns: list[QueryPatternMetrics] = Field(..., description="Top query patterns by frequency")
    slowest_patterns: list[QueryPatternMetrics] = Field(..., description="Query patterns with highest average time")
    recent_slow_queries: list[SlowQueryInfo] = Field(..., description="Recent slow query executions")


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


# reason: lazy-import factory — try/except ImportError branch raises HTTPException so the function body has no consistent return type for mypy to infer
def _get_tracker():  # type: ignore
    """Get the QueryPerformanceTracker singleton."""
    try:
        from monitor_data.db.neo4j import get_perf_tracker

        return get_perf_tracker()
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Performance tracking not available: {exc}",
        )


def _calculate_percentile(times: list[float], percentile: float) -> float:
    """Calculate percentile from a list of times."""
    if not times:
        return 0.0
    sorted_times = sorted(times)
    index = int(len(sorted_times) * percentile)
    return sorted_times[min(index, len(sorted_times) - 1)]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/performance", response_model=PerformanceOverview, tags=["performance"])
async def get_performance_overview() -> PerformanceOverview:
    """Get high-level performance metrics for Neo4j queries.

    Returns:
        Overview with total queries, average time, slow query count, etc.

    Raises:
        HTTPException: If performance tracking is not available
    """
    # reason: _get_tracker is untyped (see its definition above); mypy reports [no-untyped-call] for every caller until that helper gets a return type
    tracker = _get_tracker()  # type: ignore
    stats = tracker.get_stats()

    return PerformanceOverview(
        total_queries=stats["total_queries"],
        total_time_ms=stats["total_time_ms"],
        avg_time_ms=stats["avg_time_ms"],
        slow_queries=stats["slow_queries"],
        slow_query_rate=stats["slow_query_rate"],
        unique_patterns=stats["unique_patterns"],
        uptime_seconds=stats.get("uptime_seconds"),
    )


@router.get(
    "/performance/patterns",
    response_model=list[QueryPatternMetrics],
    tags=["performance"],
)
async def get_query_patterns(
    limit: int = Query(default=20, ge=1, le=100, description="Maximum results to return"),
    sort_by: str = Query(
        default="count",
        pattern="^(count|avg_time|max_time|slow_count)$",
        description="Sort field: count, avg_time, max_time, or slow_count",
    ),
    min_count: int = Query(default=1, ge=1, description="Minimum query count to include"),
) -> list[QueryPatternMetrics]:
    """Get query patterns sorted by specified metric.

    Args:
        limit: Maximum number of patterns to return
        sort_by: Sort field (count, avg_time, max_time, slow_count)
        min_count: Minimum number of executions to include

    Returns:
        List of query pattern metrics sorted by specified metric
    """
    # reason: _get_tracker is untyped (see its definition above); mypy reports [no-untyped-call] for every caller until that helper gets a return type
    tracker = _get_tracker()  # type: ignore
    report = tracker.get_report(limit=None, sort_by=sort_by)

    # Filter by min_count and apply limit
    patterns = [
        QueryPatternMetrics(
            pattern=pattern["pattern"],
            count=pattern["count"],
            total_time_ms=pattern["total_time_ms"],
            avg_time_ms=pattern["avg_time_ms"],
            min_time_ms=pattern["min_time_ms"],
            max_time_ms=pattern["max_time_ms"],
            p95_time_ms=pattern.get("p95_time_ms"),
            p99_time_ms=pattern.get("p99_time_ms"),
            slow_count=pattern["slow_count"],
            last_executed=pattern.get("last_executed"),
        )
        for pattern in report["by_pattern"]
        if pattern["count"] >= min_count
    ][:limit]

    return patterns


@router.get(
    "/performance/slow",
    response_model=list[SlowQueryInfo],
    tags=["performance"],
)
async def get_slow_queries(
    limit: int = Query(default=50, ge=1, le=200, description="Maximum results to return"),
    min_time_ms: float = Query(default=150.0, ge=0.0, description="Minimum execution time to include"),
) -> list[SlowQueryInfo]:
    """Get recent slow query executions.

    Args:
        limit: Maximum number of slow queries to return
        min_time_ms: Minimum execution time threshold (milliseconds)

    Returns:
        List of slow query executions with metadata
    """
    # reason: _get_tracker is untyped (see its definition above); mypy reports [no-untyped-call] for every caller until that helper gets a return type
    tracker = _get_tracker()  # type: ignore
    # QueryPerformanceTracker.get_slow_queries only accepts a threshold and
    # its records use duration_ms/query keys — map the router's
    # limit/min_time_ms parameters and SlowQueryInfo fields onto that API.
    slow_queries = tracker.get_slow_queries(threshold_ms=min_time_ms)[-limit:]

    return [
        SlowQueryInfo(
            pattern=query["pattern"],
            execution_time_ms=query["duration_ms"],
            timestamp=query["timestamp"],
            sample_query=query.get("query"),
        )
        for query in slow_queries
    ]


@router.get("/performance/report", response_model=PerformanceReport, tags=["performance"])
async def get_performance_report(
    pattern_limit: int = Query(default=10, ge=1, le=50, description="Top patterns to include"),
    slow_query_limit: int = Query(default=20, ge=1, le=100, description="Recent slow queries to include"),
) -> PerformanceReport:
    """Get a complete performance report with overview and details.

    Args:
        pattern_limit: Number of top/slowest patterns to include
        slow_query_limit: Number of recent slow queries to include

    Returns:
        Complete performance report with overview, patterns, and slow queries
    """
    # reason: _get_tracker is untyped (see its definition above); mypy reports [no-untyped-call] for every caller until that helper gets a return type
    tracker = _get_tracker()  # type: ignore

    # Get overview
    stats = tracker.get_stats()
    overview = PerformanceOverview(
        total_queries=stats["total_queries"],
        total_time_ms=stats["total_time_ms"],
        avg_time_ms=stats["avg_time_ms"],
        slow_queries=stats["slow_queries"],
        slow_query_rate=stats["slow_query_rate"],
        unique_patterns=stats["unique_patterns"],
        uptime_seconds=stats.get("uptime_seconds"),
    )

    # Get top patterns by count
    top_report = tracker.get_report(limit=pattern_limit, sort_by="count")
    top_patterns = [
        QueryPatternMetrics(
            pattern=pattern["pattern"],
            count=pattern["count"],
            total_time_ms=pattern["total_time_ms"],
            avg_time_ms=pattern["avg_time_ms"],
            min_time_ms=pattern["min_time_ms"],
            max_time_ms=pattern["max_time_ms"],
            p95_time_ms=pattern.get("p95_time_ms"),
            p99_time_ms=pattern.get("p99_time_ms"),
            slow_count=pattern["slow_count"],
            last_executed=pattern.get("last_executed"),
        )
        for pattern in top_report["by_pattern"]
    ]

    # Get slowest patterns by average time
    slowest_report = tracker.get_report(limit=pattern_limit, sort_by="avg_time")
    slowest_patterns = [
        QueryPatternMetrics(
            pattern=pattern["pattern"],
            count=pattern["count"],
            total_time_ms=pattern["total_time_ms"],
            avg_time_ms=pattern["avg_time_ms"],
            min_time_ms=pattern["min_time_ms"],
            max_time_ms=pattern["max_time_ms"],
            p95_time_ms=pattern.get("p95_time_ms"),
            p99_time_ms=pattern.get("p99_time_ms"),
            slow_count=pattern["slow_count"],
            last_executed=pattern.get("last_executed"),
        )
        for pattern in slowest_report["by_pattern"]
    ]

    # Get recent slow queries (same tracker-API mapping as /performance/slow)
    slow_queries = tracker.get_slow_queries(threshold_ms=150.0)[-slow_query_limit:]
    recent_slow_queries = [
        SlowQueryInfo(
            pattern=query["pattern"],
            execution_time_ms=query["duration_ms"],
            timestamp=query["timestamp"],
            sample_query=query.get("query"),
        )
        for query in slow_queries
    ]

    return PerformanceReport(
        overview=overview,
        top_patterns=top_patterns,
        slowest_patterns=slowest_patterns,
        recent_slow_queries=recent_slow_queries,
    )


@router.post("/performance/reset", tags=["performance"])
async def reset_performance_tracker() -> dict[str, str]:
    """Reset the performance tracker.

    WARNING: This clears all collected metrics. Use with caution.

    Returns:
        Confirmation message
    """
    # reason: _get_tracker is untyped (see its definition above); mypy reports [no-untyped-call] for every caller until that helper gets a return type
    tracker = _get_tracker()  # type: ignore
    tracker.reset()

    return {"message": "Performance tracker reset successfully"}


@router.get("/health/performance", tags=["health"])
async def get_performance_health() -> dict[str, Any]:
    """Get performance health check.

    Returns health status based on:
    - Slow query rate (<10% = healthy, 10-20% = degraded, >20% = unhealthy)
    - Average query time (<50ms = healthy, 50-150ms = degraded, >150ms = unhealthy)

    Returns:
        Health status with metrics and status
    """
    # reason: _get_tracker is untyped (see its definition above); mypy reports [no-untyped-call] for every caller until that helper gets a return type
    tracker = _get_tracker()  # type: ignore
    stats = tracker.get_stats()

    # Determine health status
    status = "healthy"
    issues: list[str] = []

    if stats["slow_query_rate"] > 20.0:
        status = "unhealthy"
        issues.append(f"High slow query rate: {stats['slow_query_rate']:.1f}%")
    elif stats["slow_query_rate"] > 10.0:
        status = "degraded"
        issues.append(f"Elevated slow query rate: {stats['slow_query_rate']:.1f}%")

    if stats["avg_time_ms"] > 150.0:
        status = "unhealthy" if status != "healthy" else "degraded"
        issues.append(f"High average query time: {stats['avg_time_ms']:.1f}ms")
    elif stats["avg_time_ms"] > 50.0:
        if status == "healthy":
            status = "degraded"
        issues.append(f"Elevated average query time: {stats['avg_time_ms']:.1f}ms")

    return {
        "status": status,
        "metrics": {
            "total_queries": stats["total_queries"],
            "avg_time_ms": stats["avg_time_ms"],
            "slow_query_rate": stats["slow_query_rate"],
            "slow_queries": stats["slow_queries"],
        },
        "issues": issues,
        "timestamp": datetime.now(UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Alerting Endpoints (Phase 5)
# ---------------------------------------------------------------------------


class AlertInfo(BaseModel):
    """Information about a performance alert."""

    id: str = Field(..., description="Alert unique identifier")
    type: str = Field(..., description="Alert type (e.g., 'slow_query', 'high_slow_query_rate')")
    severity: str = Field(..., description="Alert severity (info, warning, error, critical)")
    message: str = Field(..., description="Alert message")
    pattern: str | None = Field(None, description="Query pattern (if applicable)")
    metrics: dict[str, Any] = Field(default_factory=dict, description="Alert metrics")
    timestamp: str = Field(..., description="ISO timestamp of alert")


class AlertConfiguration(BaseModel):
    """Alerting system configuration."""

    slow_query_threshold_ms: float = Field(..., description="Threshold for slow query alerts (milliseconds)")
    critical_query_threshold_ms: float = Field(..., description="Threshold for critical query alerts (milliseconds)")
    high_slow_query_rate_threshold: float = Field(..., description="Threshold for high slow query rate (0-1)")
    high_avg_time_threshold_ms: float = Field(..., description="Threshold for high average query time (milliseconds)")
    degradation_threshold_percent: float = Field(..., description="Threshold for performance degradation (0-1)")
    cooldown_minutes: dict[str, int] = Field(
        default_factory=dict, description="Cooldown periods by alert type (minutes)"
    )
    baseline_metrics: dict[str, float] | None = Field(None, description="Baseline metrics for degradation detection")
    baseline_timestamp: str | None = Field(None, description="ISO timestamp of baseline")


# reason: lazy-import factory — try/except ImportError branch raises HTTPException so the function body has no consistent return type for mypy to infer
def _get_alert_manager():  # type: ignore
    """Get the PerformanceAlertManager singleton."""
    try:
        from monitor_data.db.neo4j_alerts import get_alert_manager

        return get_alert_manager()
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Alerting system not available: {exc}",
        )


@router.get(
    "/performance/alerts",
    response_model=list[AlertInfo],
    tags=["performance", "alerts"],
)
async def get_alerts(
    limit: int = Query(default=50, ge=1, le=200, description="Maximum alerts to return"),
    severity: str | None = Query(
        default=None,
        pattern="^(info|warning|error|critical)$",
        description="Filter by severity",
    ),
    alert_type: str | None = Query(
        default=None,
        description="Filter by alert type",
    ),
    since: str | None = Query(
        default=None,
        description="Filter alerts after this ISO timestamp",
    ),
) -> list[AlertInfo]:
    """Get alert history with optional filtering.

    Args:
        limit: Maximum number of alerts to return
        severity: Filter by severity (info, warning, error, critical)
        alert_type: Filter by alert type
        since: Filter to alerts after this ISO timestamp

    Returns:
        List of alert information
    """
    # reason: _get_alert_manager is untyped (see its definition above); mypy reports [no-untyped-call] for every caller until that helper gets a return type
    manager = _get_alert_manager()  # type: ignore

    # Parse optional filters
    severity_filter = None
    if severity:
        from monitor_data.db.neo4j_alerts import AlertSeverity

        severity_filter = AlertSeverity(severity)

    alert_type_filter = None
    if alert_type:
        from monitor_data.db.neo4j_alerts import AlertType

        alert_type_filter = AlertType(alert_type)

    since_filter = None
    if since:
        since_filter = datetime.fromisoformat(since)

    alerts = manager.get_alert_history(
        limit=limit,
        severity=severity_filter,
        alert_type=alert_type_filter,
        since=since_filter,
    )

    return [AlertInfo(**alert) for alert in alerts]


@router.get(
    "/performance/alerts/config",
    response_model=AlertConfiguration,
    tags=["performance", "alerts"],
)
async def get_alerts_config() -> AlertConfiguration:
    """Get current alerting system configuration.

    Returns:
        Alerting configuration
    """
    # reason: _get_alert_manager is untyped (see its definition above); mypy reports [no-untyped-call] for every caller until that helper gets a return type
    manager = _get_alert_manager()  # type: ignore
    config = manager.get_configuration()

    return AlertConfiguration(
        slow_query_threshold_ms=config["slow_query_threshold_ms"],
        critical_query_threshold_ms=config["critical_query_threshold_ms"],
        high_slow_query_rate_threshold=config["high_slow_query_rate_threshold"],
        high_avg_time_threshold_ms=config["high_avg_time_threshold_ms"],
        degradation_threshold_percent=config["degradation_threshold_percent"],
        cooldown_minutes=config["cooldown_minutes"],
        baseline_metrics=config["baseline_metrics"],
        baseline_timestamp=config["baseline_timestamp"],
    )


@router.put("/performance/alerts/config", tags=["performance", "alerts"])
async def update_alerts_config(
    slow_query_threshold_ms: float | None = Query(default=None, ge=0.0, description="Slow query threshold (ms)"),
    critical_query_threshold_ms: float | None = Query(
        default=None, ge=0.0, description="Critical query threshold (ms)"
    ),
    high_slow_query_rate_threshold: float | None = Query(
        default=None, ge=0.0, le=1.0, description="High slow query rate threshold (0-1)"
    ),
    high_avg_time_threshold_ms: float | None = Query(
        default=None, ge=0.0, description="High average query time threshold (ms)"
    ),
    degradation_threshold_percent: float | None = Query(
        default=None, ge=0.0, le=1.0, description="Degradation threshold (0-1)"
    ),
) -> dict[str, Any]:
    """Update alerting system configuration.

    Only parameters provided will be updated. Others remain unchanged.

    Args:
        slow_query_threshold_ms: Slow query threshold (milliseconds)
        critical_query_threshold_ms: Critical query threshold (milliseconds)
        high_slow_query_rate_threshold: High slow query rate threshold (0-1)
        high_avg_time_threshold_ms: High average query time threshold (milliseconds)
        degradation_threshold_percent: Performance degradation threshold (0-1)

    Returns:
        Updated configuration
    """
    # reason: _get_alert_manager is untyped (see its definition above); mypy reports [no-untyped-call] for every caller until that helper gets a return type
    manager = _get_alert_manager()  # type: ignore

    # Build update dictionary with only provided parameters
    updates: dict[str, float] = {}
    if slow_query_threshold_ms is not None:
        updates["slow_query_threshold_ms"] = slow_query_threshold_ms
    if critical_query_threshold_ms is not None:
        updates["critical_query_threshold_ms"] = critical_query_threshold_ms
    if high_slow_query_rate_threshold is not None:
        updates["high_slow_query_rate_threshold"] = high_slow_query_rate_threshold
    if high_avg_time_threshold_ms is not None:
        updates["high_avg_time_threshold_ms"] = high_avg_time_threshold_ms
    if degradation_threshold_percent is not None:
        updates["degradation_threshold_percent"] = degradation_threshold_percent

    if updates:
        manager.update_configuration(**updates)

    # Return updated configuration
    config = manager.get_configuration()
    return {
        "message": "Alert configuration updated",
        "configuration": {
            "slow_query_threshold_ms": config["slow_query_threshold_ms"],
            "critical_query_threshold_ms": config["critical_query_threshold_ms"],
            "high_slow_query_rate_threshold": config["high_slow_query_rate_threshold"],
            "high_avg_time_threshold_ms": config["high_avg_time_threshold_ms"],
            "degradation_threshold_percent": config["degradation_threshold_percent"],
        },
    }


@router.post("/performance/alerts/check-health", tags=["performance", "alerts"])
async def check_system_health_for_alerts() -> dict[str, Any]:
    """Check system health and emit alerts if needed.

    Performs a health check and automatically emits alerts for:
    - High slow query rate
    - High average query time
    - Consistently slow query patterns
    - Performance degradation (if baseline is set)

    Returns:
        Summary of alerts emitted
    """
    # reason: _get_alert_manager is untyped (see its definition above); mypy reports [no-untyped-call] for every caller until that helper gets a return type
    manager = _get_alert_manager()  # type: ignore
    alerts = manager.check_system_health()

    return {
        "alerts_emitted": len(alerts),
        "alert_summaries": [
            {
                "id": alert.id,
                "type": alert.alert_type.value,
                "severity": alert.severity.value,
                "message": alert.message,
                "timestamp": alert.timestamp.isoformat(),
            }
            for alert in alerts
        ],
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.post("/performance/baseline", tags=["performance", "alerts"])
async def set_performance_baseline(
    use_current_metrics: bool = Query(
        default=True,
        description="If True, use current system metrics as baseline",
    ),
) -> dict[str, Any]:
    """Set performance baseline for degradation detection.

    If use_current_metrics is True (default), uses current system metrics.
    Otherwise, you can provide custom baseline metrics in the request body.

    Args:
        use_current_metrics: If True, use current system metrics as baseline

    Returns:
        Baseline confirmation
    """
    # reason: _get_alert_manager is untyped (see its definition above); mypy reports [no-untyped-call] for every caller until that helper gets a return type
    manager = _get_alert_manager()  # type: ignore

    if use_current_metrics:
        manager.set_baseline()
    else:
        # In the future, we could accept custom metrics in request body
        manager.set_baseline({})

    config = manager.get_configuration()

    return {
        "message": "Performance baseline set",
        "baseline_metrics": config["baseline_metrics"],
        "baseline_timestamp": config["baseline_timestamp"],
    }
