"""WorldSeed — models, option composition, sparse expansion (Phase 2)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from monitor_agents.world_seed import seed as seed_mod
from monitor_agents.world_seed.models import (
    StartOption,
    StartOptionNPC,
    StartOptionThread,
    UniverseMaterial,
    WorldSeedResult,
)
from monitor_agents.world_seed.seed import WorldSeed, _coerce_json_list, _slugify

pytestmark = pytest.mark.unit


# ─── models ──────────────────────────────────────────────────────────────────


def test_start_option_chip_dict_shape():
    option = StartOption(
        option_id="dockside-heist-1",
        title="Dockside Heist",
        summary="A ledger is missing.",
        location="The Docks",
        npcs=[StartOptionNPC(name="Mara", want="the ledger")],
        hook="Someone stole the tide-locks ledger.",
        player_role="the outsider who just arrived",
    )
    chip = option.chip_dict()
    assert chip["option_id"] == "dockside-heist-1"
    assert chip["title"] == "Dockside Heist"
    assert chip["location"] == "The Docks"
    assert chip["npc_names"] == ["Mara"]
    assert chip["hook"] == "Someone stole the tide-locks ledger."
    assert chip["generated"] is False


def test_world_seed_result_by_id_and_chips():
    option = StartOption(option_id="a-1", title="A", location="L")
    result = WorldSeedResult(universe_id=str(uuid4()), options=[option])
    assert result.by_id("a-1") is option
    assert result.by_id("missing") is None
    assert result.to_chips()[0]["title"] == "A"


def test_material_sparse_detection():
    sparse = UniverseMaterial(universe_id="u", facts=["a single fact"])
    assert sparse.is_sparse() is True
    rich = UniverseMaterial(
        universe_id="u",
        locations=[{"name": "Docks", "description": ""}],
        characters=[{"name": "Mara", "description": "", "want": ""}],
    )
    assert rich.is_sparse() is False


def test_material_digest_lists_sections():
    material = UniverseMaterial(
        universe_id="u",
        description="a drowned coast",
        locations=[{"name": "Docks", "description": "tide-locks"}],
        characters=[{"name": "Mara", "description": "harbourmaster", "want": "the ledger"}],
        facts=["The tide-locks failed once."],
    )
    digest = material.digest()
    assert "a drowned coast" in digest
    assert "Docks" in digest
    assert "Mara" in digest
    assert "The tide-locks failed once." in digest


# ─── helpers ─────────────────────────────────────────────────────────────────


def test_coerce_json_list_handles_fences_and_prose():
    assert _coerce_json_list('[{"a": 1}]') == [{"a": 1}]
    assert _coerce_json_list('```json\n[{"a": 1}]\n```') == [{"a": 1}]
    assert _coerce_json_list('noise before [{"a": 1}] after') == [{"a": 1}]
    assert _coerce_json_list("not json") == []
    assert _coerce_json_list(None) == []


def test_slugify():
    assert _slugify("Dockside Heist!") == "dockside-heist"
    assert _slugify("") == "option"


# ─── sparse expansion reuses the Quick World generator ───────────────────────


@pytest.mark.asyncio
async def test_sparse_universe_expands_through_quick_world(monkeypatch: pytest.MonkeyPatch):
    """Cross-component: the sparse path invokes QuickWorldModule with the
    universe's own seed material (not a second generator)."""
    called: dict[str, Any] = {}

    class _FakeModule:
        def __call__(self, *, seed: str, genre: str, tone: str) -> Any:
            called["seed"] = seed
            called["genre"] = genre
            called["tone"] = tone
            return SimpleNamespace(
                entities_json='[{"name": "Mara", "type": "character", "description": "harbourmaster", "want": "the ledger"}]',
                lore_json='["The tide-locks failed once."]',
                opening_scene="Rain on the quay; the ledger is gone.",
                pc_concept="a stranger with a forged key",
                world_description="",
            )

    monkeypatch.setattr("monitor_agents.quick_world.quick_world.QuickWorldModule", _FakeModule)
    material = UniverseMaterial(universe_id="u", description="a drowned coast", genre="noir")

    await WorldSeed()._expand_sparse(material)

    assert called["seed"] == "a drowned coast"
    assert called["genre"] == "noir"
    assert any(c["name"] == "Mara" for c in material.characters)
    assert "The tide-locks failed once." in material.facts
    # The expansion is marked for the generated provenance.
    assert any(p.get("name") == "__pc_concept__" for p in material.character_profiles)


