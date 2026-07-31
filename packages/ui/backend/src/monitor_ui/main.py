"""
MONITOR UI Backend — FastAPI entry point.

Provides REST + WebSocket APIs consumed by the Next.js frontend.
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from monitor_ui.config import get_settings
from monitor_ui.routers import (
    architect,
    canon_review,
    change_log,
    chat,
    databases,
    entities,
    forge,
    game_systems,
    gm_notes,
    gm_tools,
    graph,
    image_gen,
    ingest,
    jobs_health,
    llm_mgmt,
    lorebook,
    modes,
    pack_library,
    parties,
    performance,
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
    except Exception as exc:
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
    except Exception as exc:
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
    except Exception as exc:
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
    except Exception as exc:
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
    except Exception as exc:
        logger.warning("Could not stop StaleJobWatchdog: %s", exc)


def get_jobs_collection():  # type: ignore
    """Accessor for routers/jobs_health.py — returns the live
    ``ingestion_jobs`` collection."""
    from monitor_data.db.mongodb import get_mongodb_client

    return get_mongodb_client().get_collection("ingestion_jobs")


@asynccontextmanager
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

    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
    app.include_router(modes.router, prefix="/api/modes", tags=["modes"])
    app.include_router(ingest.router, prefix="/api/ingest", tags=["ingest"])
    app.include_router(llm_mgmt.router, prefix="/api/llm", tags=["llm"])
    app.include_router(databases.router, prefix="/api/databases", tags=["databases"])
    app.include_router(entities.router, prefix="/api/entities", tags=["entities"])
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
    app.include_router(templates.router, prefix="/api", tags=["templates"])
    app.include_router(gm_tools.router, prefix="/api", tags=["gm-tools"])
    app.include_router(gm_notes.router, prefix="/api", tags=["gm-notes"])
    app.include_router(lorebook.router, prefix="/api", tags=["lorebook"])
    app.include_router(canon_review.router, prefix="/api", tags=["canon-review"])
    app.include_router(jobs_health.router, prefix="/api", tags=["ingestion-jobs"])
    app.include_router(parties.router, prefix="/api/parties", tags=["parties"])
    app.include_router(change_log.router, prefix="/api", tags=["change-log"])
    app.include_router(play_sessions.router, prefix="/api", tags=["play-sessions"])
    app.include_router(architect.router, prefix="/api", tags=["architect"])

    @app.get("/api/health")
    async def health(deep: bool = False) -> dict:  # type: ignore
        """Liveness by default; ``?deep=true`` aggregates component health."""
        payload: dict = {  # type: ignore
            "status": "ok",
            "service": "monitor-ui-backend",
            "version": "0.1.0",
        }
        if deep:
            try:
                from monitor_ui.routers.databases import get_all_status

                statuses = await get_all_status()
                payload["components"] = {s.db_type: s.status for s in statuses}
                if any(s.status != "online" for s in statuses):
                    payload["status"] = "degraded"
            except Exception as exc:
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
