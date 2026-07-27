"""API tests for the entity-templates router (F3-2a).

Covers the CRUD surface plus the new instantiation semantics:
variable_properties resolution (choice / range / pattern / table / llm),
naming_pattern resolution (override / pattern / numbered / list / fallback),
parent-template inheritance, override merging, and usage_count accounting.

All MongoDB tool functions are patched at the router module boundary,
mirroring the ``test_entities_crud.py`` style.
"""

from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from monitor_data.schemas.entity_templates import (
    EntityTemplateResponse,
)

from monitor_ui.main import app

client = TestClient(app)

TOOLS = "monitor_ui.routers.templates"


def _template(**over) -> EntityTemplateResponse:
    """Build a realistic EntityTemplateResponse."""
    data = {
        "template_id": uuid4(),
        "universe_id": uuid4(),
        "name": "City Guard",
        "description": "A rank-and-file watchman.",
        "entity_type": "character",
        "base_properties": {"role": "guard", "faction_kind": "municipal"},
        "variable_properties": [],
        "naming_pattern": {"type": "numbered"},
        "stat_generation": {"method": "fixed", "formulas": {}, "constraints": {}},
        "default_state_tags": ["on_duty"],
        "default_detail_level": "stub",
        "default_personality": None,
        "parent_template_id": None,
        "usage_count": 0,
        "created_at": "2026-07-24T00:00:00Z",
        "updated_at": None,
    }
    data.update(over)
    return EntityTemplateResponse(**data)


# ── CRUD smoke ────────────────────────────────────────────────────


def test_create_template_201():
    tpl = _template()
    with patch(f"{TOOLS}.mongodb_create_entity_template", return_value=tpl) as mock_create:
        resp = client.post(
            "/api/templates",
            json={
                "universe_id": str(tpl.universe_id),
                "name": "City Guard",
                "entity_type": "character",
            },
        )
    assert resp.status_code == 201
    assert resp.json()["name"] == "City Guard"
    assert mock_create.called


def test_create_template_rejects_bad_entity_type():
    resp = client.post(
        "/api/templates",
        json={"universe_id": str(uuid4()), "name": "X", "entity_type": "wizardish"},
    )
    assert resp.status_code == 422


def test_get_template_404():
    with patch(f"{TOOLS}.mongodb_get_entity_template", return_value=None):
        resp = client.get(f"/api/templates/{uuid4()}")
    assert resp.status_code == 404


def test_delete_template_404():
    with patch(f"{TOOLS}.mongodb_delete_entity_template", return_value=False):
        resp = client.delete(f"/api/templates/{uuid4()}")
    assert resp.status_code == 404


# ── increment-usage ───────────────────────────────────────────────


def test_increment_usage_bumps_count():
    tpl = _template(usage_count=3)
    bumped = _template(template_id=tpl.template_id, universe_id=tpl.universe_id, usage_count=4)
    with (
        patch(f"{TOOLS}.mongodb_get_entity_template", side_effect=[tpl, bumped]),
        patch(f"{TOOLS}.mongodb_increment_template_usage") as mock_inc,
    ):
        resp = client.post(f"/api/templates/{tpl.template_id}/increment-usage")
    assert resp.status_code == 200
    assert resp.json()["usage_count"] == 4
    mock_inc.assert_called_once_with(tpl.template_id)


def test_increment_usage_404():
    with patch(f"{TOOLS}.mongodb_get_entity_template", return_value=None):
        resp = client.post(f"/api/templates/{uuid4()}/increment-usage")
    assert resp.status_code == 404


# ── instantiate: validation ───────────────────────────────────────


def test_instantiate_404():
    with patch(f"{TOOLS}.mongodb_get_entity_template", return_value=None):
        resp = client.post(f"/api/templates/{uuid4()}/instantiate", json={})
    assert resp.status_code == 404


def test_instantiate_rejects_mismatched_body_template_id():
    tpl = _template()
    with patch(f"{TOOLS}.mongodb_get_entity_template", return_value=tpl):
        resp = client.post(
            f"/api/templates/{tpl.template_id}/instantiate",
            json={"template_id": str(uuid4())},
        )
    assert resp.status_code == 400


# ── instantiate: naming ───────────────────────────────────────────


def _instantiate(tpl: EntityTemplateResponse, body: dict | None = None):
    with (
        patch(f"{TOOLS}.mongodb_get_entity_template", return_value=tpl),
        patch(f"{TOOLS}.mongodb_increment_template_usage") as mock_inc,
    ):
        resp = client.post(f"/api/templates/{tpl.template_id}/instantiate", json=body or {})
    return resp, mock_inc


def test_instantiate_numbered_naming_uses_usage_count():
    tpl = _template(usage_count=4, naming_pattern={"type": "numbered"})
    resp, mock_inc = _instantiate(tpl)
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "City Guard 5"
    assert data["usage_count"] == 5
    mock_inc.assert_called_once_with(tpl.template_id)


def test_instantiate_override_name_wins():
    tpl = _template(naming_pattern={"type": "numbered"})
    resp, _ = _instantiate(tpl, {"override_name": "Sergeant Brann"})
    assert resp.json()["name"] == "Sergeant Brann"


def test_instantiate_pattern_naming_substitutes_tokens():
    tpl = _template(
        naming_pattern={
            "type": "pattern",
            "pattern": "{adjective} {noun} #{number}",
            "adjectives": ["Grim"],
            "nouns": ["Watchman"],
        },
        usage_count=1,
    )
    resp, _ = _instantiate(tpl)
    assert resp.json()["name"] == "Grim Watchman #2"


