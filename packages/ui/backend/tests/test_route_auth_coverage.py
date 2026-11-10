"""Route auth coverage for the MONITOR UI backend.

Every route the app registers in ``monitor_ui.main`` must be authenticated:
either it carries an auth dependency (router-level or route-level, as
``monitor_ui.auth`` and ``monitor_ui.ownership`` define them) or it appears
in the explicit public allowlist below.

The allowlist is a literal in this module, so making a route public is a
deliberate, reviewable edit rather than something that happens by omission.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute, APIWebSocketRoute
from fastapi.testclient import TestClient
from fake_postgres import FakePostgres

from monitor_ui import auth as auth_mod
from monitor_ui import ownership as ownership_mod
from monitor_ui.auth import get_postgres
from monitor_ui.config import get_settings
from monitor_ui.main import create_app

# Dependencies that authenticate a caller. A route counts as guarded when its
# dependency tree contains one of them — FastAPI folds the router's
# ``dependencies=[...]`` and the route's own into a single tree, so one
# lookup covers router level, route level and the endpoint signature.
AUTH_DEPENDENCIES: frozenset[Any] = frozenset(
    {
        auth_mod.get_current_user,
        auth_mod.get_current_ws_principal,
        auth_mod.require_admin,
        ownership_mod.resource_route_guard,
    }
)

# Routes that are public on purpose, keyed by (path, method). Every entry
# states why it is public so the list cannot grow silently.
PUBLIC_ROUTES: dict[tuple[str, str], str] = {
    ("/api/auth/config", "GET"): ("Public auth capabilities (which providers are enabled). No private data."),
    ("/api/auth/login", "POST"): "Login has to be reachable without a session.",
    ("/api/auth/signup", "POST"): "Signup has to be reachable without a session.",
    ("/api/auth/oauth/google", "GET"): ("OAuth start: redirects to the provider, so there is no session yet."),
    ("/api/auth/oauth/google/callback", "GET"): (
        "OAuth callback: the provider calls it, not a session-holding browser."
    ),
    ("/api/health", "GET"): ("Liveness probe. ?deep=true performs its own admin check inside the handler."),
}

# Every router the app registers, as a path prefix. A build that lost a
# router would otherwise slip past the coverage check with fewer routes.
EXPECTED_PREFIXES: tuple[str, ...] = (
    "/api/admin",
    "/api/architect",
    "/api/auth",
    "/api/canon-review",
    "/api/change-log",
    "/api/chat",
    "/api/databases",
    "/api/entities",
    "/api/forge",
    "/api/gm",
    "/api/graph",
    "/api/health",
    "/api/image",
    "/api/ingest",
    "/api/jobs",
    "/api/llm",
    "/api/lorebook",
    "/api/modes",
    "/api/parties",
    "/api/performance",
    "/api/play-sessions",
    "/api/prompt-collections",
    "/api/prompts",
    "/api/random-tables",
    "/api/scenes",
    "/api/search",
    "/api/stories",
    "/api/systems",
    "/api/templates",
    "/api/tone",
    "/api/universes",
    "/api/v1",
)


def _routes(app: FastAPI) -> list[tuple[Any, str, tuple[str, ...]]]:
    """Every HTTP and WebSocket route the app registered."""
    found: list[tuple[Any, str, tuple[str, ...]]] = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            methods = tuple(sorted(m for m in (route.methods or set()) if m != "HEAD"))
            found.append((route, route.path, methods))
        elif isinstance(route, APIWebSocketRoute):
            found.append((route, route.path, ("WEBSOCKET",)))
    return found


def _dependency_calls(route: Any) -> set[Any]:
    """Every callable in the route's dependency tree.

    FastAPI merges the router's ``dependencies=[...]`` into every route it
    registers, and a route-level ``Depends(get_current_user)`` becomes a
    child of the route's own dependant. Walking the tree therefore covers
    router level, route level and the endpoint signature at once — and it
    also finds a guard that is reached through a wrapper dependency.
    """
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return set()
    calls: set[Any] = set()
    stack = [dependant]
    while stack:
        current = stack.pop()
        for sub in current.dependencies:
            calls.add(sub.call)
            stack.append(sub)
    return calls


@pytest.fixture(scope="module")
def app() -> FastAPI:
    """The app exactly as ``monitor_ui.main`` builds it."""
    return create_app()


def test_app_registers_the_full_route_surface(app: FastAPI) -> None:
    """No router may silently disappear from the registered surface."""
    paths = {path for _, path, _ in _routes(app)}
    missing = [
        prefix
        for prefix in EXPECTED_PREFIXES
        if not any(path == prefix or path.startswith(prefix + "/") for path in paths)
    ]
    assert not missing, f"no route registered under: {', '.join(missing)}"


def test_every_route_is_authenticated_or_public(app: FastAPI) -> None:
    """No route may be reachable without a credential and without a reason."""
    unguarded: list[str] = []
    for route, path, methods in _routes(app):
        if _dependency_calls(route) & AUTH_DEPENDENCIES:
            continue
        if any((path, method) in PUBLIC_ROUTES for method in methods):
            continue
        unguarded.append(f"{','.join(methods):<12} {path}")
    assert not unguarded, "Routes with no auth dependency and no PUBLIC_ROUTES entry:\n" + "\n".join(sorted(unguarded))


def test_public_allowlist_has_no_stale_entries(app: FastAPI) -> None:
    """The allowlist must not keep entries for routes that no longer exist."""
    registered = {(path, method) for _, path, methods in _routes(app) for method in methods}
    stale = sorted(f"{method} {path}" for path, method in PUBLIC_ROUTES if (path, method) not in registered)
    assert not stale, "PUBLIC_ROUTES entries without a registered route:\n" + "\n".join(stale)


def test_public_allowlist_entries_state_why() -> None:
    """Every allowlist entry carries the reason the route is public."""
    unjustified = sorted(f"{method} {path}" for (path, method), reason in PUBLIC_ROUTES.items() if not reason.strip())
    assert not unjustified, "PUBLIC_ROUTES entries without a reason:\n" + "\n".join(unjustified)


def test_public_allowlist_has_no_destructive_methods() -> None:
    """A public DELETE/PUT/PATCH would let anyone mutate state."""
    destructive = sorted(f"{method} {path}" for path, method in PUBLIC_ROUTES if method in {"DELETE", "PUT", "PATCH"})
    assert not destructive, "PUBLIC_ROUTES entries with a destructive method:\n" + "\n".join(destructive)


def test_public_allowlist_entries_are_really_public(app: FastAPI) -> None:
    """An allowlisted route must not carry an auth dependency.

    Otherwise the entry is misleading: the route would ask for a credential
    and the allowlist would claim it does not.
    """
    guarded = sorted(
        f"{method} {path}"
        for path, method in PUBLIC_ROUTES
        if any(
            _dependency_calls(route) & AUTH_DEPENDENCIES
            for route, route_path, methods in _routes(app)
            if route_path == path and method in methods
        )
    )
    assert not guarded, "PUBLIC_ROUTES entries that carry an auth dependency:\n" + "\n".join(guarded)


def test_websocket_route_is_guarded(app: FastAPI) -> None:
    """The chat WebSocket authenticates its handshake through a dependency.

    The WebSocket surface cannot answer with an HTTP status code, so the
    guard has to be a dependency that closes the socket — not an inline
    check the route-coverage walk could not see.
    """
    websocket_routes = [(route, path) for route, path, _ in _routes(app) if path.endswith("/ws/{session_id}")]
    assert websocket_routes, "the chat WebSocket route is gone"
    for route, path in websocket_routes:
        assert _dependency_calls(route) & AUTH_DEPENDENCIES, path


@pytest.fixture(scope="module")
def anon_client() -> Iterator[TestClient]:
    """A client with authentication enabled and no credentials."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("MONITOR_AUTH_DISABLED", "false")
        mp.setenv("AUTH_COOKIE_SECURE", "false")
        get_settings.cache_clear()
        anon_app = create_app()
        fake = FakePostgres()

        async def _fake_get_postgres() -> FakePostgres:
            return fake

        anon_app.dependency_overrides[get_postgres] = _fake_get_postgres
        yield TestClient(anon_app)
        anon_app.dependency_overrides.pop(get_postgres, None)
        get_settings.cache_clear()


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/auth/me"),
        ("GET", "/api/databases"),
        ("GET", "/api/entities/npcs"),
        ("GET", "/api/chat"),
        ("GET", "/api/ingest/jobs"),
    ],
)
def test_guarded_route_rejects_an_anonymous_caller(anon_client: TestClient, method: str, path: str) -> None:
    """A route with an auth dependency answers 401 without credentials."""
    response = anon_client.request(method, path)
    assert response.status_code == 401, (method, path, response.status_code, response.text)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/chat/benchmarks"),
        ("GET", "/api/ingest/assets"),
        ("GET", "/api/ingest/assets/abc"),
        ("DELETE", "/api/ingest/assets/abc"),
        ("GET", "/api/ingest/jobs/abc/stream"),
        ("DELETE", "/api/ingest/jobs/abc"),
        ("DELETE", "/api/ingest/jobs"),
        ("POST", "/api/ingest/cache/clear"),
    ],
)
def test_newly_guarded_routes_reject_an_anonymous_caller(anon_client: TestClient, method: str, path: str) -> None:
    """The routes this change closed answer 401 without credentials."""
    response = anon_client.request(method, path)
    assert response.status_code == 401, (method, path, response.status_code, response.text)


