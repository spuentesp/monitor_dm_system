"""Shared helpers for the VtM Embrace session harness.

Provides:
    format_dice_highlight  -- inline dice string for transcript
    utc_timestamp          -- YYYYMMDDTHHMMSSZ for filenames
    setup_logging          -- structlog config
    ping_player_model -- startup smoke check for the player LLM
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog

try:
    import litellm
except ImportError:  # pragma: no cover
    litellm = None  # type: ignore[assignment]


def format_dice_highlight(action: str, dice_result: dict | None) -> str:
    """Render a VtM dice-pool result as an inline transcript highlight.

    Args:
        action: the player's action text (for context).
        dice_result: dict with keys pool_size, successes, botches, results
                     OR None/empty when no roll was needed.

    Returns:
        Empty string if no dice were rolled, else e.g.
        "dice: I leap the fence: 5 dice -> 3 successes (0 botches)"
    """
    if not dice_result:
        return ""
    pool = dice_result.get("pool_size", "?")
    succ = dice_result.get("successes", 0)
    botch = dice_result.get("botches", 0)
    return f"dice: {action}: {pool} dice -> {succ} successes ({botch} botches)"


def utc_timestamp() -> str:
    """Return a filesystem-safe UTC timestamp suitable for filenames."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def setup_logging() -> None:
    """Configure structlog for the harness."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(colors=False),
        ]
    )


async def ping_player_model(model: str = "gemini/gemini-2.5-flash") -> None:
    """Smoke check that the player LLM is reachable. Raises on failure."""
    if litellm is None:
        raise RuntimeError("litellm is not installed")
    resp = await litellm.acompletion(
        model=model,
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=5,
    )
    if not resp or not getattr(resp, "choices", None):
        raise RuntimeError(f"Empty response from {model}")
    content = resp.choices[0].message.content
    if not content or not content.strip():
        raise RuntimeError(
            f"Empty content from {model} (got {content!r}). "
            "Model may be a 'thinking' model that puts reasoning in a separate field."
        )