def test_instantiate_list_naming_draws_from_pool():
    tpl = _template(naming_pattern={"type": "list", "name_list": ["Onlyname"]})
    resp, _ = _instantiate(tpl)
    assert resp.json()["name"] == "Onlyname"


def test_instantiate_llm_naming_falls_back_to_default():
    tpl = _template(naming_pattern={"type": "llm"})
    resp, _ = _instantiate(tpl)
    assert resp.json()["name"] == "City Guard (Instance)"


# ── instantiate: variable properties ──────────────────────────────


def test_instantiate_resolves_choice_and_range():
    tpl = _template(
        variable_properties=[
            {
                "property_path": "properties.faction",
                "generation_type": "choice",
                "options": ["watch"],
            },
            {
                "property_path": "stats.STR",
                "generation_type": "range",
                "range_min": 12,
                "range_max": 12,
            },
        ]
    )
    resp, _ = _instantiate(tpl)
    data = resp.json()
    assert data["properties"]["faction"] == "watch"
    assert data["properties"]["stats"]["STR"] == 12
    assert data["resolved_variables"]["properties.faction"] == "watch"
    assert data["resolved_variables"]["stats.STR"] == 12


def test_instantiate_fixed_uses_first_option():
    tpl = _template(variable_properties=[{"property_path": "rank", "generation_type": "fixed", "options": ["recruit"]}])
    resp, _ = _instantiate(tpl)
    assert resp.json()["properties"]["rank"] == "recruit"


def test_instantiate_llm_variables_surfaced_as_hints_not_resolved():
    tpl = _template(
        variable_properties=[
            {
                "property_path": "quirk",
                "generation_type": "llm",
                "llm_hint": "a memorable nervous tic",
            }
        ]
    )
    resp, _ = _instantiate(tpl)
    data = resp.json()
    assert data["llm_hints"] == {"quirk": "a memorable nervous tic"}
    assert "quirk" not in data["properties"]
    assert "quirk" not in data["resolved_variables"]


def test_instantiate_table_variable_rolls_on_table():
    tpl = _template(
        variable_properties=[
            {
                "property_path": "weapon",
                "generation_type": "table",
                "table_id": str(uuid4()),
            }
        ]
    )
    with patch(f"{TOOLS}.mongodb_roll_on_table", return_value={"value": "rusty halberd"}):
        resp, _ = _instantiate(tpl)
    assert resp.json()["properties"]["weapon"] == "rusty halberd"


def test_instantiate_table_variable_missing_table_is_skipped():
    tpl = _template(
        variable_properties=[
            {
                "property_path": "weapon",
                "generation_type": "table",
                "table_id": str(uuid4()),
            }
        ]
    )
    with patch(f"{TOOLS}.mongodb_roll_on_table", side_effect=ValueError("not found")):
        resp, _ = _instantiate(tpl)
    data = resp.json()
    assert "weapon" not in data["properties"]
    assert data["resolved_variables"] == {}


def test_instantiate_pattern_variable_uses_naming_lists():
    tpl = _template(
        naming_pattern={"type": "llm", "adjectives": ["Scarred"], "nouns": ["Veteran"]},
        variable_properties=[
            {
                "property_path": "epithet",
                "generation_type": "pattern",
                "pattern": "the {adjective} {noun}",
            }
        ],
    )
    resp, _ = _instantiate(tpl)
    assert resp.json()["properties"]["epithet"] == "the Scarred Veteran"


# ── instantiate: inheritance + overrides ──────────────────────────


def test_instantiate_merges_parent_base_properties_child_wins():
    parent = _template(
        name="Humanoid",
        base_properties={"role": "civilian", "species": "human", "size": "medium"},
    )
    child = _template(
        parent_template_id=parent.template_id,
        base_properties={"role": "guard"},
    )

    def fake_get(tid):
        return parent if tid == parent.template_id else child

    with (
        patch(f"{TOOLS}.mongodb_get_entity_template", side_effect=fake_get),
        patch(f"{TOOLS}.mongodb_increment_template_usage"),
    ):
        resp = client.post(f"/api/templates/{child.template_id}/instantiate", json={})
    props = resp.json()["properties"]
    assert props == {"role": "guard", "species": "human", "size": "medium"}


def test_instantiate_parent_cycle_does_not_recurse_forever():
    tid = uuid4()
    tpl = _template(template_id=tid, parent_template_id=tid, base_properties={"a": 1})
    resp, _ = _instantiate(tpl)
    assert resp.json()["properties"] == {"a": 1}


def test_instantiate_override_properties_deep_merge():
    tpl = _template(base_properties={"stats": {"STR": 10, "DEX": 8}, "role": "guard"})
    resp, _ = _instantiate(tpl, {"override_properties": {"stats": {"STR": 14}}})
    props = resp.json()["properties"]
    assert props["stats"] == {"STR": 14, "DEX": 8}
    assert props["role"] == "guard"


# ── instantiate: pass-through fields ──────────────────────────────


def test_instantiate_returns_defaults_and_context():
    tpl = _template(
        default_state_tags=["on_duty", "armed"],
        default_detail_level="sketched",
        default_personality={"trait_pool": ["gruff"], "default_disposition": "neutral"},
    )
    scene_id = uuid4()
    resp, _ = _instantiate(tpl, {"scene_id": str(scene_id), "provide_context": "night watch"})
    data = resp.json()
    assert data["state_tags"] == ["on_duty", "armed"]
    assert data["detail_level"] == "sketched"
    assert data["default_personality"]["trait_pool"] == ["gruff"]
    assert data["scene_id"] == str(scene_id)
    assert data["entity_type"] == "character"
    assert data["universe_id"] == str(tpl.universe_id)
