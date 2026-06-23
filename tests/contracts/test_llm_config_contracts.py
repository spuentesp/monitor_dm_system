"""Contract tests for the LLMConfig schemas.

Verifies that llm_config Pydantic models:
- instantiate with valid data,
- enforce required fields,
- enforce enum membership,
- support to_dict() helper on ModelParams.
"""
from __future__ import annotations

import pytest
from monitor_data.schemas.llm_config import (
    EffectiveLLMConfig,
    LLMNodeAssignment,
    LLMProviderConfig,
    LLMProviderType,
    LLMTaskAttemptResponse,
    ModelParams,
    ModelRole,
    PROVIDER_BASE_URLS,
)
from pydantic import ValidationError


pytestmark = pytest.mark.unit


# =============================================================================
# LLMProviderType
# =============================================================================


class TestLLMProviderType:
    def test_provider_values_present(self):
        expected = {
            "anthropic", "openai", "github_models", "google_ai_studio",
            "azure_openai", "groq", "ollama", "openrouter", "z_ai", "minimax", "custom",
        }
        actual = {p.value for p in LLMProviderType}
        assert expected.issubset(actual)

    def test_is_openai_compatible(self):
        assert LLMProviderType.OPENAI.is_openai_compatible is True
        assert LLMProviderType.ANTHROPIC.is_openai_compatible is False
        assert LLMProviderType.MINIMAX.is_openai_compatible is False


# =============================================================================
# ModelRole
# =============================================================================


class TestModelRole:
    def test_roles(self):
        assert ModelRole.LIGHT.value == "light"
        assert ModelRole.STANDARD.value == "standard"
        assert ModelRole.HEAVY.value == "heavy"
        assert ModelRole.EMBEDDING.value == "embedding"


# =============================================================================
# PROVIDER_BASE_URLS
# =============================================================================


class TestProviderBaseUrls:
    def test_anthropic_not_in_default_urls(self):
        # Anthropic uses its own SDK
        assert LLMProviderType.ANTHROPIC not in PROVIDER_BASE_URLS

    def test_openai_in_default_urls(self):
        assert "https://api.openai.com/v1" == PROVIDER_BASE_URLS[LLMProviderType.OPENAI]


# =============================================================================
# ModelParams
# =============================================================================


class TestModelParams:
    def test_minimal(self):
        p = ModelParams()
        assert p.temperature is None
        assert p.max_tokens is None
        assert p.top_p is None
        assert p.frequency_penalty is None
        assert p.presence_penalty is None

    def test_with_values(self):
        p = ModelParams(temperature=0.7, max_tokens=1024, top_p=0.9)
        assert p.temperature == 0.7
        assert p.max_tokens == 1024
        assert p.top_p == 0.9

    def test_to_dict_excludes_none(self):
        p = ModelParams(temperature=0.5, max_tokens=100)
        d = p.to_dict()
        assert "temperature" in d
        assert "max_tokens" in d
        assert "top_p" not in d
        assert "frequency_penalty" not in d
        assert "presence_penalty" not in d

    def test_to_dict_empty(self):
        p = ModelParams()
        assert p.to_dict() == {}


# =============================================================================
# LLMProviderConfig
# =============================================================================


class TestLLMProviderConfig:
    def test_minimal(self):
        c = LLMProviderConfig(
            id="gpt-mini", name="GPT-4o mini", provider=LLMProviderType.OPENAI, model="gpt-4o-mini"
        )
        assert c.id == "gpt-mini"
        assert c.provider == LLMProviderType.OPENAI
        assert c.model == "gpt-4o-mini"
        assert c.api_key == ""
        assert c.base_url is None
        assert c.model_params == {}
        assert c.role == ModelRole.STANDARD
        assert c.status == "unconfigured"
        assert c.latency_ms is None
        assert c.is_default is False

    def test_full(self):
        c = LLMProviderConfig(
            id="claude-haiku-heavy",
            name="Claude Haiku",
            provider=LLMProviderType.ANTHROPIC,
            model="claude-haiku-4-5",
            api_key="sk-test",
            base_url=None,
            model_params={"temperature": 0.7, "max_tokens": 4096},
            role=ModelRole.HEAVY,
            status="active",
            latency_ms=300,
            is_default=True,
        )
        assert c.role == ModelRole.HEAVY
        assert c.is_default is True
        assert c.latency_ms == 300

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            LLMProviderConfig()  # type: ignore[call-arg]

    def test_id_required(self):
        with pytest.raises(ValidationError):
            LLMProviderConfig(
                name="x", provider=LLMProviderType.OPENAI, model="gpt-4o"
            )  # type: ignore[call-arg]

    def test_name_required(self):
        with pytest.raises(ValidationError):
            LLMProviderConfig(
                id="x", provider=LLMProviderType.OPENAI, model="gpt-4o"
            )  # type: ignore[call-arg]

    def test_model_required(self):
        with pytest.raises(ValidationError):
            LLMProviderConfig(
                id="x", name="y", provider=LLMProviderType.OPENAI
            )  # type: ignore[call-arg]

    def test_provider_required(self):
        with pytest.raises(ValidationError):
            LLMProviderConfig(id="x", name="y", model="z")  # type: ignore[call-arg]

    def test_invalid_provider(self):
        with pytest.raises(ValidationError):
            LLMProviderConfig(
                id="x", name="y", provider="bogus", model="z"  # type: ignore[arg-type]
            )

    def test_invalid_role(self):
        with pytest.raises(ValidationError):
            LLMProviderConfig(
                id="x", name="y", provider=LLMProviderType.OPENAI,
                model="z", role="bogus"  # type: ignore[arg-type]
            )


