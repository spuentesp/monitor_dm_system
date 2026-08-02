"""HTTP-shape tests for the OpenAI-compatible /v1/chat/completions endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from monitor_ui.main import app

client = TestClient(app)


def _fake_client(reply: str = "This is the assistant.") -> MagicMock:
    c = MagicMock()
    c.model = "monitor-default"
    c.complete_text = AsyncMock(return_value=reply)
    return c


def _make_registry(client_obj):
    fake_registry = MagicMock()
    fake_registry.for_role = AsyncMock(return_value=client_obj)
    return fake_registry


def test_completions_returns_openai_shape():
    """Happy path: response shape matches the OpenAI ChatCompletion contract."""
    fake = _fake_client("A polite reply.")
    registry = _make_registry(fake)

    with (
        patch("monitor_ui.routers.openai_compat.get_postgres_client", return_value=MagicMock()),
        patch("monitor_ui.routers.openai_compat.LLMRegistry", return_value=registry),
    ):
        resp = client.post(
            "/api/v1/chat/completions",
            json={
                "model": "gpt-4o-mini",
                "messages": [
                    {"role": "system", "content": "You are a wary ranger."},
                    {"role": "user", "content": "Who goes there?"},
                ],
            },
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["object"] == "chat.completion"
    assert body["model"] == "gpt-4o-mini"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["message"]["content"] == "A polite reply."
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["id"].startswith("chatcmpl-")
    assert isinstance(body["created"], int)


def test_sampling_params_passed_to_provider():
    """temperature/max_tokens/top_p are forwarded to complete_text."""
    fake = _fake_client()
    registry = _make_registry(fake)

    with (
        patch("monitor_ui.routers.openai_compat.get_postgres_client", return_value=MagicMock()),
        patch("monitor_ui.routers.openai_compat.LLMRegistry", return_value=registry),
    ):
        client.post(
            "/api/v1/chat/completions",
            json={
                "model": "x",
                "messages": [{"role": "user", "content": "hi"}],
                "temperature": 0.3,
                "max_tokens": 100,
                "top_p": 0.9,
            },
        )

    kwargs = fake.complete_text.await_args.kwargs
    assert kwargs["temperature"] == 0.3
    assert kwargs["max_tokens"] == 100
    assert kwargs["top_p"] == 0.9
    args = fake.complete_text.await_args.args
    assert args[0] == [{"role": "user", "content": "hi"}]


def test_stream_true_rejected_v1():
    """Streaming is called out as a v1 limitation."""
    with patch("monitor_ui.routers.openai_compat.get_postgres_client", return_value=MagicMock()):
        resp = client.post(
            "/api/v1/chat/completions",
            json={
                "model": "x",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        )
    assert resp.status_code == 400
    assert "stream" in resp.json()["detail"].lower()


def test_empty_messages_rejected():
    with patch("monitor_ui.routers.openai_compat.get_postgres_client", return_value=MagicMock()):
        resp = client.post(
            "/api/v1/chat/completions",
            json={"model": "x", "messages": []},
        )
    assert resp.status_code == 400


def test_no_llm_configured_returns_503():
    """Registry returning None → 503."""
    registry = MagicMock()
    registry.for_role = AsyncMock(return_value=None)

    with (
        patch("monitor_ui.routers.openai_compat.get_postgres_client", return_value=MagicMock()),
        patch("monitor_ui.routers.openai_compat.LLMRegistry", return_value=registry),
    ):
        resp = client.post(
            "/api/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code == 503


def test_provider_failure_returns_502():
    fake = MagicMock()
    fake.model = "x"
    fake.complete_text = AsyncMock(side_effect=RuntimeError("upstream down"))
    registry = _make_registry(fake)

    with (
        patch("monitor_ui.routers.openai_compat.get_postgres_client", return_value=MagicMock()),
        patch("monitor_ui.routers.openai_compat.LLMRegistry", return_value=registry),
    ):
        resp = client.post(
            "/api/v1/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code == 502
