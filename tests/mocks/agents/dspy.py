"""
Fake DSPy modules and context manager stubs.

Re-exports FakeDSPyPrediction and FakeDSPyLM from conftest.py,
plus provides a nullcontext-based dspy_context_for stub.

Usage::

    from tests.mocks.agents.dspy import FakeDSPyPrediction, dspy_context_stub

    # Patch dspy_context_for to avoid real LLM/PostgreSQL calls
    @pytest.fixture(autouse=True)
    def mock_dspy(self, monkeypatch):
        monkeypatch.setattr("monitor_agents.simulacrum.agent.dspy_context_for", dspy_context_stub)
"""

from __future__ import annotations

from contextlib import nullcontext
from typing import Any
from unittest.mock import MagicMock


class FakeDSPyPrediction:
    """A fake dspy.Prediction-like object for unit testing DSPy modules.

    DSPy modules access output fields as attributes (e.g. ``result.narrative_text``).
    This class lets tests script those attributes without a real LLM call.

    Usage::

        pred = FakeDSPyPrediction(narrative_text="The dragon roars.")
        mock_module = MagicMock()
        mock_module.forward.return_value = pred
    """

    def __init__(self, **fields: Any) -> None:
        self._fields = fields
        for name, value in fields.items():
            setattr(self, name, value)

    def __repr__(self) -> str:
        return f"FakeDSPyPrediction({self._fields})"


class FakeDSPyLM:
    """Fake DSPy LM for unit testing DSPy modules without real LLM calls.

    Produces ``FakeDSPyPrediction`` objects with scripted output fields.
    Supports both queue mode (pop responses in order) and mapping mode
    (match by prompt content).

    Usage in tests::

        fake_lm = FakeDSPyLM(responses=[
            FakeDSPyPrediction(narrative_text="The dragon roars."),
        ])
        with dspy.context(lm=fake_lm):
            result = narrator_module.forward(...)
    """

    def __init__(
        self,
        responses: list[FakeDSPyPrediction]
        | dict[str, FakeDSPyPrediction]
        | None = None,
    ) -> None:
        self.model = "fake/model"
        self.kwargs: dict[str, Any] = {}
        if isinstance(responses, dict):
            self._response_map: dict[str, FakeDSPyPrediction] = responses
            self._response_queue: list[FakeDSPyPrediction] = []
        else:
            self._response_map = {}
            self._response_queue = list(responses or [FakeDSPyPrediction(output="ok")])

    def __call__(
        self,
        prompt: str | None = None,
        messages: list[dict] | None = None,
        **kwargs: Any,
    ) -> list[FakeDSPyPrediction]:
        """Return the next scripted prediction (or match by prompt content)."""
        # Try mapping mode first
        if self._response_map and prompt:
            for key, pred in self._response_map.items():
                if key.lower() in prompt.lower():
                    return [pred]
            for key, pred in self._response_map.items():
                if messages and any(
                    key.lower() in str(m.get("content", "")).lower() for m in messages
                ):
                    return [pred]

        # Queue mode
        if self._response_queue:
            return [self._response_queue.pop(0)]

        # Fallback
        return [FakeDSPyPrediction(output="ok")]


def dspy_context_stub(*_args: Any, **_kwargs: Any) -> Any:
    """Return a nullcontext — a no-op replacement for dspy_context_for.

    Usage::

        monkeypatch.setattr("monitor_agents.simulacrum.agent.dspy_context_for", dspy_context_stub)
    """
    return nullcontext()


def make_mock_dspy_module(**fields: Any) -> MagicMock:
    """Create a mock DSPy module that returns a FakeDSPyPrediction.

    Usage::

        mock_narrator = make_mock_dspy_module(narrative_text="The dragon roars.")
        agent._narrator_module = mock_narrator
    """
    mock = MagicMock()
    mock.return_value = FakeDSPyPrediction(**fields)
    mock.forward.return_value = FakeDSPyPrediction(**fields)
    return mock
