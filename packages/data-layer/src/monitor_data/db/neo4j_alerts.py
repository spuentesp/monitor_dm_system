"""
Neo4j performance alerting system.

Provides automated alerting for slow queries and performance issues.
Integrates with QueryPerformanceTracker to detect and report problems.

This module is part of Phase 5 of the Neo4j performance optimization plan.
"""

import logging
import threading
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from monitor_data.db.neo4j import get_perf_tracker

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    """Severity levels for performance alerts."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(str, Enum):
    """Types of performance alerts."""

    SLOW_QUERY = "slow_query"  # Single slow query detected
    SLOW_QUERY_PATTERN = "slow_query_pattern"  # Pattern consistently slow
    HIGH_SLOW_QUERY_RATE = "high_slow_query_rate"  # Too many slow queries
    HIGH_AVG_TIME = "high_avg_time"  # Average query time too high
    REPEATED_FAILURE = "repeated_failure"  # Repeated query failures
    PERFORMANCE_DEGRADATION = "performance_degradation"  # Performance getting worse


class PerformanceAlert:
    """Represents a performance alert."""

    def __init__(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        message: str,
        pattern: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ):
        self.alert_type = alert_type
        self.severity = severity
        self.message = message
        self.pattern = pattern
        self.metrics = metrics or {}
        self.timestamp = datetime.now(timezone.utc)
        self.id = f"{alert_type.value}_{int(self.timestamp.timestamp())}"

    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary."""
        return {
            "id": self.id,
            "type": self.alert_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "pattern": self.pattern,
            "metrics": self.metrics,
            "timestamp": self.timestamp.isoformat(),
        }


