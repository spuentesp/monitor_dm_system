import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI
import os

import monitor_ui.routers.llm_mgmt as llm_mgmt_module
from monitor_ui.routers.llm_mgmt import (
    router,
    _invalidate_llm_cache,
    _discover_ollama_model_sync,
    _resolve_model,
    _mask_key,
)

app = FastAPI()
app.include_router(router)
client = TestClient(app)


@pytest.fixture
def mock_postgres():
    postgres = AsyncMock()

    postgres.providers_list.return_value = [
        {
            "id": "provider-1",
            "name": "Anthropic",
            "provider": "anthropic",
            "model": "claude-sonnet-4-20250514",
            "api_key": "sk-ant-12345",
            "base_url": None,
            "status": "connected",
            "latency_ms": 120,
            "is_default": True,
            "role": "heavy",
        }
    ]

    postgres.provider_get.return_value = {
        "id": "provider-1",
        "name": "Anthropic",
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "api_key": "sk-ant-12345",
        "base_url": None,
        "status": "connected",
        "latency_ms": 120,
        "is_default": True,
        "role": "heavy",
    }

    postgres.node_assignments_list.return_value = [
        {"node_name": "node-1", "provider_id": "provider-1", "param_overrides": {}, "notes": "test node"}
    ]

    postgres.node_assignment_get.return_value = {
        "node_name": "node-1",
        "provider_id": "provider-1",
        "param_overrides": {"temperature": 0.5},
        "notes": "updated",
    }

    return postgres


def test_mask_key():
    assert _mask_key(None) is None
    assert _mask_key("short") == "••••••••"
    assert _mask_key("12345678901234567890") == "1234••••••••7890"


def test_resolve_model():
    assert _resolve_model("TEST_ENV_VAR", "existing-model", "fallback-model") == "existing-model"
    with patch.dict(os.environ, {"TEST_ENV_VAR": "env-model"}):
        assert _resolve_model("TEST_ENV_VAR", "", "fallback-model") == "env-model"
    assert _resolve_model("TEST_ENV_VAR", "", "fallback-model") == "fallback-model"


def test_discover_ollama_model_sync_success():
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"models": [{"name": "my-ollama-model"}]}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        assert _discover_ollama_model_sync("http://localhost:11434") == "my-ollama-model"


def test_discover_ollama_model_sync_fail():
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = Exception("Network error")
        assert _discover_ollama_model_sync("http://localhost:11434") == "qwen2.5:latest"


def test_invalidate_llm_cache():
    import sys

    mock_module = MagicMock()
    with patch.dict(sys.modules, {"monitor_agents.dspy_runtime": mock_module}):
        _invalidate_llm_cache()
        mock_module.clear_bg_registry_cache.assert_called_once()

    # Test suppression of exception
    with patch.dict(sys.modules, {"monitor_agents.dspy_runtime": None}):
        _invalidate_llm_cache()  # Should not raise


def test_list_providers_seed_full(mock_postgres):
    llm_mgmt_module._seeded = False
    env_vars = {
        "GITHUB_MODELS_TOKEN": "gh-token",
        "GOOGLE_API_KEY": "google-key",
        "ANTHROPIC_API_KEY": "ant-key",
        "OPENAI_API_KEY": "openai-key",
        "MINIMAX_TOKEN": "minimax-key",
        "Z_AI_TOKEN": "zai-key",
    }
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        with patch.dict(os.environ, env_vars):
            response = client.get("/providers")
            assert response.status_code == 200
            # should have hit the seeded logic


def test_list_providers_seed_with_existing_legacy(mock_postgres):
    llm_mgmt_module._seeded = False
    mock_postgres.providers_list.return_value = [
        {"id": "minimax-default", "name": "legacy", "provider": "minimax", "model": "m"},
        {"id": "zai-default", "name": "legacy", "provider": "z_ai", "model": "m"},
    ]
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        with patch.dict(os.environ, {}, clear=True):
            response = client.get("/providers")
            assert response.status_code == 200


