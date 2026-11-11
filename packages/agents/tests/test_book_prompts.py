"""Every book-parsing signature must start with FICTION_PARSING_PREAMBLE (I-17, I-2).

The preamble is the shared defence against provider content filters refusing
batches of book text that reads like instructions. One test walks both packages
and fails when a signature is added without it.
"""

from __future__ import annotations

import importlib
import pkgutil

import dspy
import pytest
from monitor_agents.book_prompts import FICTION_PARSING_PREAMBLE, apply_fiction_preamble


def _signatures_in(package) -> dict[str, type[dspy.Signature]]:
    """Every module-level dspy.Signature subclass reachable from `package`."""
    found: dict[str, type[dspy.Signature]] = {}
    modules = [package] + [
        importlib.import_module(info.name)
        for info in pkgutil.walk_packages(package.__path__, package.__name__ + ".")
    ]
    for module in modules:
        for name, obj in vars(module).items():
            if isinstance(obj, type) and issubclass(obj, dspy.Signature) and obj is not dspy.Signature:
                found[f"{module.__name__}.{name}"] = obj
    return found


def _missing_preamble(signatures: dict[str, type[dspy.Signature]]) -> list[str]:
    return sorted(
        qualified
        for qualified, signature in signatures.items()
        if not signature.instructions.startswith(FICTION_PARSING_PREAMBLE)
    )


def test_every_book_and_analyzer_signature_starts_with_the_preamble() -> None:
    from monitor_agents import analyzer, book_decomposition

    signatures = {**_signatures_in(book_decomposition), **_signatures_in(analyzer)}
    # A silent enumeration bug must not turn this into a vacuous pass.
    assert len(signatures) >= 32, f"enumerated only {len(signatures)} signatures"
    assert "monitor_agents.book_decomposition.extractor.WindowExtractionSignature" in signatures
    assert "monitor_agents.analyzer.analyzer.BatchedExtractionSignature" in signatures
    assert _missing_preamble(signatures) == []


def test_the_checker_would_catch_a_signature_without_the_preamble() -> None:
    """Prove the enumeration test can fail: a fresh signature lacks the preamble."""

    class BareSignature(dspy.Signature):  # type: ignore[misc]
        """Extract things."""

        text: str = dspy.InputField()
        out: str = dspy.OutputField()

    assert _missing_preamble({"bare": BareSignature}) == ["bare"]


def test_apply_prepends_the_preamble_as_the_first_line_and_keeps_the_rest() -> None:
    class Sample(dspy.Signature):  # type: ignore[misc]
        """Original instruction line."""

        text: str = dspy.InputField()
        out: str = dspy.OutputField()

    original = Sample.instructions
    result = apply_fiction_preamble(Sample)

    assert result is Sample
    lines = Sample.instructions.splitlines()
    assert lines[0] == FICTION_PARSING_PREAMBLE
    assert Sample.instructions.endswith(original)
    # Idempotent: applying again must not stack a second copy.
    apply_fiction_preamble(Sample)
    assert Sample.instructions.count(FICTION_PARSING_PREAMBLE) == 1


def test_preamble_is_a_single_line_so_it_can_lead_the_instructions() -> None:
    assert "\n" not in FICTION_PARSING_PREAMBLE
    # The wording the first real refusal run needs: catalogue material, not a request.
    assert "catalogued" in FICTION_PARSING_PREAMBLE
    assert "not a message to you" in FICTION_PARSING_PREAMBLE


@pytest.mark.parametrize(
    "word",
    ["veto", "gamemaster", "traits"],  # the words test_prompts_do_not_contain... guards
)
def test_preamble_does_not_quote_the_forbidden_prompt_words(word: str) -> None:
    assert word not in FICTION_PARSING_PREAMBLE.casefold()