class PerformanceAlertManager:
    """Manages performance alerts and notifications.

    Provides singleton access to alerting functionality with
    configurable thresholds and alert handlers.
    """

    _instance: Optional["PerformanceAlertManager"] = None
    _lock = threading.Lock()
    _initialized: bool = False

    def __new__(cls) -> "PerformanceAlertManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self._initialized = True

        # Configuration thresholds
        self.slow_query_threshold_ms = 150.0
        self.critical_query_threshold_ms = 1000.0
        self.high_slow_query_rate_threshold = 0.20  # 20%
        self.high_avg_time_threshold_ms = 50.0
        self.degradation_threshold_percent = 0.50  # 50% worse than baseline

        # Alert handlers
        self._handlers: List[Callable[[PerformanceAlert], None]] = []

        # Alert history
        self._alert_history: List[PerformanceAlert] = []
        self._max_history_size = 1000

        # Baseline metrics for degradation detection
        self._baseline_metrics: Optional[Dict[str, float]] = None
        self._baseline_timestamp: Optional[datetime] = None

        # Cooldown periods (prevent alert spam)
        self._cooldowns: Dict[str, datetime] = {}
        self._cooldown_minutes = {
            AlertType.SLOW_QUERY: 0,  # No cooldown for single slow queries
            AlertType.SLOW_QUERY_PATTERN: 30,  # 30 minutes
            AlertType.HIGH_SLOW_QUERY_RATE: 15,  # 15 minutes
            AlertType.HIGH_AVG_TIME: 15,  # 15 minutes
            AlertType.PERFORMANCE_DEGRADATION: 60,  # 1 hour
        }

        # Register default handler (logging)
        self.add_handler(self._default_log_handler)

        logger.info("PerformanceAlertManager initialized")

    def add_handler(self, handler: Callable[[PerformanceAlert], None]) -> None:
        """Add a custom alert handler.

        Args:
            handler: Function that takes a PerformanceAlert and returns None
        """
        self._handlers.append(handler)
        logger.info("Added alert handler: %s", handler.__name__)

    def remove_handler(self, handler: Callable[[PerformanceAlert], None]) -> None:
        """Remove an alert handler.

        Args:
            handler: Handler function to remove
        """
        if handler in self._handlers:
            self._handlers.remove(handler)
            logger.info("Removed alert handler: %s", handler.__name__)

    def _default_log_handler(self, alert: PerformanceAlert) -> None:
        """Default handler: log the alert.

        Args:
            alert: Alert to log
        """
        log_func = {
            AlertSeverity.INFO: logger.info,
            AlertSeverity.WARNING: logger.warning,
            AlertSeverity.ERROR: logger.error,
            AlertSeverity.CRITICAL: logger.critical,
        }.get(alert.severity, logger.warning)

        msg = f"[{alert.severity.upper()}] {alert.message}"
        if alert.pattern:
            msg += f" | Pattern: {alert.pattern[:100]}"
        if alert.metrics:
            msg += f" | Metrics: {alert.metrics}"

        log_func(msg)

    def _check_cooldown(self, alert_type: AlertType, pattern: Optional[str] = None) -> bool:
        """Check if alert is in cooldown period.

        Args:
            alert_type: Type of alert
            pattern: Query pattern (for pattern-specific cooldowns)

        Returns:
            True if in cooldown, False otherwise
        """
        cooldown_minutes = self._cooldown_minutes.get(alert_type, 0)
        if cooldown_minutes == 0:
            return False

        cooldown_key = f"{alert_type.value}_{pattern or 'global'}"
        last_alert_time = self._cooldowns.get(cooldown_key)

        if last_alert_time:
            time_since_last = datetime.now(timezone.utc) - last_alert_time
            if time_since_last < timedelta(minutes=cooldown_minutes):
                return True

        return False

    def _set_cooldown(self, alert_type: AlertType, pattern: Optional[str] = None) -> None:
        """Set cooldown for an alert type.

        Args:
            alert_type: Type of alert
            pattern: Query pattern (for pattern-specific cooldowns)
        """
        cooldown_key = f"{alert_type.value}_{pattern or 'global'}"
        self._cooldowns[cooldown_key] = datetime.now(timezone.utc)

    def _emit_alert(self, alert: PerformanceAlert) -> None:
        """Emit alert to all registered handlers.

        Args:
            alert: Alert to emit
        """
        # Add to history
        self._alert_history.append(alert)
        if len(self._alert_history) > self._max_history_size:
            self._alert_history.pop(0)

        # Call all handlers
        for handler in self._handlers:
            try:
                handler(alert)
            except Exception as exc:  # noqa: BLE001
                logger.error("Error in alert handler %s: %s", handler.__name__, exc)

    def check_slow_query(
        self,
        pattern: str,
        execution_time_ms: float,
        query_sample: Optional[str] = None,
    ) -> Optional[PerformanceAlert]:
        """Check if a query is slow and emit alert if needed.

        Args:
            pattern: Query pattern
            execution_time_ms: Query execution time
            query_sample: Sample query text

        Returns:
            Alert if emitted, None otherwise
        """
        if execution_time_ms < self.slow_query_threshold_ms:
            return None

        # Determine severity
        if execution_time_ms >= self.critical_query_threshold_ms:
            severity = AlertSeverity.CRITICAL
            message = f"CRITICAL slow query detected ({execution_time_ms:.2f}ms > {self.critical_query_threshold_ms}ms)"
        elif execution_time_ms >= self.slow_query_threshold_ms * 2:
            severity = AlertSeverity.ERROR
            message = f"Very slow query detected ({execution_time_ms:.2f}ms)"
        else:
            severity = AlertSeverity.WARNING
            message = f"Slow query detected ({execution_time_ms:.2f}ms)"

        alert = PerformanceAlert(
            alert_type=AlertType.SLOW_QUERY,
            severity=severity,
            message=message,
            pattern=pattern,
            metrics={
                "execution_time_ms": execution_time_ms,
                "threshold_ms": self.slow_query_threshold_ms,
                "query_sample": query_sample[:200] if query_sample else None,
            },
        )

        # No cooldown for single slow queries
        self._emit_alert(alert)
        return alert

    def check_system_health(self) -> List[PerformanceAlert]:
        """Check overall system health and emit alerts if needed.

        Returns:
            List of alerts emitted
        """
        alerts: List[PerformanceAlert] = []
        tracker = get_perf_tracker()
        stats = tracker.get_stats()

        # Check slow query rate
        slow_query_rate = stats["slow_query_rate"]
        if slow_query_rate > self.high_slow_query_rate_threshold:
            if not self._check_cooldown(AlertType.HIGH_SLOW_QUERY_RATE):
                severity = AlertSeverity.CRITICAL if slow_query_rate > 0.40 else AlertSeverity.ERROR
                alert = PerformanceAlert(
                    alert_type=AlertType.HIGH_SLOW_QUERY_RATE,
                    severity=severity,
                    message=f"High slow query rate: {slow_query_rate:.1f}% (threshold: {self.high_slow_query_rate_threshold * 100:.0f}%)",
                    metrics={
                        "slow_query_rate": slow_query_rate,
                        "slow_queries": stats["slow_queries"],
                        "total_queries": stats["total_queries"],
                    },
                )
                alerts.append(alert)
                self._emit_alert(alert)
                self._set_cooldown(AlertType.HIGH_SLOW_QUERY_RATE)

        # Check average query time
        avg_time = stats["avg_time_ms"]
        if avg_time > self.high_avg_time_threshold_ms:
            if not self._check_cooldown(AlertType.HIGH_AVG_TIME):
                severity = (
                    AlertSeverity.CRITICAL
                    if avg_time > self.high_avg_time_threshold_ms * 3
                    else AlertSeverity.ERROR
                )
                alert = PerformanceAlert(
                    alert_type=AlertType.HIGH_AVG_TIME,
                    severity=severity,
                    message=f"High average query time: {avg_time:.2f}ms (threshold: {self.high_avg_time_threshold_ms}ms)",
                    metrics={
                        "avg_time_ms": avg_time,
                        "total_time_ms": stats["total_time_ms"],
                        "total_queries": stats["total_queries"],
                    },
                )
                alerts.append(alert)
                self._emit_alert(alert)
                self._set_cooldown(AlertType.HIGH_AVG_TIME)

        # Check for consistently slow patterns
        report = tracker.get_report(limit=10, sort_by="avg_time")
        for pattern_data in report["by_pattern"]:
            pattern = pattern_data["pattern"]
            avg_time = pattern_data["avg_time_ms"]
            count = pattern_data["count"]

            # Only alert if we have enough data points and it's consistently slow
            if count >= 5 and avg_time > self.slow_query_threshold_ms * 2:
                if not self._check_cooldown(AlertType.SLOW_QUERY_PATTERN, pattern):
                    severity = (
                        AlertSeverity.CRITICAL
                        if avg_time > self.critical_query_threshold_ms
                        else AlertSeverity.ERROR
                    )
                    alert = PerformanceAlert(
                        alert_type=AlertType.SLOW_QUERY_PATTERN,
                        severity=severity,
                        message=f"Consistently slow query pattern: avg {avg_time:.2f}ms over {count} executions",
                        pattern=pattern,
                        metrics={
                            "avg_time_ms": avg_time,
                            "max_time_ms": pattern_data["max_time_ms"],
                            "count": count,
                            "slow_count": pattern_data["slow_count"],
                        },
                    )
                    alerts.append(alert)
                    self._emit_alert(alert)
                    self._set_cooldown(AlertType.SLOW_QUERY_PATTERN, pattern)

        # Check for performance degradation
        if self._baseline_metrics:
            current_avg_time = stats["avg_time_ms"]
            baseline_avg_time = self._baseline_metrics.get("avg_time_ms", 0)

            if baseline_avg_time > 0:
                degradation_percent = (current_avg_time - baseline_avg_time) / baseline_avg_time

                if degradation_percent > self.degradation_threshold_percent:
                    if not self._check_cooldown(AlertType.PERFORMANCE_DEGRADATION):
                        severity = (
                            AlertSeverity.CRITICAL
                            if degradation_percent > 1.0
                            else AlertSeverity.ERROR
                        )
                        alert = PerformanceAlert(
                            alert_type=AlertType.PERFORMANCE_DEGRADATION,
                            severity=severity,
                            message=f"Performance degraded by {degradation_percent * 100:.1f}% (baseline: {baseline_avg_time:.2f}ms, current: {current_avg_time:.2f}ms)",
                            metrics={
                                "degradation_percent": degradation_percent,
                                "baseline_avg_time_ms": baseline_avg_time,
                                "current_avg_time_ms": current_avg_time,
                                "baseline_timestamp": self._baseline_timestamp.isoformat()
                                if self._baseline_timestamp
                                else None,
                            },
                        )
                        alerts.append(alert)
                        self._emit_alert(alert)
                        self._set_cooldown(AlertType.PERFORMANCE_DEGRADATION)

        return alerts

    def set_baseline(self, metrics: Optional[Dict[str, float]] = None) -> None:
        """Set baseline metrics for degradation detection.

        If no metrics provided, uses current system metrics.

        Args:
            metrics: Optional metrics to use as baseline
        """
        if metrics is None:
            tracker = get_perf_tracker()
            stats = tracker.get_stats()
            metrics = {
                "avg_time_ms": stats["avg_time_ms"],
                "slow_query_rate": stats["slow_query_rate"],
            }

        self._baseline_metrics = metrics
        self._baseline_timestamp = datetime.now(timezone.utc)

        logger.info(
            "Performance baseline set: avg_time_ms=%.2f, slow_query_rate=%.1f%%",
            metrics.get("avg_time_ms", 0),
            metrics.get("slow_query_rate", 0) * 100,
        )

    def get_alert_history(
        self,
        limit: int = 50,
        severity: Optional[AlertSeverity] = None,
        alert_type: Optional[AlertType] = None,
        since: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Get alert history with optional filtering.

        Args:
            limit: Maximum number of alerts to return
            severity: Filter by severity
            alert_type: Filter by alert type
            since: Filter to alerts after this timestamp

        Returns:
            List of alert dictionaries
        """
        filtered = self._alert_history

        if severity:
            filtered = [a for a in filtered if a.severity == severity]

        if alert_type:
            filtered = [a for a in filtered if a.alert_type == alert_type]

        if since:
            filtered = [a for a in filtered if a.timestamp >= since]

        # Get most recent first
        filtered = sorted(filtered, key=lambda a: a.timestamp, reverse=True)

        return [alert.to_dict() for alert in filtered[:limit]]

    def get_configuration(self) -> Dict[str, Any]:
        """Get current alerting configuration.

        Returns:
            Configuration dictionary
        """
        return {
            "slow_query_threshold_ms": self.slow_query_threshold_ms,
            "critical_query_threshold_ms": self.critical_query_threshold_ms,
            "high_slow_query_rate_threshold": self.high_slow_query_rate_threshold,
            "high_avg_time_threshold_ms": self.high_avg_time_threshold_ms,
            "degradation_threshold_percent": self.degradation_threshold_percent,
            "cooldown_minutes": self._cooldown_minutes,
            "baseline_metrics": self._baseline_metrics,
            "baseline_timestamp": self._baseline_timestamp.isoformat()
            if self._baseline_timestamp
            else None,
            "handlers_count": len(self._handlers),
            "alert_history_size": len(self._alert_history),
        }

    def update_configuration(self, **kwargs: Any) -> None:
        """Update alerting configuration.

        Args:
            **kwargs: Configuration parameters to update
        """
        valid_params = {
            "slow_query_threshold_ms": float,
            "critical_query_threshold_ms": float,
            "high_slow_query_rate_threshold": float,
            "high_avg_time_threshold_ms": float,
            "degradation_threshold_percent": float,
        }

        for key, value in kwargs.items():
            if key in valid_params:
                expected_type = valid_params[key]
                if isinstance(value, expected_type):
                    setattr(self, key, value)
                    logger.info("Updated configuration: %s = %s", key, value)
                else:
                    logger.warning(
                        "Invalid type for %s: expected %s, got %s",
                        key,
                        expected_type.__name__,
                        type(value).__name__,
                    )
            else:
                logger.warning("Unknown configuration parameter: %s", key)


# Singleton accessor
def get_alert_manager() -> PerformanceAlertManager:
    """Get the singleton PerformanceAlertManager instance.

    Returns:
        PerformanceAlertManager instance
    """
    return PerformanceAlertManager()
