#!/usr/bin/env python3
"""Live two-user tenancy smoke against an auth-ENABLED MONITOR backend.

Drives the HTTP API end to end (plan UX-1/UX-2): admin login, invite-only
signup, cross-tenant denial for a second user, enumeration-safe forgot-
password with an SMTP sink, and the admin reset/revoke/ban controls. Every
step prints ``PASS:`` or ``FAIL:`` and the process exits non-zero if any
check failed.

CSRF is handled exactly like the frontend: a safe ``GET /api/auth/config``
issues the readable ``monitor_csrf`` cookie, and every unsafe request sends
it back in the ``X-CSRF-Token`` header (double-submit). Requests carry no
Origin header, which the middleware allows for non-browser clients.

The backend must be running WITH authentication enabled, e.g.:

    uv run python scripts/smtp_sink.py --port 2525 --out /tmp/smtp_sink.jsonl &
    # second backend on :8002 with MONITOR_AUTH_DISABLED=false,
    # MONITOR_SIGNUP_MODE=invite, AUTH_COOKIE_SECURE=false,
    # MONITOR_SMTP_HOST=127.0.0.1 MONITOR_SMTP_PORT=2525
    # MONITOR_SMTP_STARTTLS=false, MONITOR_PUBLIC_URL, and
    # MONITOR_PROVIDER_KEY_ENCRYPTION_KEY set
    uv run python scripts/create_admin.py --email admin@example.com --username admin
    uv run python scripts/live_tenancy_smoke.py \\
        --base-url http://127.0.0.1:8002 \\
        --admin-login admin@example.com --admin-password '…' \\
        --sink /tmp/smtp_sink.jsonl

The stages accept an injected httpx-compatible client factory (see
``SmokeContext.make_client``) so the Postgres-only stages run hermetically
in tests against the FastAPI app with a fake registry.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_TIMEOUT = 30.0
RESET_LINK_RE = re.compile(r"/reset-password\?token=([A-Za-z0-9_\-]+)")

# Stage run order; dependencies run first (email_reset consumes the mail
# that forgot_probe triggers).
STAGE_ORDER: tuple[str, ...] = (
    "admin_login",
    "invites_signup",
    "create_resources",
    "cross_tenant",
    "forgot_probe",
    "email_reset",
    "admin_controls",
)


class Report:
    """Collects PASS/FAIL lines; the smoke exits with ``exit_code``."""

    def __init__(self) -> None:
        self.checks = 0
        self.failures: list[str] = []

    def check(self, label: str, ok: bool, detail: str = "") -> bool:
        self.checks += 1
        if ok:
            print(f"PASS: {label}", flush=True)
        else:
            line = f"FAIL: {label}" + (f" — {detail}" if detail else "")
            print(line, flush=True)
            self.failures.append(line)
        return ok

    @property
    def ok(self) -> bool:
        return not self.failures

    @property
    def exit_code(self) -> int:
        return 0 if self.ok else 1


def _brief(response: Any) -> str:
    """Status plus a safe ``detail`` string — never a raw body (422 bodies
    echo request input, which can contain passwords)."""
    try:
        body = response.json()
    except Exception:  # noqa: BLE001  # reason: non-JSON body → status only
        return f"status={response.status_code}"
    if isinstance(body, dict) and isinstance(body.get("detail"), str):
        return f"status={response.status_code} detail={body['detail']!r}"
    if response.status_code == 422:
        return "status=422 (validation error)"
    return f"status={response.status_code}"


def csrf_headers(client: Any) -> dict[str, str]:
    """Double-submit CSRF exactly like the frontend (readable cookie → header)."""
    token = client.cookies.get("monitor_csrf")
    if not token:
        client.get("/api/auth/config")  # safe GET issues the cookie
        token = client.cookies.get("monitor_csrf", "")
    return {"X-CSRF-Token": token}


@dataclass
class SmokeContext:
    """Injected collaborators: a factory for fresh cookie-jar clients."""

    make_client: Callable[[], Any]
    admin_login: str
    admin_password: str
    sink_path: Path | None = None
    timeout: float = DEFAULT_TIMEOUT


@dataclass
class SmokeState:
    """Identities, clients and resource ids shared by the stages."""

    suffix: str
    email_a: str
    username_a: str
    password_a: str
    email_b: str
    username_b: str
    password_b: str
    admin: Any = None
    client_a: Any = None
    client_b: Any = None
    user_a_id: str = ""
    user_b_id: str = ""
    resources: dict[str, str] = field(default_factory=dict)


def new_state() -> SmokeState:
    """Fresh unique identities per run (the shared CI database may already
    contain rows from earlier steps)."""
    suffix = secrets.token_hex(4)
    return SmokeState(
        suffix=suffix,
        email_a=f"smoke-a-{suffix}@example.com",
        username_a=f"smoke-a-{suffix}",
        password_a=f"SmokePass!{suffix}-a",
        email_b=f"smoke-b-{suffix}@example.com",
        username_b=f"smoke-b-{suffix}",
        password_b=f"SmokePass!{suffix}-b",
    )


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------


def stage_admin_login(ctx: SmokeContext, state: SmokeState, report: Report) -> None:
    client = ctx.make_client()
    response = client.post(
        "/api/auth/login",
        json={"login": ctx.admin_login, "password": ctx.admin_password},
        headers=csrf_headers(client),
    )
    if not report.check("admin logs in", response.status_code == 200, _brief(response)):
        return
    me = client.get("/api/auth/me")
    body = me.json() if me.status_code == 200 else {}
    report.check(
        "admin session reports is_admin",
        me.status_code == 200 and body.get("user", {}).get("is_admin") is True,
        _brief(me),
    )
    state.admin = client


def stage_invites_signup(ctx: SmokeContext, state: SmokeState, report: Report) -> None:
    admin = state.admin
    if admin is None:
        report.check("admin available for invites", False, "admin_login did not complete")
        return

    config = admin.get("/api/auth/config")
    report.check(
        "auth config reports invite-only signup",
        config.status_code == 200 and config.json().get("signup_invite_only") is True,
        _brief(config),
    )

    invite_a = admin.post(
        "/api/admin/invites", json={"email": state.email_a}, headers=csrf_headers(admin)
    )
    invite_b = admin.post(
        "/api/admin/invites", json={"email": state.email_b}, headers=csrf_headers(admin)
    )
    if not report.check(
        "admin creates two invites",
        invite_a.status_code == 200 and invite_b.status_code == 200,
        f"A={_brief(invite_a)} B={_brief(invite_b)}",
    ):
        return
    token_a = invite_a.json()["token"]
    token_b = invite_b.json()["token"]

    # Signup WITHOUT an invite is refused (fresh identity → the invite gate,
    # not the duplicate-account check, decides).
    anon = ctx.make_client()
    refused = anon.post(
        "/api/auth/signup",
        json={
            "email": f"no-invite-{state.suffix}@example.com",
            "username": f"no-invite-{state.suffix}",
            "password": f"SmokePass!{state.suffix}-x",
        },
        headers=csrf_headers(anon),
    )
    report.check("signup without invite is refused", refused.status_code == 403, _brief(refused))

    # User A signs up with their invite.
    client_a = ctx.make_client()
    signup_a = client_a.post(
        "/api/auth/signup",
        json={
            "email": state.email_a,
            "username": state.username_a,
            "password": state.password_a,
            "invite_token": token_a,
        },
        headers=csrf_headers(client_a),
    )
    if report.check(
        "user A signs up with their invite", signup_a.status_code == 201, _brief(signup_a)
    ):
        state.client_a = client_a
        state.user_a_id = str(signup_a.json()["id"])

    # User B signs up with their invite.
    client_b = ctx.make_client()
    signup_b = client_b.post(
        "/api/auth/signup",
        json={
            "email": state.email_b,
            "username": state.username_b,
            "password": state.password_b,
            "invite_token": token_b,
        },
        headers=csrf_headers(client_b),
    )
    if report.check(
        "user B signs up with their invite", signup_b.status_code == 201, _brief(signup_b)
    ):
        state.client_b = client_b
        state.user_b_id = str(signup_b.json()["id"])

    # Reusing A's (now consumed) invite with a fresh identity is refused.
    reuse = ctx.make_client()
    reused = reuse.post(
        "/api/auth/signup",
        json={
            "email": f"reuse-{state.suffix}@example.com",
            "username": f"reuse-{state.suffix}",
            "password": f"SmokePass!{state.suffix}-r",
            "invite_token": token_a,
        },
        headers=csrf_headers(reuse),
    )
    report.check("reusing an invite is refused", reused.status_code == 403, _brief(reused))


def stage_create_resources(ctx: SmokeContext, state: SmokeState, report: Report) -> None:
    """User A creates real resources that need no LLM call."""
    a = state.client_a
    if a is None:
        report.check(
            "user A available for resource creation", False, "invites_signup did not complete"
        )
        return
    res = state.resources
    csrf = csrf_headers(a)

    mv_name = f"A multiverse {state.suffix}"
    response = a.post(
        "/api/universes/multiverses",
        json={"name": mv_name, "description": "live tenancy smoke"},
        headers=csrf,
    )
    if report.check("A creates a multiverse", response.status_code == 201, _brief(response)):
        res["multiverse_id"] = str(response.json()["id"])
        res["multiverse_name"] = mv_name

    if not res.get("multiverse_id"):
        report.check("A's multiverse available for the universe", False, "multiverse create failed")
        return
    universe_name = f"A universe {state.suffix}"
    response = a.post(
        "/api/universes/universes",
        json={
            "name": universe_name,
            "multiverse_id": res["multiverse_id"],
            "description": "live tenancy smoke",
        },
        headers=csrf,
    )
    if report.check("A creates a universe", response.status_code == 201, _brief(response)):
        res["universe_id"] = str(response.json()["id"])
        res["universe_name"] = universe_name

    if not res.get("universe_id"):
        report.check("A's universe available for later steps", False, "universe create failed")
        return
    chat_title = f"A chat {state.suffix}"
    response = a.post(
        "/api/chat",
        json={"title": chat_title, "universe_id": res["universe_id"]},
        headers=csrf,
    )
    if report.check("A creates a chat session", response.status_code == 201, _brief(response)):
        res["session_id"] = str(response.json()["id"])
        res["chat_title"] = chat_title

    character_name = f"A hero {state.suffix}"
    response = a.post(
        "/api/entities/characters",
        json={
            "name": character_name,
            "description": "live tenancy smoke",
            "personality": "cautious",
            "first_message": "Hello.",
        },
        headers=csrf,
    )
    if report.check("A creates a character card", response.status_code == 201, _brief(response)):
        res["character_id"] = str(response.json()["id"])
        res["character_name"] = character_name

    if not res.get("character_id"):
        report.check("A's character available for the lorebook", False, "character create failed")
        return
    lore_content = f"A lore {state.suffix}"
    response = a.post(
        "/api/lorebook/entries",
        params={"character_id": res["character_id"]},
        json={"content": lore_content, "keywords": ["smoke"]},
        headers=csrf,
    )
    if report.check("A creates a lorebook entry", response.status_code == 201, _brief(response)):
        res["entry_id"] = str(response.json()["id"])
        res["entry_content"] = lore_content

    note_content = f"A notes {state.suffix}"
    response = a.put(
        f"/api/gm/notes/{res['universe_id']}",
        json={"content": note_content},
        headers=csrf,
    )
    if report.check("A writes a GM note", response.status_code == 200, _brief(response)):
        res["note_content"] = note_content


def stage_cross_tenant(ctx: SmokeContext, state: SmokeState, report: Report) -> None:
    """User B must not read/update/delete A's resources; A stays intact."""
    a, b = state.client_a, state.client_b
    res = state.resources
    if a is None or b is None or not res.get("universe_id"):
        report.check(
            "cross-tenant prerequisites", False, "invites_signup/create_resources incomplete"
        )
        return

    mv_id, uid = res["multiverse_id"], res["universe_id"]
    sid = res.get("session_id", "")
    cid = res.get("character_id", "")
    eid = res.get("entry_id", "")

    probes: list[tuple[str, str, str, dict[str, Any]]] = [
        (
            "multiverse update",
            "PUT",
            f"/api/universes/multiverses/{mv_id}",
            {"json": {"name": "hijack"}},
        ),
        ("multiverse delete", "DELETE", f"/api/universes/multiverses/{mv_id}", {}),
        ("universe read", "GET", f"/api/universes/universes/{uid}", {}),
        ("universe update", "PUT", f"/api/universes/universes/{uid}", {"json": {"name": "hijack"}}),
        ("universe delete", "DELETE", f"/api/universes/universes/{uid}", {}),
        ("chat session state", "GET", f"/api/chat/{sid}/state", {}),
        ("chat session messages", "GET", f"/api/chat/{sid}/messages", {}),
        ("chat session update", "PATCH", f"/api/chat/{sid}", {"json": {"title": "hijack"}}),
        ("chat session delete", "DELETE", f"/api/chat/{sid}", {}),
        ("chat session rewind", "POST", f"/api/chat/{sid}/rewind", {"json": {}}),
        ("character read", "GET", f"/api/entities/characters/{cid}", {}),
        (
            "character update",
            "PUT",
            f"/api/entities/characters/{cid}",
            {"json": {"name": "hijack"}},
        ),
        ("character delete", "DELETE", f"/api/entities/characters/{cid}", {}),
        ("lorebook entry read", "GET", f"/api/lorebook/entries/{eid}", {}),
        (
            "lorebook entry update",
            "PATCH",
            f"/api/lorebook/entries/{eid}",
            {"json": {"content": "hijack"}},
        ),
        ("lorebook entry delete", "DELETE", f"/api/lorebook/entries/{eid}", {}),
        ("lorebook list for A's character", "GET", f"/api/lorebook/entries?character_id={cid}", {}),
        ("GM note read", "GET", f"/api/gm/notes/{uid}", {}),
        ("GM note update", "PUT", f"/api/gm/notes/{uid}", {"json": {"content": "hijack"}}),
    ]
    rejected: list[str] = []
    for label, method, path, kwargs in probes:
        response = b.request(method, path, headers=csrf_headers(b), **kwargs)
        if response.status_code not in (403, 404):
            rejected.append(f"{label}: {method} {path} -> {response.status_code}")
    report.check(
        "B is rejected with 404/403 on every A-owned resource",
        not rejected,
        "; ".join(rejected),
    )

    # Lists are owner-scoped: nothing of A's appears in B's listings.
    leaks: list[str] = []
    for label, path, needle in (
        ("multiverses", "/api/universes/multiverses", mv_id),
        ("universes", "/api/universes/universes", uid),
        ("chat sessions", "/api/chat", sid),
        ("characters", "/api/entities/characters", cid),
    ):
        response = b.get(path, headers=csrf_headers(b))
        if response.status_code != 200:
            leaks.append(f"{label}: {_brief(response)}")
        elif needle in response.text:
            leaks.append(f"{label} list contains A's id {needle}")
    report.check("B's list endpoints never include A's resources", not leaks, "; ".join(leaks))

    # Search and graph return none of A's data (owner-scoped predicates).
    needles = [mv_id, uid, res.get("multiverse_name", ""), res.get("universe_name", "")]
    search = b.get(
        "/api/search/search",
        params={"q": f"A multiverse {state.suffix}"},
        headers=csrf_headers(b),
    )
    search_leak = search.status_code != 200 or any(n and n in search.text for n in needles)
    report.check(
        "/api/search returns none of A's data",
        not search_leak,
        _brief(search) if search.status_code != 200 else "A's ids/names present in search body",
    )

    graph = b.get("/api/graph/world", headers=csrf_headers(b))
    graph_leak = graph.status_code != 200 or any(n and n in graph.text for n in needles)
    report.check(
        "/api/graph returns none of A's data",
        not graph_leak,
        _brief(graph) if graph.status_code != 200 else "A's ids/names present in body",
    )

    # Operator + provider surfaces are admin-only.
    llm = b.get("/api/llm/providers", headers=csrf_headers(b))
    admin_users = b.get("/api/admin/users", headers=csrf_headers(b))
    admin_invites = b.get("/api/admin/invites", headers=csrf_headers(b))
    report.check(
        "B is refused /api/llm/* with 403",
        llm.status_code == 403,
        _brief(llm),
    )
    report.check(
        "B is refused /api/admin/* with 403",
        admin_users.status_code == 403 and admin_invites.status_code == 403,
        f"users={_brief(admin_users)} invites={_brief(admin_invites)}",
    )

    # A re-reads every resource: B's attempts changed nothing.
    diffs: list[str] = []
    # No GET-by-id route for multiverses: read back through A's list.
    response = a.get("/api/universes/multiverses", headers=csrf_headers(a))
    mvs = response.json() if response.status_code == 200 else []
    if response.status_code != 200 or not any(
        str(m.get("id")) == str(mv_id) and m.get("name") == res.get("multiverse_name") for m in mvs
    ):
        diffs.append(f"multiverse read-back: {_brief(response)}")
    response = a.get(f"/api/universes/universes/{uid}", headers=csrf_headers(a))
    if response.status_code != 200 or response.json().get("name") != res.get("universe_name"):
        diffs.append(f"universe read-back: {_brief(response)}")
    response = a.get("/api/chat", headers=csrf_headers(a))
    sessions = response.json() if response.status_code == 200 else []
    if response.status_code != 200 or not any(
        s.get("id") == sid and s.get("title") == res.get("chat_title") for s in sessions
    ):
        diffs.append("chat session missing or renamed")
    response = a.get(f"/api/entities/characters/{cid}", headers=csrf_headers(a))
    if response.status_code != 200 or response.json().get("name") != res.get("character_name"):
        diffs.append(f"character read-back: {_brief(response)}")
    response = a.get(f"/api/lorebook/entries/{eid}", headers=csrf_headers(a))
    if response.status_code != 200 or response.json().get("content") != res.get("entry_content"):
        diffs.append(f"lorebook read-back: {_brief(response)}")
    response = a.get(f"/api/gm/notes/{uid}", headers=csrf_headers(a))
    if response.status_code != 200 or response.json().get("content") != res.get("note_content"):
        diffs.append(f"GM note read-back: {_brief(response)}")
    report.check("A's resources are unchanged after B's attempts", not diffs, "; ".join(diffs))


