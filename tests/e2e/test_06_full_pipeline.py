"""
E2E Test 06 — Full Rulebook → World → System → Story Pipeline

This suite ties together the previously isolated stages so MONITOR can be
validated against the intended RPG-book-to-story journey.

Use cases covered
-----------------
I-1 / I-2   Ingest a PDF rulebook and chunk it
M-1..M-4    Use the seeded multiverse / world / entities / axioms / events
RS-1..RS-3  Use the seeded game system rules
P-1..P-5    Start a story, start a scene, resolve a turn, and narrate it
"""

from __future__ import annotations

from typing import Any, Dict

import fitz
import pytest


def _make_pdf_bytes(text: str) -> bytes:
    """Render plain text into a tiny in-memory PDF for real PDF-ingest coverage."""
    doc = fitz.open()
    chunk_size = 1800
    for start in range(0, len(text), chunk_size):
        page = doc.new_page()
        page.insert_textbox(
            fitz.Rect(40, 40, 555, 800),
            text[start : start + chunk_size],
            fontsize=10,
        )
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.mark.e2e
class TestFullPipeline:
    """End-to-end smoke coverage for the RPG book → playable story pipeline."""

    def test_ingest_pdf_extracts_world_and_rules_keywords(
        self, rpg_book_text: str
    ) -> None:
        """I-1/I-2: A real PDF can be ingested and yields lore + rules text."""
        from monitor_data.tools.ingest_tools import ingest_pdf

        pdf_bytes = _make_pdf_bytes(rpg_book_text)
        chunks = ingest_pdf(pdf_bytes, "realm_of_shadows.pdf")

        assert chunks, "Expected at least one chunk from the generated PDF"
        combined_text = "\n".join(chunk.text for chunk in chunks)
        assert "Realm of Shadows" in combined_text
        assert "Iron Throne" in combined_text
        assert "d20" in combined_text.lower()

    @pytest.mark.asyncio
    async def test_rulebook_world_system_and_gm_loop_work_together(
        self,
        rpg_book_text: str,
        seeded_world: Dict[str, Any],
        seeded_game_system: Any,
        e2e_story: Any,
        e2e_scene: Any,
        mock_context_assembly,
        mock_dspy_narrator,
        mock_narrator_llm,
    ) -> None:
        """Full smoke path: ingest the rulebook, then narrate a turn in the seeded setting."""
        from monitor_agents.loops.scene_loop import SceneLoop
        from monitor_data.tools.ingest_tools import ingest_pdf
        from monitor_data.tools.mongodb_tools import mongodb_get_scene

        pdf_chunks = ingest_pdf(
            _make_pdf_bytes(rpg_book_text), "realm_of_shadows_full.pdf"
        )
        assert any("Void Cult" in chunk.text for chunk in pdf_chunks)
        assert seeded_game_system.name == "Realm of Shadows D20"
        assert seeded_world["multiverse_id"] is not None
        assert seeded_world["axiom_magic_id"] is not None
        assert seeded_world["event_shadow_war_id"] is not None

        loop = SceneLoop(
            scene_id=e2e_scene.scene_id,
            story_id=e2e_story.id,
            max_turns=5,
        )
        result = await loop.run(
            "I ask High Priestess Mara what the Old Faith knows about the Ashlands and the missing prince."
        )

        assert result["narrative_text"]
        assert result["turns_count"] == 1

        scene = mongodb_get_scene(e2e_scene.scene_id)
        assert scene is not None
        assert len(scene.turns) >= 2
        assert any(
            "hooded stranger" in turn.text.lower()
            or "shadowed alley" in turn.text.lower()
            for turn in scene.turns
        )
