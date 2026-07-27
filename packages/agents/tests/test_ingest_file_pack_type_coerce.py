"""Regression tests: ingest_file must coerce a string pack_type.

Live bug (2026-07-22): `monitor ingest file --type setting_supplement` — the
actual CLI command, not a hand-rolled repro script — crashed with
AttributeError: 'str' object has no attribute 'value' inside the analyzer
(_classify_and_build_profile calling pack_type.value), because the CLI types
--type as a plain str and IngestionPipeline.ingest_file() never coerced it.
The UI backend router already converts via KnowledgePackType(...) before
calling the pipeline, so this was CLI-only and invisible to every prior
repro, which always passed a real KnowledgePackType enum member directly.
"""

from __future__ import annotations

import pytest
from monitor_data.schemas.knowledge_packs import KnowledgePackType


@pytest.mark.parametrize(
    "value,expected",
    [
        (KnowledgePackType.RULEBOOK, KnowledgePackType.RULEBOOK),
        ("rulebook", KnowledgePackType.RULEBOOK),
        ("SETTING_SUPPLEMENT", KnowledgePackType.SETTING_SUPPLEMENT),
        ("  wiki  ", KnowledgePackType.WIKI),
    ],
)
def test_knowledge_pack_type_coerce_accepts_valid_values(value, expected):
    assert KnowledgePackType.coerce(value) is expected


def test_knowledge_pack_type_coerce_rejects_unknown_string():
    assert KnowledgePackType.coerce("not_a_real_type") is None


def test_knowledge_pack_type_coerce_passes_through_none():
    assert KnowledgePackType.coerce(None) is None


@pytest.mark.asyncio
async def test_ingest_file_rejects_invalid_pack_type_string_before_any_io(monkeypatch):
    """The exact shape of the live crash: a CLI-style raw string pack_type.

    Asserts the pipeline now fails fast with a clear ValueError instead of
    reaching the analyzer and blowing up on pack_type.value three stages
    later with no traceback anywhere.
    """
    from uuid import uuid4

    from monitor_agents.ingestion.agent import IngestionPipeline

    pipeline = IngestionPipeline(agent_id="test-pipeline")

    with pytest.raises(ValueError, match="Invalid pack_type"):
        await pipeline.ingest_file(
            file_bytes=b"not read",
            filename="x.pdf",
            source_title="x",
            universe_id=uuid4(),
            pack_name="x",
            pack_type="definitely_not_a_real_pack_type",  # type: ignore[arg-type]
        )