def test_list_providers_already_seeded(mock_postgres):
    llm_mgmt_module._seeded = True
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        response = client.get("/providers")
        assert response.status_code == 200


def test_add_provider(mock_postgres):
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        response = client.post(
            "/providers",
            json={"name": "New Prov", "provider": "openai", "model": "gpt-4", "is_default": True, "role": "standard"},
        )
        assert response.status_code == 201
        assert response.json()["name"] == "New Prov"


def test_update_provider(mock_postgres):
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        response = client.put(
            "/providers/provider-1",
            json={
                "name": "Updated Name",
                "is_default": True,
                "api_key": "",  # should be ignored
            },
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"


def test_update_provider_not_found(mock_postgres):
    mock_postgres.provider_get.return_value = None
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        response = client.put("/providers/provider-1", json={"name": "Updated Name"})
        assert response.status_code == 404


def test_delete_provider(mock_postgres):
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        response = client.delete("/providers/provider-1")
        assert response.status_code == 204


def test_duplicate_provider(mock_postgres):
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        response = client.post("/providers/provider-1/duplicate", json={"name": "Duplicated"})
        assert response.status_code == 201
        assert response.json()["name"] == "Duplicated"


def test_duplicate_provider_not_found(mock_postgres):
    mock_postgres.provider_get.return_value = None
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        response = client.post("/providers/provider-1/duplicate", json={"name": "Duplicated"})
        assert response.status_code == 404


def test_list_node_assignments(mock_postgres):
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        response = client.get("/assignments")
        assert response.status_code == 200
        assert len(response.json()) == 1


def test_upsert_node_assignment(mock_postgres):
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        response = client.put(
            "/assignments/node-1",
            json={"provider_id": "provider-1", "param_overrides": {"temperature": 0.8}, "notes": "my note"},
        )
        assert response.status_code == 200
        assert response.json()["notes"] == "updated"


def test_upsert_node_assignment_not_found(mock_postgres):
    mock_postgres.node_assignment_get.return_value = None
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        response = client.put("/assignments/node-1", json={"provider_id": "provider-1"})
        assert response.status_code == 404


def test_delete_node_assignment(mock_postgres):
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        response = client.delete("/assignments/node-1")
        assert response.status_code == 204


def test_discover_ollama_model_sync_empty_models():
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"models": []}'
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        assert _discover_ollama_model_sync("http://localhost:11434") == "qwen2.5:latest"


def test_add_provider_clear_existing_default(mock_postgres):
    mock_postgres.providers_list.return_value = [
        {"id": "prov1", "is_default": True},
        {"id": "prov2", "is_default": False},
    ]
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        response = client.post(
            "/providers",
            json={"name": "New Prov", "provider": "openai", "model": "gpt-4", "is_default": True, "role": "standard"},
        )
        assert response.status_code == 201


def test_update_provider_with_api_key(mock_postgres):
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        response = client.put(
            "/providers/provider-1", json={"name": "Updated Name", "api_key": "new-api-key", "is_default": False}
        )
        assert response.status_code == 200


# Provider test endpoints


def _mock_provider_get(provider_type, base_url=None):
    return {
        "id": "test-id",
        "name": "Test",
        "provider": provider_type,
        "model": "test-model",
        "api_key": "test-key",
        "base_url": base_url,
    }


def test_test_provider_not_found(mock_postgres):
    mock_postgres.provider_get.return_value = None
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        response = client.post("/providers/provider-1/test")
        assert response.status_code == 404


def test_test_provider_anthropic(mock_postgres):
    mock_postgres.provider_get.return_value = _mock_provider_get("anthropic")
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.json.return_value = {"content": [{"text": "hello"}]}
        mock_response.raise_for_status.return_value = None
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            response = client.post("/providers/test-id/test")
            assert response.status_code == 200
            assert response.json()["ok"] is True
            assert response.json()["model_response"] == "hello"


def test_test_provider_openai(mock_postgres):
    mock_postgres.provider_get.return_value = _mock_provider_get("openai")
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            response = client.post("/providers/test-id/test")
            assert response.status_code == 200
            assert response.json()["ok"] is True


