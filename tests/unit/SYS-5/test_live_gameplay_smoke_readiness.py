"""SYS-5: the live gameplay smoke must not report success on a backend that
never narrated a turn.

Two properties are covered:

* ``live_readiness_problems`` names the missing precondition instead of
  letting the smoke run against a backend that cannot answer;
* the provider-error reply counts as a fallback, so a smoke run whose every
  GM turn was a provider error fails instead of reporting success.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT / "scripts" / "live_gameplay_smoke.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("live_gameplay_smoke", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


smoke = _load_mod()


def _provider(**overrides: Any) -> dict[str, Any]:
    provider = {
        "id": "anthropic-default",
        "name": "Anthropic (Claude)",
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "api_key_masked": "sk-a••••••••zzzz",
        "role": "standard",
        "is_default": True,
    }
    provider.update(overrides)
    return provider


def _fetcher(providers: list[dict[str, Any]], universes: list[dict[str, Any]]):
    def fetch(path: str) -> Any:
        if path == "/llm/providers":
            return providers
        if path == "/universes/universes":
            return universes
        raise AssertionError(f"unexpected path: {path}")

    return fetch


def test_ready_backend_reports_no_problems() -> None:
    providers = [
        _provider(),
        _provider(id="ollama-embed", role="embedding", is_default=True, api_key_masked=None),
    ]
    problems = smoke.live_readiness_problems(_fetcher(providers, [{"id": "u1"}]))
    assert problems == []


def test_missing_default_standard_provider_is_named() -> None:
    providers = [_provider(is_default=False)]
    problems = smoke.live_readiness_problems(_fetcher(providers, [{"id": "u1"}]))
    assert "no default STANDARD LLM provider is configured" in problems


def test_default_standard_provider_without_credentials_is_named() -> None:
    providers = [_provider(api_key_masked=None)]
    problems = smoke.live_readiness_problems(_fetcher(providers, [{"id": "u1"}]))
    assert "the default STANDARD LLM provider holds no credentials" in problems


def test_missing_embedding_provider_is_named() -> None:
    providers = [_provider()]
    problems = smoke.live_readiness_problems(_fetcher(providers, [{"id": "u1"}]))
    assert "no EMBEDDING LLM provider is configured" in problems


def test_missing_universe_is_named() -> None:
    providers = [
        _provider(),
        _provider(id="ollama-embed", role="embedding", is_default=True, api_key_masked=None),
    ]
    problems = smoke.live_readiness_problems(_fetcher(providers, []))
    assert "no universe is seeded" in problems


def test_provider_error_reply_counts_as_a_fallback() -> None:
    provider_error = "The GM's AI provider rejected the request (authentication issue)."
    assert any(marker in provider_error.lower() for marker in smoke.FALLBACK_MARKERS)


def test_provider_error_reply_is_not_missed_by_the_fallback_scan() -> None:
    """The marker list is matched case-insensitively, like the run does."""
    provider_error = "The GM's AI provider is misconfigured. Contact an administrator."
    lowered = provider_error.lower()
    matched = [marker for marker in smoke.FALLBACK_MARKERS if marker in lowered]
    assert matched, "a provider error must be recognised as a fallback"
