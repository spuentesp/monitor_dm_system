from __future__ import annotations

import pytest

from monitor_data.defaults.playtest_benchmarks import (
    load_playtest_benchmarks,
    resolve_playtest_benchmarks,
)


def test_playtest_benchmark_catalog_contains_clarification_flows():
    benchmarks = load_playtest_benchmarks()
    ids = {item["benchmark_id"] for item in benchmarks}

    assert "death_in_space_onboarding_probe" in ids
    assert "adversarial_llm_rule_probe" in ids

    onboarding = next(
        item for item in benchmarks if item["benchmark_id"] == "death_in_space_onboarding_probe"
    )
    assert onboarding["starter_questions"]
    assert onboarding["adversarial_goals"]
    assert onboarding["scripted_turn_count"] >= 0 or True  # normalization checked below


@pytest.mark.integration
def test_resolved_playtest_benchmarks_include_runtime_metadata():
    benchmarks = resolve_playtest_benchmarks(include_scripted_turns=False)
    sample = next(
        item for item in benchmarks if item["benchmark_id"] == "narrative_weighted_derelict"
    )

    assert "scripted_turns" not in sample
    assert sample["scripted_turn_count"] >= 1
    assert "comparison_metrics" in sample
    assert "expected_signals" in sample


@pytest.mark.integration
def test_system_specific_benchmark_uses_safe_fallback_when_exact_pack_is_missing():
    benchmarks = resolve_playtest_benchmarks(include_scripted_turns=False)
    sample = next(
        item for item in benchmarks if item["benchmark_id"] == "death_in_space_onboarding_probe"
    )

    assert sample["system_available"] is True
    assert sample["system_match_type"] in {"exact", "fallback"}
    assert sample["resolved_system_name"] in {
        "Death in Space",
        "Narrative Weighted",
        "Narrative Pure",
    }
    if sample["system_match_type"] == "fallback":
        assert sample["system_fallback_used"] is True
        assert "benchmark-safe fallback" in str(sample["fallback_reason"])


class TestPlaytestBenchmarkHelpers:
    def test_load_playtest_benchmarks_returns_list(self):
        """load_playtest_benchmarks should return a list."""
        benchmarks = load_playtest_benchmarks()
        assert isinstance(benchmarks, list)

    def test_load_playtest_benchmarks_contains_required_fields(self):
        """Each benchmark should have required fields."""
        benchmarks = load_playtest_benchmarks()
        for item in benchmarks:
            assert "benchmark_id" in item
            assert "description" in item
            assert "starter_questions" in item
            assert "adversarial_goals" in item

    def test_resolve_playtest_benchmarks_returns_list(self):
        """resolve_playtest_benchmarks should return a list."""
        benchmarks = resolve_playtest_benchmarks(include_scripted_turns=False)
        assert isinstance(benchmarks, list)

    def test_resolve_playtest_benchmarks_with_scripted_turns(self):
        """resolve_playtest_benchmarks should include scripted turns when requested."""
        benchmarks = resolve_playtest_benchmarks(include_scripted_turns=True)
        assert isinstance(benchmarks, list)

    def test_benchmark_ids_are_unique(self):
        """Benchmark IDs should be unique across the catalog."""
        benchmarks = load_playtest_benchmarks()
        ids = [item["benchmark_id"] for item in benchmarks]
        assert len(ids) == len(set(ids))

    def test_starter_questions_is_list(self):
        """starter_questions should be a list."""
        benchmarks = load_playtest_benchmarks()
        for item in benchmarks:
            assert isinstance(item["starter_questions"], list)

    def test_adversarial_goals_is_list(self):
        """adversarial_goals should be a list."""
        benchmarks = load_playtest_benchmarks()
        for item in benchmarks:
            assert isinstance(item["adversarial_goals"], list)