def stage_forgot_probe(ctx: SmokeContext, state: SmokeState, report: Report) -> None:
    """Known and unknown logins get the identical 202 (and, with SMTP
    configured, the known login triggers A's single reset mail)."""
    known = ctx.make_client()
    response_known = known.post(
        "/api/auth/password/forgot",
        json={"login": state.email_a},
        headers=csrf_headers(known),
    )
    unknown = ctx.make_client()
    ghost = f"ghost-{state.suffix}@example.com"
    response_unknown = unknown.post(
        "/api/auth/password/forgot",
        json={"login": ghost},
        headers=csrf_headers(unknown),
    )
    same = (
        response_known.status_code == 202
        and response_unknown.status_code == 202
        and response_known.content == response_unknown.content
        and response_known.json() == {"ok": True}
    )
    report.check(
        "forgot-password answers an identical 202 for known and unknown logins",
        same,
        f"known={_brief(response_known)} unknown={_brief(response_unknown)}",
    )


def _read_sink(path: Path) -> list[dict]:
    if not path.exists():
        return []
    messages = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return messages


def stage_email_reset(ctx: SmokeContext, state: SmokeState, report: Report) -> None:
    """Consume the mail forgot_probe triggered: exactly one mail for A, a
    /reset-password?token= link, single-use token, sessions revoked."""
    sink = ctx.sink_path
    if sink is None:
        report.check("email reset has an SMTP sink file", False, "--sink was not provided")
        return
    if state.client_a is None:
        report.check(
            "user A available for the email reset", False, "invites_signup did not complete"
        )
        return

    deadline = time.monotonic() + 15.0
    messages: list[dict] = []
    while time.monotonic() < deadline:
        messages = _read_sink(sink)
        if any(state.email_a.lower() in str(m.get("to", "")).lower() for m in messages):
            break
        time.sleep(0.2)

    for_a = [m for m in messages if state.email_a.lower() in str(m.get("to", "")).lower()]
    if not report.check(
        "the sink received exactly one mail for A", len(for_a) == 1, f"found {len(for_a)} in {sink}"
    ):
        return
    ghosts = [m for m in messages if f"ghost-{state.suffix}" in str(m.get("to", ""))]
    report.check("no mail was sent for the unknown login", not ghosts, f"{len(ghosts)} ghost mails")

    match = RESET_LINK_RE.search(str(for_a[0].get("body", "")))
    if not report.check(
        "A's mail contains a /reset-password?token= link",
        match is not None,
        "link not found in body",
    ):
        return
    token = match.group(1)

    before = state.client_a.get("/api/auth/me")
    report.check("A's session works before the reset", before.status_code == 200, _brief(before))

    new_password = f"SmokeReset!{state.suffix}-a"
    redeem = ctx.make_client()
    response = redeem.post(
        "/api/auth/password/reset",
        json={"token": token, "new_password": new_password},
        headers=csrf_headers(redeem),
    )
    if report.check(
        "reset with the emailed token succeeds", response.status_code == 200, _brief(response)
    ):
        state.password_a = new_password

    after = state.client_a.get("/api/auth/me")
    report.check("A's old session is 401 after the reset", after.status_code == 401, _brief(after))

    reuse = ctx.make_client()
    response = reuse.post(
        "/api/auth/password/reset",
        json={"token": token, "new_password": f"SmokeReuse!{state.suffix}"},
        headers=csrf_headers(reuse),
    )
    report.check("the reset token cannot be reused", response.status_code == 400, _brief(response))

    fresh = ctx.make_client()
    response = fresh.post(
        "/api/auth/login",
        json={"login": state.email_a, "password": state.password_a},
        headers=csrf_headers(fresh),
    )
    if report.check(
        "A logs in with the new password", response.status_code == 200, _brief(response)
    ):
        state.client_a = fresh