def test_test_provider_github_models(mock_postgres):
    mock_postgres.provider_get.return_value = _mock_provider_get("github_models")
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            response = client.post("/providers/test-id/test")
            assert response.status_code == 200
            assert response.json()["ok"] is True


def test_test_provider_google_ai_studio(mock_postgres):
    mock_postgres.provider_get.return_value = _mock_provider_get("google_ai_studio")
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            response = client.post("/providers/test-id/test")
            assert response.status_code == 200
            assert response.json()["ok"] is True


def test_test_provider_google_ai_studio_models_prefix(mock_postgres):
    p = _mock_provider_get("google_ai_studio")
    p["model"] = "models/test-model"
    mock_postgres.provider_get.return_value = p
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            response = client.post("/providers/test-id/test")
            assert response.status_code == 200
            assert response.json()["ok"] is True


def test_test_provider_ollama(mock_postgres):
    mock_postgres.provider_get.return_value = _mock_provider_get("ollama")
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.json.return_value = {"models": [{"name": "llama3"}]}
        mock_response.raise_for_status.return_value = None
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            response = client.post("/providers/test-id/test")
            assert response.status_code == 200
            assert response.json()["ok"] is True


def test_test_provider_groq(mock_postgres):
    mock_postgres.provider_get.return_value = _mock_provider_get("groq")
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            response = client.post("/providers/test-id/test")
            assert response.status_code == 200
            assert response.json()["ok"] is True


def test_test_provider_openrouter(mock_postgres):
    mock_postgres.provider_get.return_value = _mock_provider_get("openrouter")
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            response = client.post("/providers/test-id/test")
            assert response.status_code == 200
            assert response.json()["ok"] is True


def test_test_provider_z_ai(mock_postgres):
    mock_postgres.provider_get.return_value = _mock_provider_get("z_ai")
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            response = client.post("/providers/test-id/test")
            assert response.status_code == 200
            assert response.json()["ok"] is True


def test_test_provider_minimax(mock_postgres):
    mock_postgres.provider_get.return_value = _mock_provider_get("minimax")
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"content": [{"text": "ok"}]}
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            response = client.post("/providers/test-id/test")
            assert response.status_code == 200
            assert response.json()["ok"] is True


def test_test_provider_minimax_m2(mock_postgres):
    p = _mock_provider_get("minimax")
    p["model"] = "MiniMax-M2.7"
    mock_postgres.provider_get.return_value = p
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"content": [{"text": "ok"}]}
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            response = client.post("/providers/test-id/test")
            assert response.status_code == 200
            assert response.json()["ok"] is True


def test_test_provider_custom(mock_postgres):
    p = _mock_provider_get("custom")
    p["base_url"] = "http://custom-url/v1"
    mock_postgres.provider_get.return_value = p
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            response = client.post("/providers/test-id/test")
            assert response.status_code == 200
            assert response.json()["ok"] is True


def test_test_provider_unknown(mock_postgres):
    mock_postgres.provider_get.return_value = _mock_provider_get("unknown_provider")
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        response = client.post("/providers/test-id/test")
        assert response.status_code == 200
        assert response.json()["ok"] is False


def test_test_provider_exception(mock_postgres):
    mock_postgres.provider_get.return_value = _mock_provider_get("openai")
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = Exception("HTTP Error")
            response = client.post("/providers/test-id/test")
            assert response.status_code == 200
            assert response.json()["ok"] is False
            assert "HTTP Error" in response.json()["error"]


def test_test_provider_custom_no_base_url(mock_postgres):
    mock_postgres.provider_get.return_value = _mock_provider_get("custom")
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        response = client.post("/providers/test-id/test")
        assert response.status_code == 200
        assert response.json()["ok"] is False


def test_list_models_anthropic(mock_postgres):
    mock_postgres.providers_list.return_value = [_mock_provider_get("anthropic")]
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "claude-3"}]}
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            response = client.get("/models/anthropic")
            assert response.status_code == 200
            assert "claude-3" in response.json()


