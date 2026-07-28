import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from monitor_ui.routers.performance import router, _calculate_percentile
from fastapi import FastAPI
from datetime import datetime, UTC

app = FastAPI()
app.include_router(router)
client = TestClient(app)

@pytest.fixture
def mock_tracker():
    tracker = MagicMock()
    tracker.get_stats.return_value = {
        "total_queries": 100,
        "total_time_ms": 1000.0,
        "avg_time_ms": 10.0,
        "slow_queries": 5,
        "slow_query_rate": 5.0,
        "unique_patterns": 10,
        "uptime_seconds": 3600.0,
    }
    tracker.get_report.return_value = {
        "by_pattern": [
            {
                "pattern": "MATCH (n) RETURN n",
                "count": 50,
                "total_time_ms": 500.0,
                "avg_time_ms": 10.0,
                "min_time_ms": 5.0,
                "max_time_ms": 20.0,
                "p95_time_ms": 18.0,
                "p99_time_ms": 19.5,
                "slow_count": 0,
                "last_executed": "2023-01-01T00:00:00Z"
            },
            {
                "pattern": "MATCH (n) WHERE n.id = $id RETURN n",
                "count": 0, # Should be filtered out if min_count > 0
                "total_time_ms": 0.0,
                "avg_time_ms": 0.0,
                "min_time_ms": 0.0,
                "max_time_ms": 0.0,
                "p95_time_ms": 0.0,
                "p99_time_ms": 0.0,
                "slow_count": 0,
                "last_executed": "2023-01-01T00:00:00Z"
            }
        ]
    }
    tracker.get_slow_queries.return_value = [
        {
            "pattern": "MATCH (n) RETURN n",
            "execution_time_ms": 200.0,
            "timestamp": "2023-01-01T00:00:00Z",
            "sample_query": "MATCH (n) RETURN n LIMIT 1"
        }
    ]
    return tracker

@pytest.fixture
def mock_alert_manager():
    manager = MagicMock()
    
    manager.get_configuration.return_value = {
        "slow_query_threshold_ms": 150.0,
        "critical_query_threshold_ms": 500.0,
        "high_slow_query_rate_threshold": 0.1,
        "high_avg_time_threshold_ms": 50.0,
        "degradation_threshold_percent": 0.2,
        "cooldown_minutes": {"slow_query": 5},
        "baseline_metrics": {"avg_time_ms": 10.0},
        "baseline_timestamp": "2023-01-01T00:00:00Z"
    }
    
    alert1 = MagicMock()
    alert1.id = "alert-1"
    
    alert_type_mock = MagicMock()
    alert_type_mock.value = "slow_query"
    alert1.alert_type = alert_type_mock
    
    severity_mock = MagicMock()
    severity_mock.value = "warning"
    alert1.severity = severity_mock
    
    alert1.message = "Slow query detected"
    alert1.timestamp = datetime(2023, 1, 1, tzinfo=UTC)
    
    manager.check_system_health.return_value = [alert1]
    
    manager.get_alert_history.return_value = [
        {
            "id": "alert-1",
            "type": "slow_query",
            "severity": "warning",
            "message": "Slow query detected",
            "pattern": "MATCH (n) RETURN n",
            "metrics": {},
            "timestamp": "2023-01-01T00:00:00Z"
        }
    ]
    return manager


def test_get_performance_overview(mock_tracker):
    with patch("monitor_ui.routers.performance._get_tracker", return_value=mock_tracker):
        response = client.get("/performance")
        assert response.status_code == 200
        assert response.json()["total_queries"] == 100

def test_get_query_patterns(mock_tracker):
    with patch("monitor_ui.routers.performance._get_tracker", return_value=mock_tracker):
        response = client.get("/performance/patterns?limit=10&sort_by=count&min_count=1")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["pattern"] == "MATCH (n) RETURN n"

def test_get_slow_queries(mock_tracker):
    with patch("monitor_ui.routers.performance._get_tracker", return_value=mock_tracker):
        response = client.get("/performance/slow?limit=10&min_time_ms=100")
        assert response.status_code == 200
        assert len(response.json()) == 1

def test_get_performance_report(mock_tracker):
    with patch("monitor_ui.routers.performance._get_tracker", return_value=mock_tracker):
        response = client.get("/performance/report")
        assert response.status_code == 200
        data = response.json()
        assert "overview" in data
        assert "top_patterns" in data
        assert "slowest_patterns" in data
        assert "recent_slow_queries" in data

def test_reset_performance_tracker(mock_tracker):
    with patch("monitor_ui.routers.performance._get_tracker", return_value=mock_tracker):
        response = client.post("/performance/reset")
        assert response.status_code == 200
        mock_tracker.reset.assert_called_once()

def test_get_performance_health_healthy(mock_tracker):
    with patch("monitor_ui.routers.performance._get_tracker", return_value=mock_tracker):
        response = client.get("/health/performance")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

def test_get_performance_health_unhealthy(mock_tracker):
    mock_tracker.get_stats.return_value["slow_query_rate"] = 25.0
    mock_tracker.get_stats.return_value["avg_time_ms"] = 200.0
    with patch("monitor_ui.routers.performance._get_tracker", return_value=mock_tracker):
        response = client.get("/health/performance")
        assert response.status_code == 200
        assert response.json()["status"] == "unhealthy"

def test_get_performance_health_degraded(mock_tracker):
    mock_tracker.get_stats.return_value["slow_query_rate"] = 15.0
    mock_tracker.get_stats.return_value["avg_time_ms"] = 100.0
    with patch("monitor_ui.routers.performance._get_tracker", return_value=mock_tracker):
        response = client.get("/health/performance")
        assert response.status_code == 200
        assert response.json()["status"] == "degraded"

