"""
MONITOR UI Backend — FastAPI entry point.

Provides REST + WebSocket APIs consumed by the Next.js frontend.
"""

import logging
import os
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from monitor_data.db.postgres import get_postgres_client
from monitor_data.security import new_csrf_token
from monitor_data.tenancy import OwnerViolationError
from monitor_data.usage import QuotaExceededError

from monitor_ui.auth import get_optional_principal
from monitor_ui.config import get_settings
from monitor_ui.routers import (
    admin,
    architect,
    auth,
    canon_review,
    change_log,
    character_promotion,
    character_templates,
    chat,
    databases,
    entities,
    forge,
    game_systems,
    gm_notes,
    gm_tools,
    graph,
    image_assets,
    image_gen,
    ingest,
    jobs_health,
    light_rp,
    llm_mgmt,
    lorebook,
    modes,
    openai_compat,
    pack_library,
    parties,
    performance,
    player_view,
    play_sessions,
    prompt_collections,
    prompts,
    random_tables,
    search,
    stories,
    templates,
    tone,
    universes,
)


def _load_tokens_env() -> None:
    """Load .env.tokens if present (API keys stored separately for security)."""
    # main.py is at packages/ui/backend/src/monitor_ui/main.py — go up 5 levels to repo root
    tokens_file = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", ".env.tokens")
    if os.path.exists(tokens_file):
        load_dotenv(tokens_file, override=True)
    load_dotenv()


logger = logging.getLogger(__name__)


def _startup_runtime() -> None:
    from monitor_data.initialization.ensure_tone_builtins import ensure_tone_builtins

    if get_settings().monitor_auth_disabled:
        logger.warning(
            "MONITOR_AUTH_DISABLED=true — authentication is DISABLED and every request "
            "resolves to the fixed local admin account. This is a local-development "
            "exception only; never run it on a reachable host."
        )
    # Provider-key encryption: warns (once) when MONITOR_PROVIDER_KEY_ENCRYPTION_KEY
    # is unset so plaintext storage is a deliberate, visible state.
    from monitor_data.db.postgres import ensure_provider_key_crypto_ready

    ensure_provider_key_crypto_ready()
    ingest.prepare_ingest_runtime()
    _recover_stale_jobs()
    ensure_tone_builtins()
    _ensure_builtin_game_systems()
    _start_watchdog_if_enabled()


def _start_watchdog_if_enabled() -> None:
    """Spin up the stale-job watchdog if MONITOR_INGEST_WATCHDOG_ENABLED=1.

    Disabled by default; operators opt in. The watchdog is per-process,
    so each uvicorn worker gets its own — that is acceptable because
    the operation is idempotent (failing a stale job is monotonic).
    """
    enabled = os.environ.get("MONITOR_INGEST_WATCHDOG_ENABLED", "0").lower() in (
        "true",
        "1",
        "yes",
    )
    if not enabled:
        logger.info("StaleJobWatchdog: disabled (set MONITOR_INGEST_WATCHDOG_ENABLED=1 to enable)")
        return
    try:
        import asyncio

        from monitor_data.db.mongodb import get_mongodb_client

        from monitor_ui.watchdog import StaleJobWatchdog, set_watchdog

        # reason: bare factory returned to StaleJobWatchdog whose expected signature is Callable[[], Collection]; the dynamic-dispatch watchdog consumer accepts any zero-arg callable — narrow to a typed factory in a follow-up
        def _get_collection():  # type: ignore
            return get_mongodb_client().get_collection("ingestion_jobs")

        wd = StaleJobWatchdog(get_collection=_get_collection)
        set_watchdog(wd)
        # FastAPI lifespan runs inside an asyncio loop already; schedule
        # the watchdog task on that loop without blocking startup.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("StaleJobWatchdog: no running event loop in lifespan; watchdog will not start.")
            return
        loop.create_task(wd.start())
        logger.info("StaleJobWatchdog: scheduled start on running loop")
    except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _get_collection)
        logger.warning("Could not start StaleJobWatchdog: %s", exc)


