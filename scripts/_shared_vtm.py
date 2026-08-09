"""Shared helpers for the VtM Embrace session harness.

Provides:
    format_dice_highlight  -- inline dice string for transcript
    utc_timestamp          -- YYYYMMDDTHHMMSSZ for filenames
    setup_logging          -- structlog config
    ping_player_model -- startup smoke check for the player LLM
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import structlog
from dotenv import load_dotenv

# Load .env / .env.tokens if present, so API keys reach os.environ when this
# module is imported via `uv run scripts/vtm_*.py`.
for _env in (Path(__file__).resolve().parent.parent / ".env", Path(__file__).resolve().parent.parent / ".env.tokens"):
    if _env.exists():
        load_dotenv(_env, override=False)

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


async def ping_player_model(
    model: str = "openai/MiniMax-M2.7",
    api_key_env: str = "MINIMAX_KEY",
    api_base: str = "https://api.minimax.io/v1",
) -> None:
    """Smoke check that the player LLM is reachable. Raises on failure."""
    if litellm is None:
        raise RuntimeError("litellm is not installed")
    resp = await litellm.acompletion(
        model=model,
        messages=[{"role": "user", "content": "ping"}],
        max_tokens=5,
        api_key=os.getenv(api_key_env),
        api_base=api_base,
    )
    if not resp or not getattr(resp, "choices", None):
        raise RuntimeError(f"Empty response from {model}")
    msg = resp.choices[0].message
    content = (getattr(msg, "content", None) or "").strip()
    reasoning = (getattr(msg, "reasoning_content", None) or "").strip()
    if not content and not reasoning:
        raise RuntimeError(
            f"Empty content from {model}. Model may be a thinking model "
            "with both content and reasoning_content empty."
        )


def make_minimax_player_spec(
    model: str = "openai/MiniMax-M2.7",
    api_base: str = "https://api.minimax.io/v1",
    api_key_env: str = "MINIMAX_KEY",
    temperature: float = 0.9,
    max_tokens: int = 220,
):
    """Build an InstructedSpec that extracts reasoning_content from thinking models.

    MiniMax-M2.7 (and other M2.7 variants) returns almost-empty `content` and
    puts the actual answer in `reasoning_content`. InstructedSpec reads
    `.content` only, so without this override the player emits only the
    canned fallback line. This shim subclasses InstructedSpec and overrides
    `_invoke_llm` to fall back to reasoning_content when content is empty.
    """
    from monitor_agents.players import InstructedSpec

    class _MiniMaxSpec(InstructedSpec):
        async def _invoke_llm(self, *, messages):
            import os

            resp = await litellm.acompletion(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                api_key=os.getenv(api_key_env),
                api_base=api_base,
            )
            msg = resp.choices[0].message
            content = (getattr(msg, "content", None) or "").strip()
            if content:
                return content
            reasoning = (getattr(msg, "reasoning_content", None) or "").strip()
            if not reasoning:
                return ""
            # Skip meta-reasoning lines. The thinking model often trails the
            # actual answer with instructions-to-self ("Wait, looking at the
            # context...", "Let me respond as the GM..."). Drop any line whose
            # opening suggests it's the model's own internal narration.
            skip_prefixes = (
                "the user", "wait,", "hmm,", "actually,", "let me", "i should",
                "i need", "looking at", "i think", "given ", "in this response",
                "this appears", "this looks", "this seems", "i was given",
                "the scene", "ok,", "okay,", "so the", "but the", "and the",
                "or maybe", "perhaps", "the user is", "it's possible",
                "now there's", "wait -", "wait—",
            )
            kept: list[str] = []
            for ln in reasoning.splitlines():
                s = ln.strip()
                if not s:
                    continue
                low = s.lower()
                if any(low.startswith(p) for p in skip_prefixes):
                    continue
                kept.append(ln)
            # If filtering removed everything, fall back to the last paragraph.
            if not kept:
                tail = reasoning.rsplit("\n\n", 1)[-1].strip()
                return tail or reasoning[-400:]
            return "\n".join(kept[-8:]).strip()

    return _MiniMaxSpec(
        model=model, temperature=temperature, max_tokens=max_tokens,
    )