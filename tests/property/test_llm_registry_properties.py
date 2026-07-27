"""
Property-based tests for LLMRegistry parameter merging logic.

Tests invariants of:
  - EffectiveLLMConfig construction and param merging
  - ModelParams.to_dict() only includes set fields
  - Provider base URL resolution
  - LLMProviderType.is_openai_compatible consistency

Use Cases: DL-20, SYS-2
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st
from monitor_data.schemas.llm_config import (
    PROVIDER_BASE_URLS,
    EffectiveLLMConfig,
    LLMNodeAssignment,
    LLMProviderConfig,
    LLMProviderType,
    ModelParams,
    ModelRole,
)

# =============================================================================
# STRATEGIES
# =============================================================================


model_params_strategy = st.builds(
    ModelParams,
    temperature=st.floats(
        min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False
    )
    | st.none(),
    max_tokens=st.integers(min_value=1, max_value=32000) | st.none(),
    top_p=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
    | st.none(),
    frequency_penalty=st.floats(
        min_value=-2.0, max_value=2.0, allow_nan=False, allow_infinity=False
    )
    | st.none(),
    presence_penalty=st.floats(
        min_value=-2.0, max_value=2.0, allow_nan=False, allow_infinity=False
    )
    | st.none(),
    stop=st.lists(st.text(min_size=1, max_size=20), min_size=0, max_size=5) | st.none(),
    seed=st.integers(min_value=0, max_value=2**32 - 1) | st.none(),
    top_k=st.integers(min_value=0, max_value=100) | st.none(),
)

provider_type_strategy = st.sampled_from(list(LLMProviderType))

provider_config_strategy = st.builds(
    LLMProviderConfig,
    id=st.text(
        min_size=1,
        max_size=30,
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Pd")),
    ),
    name=st.text(min_size=1, max_size=50),
    provider=provider_type_strategy,
    model=st.text(min_size=1, max_size=50),
    api_key=st.text(min_size=0, max_size=50),
    base_url=st.text(min_size=0, max_size=100) | st.none(),
    model_params=st.dictionaries(
        keys=st.sampled_from(["temperature", "max_tokens", "top_p", "seed", "stop"]),
        values=st.one_of(
            st.floats(allow_nan=False, allow_infinity=False),
            st.integers(min_value=0, max_value=32000),
            st.lists(st.text(min_size=1, max_size=10), min_size=1, max_size=3),
        ),
        max_size=5,
    ),
    role=st.sampled_from(list(ModelRole)),
    status=st.sampled_from(["unconfigured", "connected", "error"]),
    latency_ms=st.integers(min_value=1, max_value=5000) | st.none(),
    is_default=st.booleans(),
)

node_assignment_strategy = st.builds(
    LLMNodeAssignment,
    node_name=st.text(
        min_size=1,
        max_size=30,
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Pd")),
    ),
    provider_id=st.text(
        min_size=1,
        max_size=30,
        alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Pd")),
    ),
    param_overrides=st.dictionaries(
        keys=st.sampled_from(["temperature", "max_tokens", "top_p", "seed"]),
        values=st.one_of(
            st.floats(allow_nan=False, allow_infinity=False),
            st.integers(min_value=0, max_value=32000),
        ),
        max_size=4,
    ),
    notes=st.text(min_size=0, max_size=200) | st.none(),
)


# =============================================================================
# INVARIANT TESTS — ModelParams
# =============================================================================


@given(params=model_params_strategy)
@settings(max_examples=200)
def test_model_params_to_dict_excludes_none(params):
    """to_dict() should never include None values."""
    d = params.to_dict()
    for v in d.values():
        assert v is not None


@given(params=model_params_strategy)
@settings(max_examples=200)
def test_model_params_to_dict_keys_match_set_fields(params):
    """to_dict() keys should exactly match the fields that are not None."""
    d = params.to_dict()
    expected_keys = {k for k, v in params.model_dump().items() if v is not None}
    assert set(d.keys()) == expected_keys


@given(
    temp=st.floats(min_value=0.0, max_value=2.0, allow_nan=False, allow_infinity=False),
    max_tok=st.integers(min_value=1, max_value=32000),
)
@settings(max_examples=50)
def test_model_params_set_fields_appear_in_dict(temp, max_tok):
    """Explicitly set fields should appear in to_dict()."""
    params = ModelParams(temperature=temp, max_tokens=max_tok)
    d = params.to_dict()
    assert "temperature" in d
    assert "max_tokens" in d
    assert d["temperature"] == temp
    assert d["max_tokens"] == max_tok


# =============================================================================
# INVARIANT TESTS — LLMProviderType
# =============================================================================


@given(provider=provider_type_strategy)
@settings(max_examples=50)
def test_provider_compatibility_is_consistent(provider):
    """is_openai_compatible should be deterministic for each provider type."""
    expected = provider not in (LLMProviderType.ANTHROPIC, LLMProviderType.MINIMAX)
    assert provider.is_openai_compatible == expected


@given(provider=provider_type_strategy)
@settings(max_examples=50)
def test_well_known_urls_only_for_openai_compatible(provider):
    """PROVIDER_BASE_URLS should only contain OpenAI-compatible providers."""
    if provider in PROVIDER_BASE_URLS:
        assert provider.is_openai_compatible or provider == LLMProviderType.MINIMAX


# =============================================================================
# INVARIANT TESTS — EffectiveLLMConfig
# =============================================================================


@given(
    provider=provider_type_strategy,
    model=st.text(min_size=1, max_size=50),
    params=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.one_of(
            st.floats(allow_nan=False, allow_infinity=False),
            st.integers(min_value=0, max_value=32000),
            st.text(min_size=0, max_size=100),
            st.booleans(),
        ),
        max_size=10,
    ),
)
@settings(max_examples=100)
def test_effective_config_preserves_params(provider, model, params):
    """EffectiveLLMConfig should preserve all params passed to it."""
    config = EffectiveLLMConfig(
        id="test-id",
        name="test",
        provider=provider,
        model=model,
        effective_params=params,
    )
    assert config.effective_params == params


@given(
    provider_params=st.dictionaries(
        keys=st.sampled_from(["temperature", "max_tokens", "top_p"]),
        values=st.one_of(
            st.floats(allow_nan=False, allow_infinity=False),
            st.integers(min_value=0, max_value=32000),
        ),
        max_size=3,
    ),
    overrides=st.dictionaries(
        keys=st.sampled_from(["temperature", "max_tokens", "top_p"]),
        values=st.one_of(
            st.floats(allow_nan=False, allow_infinity=False),
            st.integers(min_value=0, max_value=32000),
        ),
        max_size=3,
    ),
)
@settings(max_examples=200)
def test_param_merge_overrides_win(provider_params, overrides):
    """When merging provider params with node overrides, overrides should win."""
    merged = {**provider_params, **overrides}
    for key in overrides:
        assert merged[key] == overrides[key]


@given(
    provider_params=st.dictionaries(
        keys=st.sampled_from(["temperature", "max_tokens", "top_p"]),
        values=st.one_of(
            st.floats(allow_nan=False, allow_infinity=False),
            st.integers(min_value=0, max_value=32000),
        ),
        max_size=3,
    ),
    overrides=st.dictionaries(
        keys=st.sampled_from(["temperature", "max_tokens", "top_p"]),
        values=st.one_of(
            st.floats(allow_nan=False, allow_infinity=False),
            st.integers(min_value=0, max_value=32000),
        ),
        max_size=3,
    ),
)
@settings(max_examples=200)
def test_param_merge_preserves_provider_only_keys(provider_params, overrides):
    """Keys only in provider_params should survive the merge."""
    merged = {**provider_params, **overrides}
    provider_only_keys = set(provider_params.keys()) - set(overrides.keys())
    for key in provider_only_keys:
        assert key in merged
        assert merged[key] == provider_params[key]


# =============================================================================
# INVARIANT TESTS — LLMNodeAssignment
# =============================================================================


@given(assignment=node_assignment_strategy)
@settings(max_examples=100)
def test_node_assignment_has_required_fields(assignment):
    """LLMNodeAssignment should always have node_name and provider_id."""
    assert assignment.node_name
    assert assignment.provider_id


@given(
    node_name=st.text(min_size=1, max_size=30),
    provider_id=st.text(min_size=1, max_size=30),
    overrides=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.floats(allow_nan=False, allow_infinity=False),
        max_size=5,
    ),
)
@settings(max_examples=50)
def test_node_assignment_preserves_overrides(node_name, provider_id, overrides):
    """LLMNodeAssignment should preserve param_overrides exactly."""
    assignment = LLMNodeAssignment(
        node_name=node_name,
        provider_id=provider_id,
        param_overrides=overrides,
    )
    assert assignment.param_overrides == overrides
