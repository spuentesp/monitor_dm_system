"""
Smoke + helper tests for ``monitor init`` and ``monitor doctor``.

Tests fall into three buckets:

1. Sub-app registration — `monitor init --help` and `monitor doctor --help`
   must succeed without network access.
2. ``init`` dry-run — emits a clean JSON plan without touching infra.
3. Helper functions in isolation — ``_write_env_token``,
   ``_resolve_existing_key``, ``_ask_for_key`` are exercised with mocked
   questionary so no real stdin is needed.

Live end-to-end tests (real Postgres + Ollama + wizard) live in
``tests/e2e/test_e2e_init_wizard.py`` and are gated by ``RUN_E2E=1``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from monitor_cli.commands.init import (
    PROVIDER_DEFAULTS,
    _ask_for_key,
    _resolve_existing_key,
    _write_env_token,
)
from monitor_cli.main import app

runner = CliRunner()


# ANSI codes from Rich can break substring assertions after Rich wraps long
# option descriptions across lines. Strip them before assertion.
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _strip(s: str) -> str:
    return _ANSI.sub("", s)


# ── registration ─────────────────────────────────────────────────────────────


def test_init_subapp_help():
    result = runner.invoke(app, ["init", "--help"])
    assert result.exit_code == 0, result.output
    out = _strip(result.output)
    assert "--provider" in out
    assert "--dry-run" in out
    assert "--yes" in out


def test_doctor_subapp_help():
    result = runner.invoke(app, ["doctor", "--help"])
    assert result.exit_code == 0, result.output
    out = _strip(result.output)
    assert "--fix" in out
    assert "--json" in out
    assert "--force" in out
    assert "--yes" in out


def test_init_lists_every_supported_provider():
    """Each provider in PROVIDER_DEFAULTS must appear in ``init --help``."""
    result = runner.invoke(app, ["init", "--help"])
    out = _strip(result.output)
    for provider_id in PROVIDER_DEFAULTS:
        assert provider_id in out, f"{provider_id} missing from `monitor init --help`"


def test_init_dry_run_emits_clean_json():
    """Dry-run should never touch infra; only print the plan."""
    result = runner.invoke(app, ["init", "--dry-run", "--provider", "ollama", "--json"])
    assert result.exit_code == 0, result.output

    # console.print_json may emit a leading/trailing newline around the JSON
    # block; tolerate either form by extracting the JSON substring.
    text = result.output.strip()
    start = text.find("{")
    end = text.rfind("}")
    assert start != -1 and end != -1 and end > start, f"no JSON object in output: {text!r}"
    parsed = json.loads(text[start : end + 1])
    assert "would_run" in parsed
    assert "would_write" in parsed
    assert any("preflight" in step for step in parsed["would_run"])


# ── _write_env_token ─────────────────────────────────────────────────────────


def test_write_env_token_creates_with_mode_0600(tmp_path: Path):
    p = tmp_path / ".env.tokens"
    _write_env_token("FOO", "secret", path=p)
    assert p.exists()
    assert (p.stat().st_mode & 0o777) == 0o600, f"new file should be 0o600; got {oct(p.stat().st_mode & 0o777)}"
    assert "FOO=secret" in p.read_text()


def test_write_env_token_replaces_existing_line(tmp_path: Path):
    p = tmp_path / ".env.tokens"
    p.write_text("FOO=first\nBAR=keep\n", encoding="utf-8")
    _write_env_token("FOO", "second", path=p)
    text = p.read_text()
    assert "FOO=second" in text
    assert "FOO=first" not in text
    assert "BAR=keep" in text
    assert text.count("FOO=") == 1


def test_write_env_token_appends_new_line(tmp_path: Path):
    p = tmp_path / ".env.tokens"
    p.write_text("FOO=secret\n", encoding="utf-8")
    _write_env_token("BAR", "another", path=p)
    text = p.read_text()
    assert "FOO=secret" in text
    assert "BAR=another" in text


def test_write_env_token_skips_empty_value(tmp_path: Path):
    """An empty / whitespace-only value must not be persisted."""
    p = tmp_path / ".env.tokens"
    _write_env_token("FOO", "", path=p)
    _write_env_token("FOO", "   ", path=p)
    assert not p.exists(), "empty value should not create the file"


def test_write_env_token_preserves_mode_across_replaces(tmp_path: Path):
    p = tmp_path / ".env.tokens"
    _write_env_token("FOO", "first", path=p)
    _write_env_token("FOO", "second", path=p)
    assert (p.stat().st_mode & 0o777) == 0o600


# ── _resolve_existing_key ────────────────────────────────────────────────────


def test_resolve_existing_key_reads_env_tokens(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tokens = tmp_path / ".env.tokens"
    tokens.write_text("ANTHROPIC_API_KEY=sk-from-tokens\n", encoding="utf-8")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert _resolve_existing_key("ANTHROPIC_API_KEY") == "sk-from-tokens"


def test_resolve_existing_key_falls_back_to_process_env(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")
    assert _resolve_existing_key("ANTHROPIC_API_KEY") == "sk-from-env"


def test_resolve_existing_key_returns_empty_when_unset(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert _resolve_existing_key("ANTHROPIC_API_KEY") == ""


def test_resolve_existing_key_prefers_env_tokens_over_process_env(tmp_path: Path, monkeypatch):
    """``.env.tokens`` is the canonical source; process env is a fallback."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.tokens").write_text("X=tokens\n", encoding="utf-8")
    monkeypatch.setenv("X", "process")
    assert _resolve_existing_key("X") == "tokens"


