"""
Health check endpoint for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries and data-layer modules only
CALLED BY: MCP server (server.py), k8s probes

This module provides health check functionality to verify:
- Server is running
- Database connectivity (Neo4j, MongoDB, Qdrant)
- Server version information
"""

import logging
from typing import Dict, Any
from datetime import datetime

from monitor_data.db.neo4j import get_neo4j_client
from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.db.qdrant import get_qdrant_client

logger = logging.getLogger(__name__)

# Version from package metadata
__version__ = "0.1.0"


class HealthStatus:
    """Health status constants."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


def check_neo4j_connectivity() -> Dict[str, Any]:
    """
    Check Neo4j database connectivity.

    Returns:
        Dict with status and details

    Examples:
        >>> result = check_neo4j_connectivity()
        >>> result['status']
        'healthy'
    """
    try:
        client = get_neo4j_client()
        is_connected = client.verify_connectivity()

        if is_connected:
            return {
                "status": HealthStatus.HEALTHY,
                "message": "Neo4j connection established",
            }
        else:
            return {
                "status": HealthStatus.UNHEALTHY,
                "message": "Neo4j connection failed",
            }
    except Exception as e:
        logger.error(f"Neo4j health check failed: {e}")
        return {
            "status": HealthStatus.UNHEALTHY,
            "message": f"Neo4j error: {str(e)}",
        }


def check_mongodb_connectivity() -> Dict[str, Any]:
    """
    Check MongoDB database connectivity.

    Returns:
        Dict with status and details

    Examples:
        >>> result = check_mongodb_connectivity()
        >>> result['status']
        'healthy'
    """
    try:
        client = get_mongodb_client()
        is_connected = client.verify_connectivity()

        if is_connected:
            return {
                "status": HealthStatus.HEALTHY,
                "message": "MongoDB connection established",
            }
        else:
            return {
                "status": HealthStatus.UNHEALTHY,
                "message": "MongoDB connection failed",
            }
    except Exception as e:
        logger.error(f"MongoDB health check failed: {e}")
        return {
            "status": HealthStatus.UNHEALTHY,
            "message": f"MongoDB error: {str(e)}",
        }


def check_qdrant_connectivity() -> Dict[str, Any]:
    """
    Check Qdrant database connectivity.

    Returns:
        Dict with status and details

    Examples:
        >>> result = check_qdrant_connectivity()
        >>> result['status']
        'healthy'
    """
    try:
        client = get_qdrant_client()
        is_connected = client.verify_connectivity()

        if is_connected:
            return {
                "status": HealthStatus.HEALTHY,
                "message": "Qdrant connection established",
            }
        else:
            return {
                "status": HealthStatus.UNHEALTHY,
                "message": "Qdrant connection failed",
            }
    except Exception as e:
        logger.error(f"Qdrant health check failed: {e}")
        return {
            "status": HealthStatus.UNHEALTHY,
            "message": f"Qdrant error: {str(e)}",
        }


def get_health_status() -> Dict[str, Any]:
    """
    Get comprehensive health status for all components.

    Returns:
        Dict with overall status, component statuses, and metadata

    Examples:
        >>> status = get_health_status()
        >>> status['overall_status']
        'healthy'
        >>> status['components']['neo4j']['status']
        'healthy'
    """
    # Check all components
    neo4j_health = check_neo4j_connectivity()
    mongodb_health = check_mongodb_connectivity()
    qdrant_health = check_qdrant_connectivity()

    components = {
        "neo4j": neo4j_health,
        "mongodb": mongodb_health,
        "qdrant": qdrant_health,
    }

    # Determine overall status
    statuses = [comp["status"] for comp in components.values()]

    if all(s == HealthStatus.HEALTHY for s in statuses):
        overall_status = HealthStatus.HEALTHY
    elif all(s == HealthStatus.UNHEALTHY for s in statuses):
        overall_status = HealthStatus.UNHEALTHY
    else:
        overall_status = HealthStatus.DEGRADED

    return {
        "overall_status": overall_status,
        "components": components,
        "version": __version__,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


def is_healthy() -> bool:
    """
    Quick health check - returns True if all components are healthy.

    Returns:
        True if healthy, False otherwise

    Examples:
        >>> is_healthy()
        True
    """
    try:
        status = get_health_status()
        return status["overall_status"] == HealthStatus.HEALTHY
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return False
