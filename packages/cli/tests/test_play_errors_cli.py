"""Tests for `monitor play errors` (packages/cli/src/monitor_cli/commands/play_errors.py)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

from typer.testing import CliRunner

from monitor_cli.main import app

runner = CliRunner()


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def __iter__(self):
        return iter(self._docs)


class _FakeCollection:
    def __init__(self, docs):
        self._docs = docs
        self.last_query = None

    def find(self, query):
        self.last_query = query
        matched = [d for d in self._docs if all(d.get(k) == v for k, v in query.items())]
        return _FakeCursor(matched)


def _doc(**overrides):
    base = {
        "error_id": str(uuid4()),
        "occurred_at": datetime.now(UTC),
        "source": "scene_loop",
        "category": "memory_persist_not_found",
        "llm_error_class": None,
        "message": "Entity not found",
        "fatal": False,
        "story_id": str(uuid4()),
        "scene_id": str(uuid4()),
        "conversation_id": None,
    }
    base.update(overrides)
    return base


def test_play_errors_help():
    result = runner.invoke(app, ["play", "errors", "--help"])
    assert result.exit_code == 0
    assert "roleplay errors" in result.output.lower()


def test_play_errors_json_output(monkeypatch):
    docs = [_doc(message="first"), _doc(message="second", fatal=True)]
    fake_mongo = MagicMock()
    fake_mongo.get_collection.return_value = _FakeCollection(docs)
    monkeypatch.setattr(
        "monitor_data.db.mongodb.get_mongodb_client",
        lambda: fake_mongo,
    )

    result = runner.invoke(app, ["play", "errors", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(payload) == 2
    assert {row["message"] for row in payload} == {"first", "second"}


def test_play_errors_table_output_empty(monkeypatch):
    fake_mongo = MagicMock()
    fake_mongo.get_collection.return_value = _FakeCollection([])
    monkeypatch.setattr(
        "monitor_data.db.mongodb.get_mongodb_client",
        lambda: fake_mongo,
    )

    result = runner.invoke(app, ["play", "errors"])

    assert result.exit_code == 0
    assert "No roleplay errors match" in result.output


def test_play_errors_invalid_scene_id_rejected():
    result = runner.invoke(app, ["play", "errors", "--scene-id", "not-a-uuid"])
    assert result.exit_code == 1
    assert "Invalid scene UUID" in result.output


def test_play_errors_filters_by_category(monkeypatch):
    docs = [_doc(category="memory_persist_not_found"), _doc(category="gm_decision_failed")]
    fake_mongo = MagicMock()
    collection = _FakeCollection(docs)
    fake_mongo.get_collection.return_value = collection
    monkeypatch.setattr(
        "monitor_data.db.mongodb.get_mongodb_client",
        lambda: fake_mongo,
    )

    result = runner.invoke(app, ["play", "errors", "--category", "gm_decision_failed", "--json"])

    assert result.exit_code == 0, result.output
    assert collection.last_query == {"category": "gm_decision_failed"}
    payload = json.loads(result.output)
    assert len(payload) == 1
    assert payload[0]["category"] == "gm_decision_failed"
