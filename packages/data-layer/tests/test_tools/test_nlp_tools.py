"""Tests for nlp_tools backend dispatch: GLiNER with automatic spaCy fallback.

Hermetic: GLiNER client, spaCy backend and _call_sync are all patched; no
service or model is required.
"""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import MagicMock

import pytest

from monitor_data.schemas.perception import DetectedEntity, DetectedEntityType
from monitor_data.tools import nlp_tools


def _run(x):
    return asyncio.run(x) if inspect.isawaitable(x) else x


class _FakeGliner:
    def __init__(self, healthy: bool):
        self._healthy = healthy
        self.health_calls = 0

    async def health_check(self) -> bool:
        self.health_calls += 1
        return self._healthy


class _FakeSpacy:
    def __init__(self):
        self.calls: list[str] = []

    async def detect_entities(self, text: str):
        self.calls.append(text)
        return [
            DetectedEntity(
                text="Aldric",
                entity_type=DetectedEntityType.CHARACTER,
                start=0,
                end=6,
                confidence=0.9,
            )
        ]


@pytest.fixture(autouse=True)
def _patch_common(monkeypatch):
    monkeypatch.setattr(nlp_tools, "_call_sync", _run)
    monkeypatch.setattr(nlp_tools.settings, "nlp_enabled", True)
    monkeypatch.setattr(
        nlp_tools.settings,
        "entity_types",
        "npc,faction,location,item",
    )
    nlp_tools._reset_nlp_backend_cache()
    yield
    nlp_tools._reset_nlp_backend_cache()


@pytest.mark.unit
def test_spacy_configured_never_probes_gliner(monkeypatch):
    monkeypatch.setattr(nlp_tools.settings, "nlp_backend", "spacy")
    gliner = _FakeGliner(healthy=True)
    monkeypatch.setattr(nlp_tools, "get_gliner_client", lambda: gliner)

    active, fell_back = nlp_tools._active_backend()
    assert (active, fell_back) == ("spacy", False)
    assert gliner.health_calls == 0


@pytest.mark.unit
def test_gliner_healthy_is_used(monkeypatch):
    monkeypatch.setattr(nlp_tools.settings, "nlp_backend", "gliner")
    monkeypatch.setattr(nlp_tools, "get_gliner_client", lambda: _FakeGliner(healthy=True))
    assert nlp_tools._active_backend() == ("gliner", False)


@pytest.mark.unit
def test_gliner_down_falls_back_and_caches_probe(monkeypatch):
    monkeypatch.setattr(nlp_tools.settings, "nlp_backend", "gliner")
    gliner = _FakeGliner(healthy=False)
    monkeypatch.setattr(nlp_tools, "get_gliner_client", lambda: gliner)

    assert nlp_tools._active_backend() == ("spacy", True)
    assert nlp_tools._active_backend() == ("spacy", True)
    assert gliner.health_calls == 1  # probed once, then cached


@pytest.mark.unit
def test_extract_falls_back_to_spacy_and_reports_it(monkeypatch):
    monkeypatch.setattr(nlp_tools.settings, "nlp_backend", "gliner")
    monkeypatch.setattr(nlp_tools, "get_gliner_client", lambda: _FakeGliner(healthy=False))
    spacy = _FakeSpacy()
    monkeypatch.setattr(nlp_tools, "_get_spacy_backend", lambda: spacy)
    gliner_extract = MagicMock(side_effect=AssertionError("must not call gliner"))
    monkeypatch.setattr(nlp_tools, "extract_entities", gliner_extract)

    result = nlp_tools.nlp_extract_entities("Aldric enters the tavern.")
    assert result["backend"] == "spacy"
    assert result["fallback"] is True
    assert result["count"] == 1
    assert result["entities"][0]["text"] == "Aldric"
    assert result["entities"][0]["label"] == "character"
    gliner_extract.assert_not_called()


@pytest.mark.unit
def test_extract_uses_gliner_with_configured_labels(monkeypatch):
    monkeypatch.setattr(nlp_tools.settings, "nlp_backend", "gliner")
    monkeypatch.setattr(nlp_tools, "get_gliner_client", lambda: _FakeGliner(healthy=True))
    captured: dict = {}

    async def fake_extract(text, labels=None, threshold=0.5):
        captured.update(text=text, labels=labels, threshold=threshold)
        return []

    monkeypatch.setattr(nlp_tools, "extract_entities", fake_extract)

    result = nlp_tools.nlp_extract_entities("The duke of Westmarch", labels=None, threshold=0.7)
    assert result["backend"] == "gliner"
    assert result["fallback"] is False
    # labels default to ENTITY_TYPES from settings (domain labels)
    assert captured["labels"] == ["npc", "faction", "location", "item"]
    assert captured["threshold"] == 0.7


@pytest.mark.unit
def test_batch_reports_backend(monkeypatch):
    monkeypatch.setattr(nlp_tools.settings, "nlp_backend", "gliner")
    monkeypatch.setattr(nlp_tools, "get_gliner_client", lambda: _FakeGliner(healthy=False))
    monkeypatch.setattr(nlp_tools, "_get_spacy_backend", lambda: _FakeSpacy())

    result = nlp_tools.nlp_extract_entities_batch(["Aldric", "Bryn"])
    assert result["backend"] == "spacy"
    assert result["fallback"] is True
    assert result["count"] == 2
    assert all(len(r) == 1 for r in result["results"])


@pytest.mark.unit
def test_health_check_reports_fallback(monkeypatch):
    monkeypatch.setattr(nlp_tools.settings, "nlp_backend", "gliner")
    monkeypatch.setattr(nlp_tools, "get_gliner_client", lambda: _FakeGliner(healthy=False))
    monkeypatch.setattr(nlp_tools, "_get_spacy_backend", lambda: _FakeSpacy())

    result = nlp_tools.nlp_health_check()
    assert result == {
        "healthy": True,
        "backend": "spacy",
        "configured_backend": "gliner",
        "fallback": True,
    }


@pytest.mark.unit
def test_active_backend_tool_exposes_labels(monkeypatch):
    monkeypatch.setattr(nlp_tools.settings, "nlp_backend", "spacy")
    result = nlp_tools.nlp_active_backend()
    assert result["active_backend"] == "spacy"
    assert result["configured_backend"] == "spacy"
    assert result["fallback"] is False
    assert result["entity_types"] == ["npc", "faction", "location", "item"]
    assert result["nlp_enabled"] is True


@pytest.mark.unit
def test_extract_requires_nlp_enabled(monkeypatch):
    monkeypatch.setattr(nlp_tools.settings, "nlp_enabled", False)
    with pytest.raises(ValueError, match="NLP is not enabled"):
        nlp_tools.nlp_extract_entities("anything")
