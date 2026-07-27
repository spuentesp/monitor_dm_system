"""InstructablePlayer — one LLM-backed test-player class, multiple strategies.

SRP: the player produces action lines, nothing else.
OCP / DIP: extend by adding a new ``PlayerSpec`` subclass, not by editing
this class. The harness depends on the ``PlayerSpec`` Protocol.
ISP: the only async method the harness calls is ``next()``.

Three concrete specs ship with this module:

* ``ScriptedSpec``   — replays a fixed list of (action, intent) pairs until
                        exhausted, then falls back to a closing line.
* ``InstructedSpec`` — generates each turn via litellm given a goal +
                        success/failure script + recent turns. Falls back
                        gracefully on error or empty output.
* ``MockSpec``       — returns canned lines from a callable. Test-only.

The class also exposes ``observe()`` so the harness can feed the GM's
narration back into the history buffer; the next ``next()`` call will see
that buffer in the message list.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)

PLAYER_SYSTEM_PROMPT_TEMPLATE = (
    "You are a tabletop RPG player. You are playing: {concept}.\n"
    "World: {seed}\n"
    "Goal for this session: {goal}\n"
    "Stay reactive to what the GM just said — your action should make sense "
    "as a direct response to the last GM narration. Keep it to 1-3 sentences. "
    "Do not break character. Do not narrate consequences for the GM."
)

# Language clauses appended to the system message based on
# PlayerContext.language. Default ("en") is appended to keep the
# template itself free of language-specific text — single source of
# truth lives in this map. Callers that override ``system_prompt``
# skip this entirely; they own the prompt and must include a
# language clause themselves if they want one.
_LANGUAGE_CLAUSES: dict[str, str] = {
    "en": "Respond only in English.",
    "ja": "日本語のみで応答してください。",
    "es": "Responde solo en español.",
    "fr": "Réponds uniquement en français.",
    "de": "Antworte nur auf Deutsch.",
    "pt": "Responda apenas em português.",
    "it": "Rispondi solo in italiano.",
    "zh": "只用中文回答。",
}


def _language_clause(language: str) -> str:
    """Return the language clause for the given language code.

    Unknown languages fall back to English so the LLM always has a
    clear instruction. The fallback is logged so a caller passing
    an unknown code gets a noisy reminder to register it.
    """
    if language in _LANGUAGE_CLAUSES:
        return _LANGUAGE_CLAUSES[language]
    logger.warning(
        "Unknown PlayerContext.language=%r — falling back to English clause. "
        "Add an entry to _LANGUAGE_CLAUSES in instructable_player.py to silence.",
        language,
    )
    return _LANGUAGE_CLAUSES["en"]

FALLBACK_LINE = "I take stock of the situation."


# ============================================================================
# Public dataclasses
# ============================================================================


@dataclass
class TurnObservation:
    """One recorded turn — same shape used by the prior harnesses.

    Kept stable so downstream log/JSON rendering stays the same.
    """

    index: int
    player_source: str  # "scripted" | "llm" | "mock"
    player_intent: str
    player_text: str
    gm_narrative_text: str = ""
    player_latency_ms: float = 0.0
    gm_latency_ms: float = 0.0
    coherence_overlap: int = 0


@dataclass
class PlayerContext:
    """Identity + world the player is asked to embody."""

    concept: str
    seed: str
    goal: str = ""
    actor_context: dict[str, Any] = field(default_factory=dict)
    # Optional: override the default PLAYER_SYSTEM_PROMPT_TEMPLATE.
    # Use cases: character-creation dialog (where the LLM must answer
    # structured questions, not react in-voice), tutorial mode, or any
    # caller that needs a different player role than "react in voice".
    system_prompt: str | None = None
    # Language the player LLM should respond in. Defaults to English.
    # The constraint is appended to the default template only; when a
    # caller provides ``system_prompt`` they own the prompt and must
    # include the language clause themselves (no double-appending).
    language: str = "en"


# ============================================================================
# Spec Protocol + concrete specs
# ============================================================================


class PlayerSpec(Protocol):
    """Strategy contract: produce the next line given current context."""

    def reset(self) -> None: ...

    async def next_line(
        self,
        *,
        recent_turns: list[dict[str, str]],
        scripted_left: int,
    ) -> tuple[str, str]: ...


@dataclass
class ScriptedSpec:
    """Replay a fixed arc of scripted opens."""

    arc: list[tuple[str, str]]
    _idx: int = 0

    def reset(self) -> None:
        self._idx = 0

    async def next_line(
        self,
        *,
        recent_turns: list[dict[str, str]],
        scripted_left: int,
    ) -> tuple[str, str]:
        if self._idx >= len(self.arc):
            return (FALLBACK_LINE, "fallback observation")
        action, intent = self.arc[self._idx]
        self._idx += 1
        return (action, intent)


@dataclass
class InstructedSpec:
    """Generate each turn via litellm; given a goal + script prompt."""

    model: str
    fallback_line: str = FALLBACK_LINE
    scripted_opens: list[tuple[str, str]] = field(default_factory=list)
    temperature: float = 0.7
    max_tokens: int = 220

    # Test-injection seam: tests can replace this with a stub. Accepts sync
    # or async callable so hermetic tests can stay sync.
    _llm_call: Callable[..., Any] | None = None

    _idx: int = 0

    def reset(self) -> None:
        self._idx = 0

    async def next_line(
        self,
        *,
        recent_turns: list[dict[str, str]],
        scripted_left: int,
    ) -> tuple[str, str]:
        # Play scripted opens verbatim before consulting the LLM.
        if self._idx < len(self.scripted_opens):
            action, intent = self.scripted_opens[self._idx]
            self._idx += 1
            return (action, intent)

        try:
            text = await self._invoke_llm(messages=recent_turns)
        except Exception as exc:
            logger.warning("player-llm.error (%s); falling back to canned line", exc)
            return (self.fallback_line, "fallback (player-llm error)")

        text = (text or "").strip() if isinstance(text, str) else ""
        if not text:
            return (self.fallback_line, "fallback (empty player output)")
        return (text, classify_player_intent(text))

    async def _invoke_llm(self, *, messages: list[dict[str, str]]) -> str:
        if self._llm_call is not None:
            result = self._llm_call(messages=messages)
            if isinstance(result, Awaitable):
                result = await result
            return result  # type: ignore[no-any-return]

        from litellm import acompletion  # local import keeps hermetic tests light

        resp = await acompletion(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()


@dataclass
class MockSpec:
    """Test-only: every call returns the next entry in ``lines``.

    A callable can be supplied to make ``next_line`` deterministic per
    test (e.g. branching on ``scripted_left``).
    """

    lines: list[tuple[str, str]] = field(default_factory=list)
    provider: Callable[[int], tuple[str, str]] | None = None
    _idx: int = 0

    def reset(self) -> None:
        self._idx = 0

    async def next_line(
        self,
        *,
        recent_turns: list[dict[str, str]],
        scripted_left: int,
    ) -> tuple[str, str]:
        if self.provider is not None:
            return self.provider(scripted_left)
        if self._idx >= len(self.lines):
            return (FALLBACK_LINE, "fallback mock")
        action, intent = self.lines[self._idx]
        self._idx += 1
        return (action, intent)


# ============================================================================
# Cheap intent classifier (one place — was duplicated in two scripts)
# ============================================================================


_INTENT_VERB_PREFIXES: dict[str, tuple[str, ...]] = {
    "observe / investigate": (
        "i look",
        "i glance",
        "i scan",
        "i check",
        "i examine",
        "i search",
        "i read",
    ),
    "social / dialogue": (
        "i ask",
        "i tell",
        "i say",
        "i speak",
        "i address",
        "i respond",
        "i answer",
        "i demand",
    ),
    "physical action": (
        "i attack",
        "i strike",
        "i shoot",
        "i swing",
        "i fire",
        "i charge",
        "i stab",
        "i grapple",
        "i dodge",
        "i block",
        "i run",
        "i flee",
        "i duck",
        "i roll",
        "i push",
    ),
    "reflection": ("i think", "i consider", "i wonder", "i weigh"),
    "manipulation / inventory": (
        "i take",
        "i grab",
        "i pick",
        "i pocket",
        "i hold",
    ),
}


def classify_player_intent(text: str) -> str:
    """First-verb-based label — for transcript grep-ability, not semantics."""
    first = re.split(r"[.!?\n]", text.strip(), maxsplit=1)[0].lower()
    if not first:
        return "action"
    for label, prefixes in _INTENT_VERB_PREFIXES.items():
        if any(first.startswith(p) for p in prefixes):
            return label
    return "action"


_STOP_WORDS = frozenset(
    {
        "the",
        "and",
        "that",
        "this",
        "with",
        "from",
        "they",
        "them",
        "have",
        "were",
        "what",
        "when",
        "where",
        "into",
        "your",
        "their",
        "there",
        "would",
        "could",
        "should",
        "about",
        "because",
        "than",
        "then",
    }
)


def _content_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[A-Za-z]{4,}", text.lower()) if w not in _STOP_WORDS]


def coherence_count(player_text: str, gm_narration: str) -> int:
    """Set-intersection of ≥4-char content words."""
    pw = set(_content_words(player_text))
    gw = set(_content_words(gm_narration))
    return len(pw & gw)


# ============================================================================
# InstructablePlayer
# ============================================================================


@dataclass
class InstructablePlayer:
    """Public test-player driver. Always constructed with a ``PlayerSpec``.

    Usage:
        player = InstructablePlayer(
            spec=ScriptedSpec(arc=[("I look around.", "observe")]),
            context=PlayerContext(concept="...", seed="..."),
        )
        action, intent = await player.next()
        player.observe(gm_text="...", player_text=action, intent=intent)
    """

    spec: PlayerSpec
    context: PlayerContext
    recent_turns_max: int = 3
    _recent_turns: list[dict[str, str]] = field(default_factory=list)
    _last_gm: str = ""

    def __post_init__(self) -> None:
        self.spec.reset()

    async def next(self) -> tuple[str, str]:
        """Produce the next (action, intent) line."""
        scripted_left = self._count_scripted_left()
        action, intent = await self.spec.next_line(
            recent_turns=self._build_messages(),
            scripted_left=scripted_left,
        )
        return (action, intent)

    def observe(
        self,
        *,
        gm_text: str,
        player_text: str,
        intent: str,
    ) -> None:
        """Feed the GM's narration back so the next turn sees it."""
        self._last_gm = gm_text
        self._recent_turns.append({"speaker": "GM", "text": gm_text})
        if player_text:
            self._recent_turns.append({"speaker": "PLAYER", "text": player_text})
        # Trim to a bounded window — 2x so we keep some PLAYER/GM alternation.
        cap = self.recent_turns_max * 2
        if len(self._recent_turns) > cap:
            self._recent_turns = self._recent_turns[-cap:]

    # -- private helpers --------------------------------------------------------

    def _count_scripted_left(self) -> int:
        # The spec knows its own scripted length; we expose it for tests
        # via the protocol so alternative specs can return 0 trivially.
        scripted = getattr(self.spec, "arc", None) or getattr(self.spec, "scripted_opens", None)
        if not scripted:
            return 0
        idx = getattr(self.spec, "_idx", 0)
        return max(0, len(scripted) - idx)

    def _build_messages(self) -> list[dict[str, str]]:
        if self.context.system_prompt:
            # Caller owns the prompt; do not append a language clause on
            # top. If they want a language constraint, they put it in
            # their own system_prompt string.
            system = self.context.system_prompt
        else:
            system = PLAYER_SYSTEM_PROMPT_TEMPLATE.format(
                concept=self.context.concept,
                seed=self.context.seed,
                goal=self.context.goal or "(no explicit goal — react in character)",
            )
            # Append the language clause as the final instruction. The
            # LLM is most likely to honor the most recent instruction in
            # the system prompt, so the language constraint goes last.
            system = f"{system}\n{_language_clause(self.context.language)}"
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        for entry in self._recent_turns[-self.recent_turns_max :]:
            role = "user" if entry["speaker"] == "PLAYER" else "assistant"
            messages.append({"role": role, "content": entry["text"]})
        if not messages[-1].get("content"):
            messages.append({"role": "user", "content": self._last_gm or "(continue the scene)"})
        return messages