def test_asset_upload_routes_reject_an_anonymous_caller(anon_client: TestClient) -> None:
    """The binary-asset upload routes answer 401 without credentials."""
    for path in ("/api/ingest/assets/upload", "/api/ingest/assets/abc/replace"):
        response = anon_client.post(path, files={"file": ("a.txt", b"x")})
        assert response.status_code == 401, (path, response.status_code, response.text)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/auth/config"),
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/signup"),
        ("GET", "/api/auth/oauth/google"),
        ("GET", "/api/auth/oauth/google/callback"),
        ("GET", "/api/health"),
    ],
)
def test_public_routes_stay_reachable_without_credentials(anon_client: TestClient, method: str, path: str) -> None:
    """The allowlisted routes do not demand a credential.

    The exact status differs per route (200, a validation error, a redirect
    or "not configured"), so the check is that none of them answers 401/403.
    """
    response = anon_client.request(method, path)
    assert response.status_code not in (401, 403), (method, path, response.status_code, response.text)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/auth/config"),
        ("GET", "/api/health"),
    ],
)
def test_public_read_routes_answer_200(anon_client: TestClient, method: str, path: str) -> None:
    """The public read routes answer with their payload, not an error."""
    response = anon_client.request(method, path)
    assert response.status_code == 200, (method, path, response.status_code, response.text)
