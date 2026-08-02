"""
MONITOR Data Layer — Centralised Settings.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pydantic-settings)
CALLED BY: All db clients, tools, and agents (via monitor_data.config.settings)

Single source of truth for all configuration.  Values are loaded from the
environment (or a .env file) and validated at import time using Pydantic
Settings.  Every callsite should use the module-level ``settings`` singleton
rather than reading ``os.getenv`` directly.

Usage:
    from monitor_data.config import settings

    client = Neo4jClient(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings validated from environment / .env file.

    Fields without a default are *required* — the application will fail fast
    at startup if they are missing, rather than raising a KeyError at runtime.
    """

    model_config = SettingsConfigDict(
        # Production loads .env only. Previously this listed
        # ('.env.test', '.env'), which caused live ingest runs to inherit
        # QDRANT_URL=http://127.0.0.1:1 (a test sentinel) on 2026-07-22
        # because pydantic-settings loads each existing file in order and the
        # later file's values override the earlier. Tests set their own
        # values via conftest.setdefault() and never need .env.test loaded
        # implicitly.
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Unknown env vars are silently ignored
    )

    # -------------------------------------------------------------------------
    # Neo4j
    # -------------------------------------------------------------------------
    neo4j_uri: str = Field(default="bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field(default="monitor-dev-neo4j", alias="NEO4J_PASSWORD")

    # -------------------------------------------------------------------------
    # MongoDB
    # -------------------------------------------------------------------------
    mongodb_uri: str = Field(default="mongodb://localhost:27017", alias="MONGODB_URI")
    mongodb_database: str = Field(default="monitor", alias="MONGODB_DATABASE")
    mongodb_server_selection_timeout_ms: int = Field(
        default=3000,
        alias="MONGODB_SERVER_SELECTION_TIMEOUT_MS",
    )
    mongodb_connect_timeout_ms: int = Field(default=3000, alias="MONGODB_CONNECT_TIMEOUT_MS")

    # -------------------------------------------------------------------------
    # Qdrant
    # -------------------------------------------------------------------------
    # 2026-07-22: accept both QDRANT_URI (legacy .env convention) and the
    # Pydantic-aliased QDRANT_URL so neither side goes silently unused.
    qdrant_url: str | None = Field(default=None, alias="QDRANT_URL")
    qdrant_uri_legacy: str | None = Field(default=None, alias="QDRANT_URI")
    qdrant_api_key: str | None = Field(default=None, alias="QDRANT_API_KEY")
    qdrant_path: str | None = Field(default=None, alias="QDRANT_PATH")

    @property
    def resolved_qdrant_url(self) -> str | None:
        """Return whichever QDRANT_* URL is set, preferring QDRANT_URL."""
        return self.qdrant_url or self.qdrant_uri_legacy

    # -------------------------------------------------------------------------
    # Object storage (MinIO / S3-compatible / local folder)
    # -------------------------------------------------------------------------
    storage_backend: str = Field(default="minio", alias="STORAGE_BACKEND")
    storage_endpoint: str | None = Field(default=None, alias="STORAGE_ENDPOINT")
    storage_fallback_to_local: bool = Field(default=True, alias="STORAGE_FALLBACK_TO_LOCAL")
    local_storage_path: str = Field(default=".local_storage", alias="LOCAL_STORAGE_PATH")
    minio_endpoint: str = Field(default="localhost:9000", alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="minioadmin", alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="monitor-dev-minio", alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field(default="monitor", alias="MINIO_BUCKET")
    minio_secure: bool = Field(default=False, alias="MINIO_SECURE")
    minio_region: str = Field(default="us-east-1", alias="MINIO_REGION")

    # -------------------------------------------------------------------------
    # OpenSearch
    # -------------------------------------------------------------------------
    opensearch_url: str = Field(default="http://localhost:9200", alias="OPENSEARCH_URL")
    opensearch_user: str | None = Field(default=None, alias="OPENSEARCH_USER")
    opensearch_password: str | None = Field(default=None, alias="OPENSEARCH_PASSWORD")

    # -------------------------------------------------------------------------
    # Redis (optional runtime cache / pub-sub)
    # -------------------------------------------------------------------------
    redis_url: str | None = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    redis_enabled: bool = Field(default=True, alias="REDIS_ENABLED")
    redis_key_prefix: str = Field(default="monitor", alias="REDIS_KEY_PREFIX")
    redis_cache_ttl_seconds: int = Field(default=30, alias="REDIS_CACHE_TTL_SECONDS")
    redis_solo_play_ttl_seconds: int = Field(default=15, alias="REDIS_SOLO_PLAY_TTL_SECONDS")
    redis_socket_timeout: float = Field(default=0.15, alias="REDIS_SOCKET_TIMEOUT")
    redis_connect_timeout: float = Field(default=0.15, alias="REDIS_CONNECT_TIMEOUT")

    # -------------------------------------------------------------------------
    # Embeddings (LiteLLM — provider-agnostic)
    # -------------------------------------------------------------------------
    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")
    embedding_provider: str = Field(default="ollama", alias="EMBEDDING_PROVIDER")
    embedding_base_url: str | None = Field(
        default=None,
        alias="EMBEDDING_BASE_URL",
        description="Override base URL for embedding requests (e.g. http://localhost:11434 for Ollama).",
    )
    embedding_dimension: int = Field(
        default=1536,
        alias="EMBEDDING_DIMENSION",
        description="Vector dimension for the configured embedding model.",
    )
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    # Additional provider keys used by LiteLLM are picked up automatically
    # via the standard env var names that each provider documents.

    # When the app runs inside Docker, provider rows pointing at services on
    # the *host* (ollama, LM Studio, …) say "localhost", which resolves to the
    # container itself. Set to e.g. "host.docker.internal" (with a matching
    # extra_hosts entry) to transparently reach the host instead.
    localhost_rewrite_host: str = Field(default="", alias="MONITOR_LOCALHOST_REWRITE")

    # -------------------------------------------------------------------------
    # LLM (Anthropic)
    # -------------------------------------------------------------------------
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    llm_model: str = Field(default="claude-sonnet-4-20250514", alias="LLM_MODEL")
    # Vision model for image analysis during document ingestion.
    # Must support image_url message content (GPT-4o, Claude 3, Gemini Pro Vision, etc.)
    vision_model: str = Field(default="gpt-4o-mini", alias="VISION_MODEL")

    # -------------------------------------------------------------------------
    # PostgreSQL (app config, LLM providers, settings)
    # -------------------------------------------------------------------------
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_user: str = Field(default="monitor", alias="POSTGRES_USER")
    postgres_password: str = Field(default="monitor-dev-postgres", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="monitor", alias="POSTGRES_DB")

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # -------------------------------------------------------------------------
    # Reliability
    # -------------------------------------------------------------------------
    db_retry_attempts: int = Field(default=3, alias="DB_RETRY_ATTEMPTS")
    db_retry_min_wait: float = Field(default=1.0, alias="DB_RETRY_MIN_WAIT")
    db_retry_max_wait: float = Field(default=10.0, alias="DB_RETRY_MAX_WAIT")
    # Max seconds a sync→async bridge call (run_sync) may wait; 0 = unbounded.
    db_sync_timeout: float = Field(default=120.0, alias="DB_SYNC_TIMEOUT")

    llm_retry_attempts: int = Field(default=3, alias="LLM_RETRY_ATTEMPTS")
    # Tight backoff for ingestion: Pydantic validation failures are
    # already non-retryable (LLMErrorClass.VALIDATION), and the only
    # retryable class we hit in practice is TIMEOUT on local Ollama — for
    # which long sleeps don't help. Keep attempts for transient recovery,
    # but short.
    llm_retry_min_wait: float = Field(default=0.5, alias="LLM_RETRY_MIN_WAIT")
    llm_retry_max_wait: float = Field(default=2.0, alias="LLM_RETRY_MAX_WAIT")

    # -------------------------------------------------------------------------
    # NLP / GLiNER (Named Entity Recognition)
    # -------------------------------------------------------------------------
    nlp_enabled: bool = Field(default=True, alias="NLP_ENABLED")
    # Cross-job cap on simultaneous LLM calls per provider. Prevents
    # concurrent ingestion jobs from multiplying Ollama's
    # in-flight request count past the model's load-and-queue budget.
    monitor_llm_max_concurrent_per_provider: int = Field(
        default=8,
        alias="MONITOR_LLM_MAX_CONCURRENT_PER_PROVIDER",
        ge=1,
        description="Max in-flight LLM calls per provider, across all jobs in this process.",
    )
    nlp_backend: str = Field(default="spacy", alias="NLP_BACKEND")
    gliner_url: str = Field(default="http://localhost:8082", alias="GLINER_URL")
    gliner_model: str = Field(default="knowledgator/gliner-base-v0.1", alias="GLINER_MODEL")
    gliner_max_length: int = Field(default=384, alias="GLINER_MAX_LENGTH")
    gliner_batch_size: int = Field(default=8, alias="GLINER_BATCH_SIZE")
    entity_extraction_enabled: bool = Field(default=True, alias="ENTITY_EXTRACTION_ENABLED")
    entity_types: str = Field(
        default="person,location,organization,product,event,work_of_art,law,language,date,time,percent,money,quantity,ordinal,cardinal",
        alias="ENTITY_TYPES",
    )

    # -------------------------------------------------------------------------
    # Image Generation (Task 10 — used as defaults by UI settings)
    # -------------------------------------------------------------------------
    image_moderation_mode: str = Field(
        default="provider_default",
        alias="IMAGE_MODERATION_MODE",
        description="Default image moderation policy: provider_default or lines_and_veils.",
    )
    image_max_per_scene: int = Field(
        default=4,
        ge=0,
        le=100,
        alias="IMAGE_MAX_PER_SCENE",
        description="Default per-scene generation cap; 0 disables.",
    )
    image_max_per_conversation: int = Field(
        default=8,
        ge=0,
        le=100,
        alias="IMAGE_MAX_PER_CONVERSATION",
        description="Default per-conversation/session generation cap.",
    )
    image_max_per_actor_hour: int = Field(
        default=12,
        ge=0,
        le=1000,
        alias="IMAGE_MAX_PER_ACTOR_HOUR",
        description="Default per-actor-per-hour generation cap.",
    )
    image_suggestions_enabled: bool = Field(
        default=True,
        alias="IMAGE_SUGGESTIONS_ENABLED",
        description="Whether the scene loop may emit image suggestion chips.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the cached Settings singleton.

    Using ``lru_cache`` avoids re-reading the .env file on every import while
    still allowing the cache to be cleared in tests via
    ``get_settings.cache_clear()``.
    """
    return Settings()


# Module-level convenience alias — most callsites simply do:
#   from monitor_data.config import settings
settings: Settings = get_settings()


def normalize_local_base_url(url: str | None) -> str | None:
    """
    Rewrite localhost/127.0.0.1 base URLs to ``MONITOR_LOCALHOST_REWRITE``.

    Inside Docker, a provider configured with ``http://localhost:11434/v1``
    (host-running ollama, LM Studio, …) points at the container itself and
    every call dies with ECONNREFUSED. With the env var set (compose sets it
    to ``host.docker.internal``) the same row works in both environments.
    No-op when the env var is empty or the URL targets a non-local host.
    """
    if not url:
        return url
    host = get_settings().localhost_rewrite_host.strip()
    if not host:
        return url
    for needle in ("://localhost", "://127.0.0.1"):
        if needle in url:
            return url.replace(needle, f"://{host}", 1)
    return url
