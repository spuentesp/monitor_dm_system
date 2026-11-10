"""Unit tests for monitor_data.security (password hashing and opaque tokens)."""

from __future__ import annotations

import hashlib
import re

from monitor_data.security import (
    API_TOKEN_PREFIX,
    hash_password,
    hash_token,
    needs_rehash,
    new_api_token,
    new_csrf_token,
    new_session_token,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_verify_roundtrip(self):
        h = hash_password("correct horse battery staple")
        assert h.startswith("$argon2id$")
        assert verify_password("correct horse battery staple", h)

    def test_wrong_password_fails(self):
        h = hash_password("correct horse battery staple")
        assert not verify_password("Tr0ub4dor&3", h)

    def test_malformed_hash_fails_closed(self):
        assert not verify_password("anything", "not-a-real-hash")
        assert not verify_password("anything", "")

    def test_hashes_are_salted(self):
        assert hash_password("same-password") != hash_password("same-password")

    def test_fresh_hash_does_not_need_rehash(self):
        assert not needs_rehash(hash_password("some password 123"))

    def test_malformed_hash_needs_rehash(self):
        assert needs_rehash("garbage")


class TestTokens:
    def test_session_tokens_are_unique_and_opaque(self):
        tokens = {new_session_token() for _ in range(100)}
        assert len(tokens) == 100
        for t in tokens:
            assert re.fullmatch(r"[A-Za-z0-9_-]{40,}", t)

    def test_csrf_tokens_are_unique(self):
        assert new_csrf_token() != new_csrf_token()

    def test_hash_token_is_sha256_hex(self):
        token = new_session_token()
        assert hash_token(token) == hashlib.sha256(token.encode("utf-8")).hexdigest()
        assert len(hash_token(token)) == 64

    def test_hash_token_stable(self):
        assert hash_token("abc") == hash_token("abc")
        assert hash_token("abc") != hash_token("abd")

    def test_api_token_shape(self):
        raw, prefix, token_hash = new_api_token()
        assert raw.startswith(f"{API_TOKEN_PREFIX}_")
        assert raw[: len(prefix)] == prefix
        assert len(prefix) == 12
        assert token_hash == hash_token(raw)
        # raw values are unique per call
        raw2, _, _ = new_api_token()
        assert raw != raw2


class TestMigrationBootstrap:
    """Regression: fresh-DB bootstrap must not query schema_migrations before
    it exists, and user_create must rely on the id default when omitted."""

    def test_schema_sql_creates_migration_table(self):
        from monitor_data.db.postgres import _SCHEMA_SQL

        assert "CREATE TABLE IF NOT EXISTS schema_migrations" in _SCHEMA_SQL

    def test_user_create_uses_default_id_when_none(self):
        import inspect

        from monitor_data.db.postgres import PostgresClient

        src = inspect.getsource(PostgresClient.user_create)
        assert "COALESCE($1, gen_random_uuid())" in src

    def test_empty_owned_id_allowlists_are_not_falsy_skipped(self):
        import inspect

        from monitor_data.tools.neo4j_tools import core

        assert "if ids is not None:" in inspect.getsource(core.neo4j_list_multiverses)
