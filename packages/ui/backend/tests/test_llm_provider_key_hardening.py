"""UX-4: provider keys stay encrypted and admin-only outside local mode.

Contract:

- ``/api/llm/*`` is 403 for non-admins (already covered elsewhere; pinned
  here for the providers surface).
- With ``MONITOR_AUTH_DISABLED=false`` and
  ``MONITOR_PROVIDER_KEY_ENCRYPTION_KEY`` unset, saving ANY provider API
  key (create, update, duplicate) is refused with a clear 503 that names
  the env var — and nothing is persisted.
- With the encryption key set, saves succeed, the stored value is
  ciphertext, and no response body ever contains the plaintext key
  (last-4 only, via ``_mask_key``).
- Local mode (``MONITOR_AUTH_DISABLED=true``) keeps plaintext saves; the
  one-time startup warning already covers its visibility.

Hermetic: FakePostgres for auth + an AsyncMock provider store; no real DB.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from fake_postgres import FakePostgres
from unittest.mock import AsyncMock

from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings

PLAIN_KEY = "sk-live-super-secret-key-ABCDEF123456"


@pytest.fixture
def fake_db() -> FakePostgres:
    return FakePostgres()


@pytest.fixture
def provider_pg() -> AsyncMock:
    pg = AsyncMock()
    pg.providers_list.return_value = []
    pg.provider_get.return_value = None
    return pg


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, fake_db: FakePostgres, provider_pg: AsyncMock):
    monkeypatch.setenv("MONITOR_AUTH_DISABLED", "false")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.delenv("MONITOR_PROVIDER_KEY_ENCRYPTION_KEY", raising=False)
    import monitor_ui.auth as auth_mod

    monkeypatch.setattr(auth_mod, "_signup_limiter", None)
    monkeypatch.setattr(auth_mod, "_login_limiter", None)
    get_settings.cache_clear()

    from monitor_ui.main import app
    import monitor_ui.routers.llm_mgmt as llm

    async def _db() -> FakePostgres:
        return fake_db

    app.dependency_overrides[get_postgres] = _db
    monkeypatch.setattr(llm, "get_postgres_client", lambda: provider_pg)
    monkeypatch.setattr(llm, "_seeded", True)  # skip env auto-seed per test
    c = TestClient(app)
    yield c
    app.dependency_overrides.pop(get_postgres, None)
    get_settings.cache_clear()


def _signup(c: TestClient, email: str, username: str) -> dict[str, Any]:
    if not c.cookies.get("monitor_csrf"):
        c.get("/api/auth/config")
    r = c.post(
        "/api/auth/signup",
        json={"email": email, "username": username, "password": "correct horse battery"},
        headers={"X-CSRF-Token": c.cookies.get("monitor_csrf", "")},
    )
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def _signup_admin(client: TestClient, fake_db: FakePostgres) -> dict[str, Any]:
    user = _signup(client, "root@example.com", "root")
    fake_db.users[UUID(user["id"])]["is_admin"] = True
    return user


def _csrf(c: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": c.cookies.get("monitor_csrf", "")}


class TestProviderKeyEncryptionGate:
    def test_non_admin_forbidden_on_providers(self, client: TestClient, fake_db: FakePostgres) -> None:
        _signup(client, "bob@example.com", "bob")
        assert client.get("/api/llm/providers").status_code == 403
        assert (
            client.post(
                "/api/llm/providers",
                json={"name": "p", "provider": "openai", "model": "m", "api_key": PLAIN_KEY},
                headers=_csrf(client),
            ).status_code
            == 403
        )

    def test_add_provider_key_refused_without_encryption(
        self, client: TestClient, fake_db: FakePostgres, provider_pg: AsyncMock
    ) -> None:
        _signup_admin(client, fake_db)
        r = client.post(
            "/api/llm/providers",
            json={"name": "p", "provider": "openai", "model": "m", "api_key": PLAIN_KEY},
            headers=_csrf(client),
        )
        assert r.status_code == 503, r.text
        assert "MONITOR_PROVIDER_KEY_ENCRYPTION_KEY" in r.json()["detail"]
        provider_pg.provider_upsert.assert_not_awaited()
        assert PLAIN_KEY not in r.text

    def test_update_provider_key_refused_without_encryption(
        self, client: TestClient, fake_db: FakePostgres, provider_pg: AsyncMock
    ) -> None:
        _signup_admin(client, fake_db)
        provider_pg.provider_get.return_value = {
            "id": "p-1",
            "name": "p",
            "provider": "openai",
            "model": "m",
            "api_key": "",
            "role": "standard",
        }
        r = client.put(
            "/api/llm/providers/p-1",
            json={"api_key": PLAIN_KEY},
            headers=_csrf(client),
        )
        assert r.status_code == 503, r.text
        assert "MONITOR_PROVIDER_KEY_ENCRYPTION_KEY" in r.json()["detail"]
        provider_pg.provider_upsert.assert_not_awaited()

    def test_duplicate_provider_key_refused_without_encryption(
        self, client: TestClient, fake_db: FakePostgres, provider_pg: AsyncMock
    ) -> None:
        _signup_admin(client, fake_db)
        provider_pg.provider_get.return_value = {
            "id": "p-1",
            "name": "p",
            "provider": "openai",
            "model": "m",
            "api_key": PLAIN_KEY,
            "role": "standard",
        }
        r = client.post("/api/llm/providers/p-1/duplicate", json={"name": "copy"}, headers=_csrf(client))
        assert r.status_code == 503, r.text
        provider_pg.provider_upsert.assert_not_awaited()

    def test_keyless_save_allowed_without_encryption(
        self, client: TestClient, fake_db: FakePostgres, provider_pg: AsyncMock
    ) -> None:
        _signup_admin(client, fake_db)
        r = client.post(
            "/api/llm/providers",
            json={"name": "local-ollama", "provider": "ollama", "model": "llama3"},
            headers=_csrf(client),
        )
        assert r.status_code == 201, r.text
        provider_pg.provider_upsert.assert_awaited()

    def test_add_provider_key_allowed_with_encryption_and_never_echoed(
        self, client: TestClient, fake_db: FakePostgres, provider_pg: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MONITOR_PROVIDER_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode())
        _signup_admin(client, fake_db)
        r = client.post(
            "/api/llm/providers",
            json={"name": "p", "provider": "openai", "model": "m", "api_key": PLAIN_KEY},
            headers=_csrf(client),
        )
        assert r.status_code == 201, r.text
        provider_pg.provider_upsert.assert_awaited()
        # The router forwards the key; provider_upsert (data-layer) encrypts
        # it on write — covered by test_db/test_postgres_tenancy.py.
        assert provider_pg.provider_upsert.await_args.args[0]["api_key"]
        assert PLAIN_KEY not in r.text
        masked = r.json()["api_key_masked"]
        assert masked is not None and masked.endswith(PLAIN_KEY[-4:])
        assert PLAIN_KEY[:-4] not in masked

    def test_local_mode_still_saves_plaintext_keys(
        self, provider_pg: AsyncMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Local mode keeps the plaintext path (startup warning covers it)."""
        monkeypatch.setenv("MONITOR_AUTH_DISABLED", "true")
        monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
        monkeypatch.delenv("MONITOR_PROVIDER_KEY_ENCRYPTION_KEY", raising=False)
        get_settings.cache_clear()
        from monitor_ui.main import app
        import monitor_ui.routers.llm_mgmt as llm

        async def _db() -> FakePostgres:
            return FakePostgres()

        app.dependency_overrides[get_postgres] = _db
        monkeypatch.setattr(llm, "get_postgres_client", lambda: provider_pg)
        monkeypatch.setattr(llm, "_seeded", True)
        try:
            c = TestClient(app)
            r = c.post(
                "/api/llm/providers",
                json={"name": "p", "provider": "openai", "model": "m", "api_key": PLAIN_KEY},
            )
            assert r.status_code == 201, r.text
            provider_pg.provider_upsert.assert_awaited()
            stored = provider_pg.provider_upsert.await_args.args[0]["api_key"]
            assert stored == PLAIN_KEY  # local mode: plaintext allowed
        finally:
            app.dependency_overrides.pop(get_postgres, None)
            get_settings.cache_clear()


class TestQuotaMessageIsReadable:
    def test_429_detail_mentions_admin_and_reset(self) -> None:
        """The app-level 429 handler returns user_message: readable, with the
        reset time and a pointer to the admin (UX-4 / UX-5 messaging)."""
        from monitor_data.usage import QuotaExceededError

        msg = QuotaExceededError("token", 1000).user_message
        assert "Daily token limit reached" in msg
        assert "00:00 UTC" in msg
        assert "admin" in msg.lower()