# =============================================================================
# LLMNodeAssignment
# =============================================================================


class TestLLMNodeAssignment:
    def test_minimal(self):
        a = LLMNodeAssignment(node_name="narrator", provider_id="gpt-mini")
        assert a.node_name == "narrator"
        assert a.provider_id == "gpt-mini"
        assert a.param_overrides == {}
        assert a.notes is None
        assert a.provider_name is None
        assert a.model is None
        assert a.provider is None
        assert a.role is None

    def test_with_overrides(self):
        a = LLMNodeAssignment(
            node_name="canonkeeper",
            provider_id="claude-haiku-heavy",
            param_overrides={"temperature": 0.0},
            notes="deterministic",
        )
        assert a.notes == "deterministic"
        assert a.param_overrides == {"temperature": 0.0}

    def test_with_join_data(self):
        a = LLMNodeAssignment(
            node_name="narrator",
            provider_id="x",
            provider_name="GPT-4o",
            model="gpt-4o",
            provider=LLMProviderType.OPENAI,
            role=ModelRole.HEAVY,
        )
        assert a.provider_name == "GPT-4o"
        assert a.model == "gpt-4o"
        assert a.provider == LLMProviderType.OPENAI
        assert a.role == ModelRole.HEAVY

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            LLMNodeAssignment()  # type: ignore[call-arg]


# =============================================================================
# EffectiveLLMConfig
# =============================================================================


class TestEffectiveLLMConfig:
    def test_minimal(self):
        c = EffectiveLLMConfig(
            id="x", name="y", provider=LLMProviderType.OPENAI, model="gpt-4o"
        )
        assert c.api_key == ""
        assert c.base_url is None
        assert c.role == ModelRole.STANDARD
        assert c.effective_params == {}
        assert c.node_name is None

    def test_full(self):
        c = EffectiveLLMConfig(
            id="x",
            name="y",
            provider=LLMProviderType.ANTHROPIC,
            model="claude-haiku-4-5",
            api_key="sk-test",
            base_url="https://custom.api",
            role=ModelRole.HEAVY,
            effective_params={"temperature": 0.7, "max_tokens": 4096},
            node_name="narrator",
        )
        assert c.api_key == "sk-test"
        assert c.effective_params["max_tokens"] == 4096
        assert c.node_name == "narrator"

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            EffectiveLLMConfig()  # type: ignore[call-arg]


# =============================================================================
# LLMTaskAttemptResponse
# =============================================================================


class TestLLMTaskAttemptResponse:
    def test_minimal(self):
        r = LLMTaskAttemptResponse(stage="narrate", attempt_no=1, status="ok")
        assert r.id is None
        assert r.job_id is None
        assert r.source_id is None
        assert r.batch_id is None
        assert r.provider_id is None
        assert r.model is None
        assert r.role is None
        assert r.max_attempts == 1
        assert r.retryable is False

    def test_full(self):
        r = LLMTaskAttemptResponse(
            id="att-1",
            job_id="job-1",
            source_id="src-1",
            stage="canonkeeper",
            batch_id="batch-1",
            provider_id="claude-haiku",
            model="claude-haiku-4-5",
            role="heavy",
            attempt_no=2,
            max_attempts=3,
            status="retrying",
            retryable=True,
        )
        assert r.attempt_no == 2
        assert r.max_attempts == 3
        assert r.retryable is True
        assert r.status == "retrying"

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            LLMTaskAttemptResponse()  # type: ignore[call-arg]
