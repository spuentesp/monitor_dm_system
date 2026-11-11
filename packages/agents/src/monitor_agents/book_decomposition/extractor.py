"""LLM extractor: turn one passage into atoms, accounting for every unit."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Protocol

import dspy
from dspy.utils.exceptions import AdapterParseError
from monitor_data.schemas.book_graph import WindowExtraction
from monitor_data.schemas.llm_config import ModelRole
from pydantic import ValidationError

from monitor_agents.book_prompts import apply_fiction_preamble
from monitor_agents.book_decomposition.settings import DecompositionSettings
from monitor_agents.book_decomposition.windows import Window
from monitor_agents.dspy_runtime import get_dspy_lm

_MINIMAX_PREFIX = "minimax/"
_MINIMAX_DEFAULT_BASE = "https://api.minimax.io/anthropic"
_REQUEST_TIMEOUT_SECONDS = 300
# RunGuard and the extraction loop own retries. Retrying inside LiteLLM as well would hide a
# quota error from them for several more calls.
_LM_RETRIES = 0


def max_output_tokens() -> int:
    """The output cap for one extraction call (`MONITOR_BOOK_EXTRACT_MAX_TOKENS`, default 32,768)."""
    return DecompositionSettings.from_env().extract_max_tokens


class TruncatedOutput(Exception):
    """The answer hit the token limit, so it may be missing claims even if it parses."""


# Failures that say something about this text and answer, as opposed to the provider.
CONTENT_ERRORS = (AdapterParseError, ValidationError, TruncatedOutput)


@dataclass
class _CallMeter:
    """What one logical call really used, including DSPy's hidden adapter retries."""

    input_tokens: int = 0
    output_tokens: int = 0
    last_was_truncated: bool = False

    def observe(self, response: Any) -> None:
        self.last_was_truncated = any(choice.finish_reason == "length" for choice in response.choices)
        # A cached response was already paid for.
        if getattr(response, "cache_hit", False):
            return
        usage = getattr(response, "usage", None)
        self.input_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
        self.output_tokens += int(getattr(usage, "completion_tokens", 0) or 0)


_active_meter: ContextVar[_CallMeter | None] = ContextVar("book_call_meter", default=None)


