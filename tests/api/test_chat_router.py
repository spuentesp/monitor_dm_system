"""
API tests for the Chat router (/api/chat).

Covers session CRUD, message send/receive, and state queries.
Runs as fast unit tests — all DB clients and agent loops are mocked.

Use Cases: P-1, P-2, P-3, SYS-2
"""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestChatHealth:
    """Basic connectivity tests for the chat endpoints."""

    def test_list_sessions_empty(self, ui_client: TestClient) -> None:
        """GET /api/chat returns empty list when no sessions exist."""
        response = ui_client.get("/api/chat")
        assert response.status_code == 200
        assert response.json() == []

    def test_benchmarks_returns_list(self, ui_client: TestClient) -> None:
        """GET /api/chat/benchmarks returns a list (may be empty)."""
        response = ui_client.get("/api/chat/benchmarks")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestSessionCRUD:
    """Tests for session create, read, update, and delete."""

    def test_create_session_minimal(self, ui_client: TestClient) -> None:
        """POST /api/chat creates a session with defaults."""
        response = ui_client.post("/api/chat", json={"title": "Test Session"})
        assert response.status_code == 201
        session = response.json()
        assert session["id"]
        assert session["title"] == "Test Session"
        assert session["mode"] == "autonomous_gm"
        assert session["tone"] == "dramatic"
        assert session["phase"] == "awaiting_character"

    def test_create_session_full(self, ui_client: TestClient) -> None:
        """POST /api/chat accepts all optional fields."""
        response = ui_client.post(
            "/api/chat",
            json={
                "title": "Full Session",
                "mode": "world_architect",
                "universe_id": "u-123",
                "character_id": "c-456",
                "tone": "humorous",
                "play_mode": "narrative",
                "scene_id": "s-789",
                "story_id": "st-001",
                "phase": "active_play",
            },
        )
        assert response.status_code == 201
        session = response.json()
        assert session["title"] == "Full Session"
        assert session["mode"] == "world_architect"
        assert session["universe_id"] == "u-123"

    def test_list_sessions_after_create(self, ui_client: TestClient) -> None:
        """GET /api/chat returns previously created sessions."""
        ui_client.post("/api/chat", json={"title": "Session A"})
        ui_client.post("/api/chat", json={"title": "Session B"})
        response = ui_client.get("/api/chat")
        assert response.status_code == 200
        sessions = response.json()
        assert len(sessions) == 2
        titles = {s["title"] for s in sessions}
        assert titles == {"Session A", "Session B"}

    def test_get_session_state(self, ui_client: TestClient) -> None:
        """GET /api/chat/{sid}/state returns session state."""
        create_resp = ui_client.post("/api/chat", json={"title": "State Test"})
        sid = create_resp.json()["id"]
        response = ui_client.get(f"/api/chat/{sid}/state")
        assert response.status_code == 200
        state = response.json()
        assert state["session"]["id"] == sid
        # Every new session opens with a single GM opening message
        assert state["message_count"] == 1

    def test_get_session_state_404(self, ui_client: TestClient) -> None:
        """GET /api/chat/{sid}/state returns 404 for unknown session."""
        response = ui_client.get("/api/chat/nonexistent/state")
        assert response.status_code == 404

    def test_get_messages_new_session_has_opening(self, ui_client: TestClient) -> None:
        """GET /api/chat/{sid}/messages returns just the GM opening for a new session."""
        create_resp = ui_client.post("/api/chat", json={"title": "Messages Test"})
        sid = create_resp.json()["id"]
        response = ui_client.get(f"/api/chat/{sid}/messages")
        assert response.status_code == 200
        messages = response.json()
        assert len(messages) == 1
        assert messages[0]["role"] == "gm"

    def test_patch_session_tone(self, ui_client: TestClient) -> None:
        """PATCH /api/chat/{sid} updates session tone."""
        create_resp = ui_client.post("/api/chat", json={"title": "Patch Test"})
        sid = create_resp.json()["id"]
        response = ui_client.patch(
            f"/api/chat/{sid}", json={"tone": "grim"}
        )
        assert response.status_code == 200
        assert response.json()["tone"] == "grim"

    def test_patch_session_gm_profile(self, ui_client: TestClient) -> None:
        """PATCH /api/chat/{sid} updates GM profile."""
        create_resp = ui_client.post("/api/chat", json={"title": "GM Profile Test"})
        sid = create_resp.json()["id"]
        response = ui_client.patch(
            f"/api/chat/{sid}",
            json={"gm_profile_id": "gm-profile-uuid"},
        )
        assert response.status_code == 200
        assert response.json()["gm_profile_id"] == "gm-profile-uuid"

    def test_patch_nonexistent_404(self, ui_client: TestClient) -> None:
        """PATCH /api/chat/{sid} returns 404 for unknown session."""
        response = ui_client.patch("/api/chat/nonexistent", json={"tone": "dark"})
        assert response.status_code == 404

    def test_delete_session(self, ui_client: TestClient) -> None:
        """DELETE /api/chat/{sid} removes the session."""
        create_resp = ui_client.post("/api/chat", json={"title": "Delete Me"})
        sid = create_resp.json()["id"]
        response = ui_client.delete(f"/api/chat/{sid}")
        assert response.status_code == 204
        # Confirm it's gone
        list_resp = ui_client.get("/api/chat")
        assert len(list_resp.json()) == 0

    def test_delete_nonexistent_is_idempotent(self, ui_client: TestClient) -> None:
        """DELETE /api/chat/{sid} is idempotent — unknown sessions still 204."""
        response = ui_client.delete("/api/chat/nonexistent")
        assert response.status_code == 204