def stage_admin_controls(ctx: SmokeContext, state: SmokeState, report: Report) -> None:
    """Admin-issued reset for B (no email), revoke-sessions, ban, unban."""
    admin, b = state.admin, state.client_b
    if admin is None or b is None or not state.user_b_id:
        report.check("admin controls prerequisites", False, "admin_login/invites_signup incomplete")
        return

    before = b.get("/api/auth/me")
    report.check(
        "B's session works before admin actions", before.status_code == 200, _brief(before)
    )

    issued = admin.post(
        f"/api/admin/users/{state.user_b_id}/password-reset",
        headers=csrf_headers(admin),
    )
    if not report.check(
        "admin issues a password reset link for B", issued.status_code == 200, _brief(issued)
    ):
        return
    token = issued.json()["token"]

    new_password = f"SmokeAdmin!{state.suffix}-b"
    redeem = ctx.make_client()
    response = redeem.post(
        "/api/auth/password/reset",
        json={"token": token, "new_password": new_password},
        headers=csrf_headers(redeem),
    )
    if report.check(
        "the admin-issued reset works without email", response.status_code == 200, _brief(response)
    ):
        state.password_b = new_password

    revoked = b.get("/api/auth/me")
    report.check("B's session is 401 after the reset", revoked.status_code == 401, _brief(revoked))

    reuse = ctx.make_client()
    response = reuse.post(
        "/api/auth/password/reset",
        json={"token": token, "new_password": f"SmokeReuse!{state.suffix}"},
        headers=csrf_headers(reuse),
    )
    report.check(
        "the admin reset token cannot be reused", response.status_code == 400, _brief(response)
    )

    fresh = ctx.make_client()
    response = fresh.post(
        "/api/auth/login",
        json={"login": state.email_b, "password": state.password_b},
        headers=csrf_headers(fresh),
    )
    if report.check(
        "B logs in with the new password", response.status_code == 200, _brief(response)
    ):
        state.client_b = fresh
    b = state.client_b

    response = admin.post(
        f"/api/admin/users/{state.user_b_id}/revoke-sessions",
        headers=csrf_headers(admin),
    )
    report.check("admin revokes all of B's sessions", response.status_code == 204, _brief(response))
    logged_out = b.get("/api/auth/me")
    report.check(
        "B is logged out after revoke-sessions", logged_out.status_code == 401, _brief(logged_out)
    )

    response = admin.post(
        f"/api/admin/users/{state.user_b_id}/ban",
        json={"reason": "live tenancy smoke"},
        headers=csrf_headers(admin),
    )
    report.check("admin bans B", response.status_code == 200, _brief(response))
    banned = ctx.make_client()
    response = banned.post(
        "/api/auth/login",
        json={"login": state.email_b, "password": state.password_b},
        headers=csrf_headers(banned),
    )
    report.check(
        "B's login is blocked with 403 while banned", response.status_code == 403, _brief(response)
    )

    response = admin.post(
        f"/api/admin/users/{state.user_b_id}/unban",
        headers=csrf_headers(admin),
    )
    report.check("admin unbans B", response.status_code == 200, _brief(response))
    restored = ctx.make_client()
    response = restored.post(
        "/api/auth/login",
        json={"login": state.email_b, "password": state.password_b},
        headers=csrf_headers(restored),
    )
    if report.check("unban restores B's login", response.status_code == 200, _brief(response)):
        state.client_b = restored


