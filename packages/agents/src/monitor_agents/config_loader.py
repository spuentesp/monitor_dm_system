"""
ConfigLoader — Application configuration loader (SYS-1).

Loads configuration from environment files and validates required keys.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), external libraries
CALLED BY: CLI (Layer 3), AppInitializer
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing required keys."""

    pass


# Required configuration keys per section
_REQUIRED_KEYS: Dict[str, List[str]] = {
    "neo4j": ["NEO4J_URI", "NEO4J_USERNAME", "NEO4J_PASSWORD", "NEO4J_DATABASE"],
    "mongodb": ["MONGODB_URI", "MONGODB_DATABASE"],
    "qdrant": ["QDRANT_URL"],
    "minio": ["MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "MINIO_BUCKET"],
    "llm": ["LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY"],
    "app": [],
}


class ConfigLoader:
    """
    Load and validate MONITOR configuration from .env files or environment.

    Parses a .env file, validates that all required keys are present,
    and returns a structured configuration dictionary.
    """

    def load_config(self, env_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Load configuration from a .env file or environment variables.

        Args:
            env_path: Path to .env file. If None, reads from environment only.

        Returns:
            Dict with sections: neo4j, mongodb, qdrant, minio, llm, app.

        Raises:
            ConfigurationError: If required keys are missing.
            FileNotFoundError: If env_path is specified but doesn't exist.
        """
        if env_path is not None:
            env_file = Path(env_path)
            if not env_file.exists():
                raise ConfigurationError(f"Configuration file not found: {env_path}")
            self._load_env_file(env_file)

        config = self._build_config()
        self._validate_config(config)
        return config

    def _load_env_file(self, env_file: Path) -> None:
        """Parse a .env file and set environment variables."""
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            os.environ.setdefault(key, value)

    def _build_config(self) -> Dict[str, Any]:
        """Build configuration dictionary from environment variables."""
        return {
            "neo4j": {
                "uri": os.getenv("NEO4J_URI", ""),
                "username": os.getenv("NEO4J_USERNAME", ""),
                "password": os.getenv("NEO4J_PASSWORD", ""),
                "database": os.getenv("NEO4J_DATABASE", ""),
            },
            "mongodb": {
                "uri": os.getenv("MONGODB_URI", ""),
                "database": os.getenv("MONGODB_DATABASE", ""),
            },
            "qdrant": {
                "url": os.getenv("QDRANT_URL", ""),
                "api_key": os.getenv("QDRANT_API_KEY", ""),
            },
            "minio": {
                "endpoint": os.getenv("MINIO_ENDPOINT", ""),
                "access_key": os.getenv("MINIO_ACCESS_KEY", ""),
                "secret_key": os.getenv("MINIO_SECRET_KEY", ""),
                "bucket": os.getenv("MINIO_BUCKET", ""),
            },
            "llm": {
                "provider": os.getenv("LLM_PROVIDER", ""),
                "model": os.getenv("LLM_MODEL", ""),
                "api_key": os.getenv("LLM_API_KEY", ""),
                "temperature": float(os.getenv("LLM_TEMPERATURE", "0.7")),
                "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "4096")),
            },
            "app": {
                "log_level": os.getenv("APP_LOG_LEVEL", "INFO"),
                "auto_save": os.getenv("APP_AUTO_SAVE", "true").lower() == "true",
            },
        }

    def _validate_config(self, config: Dict[str, Any]) -> None:
        """Validate that all required configuration keys have non-empty values."""
        missing: List[str] = []

        for section, keys in _REQUIRED_KEYS.items():
            for key in keys:
                value = config.get(section, {}).get(self._env_key_to_config_key(key), "")
                if not value:
                    missing.append(key)

        if missing:
            raise ConfigurationError(f"Missing required configuration keys: {', '.join(missing)}")

    @staticmethod
    def _env_key_to_config_key(env_key: str) -> str:
        """Convert NEO4J_URI -> uri, MONGODB_DATABASE -> database, etc."""
        # Remove prefix and convert to lowercase
        for prefix in ("NEO4J_", "MONGODB_", "QDRANT_", "MINIO_", "LLM_"):
            if env_key.startswith(prefix):
                return env_key[len(prefix) :].lower()
        return env_key.lower()

    @staticmethod
    def get_auto_save_enabled() -> bool:
        """Check if auto-save is enabled in the configuration."""
        return os.getenv("APP_AUTO_SAVE", "true").lower() == "true"