@pytest.mark.asyncio
async def test_generate_start_options_invokes_gather_with_universe_and_packs(
    monkeypatch: pytest.MonkeyPatch,
):
    """Cross-component: gather_universe_material is invoked with the
    universe id and the session's pack ids."""
    captured: dict[str, Any] = {}
    material = UniverseMaterial(
        universe_id="u-1",
        locations=[{"name": "Docks", "description": ""}],
        characters=[{"name": "Mara", "description": "", "want": "the ledger"}],
    )

    async def _fake_gather(universe_id: Any, *, pack_ids: Any = None) -> UniverseMaterial:
        captured["universe_id"] = str(universe_id)
        captured["pack_ids"] = pack_ids
        return material

    monkeypatch.setattr(seed_mod, "gather_universe_material", _fake_gather)

    async def _fake_compose(self: Any, material: Any, *, system_name: Any, tone: Any) -> list[Any]:
        return [
            StartOption(
                option_id="a-1",
                title="A",
                location="Docks",
                npcs=[StartOptionNPC(name="Mara"), StartOptionNPC(name="Tobias")],
                hook="the ledger",
                threads=[StartOptionThread(title="t1"), StartOptionThread(title="t2")],
            )
        ]

    monkeypatch.setattr(WorldSeed, "_compose_with_model", _fake_compose)

    result = await WorldSeed().generate_start_options(
        universe_id="u-1",
        pack_ids=["pack-9"],
        system_name="Mistlands Core",
        tone="grim",
    )

    assert captured["universe_id"] == "u-1"
    assert captured["pack_ids"] == ["pack-9"]
    assert result.source == "canon"
    assert len(result.options) == 1
    assert result.options[0].npcs[0].name == "Mara"


@pytest.mark.asyncio
async def test_generate_marks_options_generated_for_sparse_universe(monkeypatch: pytest.MonkeyPatch):
    async def _fake_gather(universe_id: Any, *, pack_ids: Any = None) -> UniverseMaterial:
        return UniverseMaterial(universe_id=str(universe_id))

    monkeypatch.setattr(seed_mod, "gather_universe_material", _fake_gather)
    monkeypatch.setattr(WorldSeed, "_expand_sparse", _noop_async)

    async def _fake_compose(self: Any, material: Any, *, system_name: Any, tone: Any) -> list[Any]:
        return [
            StartOption(
                option_id="a-1",
                title="A",
                location="L",
                npcs=[StartOptionNPC(name="N1"), StartOptionNPC(name="N2")],
                hook="h",
                threads=[StartOptionThread(title="t1"), StartOptionThread(title="t2")],
            )
        ]

    monkeypatch.setattr(WorldSeed, "_compose_with_model", _fake_compose)
    result = await WorldSeed().generate_start_options(universe_id="u")
    assert result.source == "generated"
    assert result.options[0].generated is True


async def _noop_async(*_args: Any, **_kwargs: Any) -> None:
    return None


# ─── normalization bounds ────────────────────────────────────────────────────


def test_normalize_options_enforces_bounds():
    material = UniverseMaterial(
        universe_id="u",
        characters=[
            {"name": "Fill1", "description": "", "want": ""},
            {"name": "Fill2", "description": "", "want": ""},
        ],
        plot_threads=[{"title": "FillT1"}, {"title": "FillT2"}],
    )
    raw = StartOption(option_id="x", title="X", location="L", npcs=[StartOptionNPC(name="Solo")], threads=[])
    normalized = WorldSeed()._normalize_options([raw], material, generated=False)
    option = normalized[0]
    # 2-4 NPCs and 2-3 threads even when the model under-delivered.
    assert 2 <= len(option.npcs) <= 4
    assert 2 <= len(option.threads) <= 3
    assert option.generated is False


def test_normalize_options_caps_at_four():
    material = UniverseMaterial(universe_id="u")
    raws = [StartOption(option_id=f"o{i}", title=f"T{i}", location="L") for i in range(6)]
    normalized = WorldSeed()._normalize_options(raws, material, generated=True)
    assert len(normalized) == 4
    assert all(o.generated for o in normalized)


def test_compose_fallback_builds_options_from_material():
    material = UniverseMaterial(
        universe_id="u",
        locations=[{"name": "Docks", "description": "tide-locks"}, {"name": "Underworks", "description": ""}],
        characters=[{"name": "Mara", "description": "", "want": "the ledger"}],
        plot_threads=[{"title": "The Missing Ledger", "description": "gone", "category": "mystery"}],
    )
    options = WorldSeed()._compose_fallback(material)
    assert len(options) == 2
    assert options[0].location == "Docks"
    assert options[0].npcs[0].name == "Mara"
    assert options[0].threads[0].title == "The Missing Ledger"


# ─── model composition parsing ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compose_with_model_parses_options_json(monkeypatch: pytest.MonkeyPatch):
    prediction = SimpleNamespace(
        options_json=(
            '[{"title": "Dockside Heist", "summary": "s", "location": "The Docks", '
            '"location_description": "d", "npcs": [{"name": "Mara", "description": "h", "want": "w"}], '
            '"hook": "The ledger is gone.", "player_role": "the stranger", '
            '"threads": [{"title": "t1", "category": "mystery", "urgency": "high"}]}]'
        )
    )

    class _FakeModule:
        def forward(self, **_kwargs: Any) -> Any:
            return prediction

    monkeypatch.setattr("monitor_agents.world_seed.signatures.StartOptionsModule", _FakeModule)
    options = await WorldSeed()._compose_with_model(
        UniverseMaterial(universe_id="u"),
        system_name="Mistlands Core",
        tone="grim",
    )
    assert len(options) == 1
    assert options[0].title == "Dockside Heist"
    assert options[0].npcs[0].want == "w"
    assert options[0].threads[0].urgency == "high"
