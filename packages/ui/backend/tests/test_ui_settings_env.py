"""SYS-6: UISettings reads the auth cookie flag the way env.example documents it."""

from __future__ import annotations

from pathlib import Path

import pytest
from monitor_ui.config import UISettings
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[4]


def _settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> UISettings:
    for name in ("AUTH_COOKIE_SECURE", "MONITOR_AUTH_DISABLED"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return UISettings(_env_file=None)


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_cookie_secure_means_automatic(monkeypatch: pytest.MonkeyPatch, blank: str) -> None:
    settings = _settings(monkeypatch, AUTH_COOKIE_SECURE=blank)

    assert settings.auth_cookie_secure is None
    assert settings.cookie_secure is True


def test_blank_cookie_secure_follows_auth_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(monkeypatch, AUTH_COOKIE_SECURE="", MONITOR_AUTH_DISABLED="true")

    assert settings.cookie_secure is False


@pytest.mark.parametrize(("raw", "expected"), [("true", True), ("false", False), ("1", True), ("0", False)])
def test_explicit_cookie_secure_is_kept(monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool) -> None:
    settings = _settings(monkeypatch, AUTH_COOKIE_SECURE=raw, MONITOR_AUTH_DISABLED="true")

    assert settings.auth_cookie_secure is expected
    assert settings.cookie_secure is expected


def test_nonsense_cookie_secure_is_still_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError):
        _settings(monkeypatch, AUTH_COOKIE_SECURE="maybe")


def test_env_example_loads_as_shipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """A copied env.example must not stop the backend at import."""
    for name in ("AUTH_COOKIE_SECURE", "MONITOR_AUTH_DISABLED"):
        monkeypatch.delenv(name, raising=False)

    settings = UISettings(_env_file=REPO_ROOT / "env.example")

    assert settings.auth_cookie_secure is None
