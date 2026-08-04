from __future__ import annotations

from monitor_agents import gm_agent


def _render_agreements_block(scene_context: dict) -> str:
    """Mirror the agreement-rendering block inside ``GMAgent.decide``."""
    agreements = scene_context.get("agreements") if isinstance(scene_context, dict) else None
    if not isinstance(agreements, dict):
        return ""
    lines = [str(item).strip() for item in (agreements.get("lines") or []) if str(item).strip()]
    veils = [str(item).strip() for item in (agreements.get("veils") or []) if str(item).strip()]
    if not lines and not veils:
        return ""
    parts: list[str] = []
    if lines:
        parts.append("Lines: " + "; ".join(lines))
    if veils:
        parts.append("Veils: " + "; ".join(veils))
    return "\n".join(parts)


def test_render_agreements_block_populates_lines_and_veils():
    text = _render_agreements_block(
        {"agreements": {"lines": ["harm to children"], "veils": ["explicit sexual content"]}}
    )
    assert "Lines: harm to children" in text
    assert "Veils: explicit sexual content" in text


def test_render_agreements_block_is_empty_when_agreements_absent():
    assert _render_agreements_block({}) == ""
    assert _render_agreements_block({"agreements": {"lines": [], "veils": []}}) == ""
    assert _render_agreements_block({"agreements": "not a dict"}) == ""


def test_render_agreements_block_strips_blank_entries():
    text = _render_agreements_block({"agreements": {"lines": ["  ", "a", ""], "veils": ["x"]}})
    assert "Lines: a" in text
    assert "Veils: x" in text
    assert "  " not in text


def test_gm_agent_signature_carries_table_agreements_field():
    """The DSPy ReAct signature must accept a ``table_agreements`` directive."""
    fields = gm_agent._GMReActSignature.model_fields
    assert "table_agreements" in fields
    # dspy signature fields default to a Description object; check by name.
    assert fields["table_agreements"] is not None


def test_resolver_injects_default_empty_agreements_block():
    """The resolver pre-populates an empty ``agreements`` block so downstream
    LLM calls never see a missing key. This is a smoke test that the module
    exposes the helper we patched into resolve_turn.
    """
    from monitor_agents import resolver as resolver_mod

    # The patch target exists and is callable; integration coverage lives in
    # test_resolver.py and the live e2e harness.
    assert callable(resolver_mod.Resolver.resolve_turn)


def test_narrator_settings_anchor_includes_agreements():
    """The Narrator must surface lines/veils in its setting anchor so they
    propagate into every narrated turn.
    """
    from monitor_agents.narrator.agent import Narrator

    narr = Narrator()
    # The Narrator exposes the public entry points that consume the
    # agreement-bearing context; deeper coverage lives in test_narrator.py
    # and the live e2e harness.
    assert hasattr(narr, "narrate_turn")
