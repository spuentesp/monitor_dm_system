"""Unit tests for monitor_data.security (password hashing and opaque tokens)."""

from __future__ import annotations

import pytest

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


class TestNlpInputBounds:
    """GLiNER/spaCy MCP tools must bound client input server-side."""

    def test_threshold_out_of_range_rejected(self):
        from monitor_data.tools.nlp_tools import EntityExtractionRequest

        with pytest.raises(ValueError):
            EntityExtractionRequest(text="hello", threshold=1.5)
        with pytest.raises(ValueError):
            EntityExtractionRequest(text="hello", threshold=-0.1)

    def test_oversized_text_rejected(self):
        from monitor_data.tools.nlp_tools import EntityExtractionRequest, _bounded_text

        with pytest.raises(ValueError):
            _bounded_text("x" * 10_000_000)
        with pytest.raises(ValueError):
            EntityExtractionRequest(text="x" * 10_000_000)

    def test_batch_size_and_labels_bounded(self):
        from monitor_data.tools.nlp_tools import BatchEntityExtractionRequest

        with pytest.raises(ValueError):
            BatchEntityExtractionRequest(texts=["a"] * 10_000)
        with pytest.raises(ValueError):
            BatchEntityExtractionRequest(texts=["a"], labels=["l"] * 1000)


class TestChunkIdScoping:
    """Chunk point IDs are namespaced by universe/job so the same book in two
    universes cannot overwrite each other's Qdrant points."""

    def test_stable_id_differs_by_scope(self):
        from monitor_data.tools.ingest_tools._models import IngestedChunk

        a = IngestedChunk.stable_id("book.pdf", 0, "hello", scope="universe-A")
        b = IngestedChunk.stable_id("book.pdf", 0, "hello", scope="universe-B")
        same = IngestedChunk.stable_id("book.pdf", 0, "hello")
        assert a != b != same
        assert IngestedChunk.stable_id("book.pdf", 0, "hello", scope="universe-A") == a  # deterministic


class TestNlpWindowSplitting:
    """Oversized NLP inputs are split into windows, not rejected."""

    def test_split_text_windows_cover_input(self):
        from monitor_data.tools.nlp_tools import _split_text, _enumerate_windows

        text = ("word " * 400) + "\n\n" + ("more " * 400)
        windows = _split_text(text, max_chars=1000)
        assert len(windows) > 1
        assert "".join(windows) == text
        enumerated = _enumerate_windows(text, 1000)
        assert enumerated[0][0] == 0
        assert sum(len(w) for _, w in enumerated) == len(text)

    def test_analyzer_retrieval_scopes_by_universe(self):
        import inspect

        from monitor_agents.analyzer import _core

        src = inspect.getsource(_core)
        # evidence lookup, category scroll, reference scroll, fallback queries
        assert src.count('key="universe_id"') >= 4