# ── _ask_for_key ─────────────────────────────────────────────────────────────


def test_ask_for_key_uses_prefill_without_prompting(monkeypatch):
    """``prefill`` should bypass questionary.password entirely."""

    # If questionary.password is invoked, the test fails. Using a sentinel
    # that raises if called.
    def _explode(*_args, **_kwargs):
        raise AssertionError("questionary.password should not be called when prefill is set")

    monkeypatch.setattr("monitor_cli.commands.init.questionary.password", _explode)
    assert _ask_for_key("FOO", prefill="already-set") == "already-set"


def test_ask_for_key_strips_prefill_whitespace():
    assert _ask_for_key("FOO", prefill="  padded  ") == "padded"


def test_ask_for_key_empty_prefill_falls_through_to_prompt(monkeypatch):
    """An empty prefill should NOT bypass the prompt — caller can then handle."""
    called = {"n": 0}

    class _StubQuestion:
        def ask(self):
            called["n"] += 1
            return "  typed-in  "

    def fake_password(*_args, **_kwargs):
        return _StubQuestion()

    monkeypatch.setattr("monitor_cli.commands.init.questionary.password", fake_password)
    assert _ask_for_key("FOO", prefill="   ") == "typed-in"
    assert called["n"] == 1


# ── wizard: --yes with BYOK + pre-existing key (non-interactive path) ───────


def test_init_yes_anthropic_uses_env_token_key_without_prompting(monkeypatch, tmp_path: Path):
    """``monitor init --provider anthropic --yes`` must not prompt when
    ANTHROPIC_API_KEY is already in .env.tokens. Pre-flight is mocked to
    short-circuit on infra health; PG seed is mocked so no real DB needed.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env.tokens").write_text("ANTHROPIC_API_KEY=sk-prefilled\n", encoding="utf-8")

    # Pre-flight health report (overall=healthy so wizard proceeds)
    fake_health = {"overall_status": "healthy", "components": {}}

    # Schema bootstrap should be a no-op for the test
    async def fake_bootstrap() -> None:
        return None

    # seed_provider should record what it received but not touch PG
    seed_calls: list[dict] = []

    async def fake_seed_provider(**kwargs):
        seed_calls.append(kwargs)
        return None

    # questionary.password should NEVER be called in non-interactive mode
    def _explode(*_args, **_kwargs):
        raise AssertionError("questionary.password should not be called when --yes + env-var prefill is set")

    monkeypatch.setattr("monitor_cli.commands.init.questionary.password", _explode)
    monkeypatch.setattr("monitor_cli.commands.init._bootstrap_schemas", fake_bootstrap)
    monkeypatch.setattr("monitor_cli.commands.init.seed_provider", fake_seed_provider)

    async def fake_check_all_services(*, force: bool = False):
        return fake_health

    monkeypatch.setattr("monitor_cli.commands.init.check_all_services", fake_check_all_services)

    result = runner.invoke(app, ["init", "--provider", "anthropic", "--yes", "--json"])
    assert result.exit_code == 0, result.output

    # seed_provider was called exactly once for anthropic-default.
    assert len(seed_calls) == 1
    assert seed_calls[0]["id"] == "anthropic-default"
    assert seed_calls[0]["api_key"] == "sk-prefilled"
    assert seed_calls[0]["role"] == "heavy"
    assert seed_calls[0]["is_default"] is True


def test_init_yes_anthropic_without_env_token_fails_cleanly(monkeypatch, tmp_path: Path):
    """Without --yes the key prompt is fine; with --yes and no key, the wizard
    must print a clear actionable error and exit nonzero."""
    monkeypatch.chdir(tmp_path)
    # No .env.tokens and no ANTHROPIC_API_KEY in env
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    fake_health = {"overall_status": "healthy", "components": {}}

    async def fake_bootstrap() -> None:
        return None

    async def fake_check_all_services(*, force: bool = False):
        return fake_health

    monkeypatch.setattr("monitor_cli.commands.init._bootstrap_schemas", fake_bootstrap)
    monkeypatch.setattr("monitor_cli.commands.init.check_all_services", fake_check_all_services)

    # The password prompt must NEVER be invoked.
    def _explode(*_args, **_kwargs):
        raise AssertionError("non-interactive mode must not prompt for the API key")

    monkeypatch.setattr("monitor_cli.commands.init.questionary.password", _explode)

    result = runner.invoke(app, ["init", "--provider", "anthropic", "--yes"])
    assert result.exit_code != 0, result.output
    out = _strip(result.output)
    assert "API key required" in out
    assert "ANTHROPIC_API_KEY" in out
