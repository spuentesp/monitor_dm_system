"""Unit tests for scripts/create_admin.py — first-admin bootstrap (UX follow-up).

Hermetic: the database is the FakePostgres registry; the script's seams
(``db_factory``, ``password_prompt``) drive ``main()`` without touching a
real Postgres or stdin. The password must never appear in any output.
"""

from __future__ import annotations

import pytest
from fake_postgres import FakePostgres
from pydantic import ValidationError

from scripts.create_admin import CreateAdminError, create_admin, main

ADMIN_EMAIL = "root@example.com"
ADMIN_USERNAME = "root"
ADMIN_PASSWORD = "correct horse battery"


def _row(db: FakePostgres, login: str) -> dict:
    import asyncio

    row = asyncio.run(db.user_get_by_login(login))
    assert row is not None, f"no user for {login}"
    return row


class TestCreateAdminCore:
    def test_creates_admin_with_normalized_logins_and_valid_hash(self) -> None:
        db = FakePostgres()
        status = asyncio_run(
            create_admin(
                db,
                email="  Root@Example.COM ",
                username="Root",
                password=ADMIN_PASSWORD,
            )
        )
        assert status == "created"
        row = _row(db, "root@example.com")
        assert row["is_admin"] is True
        assert row["email_normalized"] == "root@example.com"
        assert row["username_normalized"] == "root"
        # Signup-compatible hash: the stored hash verifies against the password.
        from monitor_data.security import verify_password

        assert verify_password(ADMIN_PASSWORD, row["password_hash"])

    def test_rerun_is_idempotent(self) -> None:
        db = FakePostgres()
        first = asyncio_run(create_admin(db, email=ADMIN_EMAIL, username=ADMIN_USERNAME, password=ADMIN_PASSWORD))
        before = dict(_row(db, ADMIN_EMAIL))
        second = asyncio_run(create_admin(db, email=ADMIN_EMAIL, username=ADMIN_USERNAME, password=ADMIN_PASSWORD))
        assert first == "created"
        assert second == "already_admin"
        assert _row(db, ADMIN_EMAIL) == before  # no rewrite, same id and hash

    def test_existing_non_admin_is_refused_without_the_flag(self) -> None:
        db = FakePostgres()
        asyncio_run(
            create_admin(
                db,
                email=ADMIN_EMAIL,
                username=ADMIN_USERNAME,
                password=ADMIN_PASSWORD,
            )
        )
        _set_admin(db, ADMIN_EMAIL, False)
        with pytest.raises(CreateAdminError, match="--promote-existing"):
            asyncio_run(create_admin(db, email=ADMIN_EMAIL, username=ADMIN_USERNAME, password=ADMIN_PASSWORD))

    def test_promote_existing_grants_admin_and_keeps_the_password(self) -> None:
        db = FakePostgres()
        asyncio_run(
            create_admin(
                db,
                email=ADMIN_EMAIL,
                username=ADMIN_USERNAME,
                password=ADMIN_PASSWORD,
            )
        )
        _set_admin(db, ADMIN_EMAIL, False)
        hash_before = _row(db, ADMIN_EMAIL)["password_hash"]
        status = asyncio_run(
            create_admin(
                db,
                email=ADMIN_EMAIL,
                username=ADMIN_USERNAME,
                password=None,
                promote_existing=True,
            )
        )
        assert status == "promoted"
        row = _row(db, ADMIN_EMAIL)
        assert row["is_admin"] is True
        assert row["password_hash"] == hash_before  # promotion never resets the password

    def test_conflicting_email_or_username_is_refused(self) -> None:
        db = FakePostgres()
        asyncio_run(create_admin(db, email=ADMIN_EMAIL, username=ADMIN_USERNAME, password=ADMIN_PASSWORD))
        with pytest.raises(CreateAdminError, match="different details"):
            asyncio_run(
                create_admin(
                    db,
                    email=ADMIN_EMAIL,
                    username="somebody-else",
                    password=ADMIN_PASSWORD,
                )
            )
        with pytest.raises(CreateAdminError, match="different details"):
            asyncio_run(
                create_admin(
                    db,
                    email="other@example.com",
                    username=ADMIN_USERNAME,
                    password=ADMIN_PASSWORD,
                )
            )

    def test_new_account_without_password_is_refused(self) -> None:
        db = FakePostgres()
        with pytest.raises(CreateAdminError, match="no password"):
            asyncio_run(create_admin(db, email=ADMIN_EMAIL, username=ADMIN_USERNAME, password=None))

    def test_password_prompt_is_used_only_when_creating(self) -> None:
        db = FakePostgres()
        prompts: list[str] = []

        def _prompt() -> str:
            prompts.append("asked")
            return ADMIN_PASSWORD

        status = asyncio_run(
            create_admin(
                db,
                email=ADMIN_EMAIL,
                username=ADMIN_USERNAME,
                password=None,
                password_prompt=_prompt,
            )
        )
        assert status == "created"
        assert prompts == ["asked"]
        # Existing account: no prompt, password untouched.
        _set_admin(db, ADMIN_EMAIL, False)
        status = asyncio_run(
            create_admin(
                db,
                email=ADMIN_EMAIL,
                username=ADMIN_USERNAME,
                password=None,
                promote_existing=True,
                password_prompt=_prompt,
            )
        )
        assert status == "promoted"
        assert prompts == ["asked"]

    def test_signup_validation_applies(self) -> None:
        db = FakePostgres()
        with pytest.raises(ValidationError):
            asyncio_run(create_admin(db, email=ADMIN_EMAIL, username=ADMIN_USERNAME, password="short"))
        with pytest.raises(ValidationError):
            asyncio_run(create_admin(db, email="not-an-email", username=ADMIN_USERNAME, password=ADMIN_PASSWORD))
        with pytest.raises(ValidationError):
            asyncio_run(create_admin(db, email=ADMIN_EMAIL, username="bad user!", password=ADMIN_PASSWORD))
        assert db.users == {}


