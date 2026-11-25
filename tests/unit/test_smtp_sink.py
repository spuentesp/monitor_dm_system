"""Unit tests for scripts/smtp_sink.py — the loopback SMTP sink.

Opens a real loopback socket (``enable_socket``: the hermetic conftest
disables networking for unit tests) and sends through stdlib ``smtplib``,
exactly the path ``monitor_ui.email`` uses against the sink in CI.
"""

from __future__ import annotations

import asyncio
import json
import smtplib
import threading
from email.message import EmailMessage
from types import SimpleNamespace

import pytest

from scripts.smtp_sink import start_sink

# Loopback SMTP for smtplib; the hermetic conftest disables sockets otherwise.
pytestmark = pytest.mark.enable_socket


@pytest.fixture
def sink(tmp_path) -> SimpleNamespace:  # type: ignore[no-untyped-def]
    """A running smtp_sink on an ephemeral port, appending to tmp_path/mail.jsonl."""
    out_path = tmp_path / "mail.jsonl"
    loop = asyncio.new_event_loop()
    holder: dict = {}
    ready = threading.Event()

    def _run() -> None:
        asyncio.set_event_loop(loop)
        server = loop.run_until_complete(start_sink("127.0.0.1", 0, out_path))
        holder["server"] = server
        holder["port"] = server.sockets[0].getsockname()[1]
        ready.set()
        try:
            loop.run_until_complete(server.serve_forever())
        except asyncio.CancelledError:
            # Python 3.11 Server.close() cancels serve_forever's future.
            pass
        finally:
            loop.run_until_complete(server.wait_closed())
            loop.close()

    thread = threading.Thread(target=_run, name="smtp-sink-test", daemon=True)
    thread.start()
    assert ready.wait(timeout=10), "smtp_sink did not bind in time"
    yield SimpleNamespace(port=holder["port"], out_path=out_path)
    loop.call_soon_threadsafe(holder["server"].close)
    thread.join(timeout=10)
    assert not thread.is_alive(), "smtp_sink thread did not stop"


def _send(
    port: int, *, to: str, subject: str, body: str, from_addr: str = "monitor@localhost"
) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_addr
    message["To"] = to
    message.set_content(body)
    with smtplib.SMTP("127.0.0.1", port, timeout=10) as smtp:
        smtp.send_message(message)


def _lines(path) -> list[dict]:  # type: ignore[no-untyped-def]
    if not path.exists():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


class TestSmtpSink:
    def test_send_message_is_recorded_as_one_json_line(self, sink) -> None:
        _send(
            sink.port,
            to="alice@example.com",
            subject="Reset your MONITOR password",
            body="Open http://localhost:3000/reset-password?token=abc123\n",
        )
        messages = _lines(sink.out_path)
        assert len(messages) == 1
        assert messages[0]["to"] == "alice@example.com"
        assert messages[0]["subject"] == "Reset your MONITOR password"
        assert "http://localhost:3000/reset-password?token=abc123" in messages[0]["body"]

    def test_multiple_messages_append_json_lines(self, sink) -> None:
        for i in range(3):
            _send(sink.port, to=f"user{i}@example.com", subject=f"mail {i}", body=f"body {i}\n")
        messages = _lines(sink.out_path)
        assert [m["to"] for m in messages] == [
            "user0@example.com",
            "user1@example.com",
            "user2@example.com",
        ]
        assert [m["subject"] for m in messages] == ["mail 0", "mail 1", "mail 2"]

    def test_body_survives_dot_leading_lines_and_long_content(self, sink) -> None:
        body = "line one\n.hidden dot line\n" + ("x" * 5000) + "\nend\n"
        _send(sink.port, to="bob@example.com", subject="multiline", body=body)
        (message,) = _lines(sink.out_path)
        assert "line one" in message["body"]
        assert ".hidden dot line" in message["body"]
        assert "x" * 5000 in message["body"]
        assert message["body"].rstrip().endswith("end")

    def test_file_contains_only_json_lines(self, sink) -> None:
        _send(sink.port, to="carol@example.com", subject="s", body="b\n")
        _send(sink.port, to="dave@example.com", subject="s2", body="b2\n")
        raw_lines = sink.out_path.read_text(encoding="utf-8").splitlines()
        assert len(raw_lines) == 2
        for line in raw_lines:
            parsed = json.loads(line)  # raises if a line is not JSON
            assert set(parsed) == {"to", "subject", "body"}
