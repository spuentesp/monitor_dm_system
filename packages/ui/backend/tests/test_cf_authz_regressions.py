"""Two-user authorization regressions for branch-added routes.

- G-6 character templates: per-owner, authenticated.
- CF-3 plot-thread PATCH: requires ownership of the story.
Hermetic: FakePostgres registry plus fake Mongo/Neo4j.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from fake_postgres import FakePostgres
from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app


class _Cursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs

    def sort(self, *a: Any, **k: Any) -> "_Cursor":
        return self

    def skip(self, n: int) -> "_Cursor":
        self.docs = self.docs[n:]
        return self

    def limit(self, n: int) -> "_Cursor":
        self.docs = self.docs[:n]
        return self

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.docs)


class _Coll:
    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = []

    def _match(self, d: dict[str, Any], q: dict[str, Any]) -> bool:
        return all(d.get(k) == v for k, v in q.items() if not isinstance(v, dict))

    def insert_one(self, doc: dict[str, Any]) -> None:
        self.docs.append(doc)

    def find_one(self, q: dict[str, Any], *a: Any, **k: Any) -> dict[str, Any] | None:
        return next((d for d in self.docs if self._match(d, q)), None)

    def find(self, q: dict[str, Any], *a: Any, **k: Any) -> _Cursor:
        return _Cursor([d for d in self.docs if self._match(d, q)])

    def count_documents(self, q: dict[str, Any]) -> int:
        return sum(1 for d in self.docs if self._match(d, q))

    def update_one(self, q: dict[str, Any], upd: dict[str, Any]) -> None:
        for d in self.docs:
            if self._match(d, q):
                d.update(upd.get("$set", {}))
                return

    def delete_one(self, q: dict[str, Any]) -> SimpleNamespace:
        for d in self.docs:
            if self._match(d, q):
                self.docs.remove(d)
                return SimpleNamespace(deleted_count=1)
        return SimpleNamespace(deleted_count=0)


@pytest.fixture
def fake_db() -> FakePostgres:
    return FakePostgres()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    get_settings.cache_clear()

    async def _db() -> FakePostgres:
        return fake_db

    app.dependency_overrides[get_postgres] = _db
    yield TestClient(app)
    app.dependency_overrides.pop(get_postgres, None)
    get_settings.cache_clear()


def _signup(c: TestClient, email: str, username: str) -> dict[str, Any]:
    r = c.post(
        "/api/auth/signup",
        json={"email": email, "username": username, "password": "correct horse battery"},
    )
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def _csrf(c: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": c.cookies.get("monitor_csrf", "")}


class TestCharacterTemplateOwnership:
    BASE = "/api/characters/templates"

    @pytest.fixture(autouse=True)
    def _coll(self, monkeypatch: pytest.MonkeyPatch) -> _Coll:
        coll = _Coll()
        monkeypatch.setattr(
            "monitor_data.tools.mongodb_tools.character_templates._collection", lambda: coll
        )
        return coll

    def test_unauthenticated_denied(self, client: TestClient) -> None:
        assert client.get(self.BASE).status_code == 401
        assert client.post(self.BASE, json={"name": "x"}).status_code in (401, 403)

    def test_templates_are_per_owner(self, client: TestClient, _coll: _Coll) -> None:
        _signup(client, "a@example.com", "alice")
        r = client.post(self.BASE, json={"name": "Varys"}, headers=_csrf(client))
        assert r.status_code == 201, r.text
        tid = r.json()["template_id"]
        assert _coll.docs[0]["owner_id"]  # stamped from the principal

        assert client.get(f"{self.BASE}/{tid}").status_code == 200
        assert client.get(self.BASE).json()["total"] == 1

        client_b = TestClient(app)
        _signup(client_b, "b@example.com", "bob")
        assert client_b.get(self.BASE).json()["total"] == 0
        assert client_b.get(f"{self.BASE}/{tid}").status_code == 404
        hb = _csrf(client_b)
        assert client_b.patch(f"{self.BASE}/{tid}", json={"name": "Pwned"}, headers=hb).status_code == 404
        assert client_b.delete(f"{self.BASE}/{tid}", headers=hb).status_code == 404
        # the owner's template is untouched
        assert _coll.docs[0]["name"] == "Varys"
        assert client.get(f"{self.BASE}/{tid}").status_code == 200


class _Neo4j:
    def __init__(self, story_universes: dict[str, str]) -> None:
        self.story_universes = story_universes

    def execute_read(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        uid = self.story_universes.get(params["id"]) if "Story" in query else None
        return [{"uid": uid}] if uid else []


class TestThreadPatchOwnership:
    def test_unauthenticated_denied(self, client: TestClient) -> None:
        r = client.patch(f"/api/stories/{uuid4()}/threads/{uuid4()}", json={"action": "resolve"})
        assert r.status_code in (401, 403)

    def test_foreign_story_thread_is_404_and_not_written(
        self, client: TestClient, fake_db: FakePostgres, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user_a = _signup(client, "a@example.com", "alice")
        world = str(uuid4())
        fake_db.worlds[world] = {
            "id": world,
            "owner_id": UUID(user_a["id"]),
            "multiverse_id": str(uuid4()),
            "label": "w",
            "active": True,
        }
        story_id = uuid4()
        monkeypatch.setattr(
            "monitor_data.db.neo4j.get_neo4j_client", lambda: _Neo4j({str(story_id): world})
        )
        writes: list[Any] = []
        monkeypatch.setattr(
            "monitor_data.tools.neo4j_tools.neo4j_get_plot_thread",
            lambda tid: SimpleNamespace(story_id=story_id),
        )
        monkeypatch.setattr(
            "monitor_data.tools.neo4j_tools.neo4j_update_plot_thread",
            lambda *a, **k: writes.append(a),
        )

        client_b = TestClient(app)
        _signup(client_b, "b@example.com", "bob")
        r = client_b.patch(
            f"/api/stories/{story_id}/threads/{uuid4()}",
            json={"action": "dismiss"},
            headers=_csrf(client_b),
        )
        assert r.status_code == 404
        assert writes == []
