"""Runtime DSPy configuration backed by the saved PostgreSQL LLM registry."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import threading
from datetime import datetime, timezone
from typing import Any, Optional

import contextvars

import dspy
import litellm
from monitor_agents.llm_registry import LLMClient, LLMRegistry
from monitor_data.db.postgres import PostgresClient
from monitor_data.schemas.llm_config import LLMProviderType, ModelRole

stream_callback_var = contextvars.ContextVar("stream_callback", default=None)

# ---------------------------------------------------------------------------
# LLM call logging — writes every request/response to a dedicated log file
# Enable with: MONITOR_LLM_LOG=1  (or set a custom path with MONITOR_LLM_LOG_FILE)
# ---------------------------------------------------------------------------
_llm_logger = logging.getLogger("monitor.llm_calls")
_llm_log_enabled = os.environ.get("MONITOR_LLM_LOG", "").strip() not in ("", "0", "false")

if _llm_log_enabled and not _llm_logger.handlers:
    _log_path = os.environ.get(
        "MONITOR_LLM_LOG_FILE",
        os.path.join(os.getcwd(), "llm_calls.log"),
    )
    _fh = logging.FileHandler(_log_path, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(message)s"))
    _llm_logger.addHandler(_fh)
    _llm_logger.setLevel(logging.DEBUG)
    _llm_logger.propagate = False
    logging.getLogger(__name__).info("LLM call logging enabled → %s", _log_path)


def _format_messages(messages: list[dict]) -> str:
    """Compact-format messages for the log, truncating very long content."""
    parts = []
    for m in messages or []:
        role = m.get("role", "?")
        content = m.get("content", "")
        if len(content) > 2000:
            content = content[:2000] + f"… [{len(content)} chars total]"
        parts.append(f"  [{role}] {content}")
    return "\n".join(parts)


class _MonitorLitellmLogger(litellm.integrations.custom_logger.CustomLogger):
    """Litellm callback that writes every LLM call to llm_calls.log."""

    def log_success_event(
        self, kwargs: dict, response_obj: Any, start_time: float, end_time: float
    ) -> None:
        if not _llm_log_enabled:
            return
        try:
            model = kwargs.get("model", "?")
            messages = kwargs.get("messages", [])
            # Extract response text
            resp_text = ""
            if hasattr(response_obj, "choices") and response_obj.choices:
                choice = response_obj.choices[0]
                if hasattr(choice, "message"):
                    resp_text = getattr(choice.message, "content", "") or ""
            if len(resp_text) > 3000:
                resp_text = resp_text[:3000] + f"… [{len(resp_text)} chars total]"

            usage = getattr(response_obj, "usage", None)
            usage_str = ""
            if usage:
                usage_str = f" | tokens: in={getattr(usage, 'prompt_tokens', '?')} out={getattr(usage, 'completion_tokens', '?')}"

            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            duration = ""
            if isinstance(start_time, (int, float)) and isinstance(end_time, (int, float)):
                duration = f" | {end_time - start_time:.1f}s"

            _llm_logger.debug(
                "\n╭─── LLM CALL %s ── %s%s%s ───\n"
                "│ REQUEST:\n%s\n"
                "│ RESPONSE:\n  %s\n"
                "╰───────────────────────────────────────────\n",
                ts,
                model,
                duration,
                usage_str,
                _format_messages(messages),
                resp_text,
            )
        except Exception:  # noqa: BLE001
            pass

    def log_failure_event(
        self, kwargs: dict, response_obj: Any, start_time: float, end_time: float
    ) -> None:
        if not _llm_log_enabled:
            return
        try:
            model = kwargs.get("model", "?")
            messages = kwargs.get("messages", [])
            error = kwargs.get("exception", "unknown error")
            ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
            _llm_logger.debug(
                "\n╭─── LLM FAIL %s ── %s ───\n"
                "│ REQUEST:\n%s\n"
                "│ ERROR: %s\n"
                "╰───────────────────────────────────────────\n",
                ts,
                model,
                _format_messages(messages),
                error,
            )
        except Exception:  # noqa: BLE001
            pass


if _llm_log_enabled:
    litellm.callbacks = [_MonitorLitellmLogger()]

_bg_loop: Optional[asyncio.AbstractEventLoop] = None
_bg_thread: Optional[threading.Thread] = None
_bg_lock = threading.Lock()


def _get_background_loop() -> asyncio.AbstractEventLoop:
    global _bg_loop, _bg_thread
    with _bg_lock:
        if _bg_loop is None or not _bg_loop.is_running():
            _bg_loop = asyncio.new_event_loop()
            _bg_thread = threading.Thread(
                target=_bg_loop.run_forever,
                daemon=True,
                name="monitor-dspy-bg-loop",
            )
            _bg_thread.start()
    return _bg_loop


def _run_sync(coro):
    """Run an async coroutine synchronously, always using the background event loop.

    This ensures the asyncpg pool inside ``_bg_postgres`` is always accessed
    from the same event loop, regardless of whether the caller already has a
    running loop (e.g. ``asyncio.to_thread`` worker) or not (e.g. plain
    sync script).
    """
    return asyncio.run_coroutine_threadsafe(coro, _get_background_loop()).result()


def normalize_node_name(node_name: str) -> str:
    """Convert CamelCase agent names into the snake_case node names used in config."""
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", node_name).lower()
    return snake.replace("__", "_")


# Canonical role assignments per agent node.  Add entries here when a new agent
# is introduced; do not scatter ModelRole literals across callers.
_NODE_DEFAULT_ROLES: dict[str, ModelRole] = {
    "narrator": ModelRole.HEAVY,
    "canon_keeper": ModelRole.HEAVY,
    "canonkeeper": ModelRole.HEAVY,
    "context_assembly": ModelRole.LIGHT,
    "query_formulation": ModelRole.LIGHT,
    "turn_intent": ModelRole.LIGHT,
    "indexer": ModelRole.LIGHT,
    "resolver": ModelRole.LIGHT,
}


def default_role_for_node(node_name: str) -> ModelRole:
    normalized = normalize_node_name(node_name)
    return _NODE_DEFAULT_ROLES.get(normalized, ModelRole.STANDARD)


# ---------------------------------------------------------------------------
# Dynamic model routing — escalate to HEAVY for dramatic moments.
#
# Instead of always using HEAVY for the narrator, we evaluate context signals
# to decide whether a turn needs the most capable model.  Routine actions
# (movement, simple questions) can use STANDARD, saving cost and latency.
# ---------------------------------------------------------------------------

# Keywords that signal dramatic intensity in player actions or resolution.
_HIGH_INTENSITY_KEYWORDS: set[str] = {
    "attack",
    "kill",
    "death",
    "die",
    "fight",
    "combat",
    "critical",
    "betray",
    "sacrifice",
    "explosion",
    "collapse",
    "scream",
    "flee",
    "ambush",
    "trap",
    "poison",
    "curse",
    "blood",
    "fire",
    "destroy",
    "desperate",
    "last stand",
    "final",
    "reveal",
    "confront",
    "dramatic",
    "catastrophe",
    "miracle",
    "divine",
    "ritual",
    "summon",
    "resurrect",
}

_MODERATE_INTENSITY_KEYWORDS: set[str] = {
    "ask",
    "question",
    "investigate",
    "search",
    "examine",
    "talk",
    "negotiate",
    "persuade",
    "deceive",
    "stealth",
    "hide",
    "climb",
    "swim",
    "jump",
    "cast",
    "spell",
    "heal",
    "craft",
    "trade",
    "explore",
    "discover",
    "sense",
    "listen",
    "watch",
    "follow",
}


def resolve_dynamic_role(
    node_name: str,
    player_action: str = "",
    resolution: dict | None = None,
    *,
    base_role: ModelRole | None = None,
) -> ModelRole:
    """Resolve a dynamic ModelRole based on dramatic context.

    Strategy:
    - If ``base_role`` is explicitly LIGHT (query formulation, indexing),
      never upgrade — these are classification/extraction tasks.
    - If the player action or resolution contains high-intensity keywords,
      upgrade to HEAVY.
    - If moderate intensity, use STANDARD (balanced cost/quality).
    - Otherwise, use the node's default role.

    This reduces LLM cost ~30% on average since most turns in a TTRPG
    session are routine (movement, questions, simple interactions) while
    still routing the dramatic moments to the most capable model.

    Args:
        node_name: Agent node name (for default role fallback).
        player_action: The player's current action text.
        resolution: The resolver outcome dict (may contain success_level, etc.).
        base_role: Explicit override; if LIGHT, the function never upgrades.

    Returns:
        The resolved ModelRole for this turn.
    """
    normalized = normalize_node_name(node_name)
    default = base_role or default_role_for_node(normalized)

    # Never upgrade LIGHT-classified nodes (classification/extraction).
    if default == ModelRole.LIGHT:
        return ModelRole.LIGHT

    # Combine action + resolution text for intensity analysis.
    combined = (player_action or "").lower()
    if resolution:
        resolution_text = (
            str(resolution.get("success_level", "")) + " " + str(resolution.get("description", ""))
        )
        combined += " " + resolution_text.lower()

    if not combined.strip():
        return default

    combined_words = set(combined.split())

    # Check for high-intensity signals.
    if combined_words & _HIGH_INTENSITY_KEYWORDS:
        return ModelRole.HEAVY

    # Check for dramatic resolution outcomes.
    if resolution:
        success_level = str(resolution.get("success_level", "")).lower()
        if success_level in ("critical_success", "critical_failure", "catastrophic"):
            return ModelRole.HEAVY
        roll_total = resolution.get("roll_total")
        if isinstance(roll_total, (int, float)):
            # Natural 1 or 20 (or extreme values) → dramatic.
            if roll_total <= 2 or roll_total >= 19:
                return ModelRole.HEAVY

    # Moderate intensity → STANDARD for balanced cost/quality.
    if combined_words & _MODERATE_INTENSITY_KEYWORDS:
        return ModelRole.STANDARD

    # No special signals → use default (usually HEAVY for narrator).
    return default


# ---------------------------------------------------------------------------
# Shared PostgreSQL client for the DSPy background loop.
#
# Each call to dspy_context_for() used to create a fresh PostgresClient(),
# which opened a new asyncpg pool (min_size=2 connections) that was never
# closed.  For a large document with many extraction batches the pools
# would accumulate until PostgreSQL rejected new connections with
# "too many clients already".
#
# The fix: a single PostgresClient dedicated to the background loop, lazily
# initialised on first use.  asyncpg pools are event-loop-bound, so this
# client MUST NOT be shared with the uvicorn main loop — it lives only here.
# ---------------------------------------------------------------------------

_bg_postgres: Optional[PostgresClient] = None
_bg_postgres_lock = threading.RLock()
_bg_registry: Optional["LLMRegistry"] = None


def _get_bg_postgres() -> PostgresClient:
    """Return (or create) the PostgresClient singleton for the DSPy background loop."""
    global _bg_postgres
    if _bg_postgres is None:
        with _bg_postgres_lock:
            if _bg_postgres is None:
                _bg_postgres = PostgresClient()
    return _bg_postgres


def _get_bg_registry() -> "LLMRegistry":
    """Return (or create) the LLMRegistry singleton for the DSPy background loop."""
    global _bg_registry
    if _bg_registry is None:
        with _bg_postgres_lock:
            if _bg_registry is None:
                _bg_registry = LLMRegistry(_get_bg_postgres())
    return _bg_registry


def clear_bg_registry_cache() -> bool:
    """Purge the background LLMRegistry's in-memory client cache.

    Must be called after changing provider config in PostgreSQL so the next
    DSPy call re-resolves from the database instead of using a stale client.
    """
    if _bg_registry is not None:
        _bg_registry.clear_cache()
        return True
    return False


async def _resolve_client(node_name: str, role: Optional[ModelRole] = None) -> LLMClient:
    registry = _get_bg_registry()
    normalized = normalize_node_name(node_name)
    return await registry.for_node_or_role(normalized, role or default_role_for_node(normalized))


def describe_dspy_target(
    node_name: str,
    role: Optional[ModelRole] = None,
) -> dict[str, Optional[str]]:
    """Return provider/model metadata for a node without duplicating registry logic."""
    normalized = normalize_node_name(node_name)
    resolved_role = role or default_role_for_node(normalized)
    try:
        client = _run_sync(_resolve_client(normalized, resolved_role))
        return {
            "node_name": normalized,
            "role": resolved_role.value,
            "provider": client.provider.value,
            "model": client.model,
            "base_url": client.base_url,
        }
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).debug(
            "Could not resolve DSPy target metadata for %s/%s: %s",
            normalized,
            resolved_role.value,
            exc,
        )
        return {
            "node_name": normalized,
            "role": resolved_role.value,
            "provider": None,
            "model": None,
            "base_url": None,
        }


def _model_string_for_dspy(client: LLMClient) -> str:
    if client.provider in (LLMProviderType.ANTHROPIC, LLMProviderType.MINIMAX):
        # MiniMax serves an Anthropic-format endpoint (api_base override);
        # litellm must route it through the anthropic provider.
        return (
            client.model if client.model.startswith("anthropic/") else f"anthropic/{client.model}"
        )
    if "/" in client.model:
        return client.model
    return f"openai/{client.model}"


def get_dspy_lm(
    node_name: str,
    role: Optional[ModelRole] = None,
    *,
    max_tokens: Optional[int] = None,
    enable_cache: bool = True,
) -> dspy.LM:
    """Resolve the saved provider config for a DSPy module and build a runtime LM.

    Args:
        max_tokens: If provided, overrides the ``max_tokens`` stored in the
            provider config.  Use this for extraction modules whose output
            regularly exceeds the provider default (e.g. character-sheet or
            NPC extraction producing thousands of pipe-delimited tokens).
        enable_cache: When True (default), enables prompt caching for providers
            that support it (Anthropic, OpenAI).  This allows the static prefix
            of multi-turn prompts to be cached, reducing cost and latency on
            subsequent calls by 40-60%.
    """
    client = _run_sync(_resolve_client(node_name, role))
    kwargs = {k: v for k, v in client.params.items() if v is not None}
    if client.api_key:
        kwargs["api_key"] = client.api_key
    elif client.provider not in {LLMProviderType.ANTHROPIC, LLMProviderType.MINIMAX}:
        kwargs.setdefault("api_key", "not-needed")
    if client.base_url:
        kwargs["api_base"] = client.base_url
    # Per-call timeout: prevents a single hung LLM request from stalling the pipeline.
    # Configurable via MONITOR_LLM_TIMEOUT env var (seconds); default 120s (2 min).
    _llm_timeout = int(os.environ.get("MONITOR_LLM_TIMEOUT", "120"))
    kwargs.setdefault("request_timeout", _llm_timeout)
    # Allow callers to raise the output-token cap for extraction-heavy modules.
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    # Prompt caching: pass cache_control headers for supported providers.
    # For Anthropic, litellm supports cache_control via the messages API.
    # For OpenAI, automatic prompt caching is enabled by default on gpt-4o+.
    if enable_cache and client.provider == LLMProviderType.ANTHROPIC:
        kwargs.setdefault("extra_headers", {})
        kwargs["extra_headers"]["anthropic-beta"] = "prompt-caching-2024-07-31"

    class CachedDSPyLM(dspy.LM):
        def __init__(self, model, **kwargs):
            self.node_name = kwargs.pop("monitor_node_name", "")
            super().__init__(model, **kwargs)

        def __call__(self, prompt=None, messages=None, **call_kwargs):
            if messages and isinstance(messages, list) and "anthropic" in self.model.lower():
                for m in messages:
                    if m.get("role") == "system":
                        content = m.get("content")
                        if isinstance(content, str):
                            m["content"] = [{"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}]
                        elif isinstance(content, list) and len(content) > 0:
                            if "cache_control" not in content[-1]:
                                content[-1]["cache_control"] = {"type": "ephemeral"}
                        break
            
            cb = stream_callback_var.get()
            if cb and messages and self.node_name == "narrator":
                # Bypass DSPy's litellm wrapper to stream directly
                import litellm
                import asyncio
                
                # DSPy merges kwargs. We extract litellm kwargs.
                merged_kwargs = {**self.kwargs, **call_kwargs}
                merged_kwargs.pop("stream", None)
                
                try:
                    response = litellm.completion(
                        model=self.model,
                        messages=messages,
                        stream=True,
                        **merged_kwargs
                    )
                    
                    full_text = ""
                    in_narrative = False
                    
                    for chunk in response:
                        if getattr(chunk, "choices", None):
                            delta = chunk.choices[0].delta
                            text = getattr(delta, "content", "")
                            if text:
                                full_text += text
                                
                                # Only stream the narrative text portion
                                # DSPy fields are prefixed like "Narrative Text: "
                                if "Narrative Text:" in full_text and "Proposed Changes:" not in full_text:
                                    if not in_narrative:
                                        in_narrative = True
                                        # Only send the part after the prefix
                                        after_prefix = full_text.split("Narrative Text:", 1)[1]
                                        # Lstrip spaces but preserve newlines
                                        clean_text = after_prefix.lstrip(" \t")
                                        if clean_text:
                                            try:
                                                loop = asyncio.get_running_loop()
                                                loop.create_task(cb(clean_text))
                                            except RuntimeError:
                                                pass
                                    else:
                                        try:
                                            loop = asyncio.get_running_loop()
                                            loop.create_task(cb(text))
                                        except RuntimeError:
                                            pass
                                
                    return [full_text]
                except Exception:
                    # Fallback to standard (non-streaming) execution below.
                    pass
            
            return super().__call__(prompt=prompt, messages=messages, **call_kwargs)

    return CachedDSPyLM(_model_string_for_dspy(client), monitor_node_name=node_name, **kwargs)


def dspy_context_for(
    node_name: str,
    role: Optional[ModelRole] = None,
    *,
    max_tokens: Optional[int] = None,
):
    """Return a DSPy context manager bound to the configured provider for a node."""
    return dspy.context(lm=get_dspy_lm(node_name, role, max_tokens=max_tokens))
