"""
MONITOR UI Backend — application config.

Reads from the same .env as the rest of the stack.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class UISettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server
    ui_host: str = Field(default="0.0.0.0", alias="UI_HOST")
    ui_port: int = Field(default=8000, alias="UI_PORT")
    ui_cors_origins: str = Field(
        default="http://localhost:3000", alias="UI_CORS_ORIGINS"
    )

    # Neo4j
    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field(default="", alias="NEO4J_PASSWORD")

    # MongoDB
    mongodb_uri: str = Field(default="mongodb://localhost:27017", alias="MONGODB_URI")
    mongodb_database: str = Field(default="monitor", alias="MONGODB_DATABASE")

    # Qdrant — accepts both QDRANT_URI (stack standard) and QDRANT_URL (legacy)
    qdrant_url: Optional[str] = Field(
        default="http://localhost:6333", alias="QDRANT_URI"
    )
    qdrant_url_alt: Optional[str] = Field(default=None, alias="QDRANT_URL")

    @property
    def qdrant_endpoint(self) -> str:
        """Return whichever Qdrant URL is set, preferring QDRANT_URI."""
        return self.qdrant_url or self.qdrant_url_alt or "http://localhost:6333"

    # MinIO
    minio_endpoint: str = Field(default="localhost:9000", alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="minioadmin", alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="", alias="MINIO_SECRET_KEY")
    minio_secure: bool = Field(default=False, alias="MINIO_SECURE")

    # PostgreSQL
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_user: str = Field(default="monitor", alias="POSTGRES_USER")
    postgres_password: str = Field(default="", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="monitor", alias="POSTGRES_DB")

    # OpenSearch
    opensearch_url: str = Field(default="http://localhost:9200", alias="OPENSEARCH_URL")

    # LLM
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    github_models_token: Optional[str] = Field(
        default=None, alias="GITHUB_MODELS_TOKEN"
    )
    github_token: Optional[str] = Field(default=None, alias="GITHUB_TOKEN")
    github_models_base_url: str = Field(
        default="https://models.github.ai/inference", alias="GITHUB_MODELS_BASE_URL"
    )
    llm_model: str = Field(default="claude-sonnet-4-20250514", alias="LLM_MODEL")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ui_cors_origins.split(",")]


@lru_cache
def get_settings() -> UISettings:
    return UISettings()
