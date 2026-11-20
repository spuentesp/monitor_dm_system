"""Outbound account email (password resets) over stdlib ``smtplib``.

LAYER: UI backend. ``smtplib`` is blocking, so sends run on a worker thread
(``schedule_password_reset_email``) and never delay or fail the HTTP response:
failures are logged with structlog and swallowed. The raw reset token appears
only in the message body and in the caller's response — never in logs.
"""

from __future__ import annotations

import smtplib
import threading
from email.message import EmailMessage

import structlog

from monitor_ui.config import UISettings

log = structlog.get_logger()

_RESET_SUBJECT = "Reset your MONITOR password"


def build_reset_link(settings: UISettings, raw_token: str) -> str:
    """Absolute reset URL for the email body (path matches the frontend route)."""
    return f"{settings.public_base_url}/reset-password?token={raw_token}"


def send_password_reset_email(settings: UISettings, to_addr: str, reset_link: str) -> None:
    """Blocking SMTP send. Raises on failure — the caller logs and swallows.

    No-op when SMTP is not configured (``MONITOR_SMTP_HOST`` unset), so a
    misconfigured deployment can never accidentally dial out.
    """
    host = settings.monitor_smtp_host
    if not host:
        return
    message = EmailMessage()
    message["Subject"] = _RESET_SUBJECT
    message["From"] = settings.monitor_smtp_from or settings.monitor_smtp_user or "monitor@localhost"
    message["To"] = to_addr
    message.set_content(
        "Someone requested a password reset for your MONITOR account.\n"
        "\n"
        "Open this link to choose a new password (valid for one hour):\n"
        f"{reset_link}\n"
        "\n"
        "If you did not request this, ignore this message — the password\n"
        "stays unchanged.\n"
    )
    with smtplib.SMTP(host, settings.monitor_smtp_port, timeout=10) as smtp:
        if settings.monitor_smtp_starttls:
            smtp.starttls()
        if settings.monitor_smtp_user:
            smtp.login(settings.monitor_smtp_user, settings.monitor_smtp_password or "")
        smtp.send_message(message)


def schedule_password_reset_email(settings: UISettings, to_addr: str, reset_link: str) -> None:
    """Fire the send on a daemon thread; log failures, never raise.

    Not awaiting the send keeps the forgot-password response timing flat for
    known and unknown accounts (SMTP latency would otherwise enumerate).
    """

    def _run() -> None:
        try:
            send_password_reset_email(settings, to_addr, reset_link)
        except Exception:  # noqa: BLE001  # reason: SMTP failure must never reach the caller
            log.warning("password_reset_email_failed", exc_info=True)

    threading.Thread(target=_run, name="monitor-smtp", daemon=True).start()