class MeteredLM(dspy.LM):  # type: ignore[misc]
    """An LM that reports every response to the current call's meter.

    Each response is seen here even when DSPy goes on to fail parsing it, and a cached
    truncated answer is still recognized as truncated.
    """

    def forward(
        self,
        prompt: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Any:
        response = super().forward(prompt=prompt, messages=messages, **kwargs)
        meter = _active_meter.get()
        if meter is not None:
            meter.observe(response)
        return response


def _metered(lm: Any) -> Any:
    """Return `lm` metered. A plain dspy.LM, as the registry builds, gets a metered copy."""
    if type(lm) is not dspy.LM:
        return lm
    copy = lm.copy()
    copy.__class__ = MeteredLM
    return copy


def failed_call_usage(exc: BaseException | None) -> tuple[int, int]:
    """The (input, output) tokens a failed call used before it failed."""
    usage = getattr(exc, "book_call_usage", (0, 0))
    return int(usage[0]), int(usage[1])


def run_metered(lm: Any, call: Callable[[], Any]) -> tuple[Any, int, int]:
    """Run a DSPy call and return (prediction, input tokens, output tokens).

    A failure keeps its type and carries its usage, because failed calls cost quota too.
    Raises TruncatedOutput when the final answer hit the token limit, even if it parsed: DSPy's
    JSON repair can close a cut-off answer, which would silently lose claims.
    """
    meter = _CallMeter()
    token = _active_meter.set(meter)
    try:
        with dspy.context(lm=_metered(lm)):
            prediction = call()
        if meter.last_was_truncated:
            raise TruncatedOutput(f"The answer hit the {max_output_tokens()} token limit")
    except Exception as exc:
        exc.book_call_usage = (meter.input_tokens, meter.output_tokens)  # type: ignore[attr-defined]
        raise
    finally:
        _active_meter.reset(token)
    return prediction, meter.input_tokens, meter.output_tokens


@dataclass(frozen=True)
class ExtractorResult:
    extraction: WindowExtraction
    input_tokens: int = 0
    output_tokens: int = 0


class WindowExtractor(Protocol):
    async def __call__(self, window: Window) -> ExtractorResult: ...


class WindowExtractionSignature(dspy.Signature):  # type: ignore[misc]
    """Decompose one passage of a tabletop RPG or setting book into atomic claims.

    Every labelled unit must be accounted for: cite it from at least one atom, or list it
    in skips with a reason. Do not leave a unit out.

    Atom kinds:
    - axiom: a lasting truth about how this world or game works.
    - entity: a named thing or type of thing (a person, group, place, item, power, species).
    - fact: a specific event or state in the setting.
    - rule: a mechanic, procedure or number players apply. Keep every number exact.
    - relationship: a typed link between two named things.

    Rules:
    - Use only this passage. Never add knowledge from outside it, even about a game you know.
    - One claim per atom. A sentence holding three claims gives three atoms.
    - Keep every condition, exception and limit with its claim. "Knights may ride any horse,
      unless it is wounded" must not become "Knights may ride any horse".
    - Skip worked examples and sample play as example, including named sample characters. If
      an example says outright that something always applies, extract only that rule.
    - Never build a rule from what one character does in an example. "Mira gets three successes,
      so she gains 3 Momentum" does not give "each success grants 1 Momentum".
    - Skip statements with no usable content, such as "Some days are better than others".
    - Each statement must stand alone: replace pronouns with what they refer to, using the
      heading path and read-only context. The context must never be cited.
    - In-world fiction that establishes something about the setting is an axiom or fact.
      Skip it as flavor only when it asserts nothing lasting.
    - Lower the confidence when the passage is ambiguous rather than guessing.
    """

    heading_path: str = dspy.InputField(desc="Where this passage sits in the book")
    context: str = dspy.InputField(desc="Read-only text just before this passage. Do not cite it.")
    units: str = dspy.InputField(
        desc="The passage, one labelled unit per line (S=sentence, T=table), each with its heading path"
    )
    result: WindowExtraction = dspy.OutputField()


apply_fiction_preamble(WindowExtractionSignature)


def build_lm(model: str, reasoning_effort: str | None = None) -> dspy.LM:
    """Build an LM from a LiteLLM model name, or `minimax/<model>` for MiniMax.

    `reasoning_effort` applies to MiniMax only. Reasoning was 92% of the output tokens on Dune
    Chapter 5, and it rejects turning reasoning off, so lowering the effort is what's left.

    MiniMax serves an Anthropic-format API, so it routes through LiteLLM's anthropic
    provider. The key is always passed explicitly: otherwise LiteLLM would fall back to
    ANTHROPIC_API_KEY and bill that account instead (see `get_dspy_lm`).
    """
    if not model.startswith(_MINIMAX_PREFIX):
        return MeteredLM(
            model,
            max_tokens=max_output_tokens(),
            temperature=0.0,
            timeout=_REQUEST_TIMEOUT_SECONDS,
            num_retries=_LM_RETRIES,
        )
    api_key = os.environ.get("MINIMAX_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("MINIMAX_API_KEY is not set. Refusing to let LiteLLM fall back to ANTHROPIC_API_KEY.")
    reasoning: dict[str, Any] = {}
    if reasoning_effort:
        reasoning = {
            "reasoning_effort": reasoning_effort,
            # LiteLLM doesn't know this model and would otherwise refuse the parameter.
            "allowed_openai_params": ["reasoning_effort"],
        }
    return MeteredLM(
        f"anthropic/{model.removeprefix(_MINIMAX_PREFIX)}",
        api_key=api_key,
        api_base=os.environ.get("MINIMAX_BASE_URL", "").strip() or _MINIMAX_DEFAULT_BASE,
        max_tokens=max_output_tokens(),
        temperature=0.1,  # MiniMax documents its temperature range as excluding 0.
        timeout=_REQUEST_TIMEOUT_SECONDS,
        num_retries=_LM_RETRIES,
        **reasoning,
    )


def prompt_fingerprint() -> str:
    """Identify the prompt and output schema, so results from different versions never mix."""
    source = WindowExtractionSignature.instructions + json.dumps(WindowExtraction.model_json_schema(), sort_keys=True)
    return hashlib.sha256(source.encode()).hexdigest()[:12]


def format_units(window: Window) -> str:
    """One unit per line, each with the heading path it sits under (a window can span headings)."""
    lines = []
    for unit in window.units:
        where = " > ".join(unit.heading_path)
        lines.append(f"[{unit.label}] ({where}) {unit.text}" if where else f"[{unit.label}] {unit.text}")
    return "\n".join(lines)


class DspyWindowExtractor:
    """Runs the signature through DSPy.

    Pass `lm` to use a specific model. Otherwise the provider registry resolves one, as it
    does for the other analyzer modules.
    """

    def __init__(self, lm: Any | None = None) -> None:
        self._lm = lm
        self._predict = dspy.Predict(WindowExtractionSignature)

    def _call(self, window: Window) -> ExtractorResult:
        lm = self._lm or get_dspy_lm("book_decomposition", ModelRole.HEAVY, max_tokens=max_output_tokens())
        prediction, input_tokens, output_tokens = run_metered(
            lm,
            lambda: self._predict(
                heading_path=" > ".join(window.heading_path) or "(none)",
                context=window.context or "(none)",
                units=format_units(window),
            ),
        )
        return ExtractorResult(prediction.result, input_tokens, output_tokens)

    async def __call__(self, window: Window) -> ExtractorResult:
        return await asyncio.to_thread(self._call, window)
