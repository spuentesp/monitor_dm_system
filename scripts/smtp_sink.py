#!/usr/bin/env python3
"""Tiny stdlib-only SMTP sink for tests and CI.

Accepts SMTP on a host/port and appends each accepted message to a file as
one JSON line: ``{"to": ..., "subject": ..., "body": ...}``. Uses asyncio
streams and the stdlib ``email`` parser only — no ``smtpd`` module (removed
in Python 3.12) and no third-party dependencies.

STARTTLS and AUTH are deliberately not advertised: point the sender at this
sink with ``MONITOR_SMTP_HOST=127.0.0.1 MONITOR_SMTP_PORT=<port>
MONITOR_SMTP_STARTTLS=false`` and no SMTP credentials.

Usage (from the repo root):

    uv run python scripts/smtp_sink.py --host 127.0.0.1 --port 2525 \\
        --out /tmp/smtp_sink.jsonl

Exit codes: 0 on clean shutdown, non-zero on bind/IO failure.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path

_GREETING = b"220 monitor-smtp-sink ESMTP\r\n"
_EHLO_OK = b"250-localhost\r\n250 HELP\r\n"
_OK = b"250 OK\r\n"
_DATA_READY = b"354 End data with <CR><LF>.<CR><LF>\r\n"
_BYE = b"221 Bye\r\n"
_UNKNOWN = b"500 5.5.2 Command not recognized\r\n"


def _extract_body(msg: EmailMessage) -> str:
    """Plain-text body of the message (best effort, never raises)."""
    try:
        if msg.is_multipart():
            part = msg.get_body(preferencelist=("plain", "html"))
            if part is not None:
                return str(part.get_content())
            return ""
        return str(msg.get_content())
    except Exception:  # noqa: BLE001  # reason: odd charsets degrade to a lossy decode, the sink must not crash
        payload = msg.get_payload(decode=True)
        if isinstance(payload, bytes):
            return payload.decode("utf-8", errors="replace")
        return str(msg.get_payload() or "")


def _record_message(raw: bytes, out_path: Path) -> tuple[str, str, str]:
    """Parse one RFC-5322 message and append it as a JSON line. Returns the triple."""
    msg = BytesParser(policy=policy.default).parsebytes(raw)
    to_addr = str(msg.get("To") or "")
    subject = str(msg.get("Subject") or "")
    body = _extract_body(msg)
    line = json.dumps({"to": to_addr, "subject": subject, "body": body}, ensure_ascii=False)
    with out_path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
        fh.flush()
    return to_addr, subject, body


async def _read_data(reader: asyncio.StreamReader) -> bytes:
    """Read a DATA payload up to the bare ``.`` terminator, unstuffed."""
    chunks: list[bytes] = []
    while True:
        line = await reader.readline()
        if not line:
            break  # client hung up mid-data
        stripped = line.rstrip(b"\r\n")
        if stripped == b".":
            break
        if stripped.startswith(b".."):
            stripped = stripped[1:]  # undo RFC-5321 dot-stuffing
        chunks.append(stripped + b"\r\n")
    return b"".join(chunks)


async def _handle_connection(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter, out_path: Path
) -> None:
    """One SMTP session: greeting → dialogue → DATA → append JSON line."""
    try:
        writer.write(_GREETING)
        await writer.drain()
        while True:
            line = await reader.readline()
            if not line:
                break
            command = line.decode("utf-8", errors="replace").strip()
            if not command:
                continue
            upper = command.upper()

            if upper.startswith("EHLO"):
                writer.write(_EHLO_OK)
            elif upper.startswith("HELO"):
                writer.write(b"250 localhost\r\n")
            elif upper.startswith("MAIL FROM"):
                writer.write(_OK)
            elif upper.startswith("RCPT TO"):
                writer.write(_OK)
            elif upper == "DATA":
                writer.write(_DATA_READY)
                await writer.drain()
                raw = await _read_data(reader)
                try:
                    to_addr, subject, _body = _record_message(raw, out_path)
                    print(f"smtp_sink: accepted mail to={to_addr!r} subject={subject!r}")
                except Exception as exc:  # noqa: BLE001  # reason: a parse/write failure still ACKs; the error is logged, not fatal
                    print(
                        f"smtp_sink: failed to record message: {type(exc).__name__}: {exc}",
                        file=sys.stderr,
                    )
                writer.write(_OK)
                await writer.drain()
                continue
            elif upper == "RSET" or upper == "NOOP":
                writer.write(_OK)
            elif upper == "QUIT":
                writer.write(_BYE)
                await writer.drain()
                break
            else:
                writer.write(_UNKNOWN)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError, OSError):
        pass  # client vanished mid-session; nothing to record
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass


async def start_sink(host: str, port: int, out_path: Path) -> asyncio.AbstractServer:
    """Bind the sink and return the asyncio server (caller closes/stops it)."""

    async def _handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await _handle_connection(reader, writer, out_path)

    return await asyncio.start_server(_handler, host, port)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=2525, help="Bind port (default: 2525)")
    parser.add_argument(
        "--out",
        default="smtp_sink.jsonl",
        help="File that receives one JSON line per message (default: smtp_sink.jsonl)",
    )
    return parser


async def _serve_forever(host: str, port: int, out_path: Path) -> None:
    server = await start_sink(host, port, out_path)
    bound_port = server.sockets[0].getsockname()[1] if server.sockets else port
    print(f"smtp_sink: listening on {host}:{bound_port}, appending messages to {out_path}")
    try:
        await server.serve_forever()
    finally:
        server.close()
        await server.wait_closed()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        asyncio.run(_serve_forever(args.host, args.port, out_path))
    except KeyboardInterrupt:
        print("smtp_sink: stopped")
    except OSError as exc:
        print(f"ERROR: smtp_sink cannot bind {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
