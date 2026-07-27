from unittest.mock import MagicMock

from monitor_agents.analyzer.analyzer import (
    SectionCategorizationModule,
    SectionSummaryModule,
    SourceMindscapeSynthesisModule,
)


class _DummyContext:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


def test_section_categorization_module_returns_valid_category(monkeypatch):
    monkeypatch.setattr(
        "monitor_agents.analyzer.analyzer.dspy_context_for",
        lambda node_name, role, max_tokens=None: _DummyContext(),
    )

    module = SectionCategorizationModule()
    mock_result = MagicMock()
    mock_result.category = "lineage"
    module._chain = lambda **kwargs: mock_result

    result = module(
        heading_path="Chapter 3 > Clans > Nosferatu",
        section_excerpt="The Nosferatu are hideous vampires who hide in sewers.",
    )
    assert result.category == "lineage"


def test_section_categorization_module_general_fallback(monkeypatch):
    monkeypatch.setattr(
        "monitor_agents.analyzer.analyzer.dspy_context_for",
        lambda node_name, role, max_tokens=None: _DummyContext(),
    )

    module = SectionCategorizationModule()
    mock_result = MagicMock()
    mock_result.category = "general"
    module._chain = lambda **kwargs: mock_result

    result = module(
        heading_path="Table of Contents",
        section_excerpt="1. Introduction ... 2. Character Creation ...",
    )
    assert result.category == "general"


def test_section_categorization_module_uses_heavy_role():
    """2026-07-22: ingestion-stage modules escalated to HEAVY for ingestion robustness."""
    from monitor_agents.analyzer.analyzer import ModelRole

    module = SectionCategorizationModule()
    assert module._role == ModelRole.HEAVY


def test_section_summary_module_returns_summary_and_themes(monkeypatch):
    monkeypatch.setattr(
        "monitor_agents.analyzer.analyzer.dspy_context_for",
        lambda node_name, role, max_tokens=None: _DummyContext(),
    )

    module = SectionSummaryModule()
    mock_result = MagicMock()
    mock_result.summary = "Describes the Nosferatu, hideous vampires skilled in Obfuscate."
    mock_result.themes = ["vampires", "stealth", "lineage"]
    module._chain = lambda **kwargs: mock_result

    result = module(
        heading_path="Chapter 3 > Clans > Nosferatu",
        section_text="The Nosferatu are hideous vampires who live in sewers.",
    )
    assert "Nosferatu" in result.summary
    assert "lineage" in result.themes


def test_section_summary_module_uses_heavy_role():
    """2026-07-22: ingestion-stage modules escalated to HEAVY for ingestion robustness."""
    from monitor_agents.analyzer.analyzer import ModelRole

    module = SectionSummaryModule()
    assert module._role == ModelRole.HEAVY


def test_source_mindscape_synthesis_module_returns_all_fields(monkeypatch):
    monkeypatch.setattr(
        "monitor_agents.analyzer.analyzer.dspy_context_for",
        lambda node_name, role, max_tokens=None: _DummyContext(),
    )

    module = SourceMindscapeSynthesisModule()
    mock_result = MagicMock()
    mock_result.global_summary = "Gothic horror TTRPG about vampires and politics."
    mock_result.themes = ["gothic horror"]
    mock_result.taxonomy_hints = ["Clan", "Discipline"]
    mock_result.system_name = "Vampire: the Masquerade"
    module._chain = lambda **kwargs: mock_result

    result = module(
        section_summaries="Chapter 3 > Clans: Describes the 13 vampire clans.",
        source_name="VtM20",
    )
    assert result.system_name == "Vampire: the Masquerade"
    assert "Clan" in result.taxonomy_hints


def test_source_mindscape_synthesis_module_uses_heavy_role():
    from monitor_agents.analyzer.analyzer import ModelRole

    module = SourceMindscapeSynthesisModule()
    assert module._role == ModelRole.HEAVY


def test_section_categorization_module_handles_empty_category(monkeypatch):
    """SectionCategorizationModule should handle empty category gracefully."""
    monkeypatch.setattr(
        "monitor_agents.analyzer.analyzer.dspy_context_for",
        lambda node_name, role, max_tokens=None: _DummyContext(),
    )

    module = SectionCategorizationModule()
    mock_result = MagicMock()
    mock_result.category = ""  # Empty category
    module._chain = lambda **kwargs: mock_result

    result = module(
        heading_path="Test > Section",
        section_excerpt="Some text content.",
    )
    assert result.category == ""


def test_section_summary_module_handles_no_themes(monkeypatch):
    """SectionSummaryModule should handle response with no themes."""
    monkeypatch.setattr(
        "monitor_agents.analyzer.analyzer.dspy_context_for",
        lambda node_name, role, max_tokens=None: _DummyContext(),
    )

    module = SectionSummaryModule()
    mock_result = MagicMock()
    mock_result.summary = "A section about basic rules."
    mock_result.themes = []  # No themes
    module._chain = lambda **kwargs: mock_result

    result = module(
        heading_path="Rules > Basic",
        section_text="Basic game rules go here.",
    )
    assert "basic rules" in result.summary.lower()
    assert result.themes == []


def test_source_mindscape_synthesis_module_handles_minimal_response(monkeypatch):
    """SourceMindscapeSynthesisModule should handle minimal required fields."""
    monkeypatch.setattr(
        "monitor_agents.analyzer.analyzer.dspy_context_for",
        lambda node_name, role, max_tokens=None: _DummyContext(),
    )

    module = SourceMindscapeSynthesisModule()
    mock_result = MagicMock()
    mock_result.global_summary = "A game system."
    mock_result.themes = []
    mock_result.taxonomy_hints = []
    mock_result.system_name = ""
    module._chain = lambda **kwargs: mock_result

    result = module(
        heading_path="Title",
        section_text="Game content.",
    )
    assert "game system" in result.global_summary.lower()
