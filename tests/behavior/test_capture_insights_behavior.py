"""
Behavior tests for P1.2: capture-specific per-entry insights (CF-1 steps 3/5).

Verifies the CaptureEntry DSPy signature carries the grounding rules, and the
agent/schema wiring, without real DB/LLM connections.
"""

from __future__ import annotations

import re


def _doc(cls: type) -> str:
    """Return the class docstring lowercased with whitespace normalized."""
    return re.sub(r"\s+", " ", (cls.__doc__ or "").lower())


# =============================================================================
# CaptureEntrySignature (DSPy prompt rules)
# =============================================================================


class TestCaptureEntrySignature:
    def test_signature_importable(self):
        """CaptureEntrySignature is importable from session_ingest."""
        from monitor_agents.ingestion.session_ingest import CaptureEntrySignature

        assert CaptureEntrySignature is not None

    def test_docstring_contains_grounding_rule(self):
        """Docstring carries the grounding rule for participants/locations."""
        from monitor_agents.ingestion.session_ingest import CaptureEntrySignature

        assert "only name participants/locations grounded in the entry" in _doc(
            CaptureEntrySignature
        )

    def test_docstring_contains_candidate_fact_rule(self):
        """Docstring restricts candidate facts to world-state claims."""
        from monitor_agents.ingestion.session_ingest import CaptureEntrySignature

        doc = _doc(CaptureEntrySignature)
        assert "world-state claims only" in doc
        assert "no dialogue" in doc

    def test_docstring_prefers_canonical_names(self):
        """Docstring instructs preferring canonical names from known_entities."""
        from monitor_agents.ingestion.session_ingest import CaptureEntrySignature

        assert "canonical names" in _doc(CaptureEntrySignature)

    def test_signature_io_fields(self):
        """Signature has the expected input/output fields."""
        from monitor_agents.ingestion.session_ingest import CaptureEntrySignature

        assert "entry_text" in CaptureEntrySignature.input_fields
        assert "known_entities" in CaptureEntrySignature.input_fields
        assert "open_threads" in CaptureEntrySignature.input_fields
        assert "participants" in CaptureEntrySignature.output_fields
        assert "locations" in CaptureEntrySignature.output_fields
        assert "candidate_facts" in CaptureEntrySignature.output_fields
        assert "advances_thread" in CaptureEntrySignature.output_fields


class TestCaptureEntryModule:
    def test_module_importable(self):
        """CaptureEntryModule is importable."""
        from monitor_agents.ingestion.session_ingest import CaptureEntryModule

        assert CaptureEntryModule is not None

    def test_module_is_dspy_module(self):
        """CaptureEntryModule is a DSPy module built on Predict."""
        import dspy
        from monitor_agents.ingestion.session_ingest import CaptureEntryModule

        module = CaptureEntryModule()
        assert isinstance(module, dspy.Module)
        assert isinstance(module.analyzer, dspy.Predict)


# =============================================================================
# CaptureInsightAgent / CaptureInsight schema
# =============================================================================


class TestCaptureInsightAgent:
    def test_agent_importable(self):
        """CaptureInsightAgent is importable."""
        from monitor_agents.ingestion.capture_insights import CaptureInsightAgent

        assert CaptureInsightAgent is not None

    def test_agent_is_base_agent(self):
        """CaptureInsightAgent inherits from BaseAgent."""
        from monitor_agents.base import BaseAgent
        from monitor_agents.ingestion.capture_insights import CaptureInsightAgent

        assert issubclass(CaptureInsightAgent, BaseAgent)

    def test_agent_has_analyze_entry(self):
        """CaptureInsightAgent has analyze_entry method."""
        from monitor_agents.ingestion.capture_insights import CaptureInsightAgent

        assert hasattr(CaptureInsightAgent, "analyze_entry")


class TestCaptureInsightSchema:
    def test_capture_insight_fields(self):
        """CaptureInsight has the expected fields with empty defaults."""
        from monitor_agents.ingestion.capture_insights import CaptureInsight

        insight = CaptureInsight()
        assert insight.participants == []
        assert insight.locations == []
        assert insight.candidate_facts == []
        assert insight.advances_thread == ""

    def test_capture_insight_populated(self):
        """CaptureInsight carries populated values."""
        from monitor_agents.ingestion.capture_insights import CaptureInsight

        insight = CaptureInsight(
            participants=["Mira"],
            locations=["The Sunken Chapel"],
            candidate_facts=["the key is now with Mira"],
            advances_thread="The sealed door",
        )
        assert insight.participants == ["Mira"]
        assert insight.candidate_facts == ["the key is now with Mira"]
        assert insight.advances_thread == "The sealed door"