def _ensure_builtin_game_systems() -> None:
    """Seed built-in game systems (incl. 'Mistlands Core') on startup.

    Without this the systems are only seeded lazily (via playtest benchmarks),
    so on a fresh DB demo-world / quick-world look up 'Mistlands Core', find
    nothing, and the modular system binding silently no-ops. Idempotent (atomic
    upsert per system), so safe to run every boot.
    """
    try:
        from monitor_data.tools.mongodb_tools import _ensure_builtin_systems_seeded

        _ensure_builtin_systems_seeded()
    except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _ensure_builtin_game_systems)
        logger.warning("Could not seed built-in game systems on startup: %s", exc)


def _recover_stale_jobs() -> None:
    """Mark orphaned pending/running ingestion jobs as failed on startup.

    Called on startup. The UI backend's OWN ingest queue lives in memory, so
    a job launched through it and left `pending`/`running` after a restart
    is genuinely orphaned. But `status=running` in Mongo does not by itself
    mean the job belongs to THIS backend's queue -- the CLI's
    `monitor ingest file` runs a job in a completely separate OS process
    with no relationship to this backend's lifecycle. Live bug 2026-07-22:
    starting this server while a CLI ingest was seconds into a real run
    immediately killed it, because this function used to mark every
    running/pending job as failed unconditionally.

    Reuses the periodic StaleJobWatchdog's own staleness threshold and
    field-fallback (stage_last_progress_at, falling back to started_at) so
    a job only gets recovered here if it would ALSO look orphaned to that
    watchdog -- not merely because it happened to be running at boot.
    """
    try:
        from monitor_data.db.mongodb import get_mongodb_client

        from monitor_ui.watchdog import _DEFAULT_STALE_AFTER_SECONDS

        cutoff = datetime.now(UTC) - timedelta(seconds=_DEFAULT_STALE_AFTER_SECONDS)
        mongodb = get_mongodb_client()
        result = mongodb.get_collection("ingestion_jobs").update_many(
            {
                "status": {"$in": ["pending", "running"]},
                "$or": [
                    {"stage_last_progress_at": {"$lt": cutoff}},
                    {
                        "stage_last_progress_at": {"$exists": False},
                        "started_at": {"$lt": cutoff},
                    },
                ],
            },
            {
                "$set": {
                    "status": "failed",
                    "errors": ["Process was interrupted; server restarted while the job was queued or running"],
                    "completed_at": datetime.now(UTC),
                }
            },
        )
        if result.modified_count:
            logger.warning(
                "Recovered %d stale pending/running ingestion job(s) → marked failed",
                result.modified_count,
            )
    except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _recover_stale_jobs)
        logger.warning("Could not recover stale jobs on startup: %s", exc)


def _shutdown_runtime() -> None:
    try:
        summary = ingest.shutdown_ingest_runtime()
        logger.info(
            "Runtime shutdown cleanup finished (active=%d, pending=%d, recovered=%d)",
            summary["cleared_active"],
            summary["cleared_pending"],
            summary["recovered_jobs"],
        )
    except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _shutdown_runtime)
        logger.warning("Could not finish runtime shutdown cleanup: %s", exc)
    _stop_watchdog()


def _stop_watchdog() -> None:
    try:
        import asyncio

        from monitor_ui.watchdog import get_watchdog

        wd = get_watchdog()
        if wd is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(wd.stop())
    except Exception as exc:  # noqa: BLE001  # reason: boundary logs and degrades gracefully (in _stop_watchdog)
        logger.warning("Could not stop StaleJobWatchdog: %s", exc)


# reason: bare accessor exposed at module scope; FastAPI routers consume it via jobs_health.Depends without an explicit return-annotation hook — narrow the signature to AsyncIOMotorCollection in a follow-up
def get_jobs_collection():  # type: ignore
    """Accessor for routers/jobs_health.py — returns the live
    ``ingestion_jobs`` collection."""
    from monitor_data.db.mongodb import get_mongodb_client

    return get_mongodb_client().get_collection("ingestion_jobs")


@asynccontextmanager
# reason: FastAPI lifespan ASGI handler — FastAPI's lifespan parameter is typed AsyncIterator but the @asynccontextmanager decorator returns AsyncContextManager; mypy can't reconcile the two without an explicit cast
async def lifespan(app: FastAPI):  # type: ignore
    _startup_runtime()
    try:
        yield
    finally:
        _shutdown_runtime()