def test_list_models_openai(mock_postgres):
    mock_postgres.providers_list.return_value = [_mock_provider_get("openai")]
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "gpt-4"}]}
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            response = client.get("/models/openai")
            assert response.status_code == 200
            assert "gpt-4" in response.json()


def test_list_models_github_models(mock_postgres):
    mock_postgres.providers_list.return_value = [_mock_provider_get("github_models")]
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"id": "gpt-4"}]
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            response = client.get("/models/github_models")
            assert response.status_code == 200
            assert "gpt-4" in response.json()


def test_list_models_custom(mock_postgres):
    p = _mock_provider_get("custom")
    p["base_url"] = "http://custom/v1"
    mock_postgres.providers_list.return_value = [p]
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "custom-model"}]}
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            response = client.get("/models/custom")
            assert response.status_code == 200
            assert "custom-model" in response.json()


def test_list_models_ollama_fallback(mock_postgres):
    mock_postgres.providers_list.return_value = []
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        response = client.get("/models/ollama")
        assert response.status_code == 200


def test_add_provider_is_default_existing(mock_postgres):
    mock_postgres.providers_list.return_value = [{"id": "1", "is_default": True}]
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        response = client.post(
            "/providers",
            json={"name": "x", "provider": "openai", "model": "gpt-4", "is_default": True, "role": "standard"},
        )
        assert response.status_code == 201


def test_test_provider_ollama_model_mismatch(mock_postgres):
    mock_postgres.provider_get.return_value = _mock_provider_get("ollama")
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.json.return_value = {"models": [{"name": "wrong_model"}, {"name": "other"}]}
        mock_response.raise_for_status.return_value = None
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            response = client.post("/providers/test-id/test")
            assert response.status_code == 200


def test_list_models_minimax(mock_postgres):
    mock_postgres.providers_list.return_value = [_mock_provider_get("minimax")]
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "abab"}]}
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            response = client.get("/models/minimax")
            assert response.status_code == 200
            assert "abab" in response.json()


def test_list_models_groq(mock_postgres):
    mock_postgres.providers_list.return_value = [_mock_provider_get("groq")]
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "llama"}]}
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            response = client.get("/models/groq")
            assert response.status_code == 200
            assert "llama" in response.json()


def test_list_models_openrouter(mock_postgres):
    mock_postgres.providers_list.return_value = [_mock_provider_get("openrouter")]
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": [{"id": "anthropic/claude"}]}
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            response = client.get("/models/openrouter")
            assert response.status_code == 200
            assert "anthropic/claude" in response.json()


def test_add_provider_not_default(mock_postgres):
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        response = client.post(
            "/providers",
            json={"name": "New Prov", "provider": "openai", "model": "gpt-4", "is_default": False, "role": "standard"},
        )
        assert response.status_code == 201


def test_list_models_status_500_all(mock_postgres):
    providers = ["github_models", "google_ai_studio", "minimax", "groq", "openrouter", "openai"]
    for prov in providers:
        mock_postgres.providers_list.return_value = [_mock_provider_get(prov)]
        with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
            mock_response = MagicMock()
            mock_response.status_code = 500
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = mock_response
                response = client.get(f"/models/{prov}")
                assert response.status_code == 200


def test_list_models_custom_status_500(mock_postgres):
    p = _mock_provider_get("custom")
    p["base_url"] = "http://test"
    mock_postgres.providers_list.return_value = [p]
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.status_code = 500
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            response = client.get("/models/custom")
            assert response.status_code == 200


def test_test_provider_ollama_model_missing_no_installed(mock_postgres):
    mock_postgres.provider_get.return_value = _mock_provider_get("ollama")
    with patch("monitor_ui.routers.llm_mgmt.get_postgres_client", return_value=mock_postgres):
        mock_response = MagicMock()
        mock_response.json.return_value = {"models": []}
        mock_response.raise_for_status.return_value = None
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            response = client.post("/providers/test-id/test")
            assert response.status_code == 200
