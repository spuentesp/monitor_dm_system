"""Hermetic stages of scripts/live_tenancy_smoke.py against the FastAPI app.

Runs the smoke's Postgres-only stages — admin login, invite-only signup,
forgot-password enumeration, admin reset/revoke/ban — with the Postgres
dependency swapped for FakePostgres and ``TestClient`` injected as the
smoke's httpx-compatible client (``SmokeContext.make_client``). The
Neo4j/Qdrant/SMTP stages (create_resources, cross_tenant, email_reset) are
live-only and covered by the CI workflow.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

import monitor_ui.auth as auth_module
from fake_postgres import FakePostgres
from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import app
from scripts.create_admin import create_admin
from scripts.live_tenancy_smoke import SmokeContext, new_state, run_smoke

ADMIN_EMAIL = "root@example.com"
ADMIN_USERNAME = "root"
ADMIN_PASSWORD = "correct horse battery"

# The smoke's Postgres-only stages, in dependency order.
HERMETIC_STAGES = ["admin_login", "invites_signup", "forgot_probe", "admin_controls"]


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MONITOR_SIGNUP_MODE", "invite")
    monkeypatch.setenv("MONITOR_AUTH_DISABLED", "false")
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.delenv("MONITOR_SMTP_HOST", raising=False)
    monkeypatch.setattr(auth_module, "_login_limiter", None)
    monkeypatch.setattr(auth_module, "_signup_limiter", None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def fake_db(env) -> FakePostgres:
    return FakePostgres()


@pytest.fixture
def make_client(fake_db: FakePostgres) -> Callable[[], TestClient]:
    async def _fake_get_postgres() -> FakePostgres:
        return fake_db

    app.dependency_overrides[get_postgres] = _fake_get_postgres

    def _make() -> TestClient:
        client = TestClient(app, raise_server_exceptions=False)
        client.get("/api/auth/config")  # safe GET issues the CSRF cookie
        return client

    yield _make
    app.dependency_overrides.pop(get_postgres, None)


@pytest.fixture
def ctx(fake_db: FakePostgres, make_client: Callable[[], TestClient]) -> SmokeContext:
    """Smoke context whose admin exists exactly as create_admin.py makes it."""
    asyncio.run(
        create_admin(
            fake_db,
            email=ADMIN_EMAIL,
            username=ADMIN_USERNAME,
            password=ADMIN_PASSWORD,
        )
    )
    return SmokeContext(
        make_client=make_client,
        admin_login=ADMIN_EMAIL,
        admin_password=ADMIN_PASSWORD,
        sink_path=None,
    )


class TestHermeticSmokeStages:
    def test_postgres_only_stages_pass_end_to_end(self, ctx: SmokeContext, fake_db: FakePostgres) -> None:
        state = new_state()
        report = run_smoke(ctx, stages=HERMETIC_STAGES, state=state)
        assert report.ok, report.failures
        assert report.exit_code == 0
        assert report.checks >= 20

        # Exactly three accounts: admin, A, B — the refused signups created none.
        assert len(fake_db.users) == 3
        admin_row = next(r for r in fake_db.users.values() if r["email_normalized"] == ADMIN_EMAIL)
        assert admin_row["is_admin"] is True
        user_a = next(r for r in fake_db.users.values() if r["email_normalized"] == state.email_a)
        user_b = next(r for r in fake_db.users.values() if r["email_normalized"] == state.email_b)
        assert user_a["is_admin"] is False
        assert user_b["is_admin"] is False

        # Both invites were created and consumed exactly once.
        assert len(fake_db.invites) == 2
        assert all(row["used_at"] is not None for row in fake_db.invites.values())
        assert all(row["revoked_at"] is None for row in fake_db.invites.values())

        # B's admin-issued reset replaced the password (old one no longer verifies).
        from monitor_data.security import verify_password

        assert state.password_b != f"SmokePass!{state.suffix}-b"
        assert verify_password(state.password_b, user_b["password_hash"]) is True

        # B ends unbanned and logged in; A never got reset in these stages.
        assert user_b["is_banned"] is False
        sessions = [r for r in fake_db.sessions.values() if r["user_id"] == user_b["id"]]
        assert sessions, "B should hold a live session after the final login"
        assert verify_password(state.password_a, user_a["password_hash"]) is True

        # The admin reset token was single-use: exactly one consumed row for B.
        resets_for_b = [r for r in fake_db.password_resets.values() if r["user_id"] == user_b["id"]]
        assert len(resets_for_b) == 1
        assert resets_for_b[0]["used_at"] is not None

    def test_wrong_admin_password_fails_the_run(self, ctx: SmokeContext, make_client: Callable[[], TestClient]) -> None:
        bad = SmokeContext(
            make_client=make_client,
            admin_login=ADMIN_EMAIL,
            admin_password="not-the-admin-password",
            sink_path=None,
        )
        report = run_smoke(bad, stages=["admin_login", "invites_signup"])
        assert not report.ok
        assert report.exit_code == 1
        assert any("admin logs in" in failure for failure in report.failures)
        # The dependent stage reports its missing prerequisite instead of crashing.
        assert any("invites_signup" in failure or "admin available" in failure for failure in report.failures)

    def test_email_reset_stage_requires_a_sink(self, ctx: SmokeContext) -> None:
        report = run_smoke(ctx, stages=["admin_login", "email_reset"])
        assert not report.ok
        assert any("sink" in failure for failure in report.failures)

    def test_unknown_stage_name_is_reported(self, ctx: SmokeContext) -> None:
        report = run_smoke(ctx, stages=["does_not_exist"])
        assert not report.ok
        assert any("does_not_exist" in failure for failure in report.failures)

    def test_signup_without_invite_is_refused_and_creates_no_user(
        self, ctx: SmokeContext, fake_db: FakePostgres, make_client: Callable[[], TestClient]
    ) -> None:
        report = run_smoke(ctx, stages=["admin_login", "invites_signup"])
        assert report.ok, report.failures
        # The no-invite and invite-reuse attempts left no rows behind.
        emails = {row["email_normalized"] for row in fake_db.users.values()}
        assert not any("no-invite-" in e for e in emails)
        assert not any("reuse-" in e for e in emails)
        assert len(fake_db.users) == 3  # admin + A + B