class TestCreateAdminMain:
    def test_main_creates_then_is_idempotent(self, capsys: pytest.CaptureFixture[str]) -> None:
        db = FakePostgres()
        rc = main(
            ["--email", ADMIN_EMAIL, "--username", ADMIN_USERNAME, "--password", ADMIN_PASSWORD],
            db_factory=lambda: db,
            password_prompt=_no_prompt,
        )
        assert rc == 0
        out = capsys.readouterr().out
        assert "PASS: admin created" in out
        assert ADMIN_PASSWORD not in out

        rc = main(
            ["--email", ADMIN_EMAIL, "--username", ADMIN_USERNAME, "--password", ADMIN_PASSWORD],
            db_factory=lambda: db,
            password_prompt=_no_prompt,
        )
        assert rc == 0
        assert "already an admin" in capsys.readouterr().out

    def test_main_refusal_exits_nonzero_without_the_password_in_output(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = FakePostgres()
        asyncio_run(create_admin(db, email=ADMIN_EMAIL, username=ADMIN_USERNAME, password=ADMIN_PASSWORD))
        _set_admin(db, ADMIN_EMAIL, False)
        rc = main(
            ["--email", ADMIN_EMAIL, "--username", ADMIN_USERNAME, "--password", ADMIN_PASSWORD],
            db_factory=lambda: db,
            password_prompt=_no_prompt,
        )
        assert rc == 1
        captured = capsys.readouterr()
        assert "ERROR:" in captured.err
        assert "--promote-existing" in captured.err
        assert ADMIN_PASSWORD not in captured.out + captured.err

    def test_main_validation_failure_exits_two_and_never_echoes_the_password(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        db = FakePostgres()
        rc = main(
            ["--email", ADMIN_EMAIL, "--username", ADMIN_USERNAME, "--password", "short"],
            db_factory=lambda: db,
            password_prompt=_no_prompt,
        )
        assert rc == 2
        captured = capsys.readouterr()
        assert "ERROR: validation failed" in captured.err
        assert "short" not in captured.out + captured.err

    def test_main_never_calls_the_prompt_when_password_is_given(self) -> None:
        db = FakePostgres()

        def _boom() -> str:
            raise AssertionError("prompt must not run when --password is given")

        rc = main(
            ["--email", ADMIN_EMAIL, "--username", ADMIN_USERNAME, "--password", ADMIN_PASSWORD],
            db_factory=lambda: db,
            password_prompt=_boom,
        )
        assert rc == 0


def _no_prompt() -> str:
    raise AssertionError("interactive prompt must not run in tests")


def _set_admin(db: FakePostgres, login: str, value: bool) -> object:
    import asyncio

    row = _row(db, login)
    return asyncio.run(db.user_set_admin(row["id"], value))


def asyncio_run(coro):  # type: ignore[no-untyped-def]
    import asyncio

    return asyncio.run(coro)