def create_app() -> FastAPI:
    # Load .env.tokens if present (separate from .env for security)
    _load_tokens_env()
    settings = get_settings()

    app = FastAPI(
        title="MONITOR UI API",
        version="0.1.0",
        description="Backend API for the MONITOR web interface",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _csrf_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Double-submit CSRF + origin check for cookie-authenticated unsafe requests.

        Applies to every unsafe method when the request could be cookie-
        authenticated — including login/signup (login-CSRF hardening): a CSRF
        cookie is issued on safe-method responses so a browser always has one
        before the first unsafe call. Bearer/API-token requests are not
        cookie-authenticated and skip. In auth-disabled local mode there are
        no cookies and this passes through.
        """
        settings = get_settings()
        if settings.monitor_auth_disabled:
            return await call_next(request)
        if request.method in ("GET", "HEAD", "OPTIONS"):
            response = await call_next(request)
            # Issue the double-submit cookie on safe responses when absent, so
            # the very first login/signup POST already carries a token pair.
            if settings.auth_csrf_cookie not in request.cookies:
                response.set_cookie(
                    key=settings.auth_csrf_cookie,
                    value=new_csrf_token(),
                    max_age=settings.auth_session_ttl_hours * 3600,
                    httponly=False,
                    secure=settings.cookie_secure,
                    samesite="lax",
                    path="/",
                )
            return response
        has_bearer = request.headers.get("authorization", "").lower().startswith("bearer ")
        if has_bearer:
            # Bearer/API-token clients are not cookie-authenticated.
            return await call_next(request)
        # Origin check for EVERY unsafe method, including login/signup:
        # browsers always send Origin on cross-site POSTs, so this blocks
        # login-CSRF even though those endpoints cannot require a pre-existing
        # CSRF cookie. Non-browser clients send no Origin/Referer and pass.
        allowed = settings.cors_origins_list
        origin = request.headers.get("origin")
        if origin is not None:
            if origin not in allowed:
                return JSONResponse({"detail": "Cross-origin request rejected."}, status_code=403)
        else:
            referer = request.headers.get("referer")
            if referer is not None and not any(referer == o or referer.startswith(o + "/") for o in allowed):
                return JSONResponse({"detail": "Cross-origin request rejected."}, status_code=403)
        # Double-submit required once a session cookie is present (any state
        # change on an authenticated session). Safe GETs above always issue
        # the CSRF cookie, so browser flows have the pair from the first load.
        if settings.auth_session_cookie in request.cookies:
            csrf_cookie = request.cookies.get(settings.auth_csrf_cookie, "")
            csrf_header = request.headers.get(settings.auth_csrf_header, "")
            if not csrf_cookie or not secrets.compare_digest(csrf_cookie, csrf_header):
                return JSONResponse({"detail": "Missing or invalid CSRF token."}, status_code=403)
        return await call_next(request)

    @app.middleware("http")
    async def _security_headers_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Baseline security headers on every response (API surface only)."""
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    # --- Multi-tenancy error mapping (defense in depth) ---------------------
    # A write refused at the tool boundary (a missed HTTP guard) answers the
    # same generic 404 as the guards (plan D4), and an owner over their daily
    # model budget answers a readable 429.

    @app.exception_handler(OwnerViolationError)
    async def _owner_violation_handler(request: Request, exc: OwnerViolationError) -> JSONResponse:
        logging.getLogger(__name__).warning("owner violation refused: %s (%s)", exc, request.url.path)
        return JSONResponse({"detail": "Not found"}, status_code=404)

    @app.exception_handler(QuotaExceededError)
    async def _quota_exceeded_handler(request: Request, exc: QuotaExceededError) -> JSONResponse:
        return JSONResponse({"detail": exc.user_message}, status_code=429)

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
    app.include_router(chat.ws_router, prefix="/api/chat", tags=["chat"])
    app.include_router(modes.router, prefix="/api/modes", tags=["modes"])
    app.include_router(ingest.router, prefix="/api/ingest", tags=["ingest"])
    app.include_router(llm_mgmt.router, prefix="/api/llm", tags=["llm"])
    app.include_router(databases.router, prefix="/api/databases", tags=["databases"])
    app.include_router(entities.router, prefix="/api/entities", tags=["entities"])
    app.include_router(character_templates.router, prefix="/api/characters", tags=["character-templates"])
    app.include_router(search.router, prefix="/api/search", tags=["search"])
    app.include_router(universes.router, prefix="/api/universes", tags=["universes"])
    app.include_router(graph.router, prefix="/api/graph", tags=["graph"])
    app.include_router(prompts.router, prefix="/api/prompts", tags=["prompts"])
    app.include_router(prompt_collections.router, prefix="/api", tags=["prompt-collections"])
    app.include_router(game_systems.router, prefix="/api", tags=["game-systems"])
    app.include_router(performance.router, prefix="/api", tags=["performance"])
    app.include_router(pack_library.router, prefix="/api/ingest", tags=["pack-library"])
    app.include_router(random_tables.router, prefix="/api", tags=["random-tables"])
    app.include_router(tone.router, prefix="/api/tone", tags=["tone"])
    app.include_router(stories.router, prefix="/api/stories", tags=["stories"])
    app.include_router(stories.scenes_router, prefix="/api", tags=["scenes"])
    app.include_router(forge.router, prefix="/api/forge", tags=["forge"])
    app.include_router(image_gen.router, prefix="/api/image", tags=["image"])
    app.include_router(image_assets.router, prefix="/api/image", tags=["image"])
    app.include_router(templates.router, prefix="/api", tags=["templates"])
    app.include_router(gm_tools.router, prefix="/api", tags=["gm-tools"])
    app.include_router(gm_notes.router, prefix="/api", tags=["gm-notes"])
    app.include_router(lorebook.router, prefix="/api", tags=["lorebook"])
    app.include_router(canon_review.router, prefix="/api", tags=["canon-review"])
    app.include_router(jobs_health.router, prefix="/api", tags=["ingestion-jobs"])
    app.include_router(parties.router, prefix="/api/parties", tags=["parties"])
    app.include_router(change_log.router, prefix="/api", tags=["change-log"])
    app.include_router(play_sessions.router, prefix="/api", tags=["play-sessions"])
    app.include_router(player_view.router, prefix="/api", tags=["player-share"])
    app.include_router(architect.router, prefix="/api", tags=["architect"])
    # OpenAI-compatible /v1/chat/completions — points RisuAI / SillyTavern /
    # LiteLLM at MONITOR. Session mode keeps conversation state on the server.
    app.include_router(openai_compat.router, prefix="/api", tags=["openai-compat"])
    # Character → canon promotion (light-RP history → ProposedChange batch).
    app.include_router(character_promotion.router, prefix="/api/entities", tags=["character-promotion"])
    # Light RP (Phase 7): one-click start, streaming send, memories view,
    # graduate-to-campaign. Mounted beside entities for the same URL family.
    app.include_router(light_rp.router, prefix="/api/entities", tags=["light-rp"])

    @app.get("/api/health")
    # reason: FastAPI route handler returns dict but response_model is absent; FastAPI/Pydantic v2 returns Any for the inferred response without an Annotated[] response_model
    async def health(request: Request, deep: bool = False) -> dict:  # type: ignore
        """Liveness by default; ``?deep=true`` aggregates component health (operator-only)."""
        # reason: FastAPI/Pydantic v2 returns Any for dynamic dict-literal payload built up under conditional branches; mypy can't narrow without an explicit Pydantic model
        payload: dict = {  # type: ignore
            "status": "ok",
            "service": "monitor-ui-backend",
            "version": "0.1.0",
        }
        if deep:
            # Deep component status is operator-only (plan §5.3): it discloses
            # which databases are reachable. Liveness stays public. The Postgres
            # client is resolved lazily so liveness never depends on the DB.
            settings = get_settings()
            db = get_postgres_client()
            await db.connect()
            principal = await get_optional_principal(request, settings, db)
            if principal is None:
                raise HTTPException(status_code=401, detail="Not authenticated")
            if not principal.is_admin:
                raise HTTPException(status_code=403, detail="Admin access required")
            try:
                from monitor_ui.routers.databases import get_all_status

                statuses = await get_all_status()
                payload["components"] = {s.db_type: s.status for s in statuses}
                if any(s.status != "online" for s in statuses):
                    payload["status"] = "degraded"
            except Exception as exc:  # noqa: BLE001  # reason: intentional boundary: documented failure tolerance (in health)
                payload["status"] = "degraded"
                payload["components_error"] = str(exc)
        return payload

    return app


app = create_app()


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "monitor_ui.main:app",
        host=settings.ui_host,
        port=settings.ui_port,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()