class TestMessageSend:
    """Tests for sending messages and the turn runner."""

    def test_send_message_to_session(self, ui_client: TestClient) -> None:
        """POST /api/chat/{sid}/send creates a player message and returns GM reply."""
        create_resp = ui_client.post(
            "/api/chat",
            json={"title": "Message Test", "phase": "active_play"},
        )
        sid = create_resp.json()["id"]

        response = ui_client.post(
            f"/api/chat/{sid}/send", json={"content": "Hello world"}
        )
        assert response.status_code == 200
        msg = response.json()
        assert msg["role"] == "gm"
        assert len(msg["content"]) > 0

    def test_send_message_to_nonexistent_404(self, ui_client: TestClient) -> None:
        """POST /api/chat/{sid}/send returns 404 for unknown session."""
        response = ui_client.post(
            "/api/chat/nonexistent/send", json={"content": "Hello"}
        )
        assert response.status_code == 404

    def test_messages_accumulate(self, ui_client: TestClient) -> None:
        """Sending multiple messages accumulates them in the message list."""
        create_resp = ui_client.post(
            "/api/chat",
            json={"title": "Multi Message", "phase": "active_play"},
        )
        sid = create_resp.json()["id"]

        ui_client.post(f"/api/chat/{sid}/send", json={"content": "First"})
        ui_client.post(f"/api/chat/{sid}/send", json={"content": "Second"})

        response = ui_client.get(f"/api/chat/{sid}/messages")
        messages = response.json()
        # Should have player messages + GM replies (at least 4 total)
        assert len(messages) >= 4
        roles = {m["role"] for m in messages}
        assert "player" in roles
        assert "gm" in roles

    def test_session_state_updates_after_message(self, ui_client: TestClient) -> None:
        """Session state reflects messages after sending."""
        create_resp = ui_client.post(
            "/api/chat",
            json={"title": "State Update", "phase": "active_play"},
        )
        sid = create_resp.json()["id"]
        ui_client.post(f"/api/chat/{sid}/send", json={"content": "Test message"})

        state_resp = ui_client.get(f"/api/chat/{sid}/state")
        state = state_resp.json()
        assert state["message_count"] > 0
        assert state["latest_gm_message_id"] is not None


class TestEndSceneEndpoint:
    """Tests for POST /api/chat/{sid}/end-scene endpoint (Phase 0.4)."""

    def test_end_scene_no_session_404(self, ui_client: TestClient) -> None:
        """POST /api/chat/{sid}/end-scene returns 404 for unknown session."""
        response = ui_client.post("/api/chat/nonexistent/end-scene")
        assert response.status_code == 404

    def test_end_scene_no_active_scene_400(self, ui_client: TestClient) -> None:
        """POST /api/chat/{sid}/end-scene returns 400 when no active scene."""
        create_resp = ui_client.post(
            "/api/chat",
            json={"title": "No Scene Session"},
        )
        sid = create_resp.json()["id"]
        # Session exists but has no scene_id or story_id
        response = ui_client.post(f"/api/chat/{sid}/end-scene")
        assert response.status_code == 400


class TestSessionEdgeCases:
    """Edge case and error path tests for sessions."""

    def test_create_session_empty_title(self, ui_client: TestClient) -> None:
        """POST /api/chat accepts empty title (defaults to 'New Session')."""
        response = ui_client.post("/api/chat", json={})
        assert response.status_code == 201
        assert response.json()["title"] == "New Session"

    def test_create_session_invalid_json(self, ui_client: TestClient) -> None:
        """POST /api/chat with invalid JSON returns 422."""
        response = ui_client.post("/api/chat", content="not json")
        assert response.status_code == 422

    def test_messages_endpoint_unknown_session_empty(self, ui_client: TestClient) -> None:
        """GET /api/chat/{sid}/messages returns an empty list for unknown sessions."""
        response = ui_client.get("/api/chat/nonexistent/messages")
        assert response.status_code == 200
        assert response.json() == []