STAGES: dict[str, Callable[[SmokeContext, SmokeState, Report], None]] = {
    "admin_login": stage_admin_login,
    "invites_signup": stage_invites_signup,
    "create_resources": stage_create_resources,
    "cross_tenant": stage_cross_tenant,
    "forgot_probe": stage_forgot_probe,
    "email_reset": stage_email_reset,
    "admin_controls": stage_admin_controls,
}


def run_smoke(
    ctx: SmokeContext,
    stages: Iterable[str] | None = None,
    state: SmokeState | None = None,
) -> Report:
    """Run the given stages (default: all, in dependency order)."""
    report = Report()
    chosen = list(stages) if stages is not None else list(STAGE_ORDER)
    unknown = [name for name in chosen if name not in STAGES]
    if unknown:
        report.check("known stage names", False, f"unknown: {', '.join(unknown)}")
        return report
    state = state or new_state()
    for name in chosen:
        try:
            STAGES[name](ctx, state, report)
        except Exception as exc:  # noqa: BLE001  # reason: a stage crash is a reported failure, not a traceback
            report.check(f"stage {name} completed", False, f"{type(exc).__name__}: {exc}")
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("MONITOR_API_URL_BASE", "http://127.0.0.1:8000"),
        help="Origin of the auth-enabled backend (env: MONITOR_API_URL_BASE)",
    )
    parser.add_argument(
        "--admin-login", required=True, help="Admin email/username created by create_admin.py"
    )
    parser.add_argument(
        "--admin-password", required=True, help="Admin password (never printed by this script)"
    )
    parser.add_argument(
        "--sink",
        default=None,
        help="smtp_sink JSONL file; required for the email_reset stage",
    )
    parser.add_argument(
        "--stages",
        default=None,
        help=f"Comma-separated stage subset (default: all of {','.join(STAGE_ORDER)})",
    )
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT, help="Per-request timeout in seconds"
    )
    return parser


def main(
    argv: list[str] | None = None, *, client_factory: Callable[[str], Any] | None = None
) -> int:
    args = build_parser().parse_args(argv)
    stages = [s.strip() for s in args.stages.split(",") if s.strip()] if args.stages else None

    if client_factory is None:
        import httpx

        def _httpx_factory(url: str) -> Any:
            return httpx.Client(base_url=url, timeout=args.timeout, follow_redirects=False)

        client_factory = _httpx_factory

    ctx = SmokeContext(
        make_client=lambda: client_factory(args.base_url.rstrip("/")),
        admin_login=args.admin_login,
        admin_password=args.admin_password,
        sink_path=Path(args.sink) if args.sink else None,
        timeout=args.timeout,
    )
    report = run_smoke(ctx, stages=stages)
    passed = report.checks - len(report.failures)
    verdict = "PASS" if report.ok else "FAIL"
    print(f"SMOKE RESULT: {verdict} — {passed}/{report.checks} checks passed", flush=True)
    if report.failures:
        print("Failures:", flush=True)
        for failure in report.failures:
            print(f"  {failure}", flush=True)
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
