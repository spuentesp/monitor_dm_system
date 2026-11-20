"""Typed tenancy/quota errors keep their HTTP shape through blanket excepts.

UX-1 item 2: handlers that normalize every failure into a 5xx must re-raise
``QuotaExceededError`` and ``OwnerViolationError`` so the app-level handlers
in ``monitor_ui.main`` can map them to a readable 429 and the generic 404.
One test per router touched (gm_tools, entities, light_rp, openai_compat);
the image-gen pair lives in ``test_image_gen.py`` next to its 502 contracts.

Hermetic: local auth mode + patched inner callables; no databases, no LLM.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from monitor_data.tenancy import OwnerViolationError
from monitor_data.usage import QuotaExceededError

pytestmark = pytest.mark.usefixtures("local_auth_mode")


@pytest.fixture
def client():
    from monitor_ui.main import app

    return TestClient(app)


def _quota() -> QuotaExceededError:
    return QuotaExceededError("token", 1)


class _BoomPlotHookAgent:
    """PlotHookAgent stand-in that always refuses with the typed error."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def suggest_hooks(self, **kwargs: object) -> object:
        raise self._exc


class TestGmToolsTypedMapping:
    def test_hooks_quota_error_is_429(self, client: TestClient) -> None:
        import monitor_ui.routers.gm_tools as gm_tools

        with patch.object(gm_tools, "PlotHookAgent", lambda: _BoomPlotHookAgent(_quota())):
            res = client.post("/api/gm/hooks", json={"universe_id": str(uuid4())})
        assert res.status_code == 429, res.text
        assert "limit" in res.json()["detail"].lower()

    def test_hooks_owner_violation_is_404(self, client: TestClient) -> None:
        import monitor_ui.routers.gm_tools as gm_tools

        with patch.object(gm_tools, "PlotHookAgent", lambda: _BoomPlotHookAgent(OwnerViolationError("nope"))):
            res = client.post("/api/gm/hooks", json={"universe_id": str(uuid4())})
        assert res.status_code == 404, res.text
        assert res.json() == {"detail": "Not found"}


class TestEntitiesTypedMapping:
    def test_npc_profile_quota_error_is_429(self, client: TestClient) -> None:
        import monitor_ui.routers.entities as entities

        char_id = str(uuid4())
        with (
            patch.object(
                entities,
                "_get_character_doc",
                return_value={"id": char_id, "entity_id": str(uuid4())},
            ),
            patch(
                "monitor_data.tools.mongodb_tools.mongodb_get_npc_profile",
                side_effect=_quota(),
            ),
        ):
            res = client.get(f"/api/entities/characters/{char_id}/profile")
        assert res.status_code == 429, res.text
        assert "limit" in res.json()["detail"].lower()

    def test_npc_profile_owner_violation_is_404(self, client: TestClient) -> None:
        import monitor_ui.routers.entities as entities

        char_id = str(uuid4())
        with (
            patch.object(
                entities,
                "_get_character_doc",
                return_value={"id": char_id, "entity_id": str(uuid4())},
            ),
            patch(
                "monitor_data.tools.mongodb_tools.mongodb_get_npc_profile",
                side_effect=OwnerViolationError("foreign"),
            ),
        ):
            res = client.get(f"/api/entities/characters/{char_id}/profile")
        assert res.status_code == 404, res.text
        assert res.json() == {"detail": "Not found"}


class TestLightRpTypedMapping:
    def test_start_chat_quota_error_is_429(self, client: TestClient) -> None:
        with patch(
            "monitor_ui.routers.character_conversation.start_universe_character_chat",
            new=AsyncMock(side_effect=_quota()),
        ):
            res = client.post(
                "/api/entities/universe-characters/start",
                json={"entity_id": str(uuid4())},
            )
        assert res.status_code == 429, res.text
        assert "limit" in res.json()["detail"].lower()

    def test_start_chat_owner_violation_is_404(self, client: TestClient) -> None:
        with patch(
            "monitor_ui.routers.character_conversation.start_universe_character_chat",
            new=AsyncMock(side_effect=OwnerViolationError("foreign")),
        ):
            res = client.post(
                "/api/entities/universe-characters/start",
                json={"entity_id": str(uuid4())},
            )
        assert res.status_code == 404, res.text
        assert res.json() == {"detail": "Not found"}


class _BoomLLMClient:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def complete_text(self, messages: object, **kwargs: object) -> object:
        raise self._exc


class TestOpenAICompatTypedMapping:
    def test_plain_completion_quota_error_is_429(self, client: TestClient) -> None:
        import monitor_ui.routers.openai_compat as oa

        with patch.object(oa, "_resolve_plain_client", new=AsyncMock(return_value=_BoomLLMClient(_quota()))):
            res = client.post(
                "/api/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )
        assert res.status_code == 429, res.text
        assert "limit" in res.json()["detail"].lower()

    def test_plain_completion_owner_violation_is_404(self, client: TestClient) -> None:
        import monitor_ui.routers.openai_compat as oa

        with patch.object(
            oa,
            "_resolve_plain_client",
            new=AsyncMock(return_value=_BoomLLMClient(OwnerViolationError("foreign"))),
        ):
            res = client.post(
                "/api/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hello"}]},
            )
        assert res.status_code == 404, res.text
        assert res.json() == {"detail": "Not found"}
