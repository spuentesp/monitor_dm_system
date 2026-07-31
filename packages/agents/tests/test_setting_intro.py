from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from monitor_agents import setting_intro as si
from monitor_data.schemas.base import CanonLevel


def _universe(universe_id, **overrides):
    values = {
        "id": universe_id,
        "name": "Chicago by Night",
        "description": "A Camarilla-held city divided by old Kindred politics",
        "genre": "personal horror",
        "tone": "political",
        "default_system_name": "Vampire: The Masquerade",
        "source_ids": [uuid4()],
        "canon_level": CanonLevel.CANON,
        "confidence": 1.0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_pack_intro_takes_precedence_without_canon_synthesis(monkeypatch):
    universe_id = uuid4()
    pack_id = uuid4()
    authored = (
        "Chicago is a city held by the Camarilla, where every favor creates "
        "a debt and every domain has a price."
    )
    monkeypatch.setattr(si, "neo4j_get_universe", lambda _uid: _universe(universe_id))
    monkeypatch.setattr(
        si,
        "mongodb_get_knowledge_pack",
        lambda _pid: SimpleNamespace(
            id=pack_id,
            intro_text=authored,
            source_document_ids=[uuid4()],
        ),
    )

    def should_not_run(*_args, **_kwargs):
        raise AssertionError("canon synthesis should not run when a pack intro exists")

    monkeypatch.setattr(si, "neo4j_list_axioms", should_not_run)
    monkeypatch.setattr(si, "neo4j_list_facts", should_not_run)
    monkeypatch.setattr(si, "neo4j_list_entities", should_not_run)

    intro = await si.assemble_session_intro(
        {"universe_id": str(universe_id), "pack_id": str(pack_id)}
    )

    assert intro.source == "pack_intro"
    assert intro.intro_text == authored
    assert any(anchor.kind == "pack" for anchor in intro.anchors)
    assert intro.unverified is False


@pytest.mark.asyncio
async def test_canon_queries_remain_scoped_to_selected_universe(monkeypatch):
    selected_id = uuid4()
    other_id = uuid4()
    source_id = uuid4()
    seen: list = []

    monkeypatch.setattr(si, "neo4j_get_universe", lambda _uid: _universe(selected_id))
    monkeypatch.setattr(si, "mongodb_get_knowledge_pack", lambda _pid: None)

    def list_axioms(filters):
        seen.append(filters.universe_id)
        return [
            SimpleNamespace(
                id=uuid4(),
                universe_id=selected_id,
                statement="The Camarilla claims Praxis over the city",
                source_ids=[source_id],
                canon_level=CanonLevel.CANON,
                confidence=0.95,
            )
        ]

    def list_facts(filters):
        seen.append(filters.universe_id)
        return []

    def list_entities(filters):
        seen.append(filters.universe_id)
        return SimpleNamespace(entities=[])

    monkeypatch.setattr(si, "neo4j_list_axioms", list_axioms)
    monkeypatch.setattr(si, "neo4j_list_facts", list_facts)
    monkeypatch.setattr(si, "neo4j_list_entities", list_entities)

    intro = await si.assemble_session_intro({"universe_id": str(selected_id)})

    assert seen and set(seen) == {selected_id}
    assert str(other_id) not in intro.intro_text
    assert "Camarilla claims Praxis" in intro.intro_text
    assert intro.source == "canon_synthesis"
    assert intro.unverified is False


@pytest.mark.asyncio
async def test_sparse_universe_is_marked_unverified_without_inventing(monkeypatch):
    universe_id = uuid4()
    monkeypatch.setattr(
        si,
        "neo4j_get_universe",
        lambda _uid: _universe(
            universe_id,
            name="Tenebris",
            description="",
            genre=None,
            tone=None,
            default_system_name=None,
            source_ids=[],
        ),
    )
    monkeypatch.setattr(si, "mongodb_get_knowledge_pack", lambda _pid: None)
    monkeypatch.setattr(si, "neo4j_list_axioms", lambda _filters: [])
    monkeypatch.setattr(si, "neo4j_list_facts", lambda _filters: [])
    monkeypatch.setattr(
        si,
        "neo4j_list_entities",
        lambda _filters: SimpleNamespace(entities=[]),
    )

    intro = await si.assemble_session_intro({"universe_id": str(universe_id)})

    assert intro.source == "universe_description"
    assert intro.unverified is True
    assert intro.intro_text == "This story takes place in **Tenebris**."