def test_get_alerts(mock_alert_manager):
    with patch("monitor_ui.routers.performance._get_alert_manager", return_value=mock_alert_manager):
        # We need to mock AlertSeverity and AlertType enum since they are imported inside the route.
        # It's easier to mock monitor_data.db.neo4j_alerts to return Enums.
        import sys
        
        class DummyEnum:
            def __init__(self, val):
                self.value = val
        
        mock_module = MagicMock()
        mock_module.AlertSeverity = DummyEnum
        mock_module.AlertType = DummyEnum
        
        with patch.dict(sys.modules, {"monitor_data.db.neo4j_alerts": mock_module}):
            response = client.get("/performance/alerts?severity=warning&alert_type=slow_query&since=2023-01-01T00:00:00")
            assert response.status_code == 200
            assert len(response.json()) == 1

def test_get_alerts_config(mock_alert_manager):
    with patch("monitor_ui.routers.performance._get_alert_manager", return_value=mock_alert_manager):
        response = client.get("/performance/alerts/config")
        assert response.status_code == 200
        assert response.json()["slow_query_threshold_ms"] == 150.0

def test_update_alerts_config(mock_alert_manager):
    with patch("monitor_ui.routers.performance._get_alert_manager", return_value=mock_alert_manager):
        response = client.put("/performance/alerts/config?slow_query_threshold_ms=200.0&degradation_threshold_percent=0.5")
        assert response.status_code == 200
        mock_alert_manager.update_configuration.assert_called_once_with(
            slow_query_threshold_ms=200.0,
            degradation_threshold_percent=0.5
        )

def test_check_system_health_for_alerts(mock_alert_manager):
    with patch("monitor_ui.routers.performance._get_alert_manager", return_value=mock_alert_manager):
        response = client.post("/performance/alerts/check-health")
        assert response.status_code == 200
        assert response.json()["alerts_emitted"] == 1

def test_set_performance_baseline_true(mock_alert_manager):
    with patch("monitor_ui.routers.performance._get_alert_manager", return_value=mock_alert_manager):
        response = client.post("/performance/baseline?use_current_metrics=true")
        assert response.status_code == 200
        mock_alert_manager.set_baseline.assert_called_once_with()

def test_set_performance_baseline_false(mock_alert_manager):
    with patch("monitor_ui.routers.performance._get_alert_manager", return_value=mock_alert_manager):
        response = client.post("/performance/baseline?use_current_metrics=false")
        assert response.status_code == 200
        mock_alert_manager.set_baseline.assert_called_once_with({})

def test_calculate_percentile():
    times = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert _calculate_percentile(times, 0.5) == 30.0
    assert _calculate_percentile([], 0.5) == 0.0

def test_get_tracker_import_error():
    import sys
    from monitor_ui.routers.performance import _get_tracker
    with patch.dict(sys.modules, {"monitor_data.db.neo4j": None}):
        with pytest.raises(Exception) as excinfo:
            _get_tracker()
        assert excinfo.value.status_code == 503

def test_get_alert_manager_import_error():
    import sys
    from monitor_ui.routers.performance import _get_alert_manager
    with patch.dict(sys.modules, {"monitor_data.db.neo4j_alerts": None}):
        with pytest.raises(Exception) as excinfo:
            _get_alert_manager()
        assert excinfo.value.status_code == 503

def test_get_tracker_success():
    import sys
    from monitor_ui.routers.performance import _get_tracker
    
    # Need to properly patch the import
    mock_neo4j = MagicMock()
    mock_neo4j.get_perf_tracker.return_value = "tracker"
    
    with patch.dict(sys.modules, {"monitor_data.db.neo4j": mock_neo4j}):
        assert _get_tracker() == "tracker"

def test_get_alert_manager_success():
    import sys
    from monitor_ui.routers.performance import _get_alert_manager
    
    mock_neo4j_alerts = MagicMock()
    mock_neo4j_alerts.get_alert_manager.return_value = "alert_manager"
    
    with patch.dict(sys.modules, {"monitor_data.db.neo4j_alerts": mock_neo4j_alerts}):
        assert _get_alert_manager() == "alert_manager"

def test_get_performance_health_avg_time_degraded(mock_tracker):
    mock_tracker.get_stats.return_value["slow_query_rate"] = 0.0
    mock_tracker.get_stats.return_value["avg_time_ms"] = 160.0
    with patch("monitor_ui.routers.performance._get_tracker", return_value=mock_tracker):
        response = client.get("/health/performance")
        assert response.status_code == 200
        assert response.json()["status"] == "degraded"

def test_update_alerts_config_full(mock_alert_manager):
    with patch("monitor_ui.routers.performance._get_alert_manager", return_value=mock_alert_manager):
        response = client.put("/performance/alerts/config?slow_query_threshold_ms=200.0&critical_query_threshold_ms=600.0&high_slow_query_rate_threshold=0.5&high_avg_time_threshold_ms=100.0&degradation_threshold_percent=0.3")
        assert response.status_code == 200
        mock_alert_manager.update_configuration.assert_called_once()
        
def test_update_alerts_config_none(mock_alert_manager):
    with patch("monitor_ui.routers.performance._get_alert_manager", return_value=mock_alert_manager):
        response = client.put("/performance/alerts/config")
        assert response.status_code == 200
        mock_alert_manager.update_configuration.assert_not_called()
