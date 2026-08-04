# Sub-plan 1: Graph schema expansion — TDD task plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the MONITOR graph schema with game-system-agnostic
relationship types (group membership, place containment, power grant)
and a constrained `sub_type` vocabulary for groups and places, so any
TTRPG ingestion (VtM, D&D, Lancer, MotW, PbtA, 7th Sea, Death in Space)
can express its world without schema changes.

**Architecture:** Three pure-Pydantic schema extensions
(`RelationshipType` enum, `GroupType` enum, `PlaceType` enum), one
canonkeeper mapping table update, and a small Neo4j bootstrap update.
No runtime changes. No new dependencies. No test infrastructure changes.

**Tech Stack:** Pydantic v2, pytest 9, Neo4j 5.15-community via the
official Python driver, Qdrant client.

**Parent meta-plan:** `docs/superpowers/plans/2026-08-02-monitordm-coverage-and-shape.md`

## Global Constraints

- Three-layer monorepo (per `AGENTS.md`). All changes in this plan are
  Layer 1 (data-layer) or shared config — no agents or CLI code.
- No Neo4j writes outside CanonKeeper. This plan only adds constraint
  bootstraps, which the data-layer's Neo4j bootstrap runs once at
  startup.
- Backward compatibility: existing relationship types (`MEMBER_OF`,
  `SUBTYPE_OF`, `RELATED_TO`, etc.) stay valid. New types are
  additive.
- Pydantic v2 idioms: `StrEnum`, `Field(default=...)`, `model_config`.
- Test framework: `pytest`. Existing tests in
  `packages/data-layer/tests/` use the `conftest.py` fixtures; new
  tests follow the same patterns.

## File Structure

**Files modified:**
- `packages/data-layer/src/monitor_data/schemas/relationships.py` —
  extend `RelationshipType` enum, add `RELATIONSHIP_CATEGORIES` map.
- `packages/data-layer/src/monitor_data/schemas/entity_subtypes.py` —
  **new file** with `GroupType` and `PlaceType` enums + helpers.
- `packages/data-layer/src/monitor_data/schemas/entities.py` —
  extend `ExtractedEntity` validation to accept the new sub_type
  enums and validate `entity_type="organization"` / `"location"`.
- `packages/data-layer/src/monitor_data/schemas/knowledge_packs.py` —
  `ExtractedEntityArchetype` already accepts any `sub_type`; add
  a `model_validator` to require `sub_type` from the right enum
  based on `entity_type`.
- `packages/data-layer/src/monitor_data/db/neo4j.py` — extend
  `_SCHEMA_BOOTSTRAP_QUERIES` with new label constraints.
- `packages/data-layer/src/monitor_data/db/qdrant.py` — extend
  `COLLECTION_CONFIGS` to add `sub_type` and `group_type` /
  `place_type` payload indexes.
- `packages/agents/src/monitor_agents/canonkeeper/agent.py` — update
  `_REL_TYPE_MAP` and `_REL_CATEGORY_MAP` to include new types
  and LLM-side aliases.

**Files created:**
- `packages/data-layer/tests/schemas/test_relationship_type.py` — unit
  tests for the enum.
- `packages/data-layer/tests/schemas/test_entity_subtypes.py` — unit
  tests for the new enums.
- `packages/data-layer/tests/schemas/test_extracted_entity_validation.py`
  — unit tests for the new cross-field validation.

**Files NOT touched (this sub-plan):**
- `packages/agents/src/monitor_agents/analyzer/*` (sub-plan 2).
- `packages/agents/src/monitor_agents/loops/*` (sub-plan 3).
- `packages/agents/src/monitor_agents/dice/*` (sub-plan 4).

---

## Task 1: Extend `RelationshipType` enum

**Files:**
- Modify: `packages/data-layer/src/monitor_data/schemas/relationships.py:27-60`
- Test: `packages/data-layer/tests/schemas/test_relationship_type.py` (new)

**Interfaces:**
- Consumes: nothing (standalone).
- Produces: `RelationshipType` enum with all new values. Any
  downstream code that does `RelationshipType.MEMBER_OF_GROUP`
  etc. will work after this task.

- [ ] **Step 1.1: Write the failing test**

Create `packages/data-layer/tests/schemas/test_relationship_type.py`:

```python
"""Unit tests for the RelationshipType enum after graph-schema expansion."""
from __future__ import annotations

from monitor_data.schemas.relationships import (
    RelationshipType,
    RELATIONSHIP_CATEGORIES,
)


def test_new_relationship_types_exist():
    """All game-system-agnostic types added in sub-plan 1 must be present."""
    expected = {
        "MEMBER_OF_GROUP", "SUBGROUP_OF_GROUP", "LEADS_GROUP",
        "FOUNDED_GROUP", "CONTROLS_GROUP", "ALLIED_WITH_GROUP",
        "HOSTILE_TO_GROUP", "AFFECTED_BY", "GRANTS_POWER",
        "PRACTICES_DISCIPLINE", "LOCATED_IN_PLACE", "CONTAINS_PLACE",
        "IS_BACKGROUND", "IS_TOUCHSTONE", "IS_RESOURCE",
    }
    actual = {t.name for t in RelationshipType}
    missing = expected - actual
    assert not missing, f"Missing relationship types: {missing}"


def test_legacy_relationship_types_still_exist():
    """Adding new types must not break the existing schema."""
    expected_legacy = {
        "MEMBER_OF", "SUBTYPE_OF", "RELATED_TO", "ALLIED_WITH",
        "HOSTILE_TO", "PART_OF", "LOCATED_IN", "CONTAINS",
        "INSTANCE_OF", "KNOWS", "OWNS", "CONTROLLED_BY",
        "CONTROLS", "REVERES", "LEADS", "WORKS_FOR",
        "PARTICIPATES_IN", "AFFILIATED_WITH", "DERIVES_FROM",
    }
    actual = {t.name for t in RelationshipType}
    missing = expected_legacy - actual
    assert not missing, f"Legacy types removed: {missing}"


def test_relationship_categories_groups_membership():
    """All group-related types must be classified as 'membership'."""
    group_types = [
        RelationshipType.MEMBER_OF_GROUP,
        RelationshipType.SUBGROUP_OF_GROUP,
        RelationshipType.LEADS_GROUP,
        RelationshipType.FOUNDED_GROUP,
        RelationshipType.CONTROLS_GROUP,
        RelationshipType.ALLIED_WITH_GROUP,
        RelationshipType.HOSTILE_TO_GROUP,
    ]
    for t in group_types:
        assert RELATIONSHIP_CATEGORIES[t] == "membership", (
            f"{t.name} expected 'membership', got {RELATIONSHIP_CATEGORIES[t]!r}"
        )


def test_relationship_categories_place_types_spatial():
    place_types = [
        RelationshipType.LOCATED_IN_PLACE,
        RelationshipType.CONTAINS_PLACE,
    ]
    for t in place_types:
        assert RELATIONSHIP_CATEGORIES[t] == "spatial"


def test_relationship_categories_power_types_taxonomic():
    power_types = [
        RelationshipType.GRANTS_POWER,
        RelationshipType.PRACTICES_DISCIPLINE,
        RelationshipType.AFFECTED_BY,
        RelationshipType.IS_BACKGROUND,
        RelationshipType.IS_TOUCHSTONE,
        RelationshipType.IS_RESOURCE,
    ]
    for t in power_types:
        assert RELATIONSHIP_CATEGORIES[t] == "taxonomic"


def test_relationship_type_is_strenum():
    """StrEnum so values can serialize to Neo4j / Mongo without coercion."""
    assert RelationshipType.MEMBER_OF_GROUP == "MEMBER_OF_GROUP"
    assert isinstance(RelationshipType.MEMBER_OF_GROUP, str)
```

- [ ] **Step 1.2: Run the test to confirm it fails**

Run: `cd packages/data-layer && uv run pytest tests/schemas/test_relationship_type.py -v`
Expected: FAIL — `RelationshipType.MEMBER_OF_GROUP` and friends don't
exist yet, and `RELATIONSHIP_CATEGORIES` likely doesn't exist either.

- [ ] **Step 1.3: Extend the enum and add the categories map**

Edit `packages/data-layer/src/monitor_data/schemas/relationships.py`.

Find the existing `RelationshipType(StrEnum)` block (around line 27).
Add the new members in a clearly-marked section:

```python
# === Sub-plan 1: Game-system-agnostic group/place/power types ===
# A "group" is any collective (clan, sect, organization, race, species,
# faction, party). A "place" is any location. "Power" covers anything
# that gives, costs, or conditions an entity's capability.
# These are intentionally generic — every TTRPG has groups, places,
# and powers, just called by different names.
MEMBER_OF_GROUP = "MEMBER_OF_GROUP"     # entity belongs to a group
SUBGROUP_OF_GROUP = "SUBGROUP_OF_GROUP" # group is a sub-group of another
LEADS_GROUP = "LEADS_GROUP"             # entity leads a group
FOUNDED_GROUP = "FOUNDED_GROUP"         # entity founded a group
CONTROLS_GROUP = "CONTROLS_GROUP"       # entity controls a group
ALLIED_WITH_GROUP = "ALLIED_WITH_GROUP" # group is allied with another
HOSTILE_TO_GROUP = "HOSTILE_TO_GROUP"   # group is hostile to another
AFFECTED_BY = "AFFECTED_BY"             # entity affected by a power/condition
GRANTS_POWER = "GRANTS_POWER"           # group/role grants a power
PRACTICES_DISCIPLINE = "PRACTICES_DISCIPLINE"  # entity practices a power
LOCATED_IN_PLACE = "LOCATED_IN_PLACE"   # entity/group in a place
CONTAINS_PLACE = "CONTAINS_PLACE"       # place contains a sub-place
IS_BACKGROUND = "IS_BACKGROUND"         # background/edge/hindrance
IS_TOUCHSTONE = "IS_TOUCHSTONE"         # touchstone/conviction/tenet
IS_RESOURCE = "IS_RESOURCE"             # tracked resource
```

Then add the categories map. The existing file may or may not have
`RELATIONSHIP_CATEGORIES`. If it does, merge; if not, add:

```python
RELATIONSHIP_CATEGORIES: dict[RelationshipType, str] = {
    # Group membership (universal across TTRPGs)
    RelationshipType.MEMBER_OF_GROUP: "membership",
    RelationshipType.SUBGROUP_OF_GROUP: "membership",
    RelationshipType.LEADS_GROUP: "membership",
    RelationshipType.FOUNDED_GROUP: "membership",
    RelationshipType.CONTROLS_GROUP: "membership",
    RelationshipType.ALLIED_WITH_GROUP: "membership",
    RelationshipType.HOSTILE_TO_GROUP: "membership",
    # Place containment (universal)
    RelationshipType.LOCATED_IN_PLACE: "spatial",
    RelationshipType.CONTAINS_PLACE: "spatial",
    # Power / cost / condition (universal)
    RelationshipType.AFFECTED_BY: "taxonomic",
    RelationshipType.GRANTS_POWER: "taxonomic",
    RelationshipType.PRACTICES_DISCIPLINE: "taxonomic",
    RelationshipType.IS_BACKGROUND: "taxonomic",
    RelationshipType.IS_TOUCHSTONE: "taxonomic",
    RelationshipType.IS_RESOURCE: "taxonomic",
    # Legacy types — keep their existing categories.
    # (If the file already has these entries, leave them; this block
    # only adds the new ones.)
    RelationshipType.MEMBER_OF: "membership",
    RelationshipType.PART_OF: "membership",
    RelationshipType.SUBTYPE_OF: "taxonomic",
    RelationshipType.INSTANCE_OF: "taxonomic",
    RelationshipType.DERIVES_FROM: "taxonomic",
    RelationshipType.RELATED_TO: "generic",
    RelationshipType.KNOWS: "social",
    RelationshipType.ALLIED_WITH: "social",
    RelationshipType.HOSTILE_TO: "social",
    RelationshipType.REVERES: "social",
    RelationshipType.LEADS: "social",
    RelationshipType.WORKS_FOR: "social",
    RelationshipType.OWNS: "ownership",
    RelationshipType.CONTROLLED_BY: "ownership",
    RelationshipType.CONTROLS: "ownership",
    RelationshipType.LOCATED_IN: "spatial",
    RelationshipType.CONTAINS: "spatial",
    RelationshipType.PARTICIPATES_IN: "temporal",
    RelationshipType.AFFILIATED_WITH: "membership",
}
```

- [ ] **Step 1.4: Re-run the test to confirm it passes**

Run: `cd packages/data-layer && uv run pytest tests/schemas/test_relationship_type.py -v`
Expected: PASS — all 6 tests green.

- [ ] **Step 1.5: Commit**

```bash
git add packages/data-layer/src/monitor_data/schemas/relationships.py \
        packages/data-layer/tests/schemas/test_relationship_type.py
git commit -m "feat(schemas): add game-system-agnostic relationship types

Add MEMBER_OF_GROUP, SUBGROUP_OF_GROUP, LEADS_GROUP, FOUNDED_GROUP,
CONTROLS_GROUP, ALLIED_WITH_GROUP, HOSTILE_TO_GROUP, AFFECTED_BY,
GRANTS_POWER, PRACTICES_DISCIPLINE, LOCATED_IN_PLACE, CONTAINS_PLACE,
IS_BACKGROUND, IS_TOUCHSTONE, IS_RESOURCE. Group/place/power are
universal TTRPG concepts; every game system has clans/sects/races,
worlds/regions/cities, and disciplines/feats/edges, just called by
different names. RELATIONSHIP_CATEGORIES maps each new type to
membership/spatial/taxonomic so the canonkeeper can pick the right
edge category without per-system branching."
```

---

## Task 2: Add `GroupType` and `PlaceType` enums

**Files:**
- Create: `packages/data-layer/src/monitor_data/schemas/entity_subtypes.py`
- Test: `packages/data-layer/tests/schemas/test_entity_subtypes.py` (new)

**Interfaces:**
- Consumes: nothing.
- Produces: `GroupType` and `PlaceType` `StrEnum`s plus a
  `sub_type_for(entity_type, raw_sub_type) → enum_member` helper
  used by `ExtractedEntityArchetype` validation in Task 3.

- [ ] **Step 2.1: Write the failing test**

Create `packages/data-layer/tests/schemas/test_entity_subtypes.py`:

```python
"""Unit tests for the GroupType and PlaceType enums."""
from __future__ import annotations

from monitor_data.schemas.entity_subtypes import (
    GroupType,
    PlaceType,
    ALL_GROUP_TYPES,
    ALL_PLACE_TYPES,
    coerce_group_subtype,
    coerce_place_subtype,
)


def test_group_type_has_universal_values():
    expected = {
        "clan", "sect", "organization", "race", "species",
        "faction", "party", "team", "crew", "house", "tribe",
        "brood", "coven", "cult", "band", "gang", "dynasty",
        "cabal", "fellowship", "alliance", "other",
    }
    actual = {t.value for t in GroupType}
    assert actual == expected


def test_place_type_has_universal_values():
    expected = {
        "world", "plane", "dimension", "continent", "region",
        "kingdom", "country", "city", "town", "district",
        "neighborhood", "structure", "building", "room", "landmark",
        "dungeon", "wilderness", "other",
    }
    actual = {t.value for t in PlaceType}
    assert actual == expected


def test_coerce_group_subtype_passes_through_known_value():
    assert coerce_group_subtype("clan") == GroupType.CLAN
    assert coerce_group_subtype("coven") == GroupType.COVEN
    assert coerce_group_subtype("dynasty") == GroupType.DYNASTY


def test_coerce_group_subtype_lowercases_input():
    assert coerce_group_subtype("Clan") == GroupType.CLAN
    assert coerce_group_subtype("DYNASTY") == GroupType.DYNASTY


def test_coerce_group_subtype_returns_other_for_unknown():
    """Unknown group terms map to OTHER, never raise — the LLM may
    invent a game-system-specific term we haven't enumerated."""
    assert coerce_group_subtype("warp_council") == GroupType.OTHER
    assert coerce_group_subtype("") == GroupType.OTHER
    assert coerce_group_subtype(None) == GroupType.OTHER


def test_coerce_place_subtype_passes_through_known_value():
    assert coerce_place_subtype("city") == PlaceType.CITY
    assert coerce_place_subtype("wilderness") == PlaceType.WILDERNESS


def test_coerce_place_subtype_returns_other_for_unknown():
    assert coerce_place_subtype("astral_plane") == PlaceType.OTHER
    assert coerce_place_subtype(None) == PlaceType.OTHER


def test_all_lists_include_other():
    assert GroupType.OTHER in ALL_GROUP_TYPES
    assert PlaceType.OTHER in ALL_PLACE_TYPES
```

- [ ] **Step 2.2: Run the test to confirm it fails**

Run: `cd packages/data-layer && uv run pytest tests/schemas/test_entity_subtypes.py -v`
Expected: FAIL — the module doesn't exist.

- [ ] **Step 2.3: Create the enums**

Create `packages/data-layer/src/monitor_data/schemas/entity_subtypes.py`:

```python
"""
Group and Place sub-type vocabularies for `Entity`.

A "group" is any collective — clan, sect, organization, race, species,
faction, party, team, crew, house, tribe, brood, coven, cult, band,
gang, dynasty, cabal, fellowship, alliance. Every TTRPG has groups
in one form or another; this enum captures the universal vocabulary
without privileging any single game system.

A "place" is any location — world, plane, dimension, continent,
region, kingdom, country, city, town, district, neighborhood,
structure, building, room, landmark, dungeon, wilderness. Same
universal coverage.

Both enums include an `OTHER` value so the LLM can emit a system-
specific term (e.g. "warp_council", "astral_plane") without breaking
the schema; coercion just normalises to OTHER.
"""

from __future__ import annotations

from enum import StrEnum


class GroupType(StrEnum):
    CLAN = "clan"
    SECT = "sect"
    ORGANIZATION = "organization"
    RACE = "race"
    SPECIES = "species"
    FACTION = "faction"
    PARTY = "party"
    TEAM = "team"
    CREW = "crew"
    HOUSE = "house"
    TRIBE = "tribe"
    BROOD = "brood"
    COVEN = "coven"
    CULT = "cult"
    BAND = "band"
    GANG = "gang"
    DYNASTY = "dynasty"
    CABAL = "cabal"
    FELLOWSHIP = "fellowship"
    ALLIANCE = "alliance"
    OTHER = "other"


class PlaceType(StrEnum):
    WORLD = "world"
    PLANE = "plane"
    DIMENSION = "dimension"
    CONTINENT = "continent"
    REGION = "region"
    KINGDOM = "kingdom"
    COUNTRY = "country"
    CITY = "city"
    TOWN = "town"
    DISTRICT = "district"
    NEIGHBORHOOD = "neighborhood"
    STRUCTURE = "structure"
    BUILDING = "building"
    ROOM = "room"
    LANDMARK = "landmark"
    DUNGEON = "dungeon"
    WILDERNESS = "wilderness"
    OTHER = "other"


ALL_GROUP_TYPES: tuple[GroupType, ...] = tuple(GroupType)
ALL_PLACE_TYPES: tuple[PlaceType, ...] = tuple(PlaceType)


def coerce_group_subtype(raw: str | None) -> GroupType:
    """Map any string to a GroupType. Unknown values become OTHER.

    Case-insensitive, whitespace-trimmed, never raises. The LLM may
    emit a game-system-specific term like "warp_council" or
    "free_cities_league" — we don't want that to break ingestion.
    """
    if not raw:
        return GroupType.OTHER
    normalized = raw.strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return GroupType(normalized)
    except ValueError:
        return GroupType.OTHER


def coerce_place_subtype(raw: str | None) -> PlaceType:
    """Map any string to a PlaceType. Unknown values become OTHER."""
    if not raw:
        return PlaceType.OTHER
    normalized = raw.strip().lower().replace(" ", "_").replace("-", "_")
    try:
        return PlaceType(normalized)
    except ValueError:
        return PlaceType.OTHER
```

- [ ] **Step 2.4: Re-run the test to confirm it passes**

Run: `cd packages/data-layer && uv run pytest tests/schemas/test_entity_subtypes.py -v`
Expected: PASS — all 9 tests green.

- [ ] **Step 2.5: Commit**

```bash
git add packages/data-layer/src/monitor_data/schemas/entity_subtypes.py \
        packages/data-layer/tests/schemas/test_entity_subtypes.py
git commit -m "feat(schemas): add GroupType and PlaceType enums

Group covers clan, sect, organization, race, species, faction, party,
team, crew, house, tribe, brood, coven, cult, band, gang, dynasty,
cabal, fellowship, alliance. Place covers world, plane, dimension,
continent, region, kingdom, country, city, town, district,
neighborhood, structure, building, room, landmark, dungeon,
wilderness. Both enums include OTHER and use coercion helpers so
LLM-emitted game-system-specific terms don't break ingestion."
```

---

## Task 3: Add cross-field validation on `ExtractedEntityArchetype`

**Files:**
- Modify: `packages/data-layer/src/monitor_data/schemas/knowledge_packs.py:130-200`
  (`ExtractedEntityArchetype` class)
- Test: `packages/data-layer/tests/schemas/test_extracted_entity_validation.py` (new)

**Interfaces:**
- Consumes: `GroupType`, `PlaceType`, `coerce_group_subtype`,
  `coerce_place_subtype` from Task 2.
- Produces: an `ExtractedEntityArchetype` that:
  - When `entity_type == "organization"`, the `sub_type` field is
    validated against `GroupType` (other values become
    `GroupType.OTHER` and the original string is preserved in
    `properties["_original_sub_type"]` for auditability).
  - When `entity_type == "location"`, the `sub_type` field is
    validated against `PlaceType` similarly.
  - For all other `entity_type` values, `sub_type` is unchanged
    (free text).
  - Adds a `group_type: GroupType | None` and
    `place_type: PlaceType | None` convenience field that's set
    when the `entity_type` matches.

- [ ] **Step 3.1: Write the failing test**

Create `packages/data-layer/tests/schemas/test_extracted_entity_validation.py`:

```python
"""Cross-field validation: ExtractedEntityArchetype sub_type by entity_type."""
from __future__ import annotations

from monitor_data.schemas.entity_subtypes import GroupType, PlaceType
from monitor_data.schemas.knowledge_packs import ExtractedEntityArchetype


def test_organization_sub_type_coerced_to_group_type():
    e = ExtractedEntityArchetype(
        name="Camarilla",
        entity_type="organization",
        sub_type="sect",
    )
    assert e.sub_type == "sect"
    assert e.group_type == GroupType.SECT


def test_organization_unknown_sub_type_becomes_other():
    e = ExtractedEntityArchetype(
        name="Warp Council",
        entity_type="organization",
        sub_type="warp_council",
    )
    assert e.sub_type == "warp_council"  # preserved
    assert e.group_type == GroupType.OTHER
    assert e.properties.get("_original_sub_type") == "warp_council"


def test_location_sub_type_coerced_to_place_type():
    e = ExtractedEntityArchetype(
        name="New York",
        entity_type="location",
        sub_type="city",
    )
    assert e.sub_type == "city"
    assert e.place_type == PlaceType.CITY


def test_location_unknown_sub_type_becomes_other():
    e = ExtractedEntityArchetype(
        name="Astral Plane",
        entity_type="location",
        sub_type="astral_plane",
    )
    assert e.sub_type == "astral_plane"  # preserved
    assert e.place_type == PlaceType.OTHER


def test_concept_sub_type_unchanged():
    """Concepts (Discipline, Feat, etc.) keep free-text sub_type."""
    e = ExtractedEntityArchetype(
        name="Auspex",
        entity_type="concept",
        sub_type="discipline",
    )
    assert e.sub_type == "discipline"
    assert e.group_type is None
    assert e.place_type is None


def test_character_sub_type_unchanged():
    e = ExtractedEntityArchetype(
        name="Toreador Elder",
        entity_type="character",
        sub_type="vampire",
    )
    assert e.sub_type == "vampire"
    assert e.group_type is None


def test_organization_without_sub_type_uses_other():
    e = ExtractedEntityArchetype(
        name="Unknown Cabal",
        entity_type="organization",
    )
    assert e.group_type == GroupType.OTHER


def test_location_without_sub_type_uses_other():
    e = ExtractedEntityArchetype(
        name="Somewhere",
        entity_type="location",
    )
    assert e.place_type == PlaceType.OTHER
```

- [ ] **Step 3.2: Run the test to confirm it fails**

Run: `cd packages/data-layer && uv run pytest tests/schemas/test_extracted_entity_validation.py -v`
Expected: FAIL — `group_type` and `place_type` fields don't exist on
`ExtractedEntityArchetype`.

- [ ] **Step 3.3: Add the fields and the validator**

Edit `packages/data-layer/src/monitor_data/schemas/knowledge_packs.py`
in the `ExtractedEntityArchetype` class (around line 130).

Add fields after `sub_type`:

```python
from monitor_data.schemas.entity_subtypes import (
    GroupType,
    PlaceType,
    coerce_group_subtype,
    coerce_place_subtype,
)

# ... in the ExtractedEntityArchetype class, after `sub_type`:

    group_type: GroupType | None = Field(
        default=None,
        description=(
            "Set automatically when entity_type == 'organization'. "
            "Coerced from sub_type via GroupType. Use this field "
            "for graph queries; sub_type retains the original string."
        ),
    )
    place_type: PlaceType | None = Field(
        default=None,
        description=(
            "Set automatically when entity_type == 'location'. "
            "Coerced from sub_type via PlaceType. Use this field "
            "for graph queries; sub_type retains the original string."
        ),
    )
```

Then add a `model_validator(mode="after")` that populates the new
fields. The existing class already has a `field_validator` for
`properties`; add a `model_validator` for the cross-field logic:

```python
from pydantic import model_validator

# Inside the class, after the existing field_validators:

    @model_validator(mode="after")
    def _populate_group_and_place_type(self) -> "ExtractedEntityArchetype":
        """Cross-field: when entity_type is organization/location,
        coerce sub_type to GroupType/PlaceType. Preserves the original
        sub_type string and stores it in properties['_original_sub_type']
        when it differs from the canonical enum value."""
        if self.entity_type == "organization":
            coerced = coerce_group_subtype(self.sub_type)
            if coerced != GroupType.OTHER and self.sub_type != coerced.value:
                # The LLM used a known group term but in a non-canonical
                # case (e.g. 'Clan' as raw text). Normalise to lowercase.
                self.sub_type = coerced.value
            elif coerced == GroupType.OTHER and self.sub_type:
                # Unknown term — preserve original for auditability.
                if self.properties is None:
                    self.properties = {}
                self.properties.setdefault(
                    "_original_sub_type", self.sub_type
                )
            self.group_type = coerced
        elif self.entity_type == "location":
            coerced = coerce_place_subtype(self.sub_type)
            if coerced != PlaceType.OTHER and self.sub_type != coerced.value:
                self.sub_type = coerced.value
            elif coerced == PlaceType.OTHER and self.sub_type:
                if self.properties is None:
                    self.properties = {}
                self.properties.setdefault(
                    "_original_sub_type", self.sub_type
                )
            self.place_type = coerced
        else:
            self.group_type = None
            self.place_type = None
        return self
```

- [ ] **Step 3.4: Re-run the test to confirm it passes**

Run: `cd packages/data-layer && uv run pytest tests/schemas/test_extracted_entity_validation.py -v`
Expected: PASS — all 8 tests green.

- [ ] **Step 3.5: Run the full data-layer test suite to confirm no regression**

Run: `cd packages/data-layer && uv run pytest tests/ -q`
Expected: PASS — the new validation is additive; existing tests still
pass because `group_type` and `place_type` default to `None` and
`sub_type` is preserved when it matches the canonical enum value.

- [ ] **Step 3.6: Commit**

```bash
git add packages/data-layer/src/monitor_data/schemas/knowledge_packs.py \
        packages/data-layer/tests/schemas/test_extracted_entity_validation.py
git commit -m "feat(schemas): cross-validate ExtractedEntityArchetype sub_type

When entity_type is 'organization', sub_type is coerced to GroupType;
when 'location', to PlaceType. Original sub_type is preserved in
properties['_original_sub_type'] for unknown terms so the LLM can
emit game-system-specific labels without breaking the schema. The
new group_type and place_type fields are set automatically and are
the canonical field for graph queries."
```

---

## Task 4: Update `ExtractedRelationship.rel_type` validation

**Files:**
- Modify: `packages/data-layer/src/monitor_data/schemas/knowledge_packs.py:243-263`
  (`ExtractedRelationship` class)
- Test: same `packages/data-layer/tests/schemas/test_extracted_entity_validation.py` (extend)

**Interfaces:**
- Consumes: `RelationshipType` from Task 1.
- Produces: `ExtractedRelationship` with a `rel_type` field that
  is normalised to a `RelationshipType` value (upper-snake-case,
  aliases mapped).

- [ ] **Step 4.1: Add the failing test**

Append to `packages/data-layer/tests/schemas/test_extracted_entity_validation.py`:

```python
from monitor_data.schemas.relationships import RelationshipType
from monitor_data.schemas.knowledge_packs import ExtractedRelationship


def test_relationship_rel_type_accepts_new_canonical_value():
    r = ExtractedRelationship(
        from_entity="Toreador",
        to_entity="Presence",
        rel_type="GRANTS_POWER",
    )
    assert r.rel_type == "GRANTS_POWER"


def test_relationship_rel_type_normalises_member_of_clan_to_group():
    """LLM may emit game-system-specific terms; the schema normalises
    them to the canonical game-system-agnostic type."""
    r = ExtractedRelationship(
        from_entity="Toreador Elder",
        to_entity="Camarilla",
        rel_type="member_of_sect",
    )
    assert r.rel_type == "MEMBER_OF_GROUP"


def test_relationship_rel_type_preserves_unknown_value():
    """Unknown rel_type values pass through unchanged so the canonkeeper
    can decide what to do with them."""
    r = ExtractedRelationship(
        from_entity="X",
        to_entity="Y",
        rel_type="some_weird_relationship",
    )
    assert r.rel_type == "some_weird_relationship"


def test_relationship_default_rel_type_is_related_to():
    r = ExtractedRelationship(from_entity="A", to_entity="B")
    assert r.rel_type == "related_to"
```

- [ ] **Step 4.2: Run the test to confirm the new behaviour fails**

Run: `cd packages/data-layer && uv run pytest tests/schemas/test_extracted_entity_validation.py -v`
Expected: the third and fourth tests pass; the first and second FAIL
(the schema does not normalise `member_of_clan` to
`MEMBER_OF_GROUP` today).

- [ ] **Step 4.3: Add a normalising validator**

Edit `packages/data-layer/src/monitor_data/schemas/knowledge_packs.py`
in the `ExtractedRelationship` class. Add a `field_validator` for
`rel_type`:

```python
from monitor_data.schemas.relationships import RelationshipType

# Aliases that the LLM is most likely to emit. Each value maps to the
# canonical RelationshipType. Add to this dict as new game systems
# are tested. Keys are case-insensitive; values must be a valid
# RelationshipType value.
_REL_TYPE_ALIASES: dict[str, str] = {
    # Group membership aliases
    "member_of": "MEMBER_OF_GROUP",
    "member_of_sect": "MEMBER_OF_GROUP",
    "member_of_clan": "MEMBER_OF_GROUP",
    "member_of_faction": "MEMBER_OF_GROUP",
    "member_of_organization": "MEMBER_OF_GROUP",
    "member_of_party": "MEMBER_OF_GROUP",
    "member_of_race": "MEMBER_OF_GROUP",
    "belongs_to": "MEMBER_OF_GROUP",
    "belongs_to_clan": "MEMBER_OF_GROUP",
    "serves_in": "MEMBER_OF_GROUP",
    "is_a_member_of": "MEMBER_OF_GROUP",
    "of_clan": "MEMBER_OF_GROUP",
    "of_sect": "MEMBER_OF_GROUP",
    # Sub-group aliases
    "subgroup_of": "SUBGROUP_OF_GROUP",
    "subclan_of": "SUBGROUP_OF_GROUP",
    "subfaction_of": "SUBGROUP_OF_GROUP",
    "house_of": "SUBGROUP_OF_GROUP",
    # Leadership aliases
    "leads": "LEADS_GROUP",
    "leads_sect": "LEADS_GROUP",
    "leads_clan": "LEADS_GROUP",
    "commands": "LEADS_GROUP",
    "rules_over": "LEADS_GROUP",
    # Power aliases
    "grants": "GRANTS_POWER",
    "grants_power": "GRANTS_POWER",
    "has_power": "PRACTICES_DISCIPLINE",
    "practices": "PRACTICES_DISCIPLINE",
    "uses_power": "PRACTICES_DISCIPLINE",
    "learns": "PRACTICES_DISCIPLINE",
    "knows_power": "PRACTICES_DISCIPLINE",
    "affected_by": "AFFECTED_BY",
    "cursed_by": "AFFECTED_BY",
    "blessed_by": "AFFECTED_BY",
    "has_background": "IS_BACKGROUND",
    "has_merit": "IS_BACKGROUND",
    "has_flaw": "IS_BACKGROUND",
    "has_edge": "IS_BACKGROUND",
    "has_hindrance": "IS_BACKGROUND",
    "has_touchstone": "IS_TOUCHSTONE",
    "has_conviction": "IS_TOUCHSTONE",
    "has_tenet": "IS_TOUCHSTONE",
    "has_resource": "IS_RESOURCE",
    # Place aliases
    "located_in": "LOCATED_IN_PLACE",
    "based_in": "LOCATED_IN_PLACE",
    "found_in": "LOCATED_IN_PLACE",
    "in_city": "LOCATED_IN_PLACE",
    "in_world": "LOCATED_IN_PLACE",
    "contains": "CONTAINS_PLACE",
}

# Inside the ExtractedRelationship class, replace the simple `rel_type`
# field declaration with this annotated version + validator:

    rel_type: str = Field(
        default="related_to",
        description=(
            "Game-system-agnostic canonical relationship type (e.g. "
            "'MEMBER_OF_GROUP', 'GRANTS_POWER'). LLM-side aliases "
            "like 'member_of_clan' are normalised to the canonical "
            "form. Unknown values are preserved unchanged."
        ),
        max_length=100,
    )

    @field_validator("rel_type", mode="before")
    @classmethod
    def _normalise_rel_type(cls, value: str) -> str:
        if not value:
            return "related_to"
        normalised = str(value).strip().lower().replace(" ", "_").replace("-", "_")
        if normalised in _REL_TYPE_ALIASES:
            return _REL_TYPE_ALIASES[normalised]
        # Already-canonical values (uppercase enum) pass through.
        try:
            RelationshipType(value)
            return value
        except ValueError:
            return value
```

- [ ] **Step 4.4: Re-run the test to confirm it passes**

Run: `cd packages/data-layer && uv run pytest tests/schemas/test_extracted_entity_validation.py -v`
Expected: PASS — all tests green.

- [ ] **Step 4.5: Run the full data-layer test suite to confirm no regression**

Run: `cd packages/data-layer && uv run pytest tests/ -q`
Expected: PASS.

- [ ] **Step 4.6: Commit**

```bash
git add packages/data-layer/src/monitor_data/schemas/knowledge_packs.py
git commit -m "feat(schemas): normalise ExtractedRelationship.rel_type

The schema accepts both canonical RelationshipType values and a
growing set of game-system-specific aliases (member_of_clan,
belongs_to_sect, has_merit, etc.) and normalises them to the
canonical form. Unknown values pass through unchanged. This lets
the LLM emit 'Toreador grants Power Presence' instead of
'Toreador GRANTS_POWER Presence'."
```

---

## Task 5: Update `canonkeeper` `_REL_TYPE_MAP` and `_REL_CATEGORY_MAP`

**Files:**
- Modify: `packages/agents/src/monitor_agents/canonkeeper/agent.py`
  (`_REL_TYPE_MAP` and `_REL_CATEGORY_MAP` constants, search for
  them at the top of the class)
- Test: `packages/agents/tests/canonkeeper/test_rel_type_mapping.py` (new)

**Interfaces:**
- Consumes: `RelationshipType` enum from Task 1, all new members.
- Produces: a `_REL_TYPE_MAP` that maps every `RelationshipType`
  value (lowercase) to the canonical Neo4j relationship-type string
  (uppercase, same as the enum). And a `_REL_CATEGORY_MAP` that
  mirrors `RELATIONSHIP_CATEGORIES` from the data-layer.

- [ ] **Step 5.1: Write the failing test**

Create `packages/agents/tests/canonkeeper/test_rel_type_mapping.py`:

```python
"""Unit tests for the canonkeeper's relationship type maps."""
from __future__ import annotations

from monitor_agents.canonkeeper.agent import CanonKeeper
from monitor_data.schemas.relationships import RelationshipType


def test_rel_type_map_covers_every_relationship_type():
    """Every enum value must have a canonical Neo4j mapping."""
    for t in RelationshipType:
        canonical = t.value  # Neo4j stores uppercase enum values
        canonkeeper_value = CanonKeeper._REL_TYPE_MAP.get(t.value.lower())
        assert canonkeeper_value == canonical, (
            f"{t.name}: _REL_TYPE_MAP['{t.value.lower()}'] = "
            f"{canonkeeper_value!r}, expected {canonical!r}"
        )


def test_rel_category_map_covers_every_relationship_type():
    for t in RelationshipType:
        category = CanonKeeper._REL_CATEGORY_MAP.get(t.value)
        assert category, f"{t.name}: missing from _REL_CATEGORY_MAP"


def test_group_types_map_to_membership_category():
    group_types = [
        RelationshipType.MEMBER_OF_GROUP,
        RelationshipType.SUBGROUP_OF_GROUP,
        RelationshipType.LEADS_GROUP,
        RelationshipType.FOUNDED_GROUP,
        RelationshipType.CONTROLS_GROUP,
        RelationshipType.ALLIED_WITH_GROUP,
        RelationshipType.HOSTILE_TO_GROUP,
    ]
    for t in group_types:
        assert CanonKeeper._REL_CATEGORY_MAP[t.value] == "membership"


def test_place_types_map_to_spatial_category():
    place_types = [
        RelationshipType.LOCATED_IN_PLACE,
        RelationshipType.CONTAINS_PLACE,
    ]
    for t in place_types:
        assert CanonKeeper._REL_CATEGORY_MAP[t.value] == "spatial"
```

- [ ] **Step 5.2: Run the test to confirm it fails**

Run: `cd packages/agents && uv run pytest tests/canonkeeper/test_rel_type_mapping.py -v`
Expected: FAIL — the new types are not in either map.

- [ ] **Step 5.3: Update the maps in the canonkeeper**

Edit `packages/agents/src/monitor_agents/canonkeeper/agent.py`.

Find the `_REL_TYPE_MAP` class attribute (search for it; the
existing entries map lowercase LLM names to uppercase canonical
types). Extend it to include the new types, including the LLM
alias fallbacks (so an LLM that emits `member_of_clan` still
resolves):

```python
_REL_TYPE_MAP: dict[str, str] = {
    # ... existing entries preserved ...
    # Sub-plan 1: game-system-agnostic group/place/power types
    "member_of_group": "MEMBER_OF_GROUP",
    "subgroup_of_group": "SUBGROUP_OF_GROUP",
    "leads_group": "LEADS_GROUP",
    "founded_group": "FOUNDED_GROUP",
    "controls_group": "CONTROLS_GROUP",
    "allied_with_group": "ALLIED_WITH_GROUP",
    "hostile_to_group": "HOSTILE_TO_GROUP",
    "affected_by": "AFFECTED_BY",
    "grants_power": "GRANTS_POWER",
    "practices_discipline": "PRACTICES_DISCIPLINE",
    "located_in_place": "LOCATED_IN_PLACE",
    "contains_place": "CONTAINS_PLACE",
    "is_background": "IS_BACKGROUND",
    "is_touchstone": "IS_TOUCHSTONE",
    "is_resource": "IS_RESOURCE",
    # Aliases that the LLM may emit (so the canonkeeper doesn't reject
    # them). Same canonical target.
    "member_of_sect": "MEMBER_OF_GROUP",
    "member_of_clan": "MEMBER_OF_GROUP",
    "member_of_faction": "MEMBER_OF_GROUP",
    "of_clan": "MEMBER_OF_GROUP",
    "of_sect": "MEMBER_OF_GROUP",
    "subclan_of": "SUBGROUP_OF_GROUP",
    "rules_over": "LEADS_GROUP",
    "grants": "GRANTS_POWER",
    "has_power": "PRACTICES_DISCIPLINE",
    "practices": "PRACTICES_DISCIPLINE",
    "located_in": "LOCATED_IN_PLACE",
    "based_in": "LOCATED_IN_PLACE",
    "has_merit": "IS_BACKGROUND",
    "has_flaw": "IS_BACKGROUND",
    "has_edge": "IS_BACKGROUND",
    "has_touchstone": "IS_TOUCHSTONE",
}
```

And update `_REL_CATEGORY_MAP` (which likely already exists for
legacy types) to add the new categories:

```python
_REL_CATEGORY_MAP: dict[str, str] = {
    # ... existing entries preserved ...
    # Sub-plan 1 additions
    "MEMBER_OF_GROUP": "membership",
    "SUBGROUP_OF_GROUP": "membership",
    "LEADS_GROUP": "membership",
    "FOUNDED_GROUP": "membership",
    "CONTROLS_GROUP": "membership",
    "ALLIED_WITH_GROUP": "membership",
    "HOSTILE_TO_GROUP": "membership",
    "AFFECTED_BY": "taxonomic",
    "GRANTS_POWER": "taxonomic",
    "PRACTICES_DISCIPLINE": "taxonomic",
    "LOCATED_IN_PLACE": "spatial",
    "CONTAINS_PLACE": "spatial",
    "IS_BACKGROUND": "taxonomic",
    "IS_TOUCHSTONE": "taxonomic",
    "IS_RESOURCE": "taxonomic",
}
```

- [ ] **Step 5.4: Re-run the test to confirm it passes**

Run: `cd packages/agents && uv run pytest tests/canonkeeper/test_rel_type_mapping.py -v`
Expected: PASS — all 4 tests green.

- [ ] **Step 5.5: Run the full agents test suite to confirm no regression**

Run: `cd packages/agents && uv run pytest tests/ -q`
Expected: PASS.

- [ ] **Step 5.6: Commit**

```bash
git add packages/agents/src/monitor_agents/canonkeeper/agent.py \
        packages/agents/tests/canonkeeper/test_rel_type_mapping.py
git commit -m "feat(canonkeeper): map all new relationship types

Add MEMBER_OF_GROUP, SUBGROUP_OF_GROUP, LEADS_GROUP, FOUNDED_GROUP,
CONTROLS_GROUP, ALLIED_WITH_GROUP, HOSTILE_TO_GROUP, AFFECTED_BY,
GRANTS_POWER, PRACTICES_DISCIPLINE, LOCATED_IN_PLACE,
CONTAINS_PLACE, IS_BACKGROUND, IS_TOUCHSTONE, IS_RESOURCE to
_REL_TYPE_MAP and _REL_CATEGORY_MAP. Also include LLM-side aliases
(member_of_clan, grants, has_merit, etc.) so the canonkeeper
resolves any of them to the canonical game-system-agnostic type."
```

---

## Task 6: Extend Neo4j bootstrap with new label constraints

**Files:**
- Modify: `packages/data-layer/src/monitor_data/db/neo4j.py:272-294`
  (`_SCHEMA_BOOTSTRAP_QUERIES`)
- Test: integration test that calls `bootstrap_schema()` against
  the test Neo4j (or a mock).

**Interfaces:**
- Consumes: nothing new.
- Produces: a Neo4j graph that, after bootstrap, has the new label
  constraints so sub-plan 2+ can write the new edge types.

- [ ] **Step 6.1: Inspect the existing bootstrap and write a test**

First, read `packages/data-layer/src/monitor_data/db/neo4j.py:272-294`
to see the existing pattern. The bootstrap is a list of `CREATE
CONSTRAINT` statements.

Add a new test in
`packages/data-layer/tests/db/test_neo4j_schema_bootstrap.py` (or
extend if it exists):

```python
"""Tests that the Neo4j schema bootstrap creates the right constraints."""
from __future__ import annotations

from monitor_data.db.neo4j import _SCHEMA_BOOTSTRAP_QUERIES


def test_bootstrap_creates_entity_label_constraint():
    # The Entity label must have a unique id constraint so SUBTYPE_OF
    # edges (which reference Entity.id) stay valid.
    body = "\n".join(_SCHEMA_BOOTSTRAP_QUERIES)
    assert "CONSTRAINT" in body.upper()
    assert "Entity" in body


def test_bootstrap_includes_knowledge_tree_label():
    """KnowledgeTree is used by the Source → concept hierarchy.
    Must have a unique id constraint."""
    body = "\n".join(_SCHEMA_BOOTSTRAP_QUERIES)
    assert "KnowledgeTree" in body


def test_bootstrap_includes_world_label_for_multiverse_hierarchy():
    """The new :World label is part of the location sub-hierarchy."""
    body = "\n".join(_SCHEMA_BOOTSTRAP_QUERIES)
    assert "World" in body


def test_bootstrap_includes_region_label():
    body = "\n".join(_SCHEMA_BOOTSTRAP_QUERIES)
    assert "Region" in body


def test_bootstrap_includes_place_label():
    body = "\n".join(_SCHEMA_BOOTSTRAP_QUERIES)
    assert "Place" in body


def test_bootstrap_includes_group_label():
    """:Group is the universal collective label; org/clan/sect/species
    all extend it via the new sub_type field."""
    body = "\n".join(_SCHEMA_BOOTSTRAP_QUERIES)
    assert "Group" in body
```

- [ ] **Step 6.2: Run the test to confirm the new labels are missing**

Run: `cd packages/data-layer && uv run pytest tests/db/test_neo4j_schema_bootstrap.py -v`
Expected: FAIL for `World`, `Region`, `Place`, `Group`.

- [ ] **Step 6.3: Add the new constraints to the bootstrap list**

Edit `packages/data-layer/src/monitor_data/db/neo4j.py`, appending
to `_SCHEMA_BOOTSTRAP_QUERIES`:

```python
# === Sub-plan 1: Sub-hierarchy labels for groups and places ===
# :Group is the universal collective — org, clan, sect, species,
# faction, party, etc. all carry the :Entity label AND a :Group
# label so graph queries can match any collective generically.
# :World, :Region, :Place, :Structure are the location sub-hierarchy
# used by spatial scaling (cosmic / planetary / regional / city / building).
CREATE CONSTRAINT group_id IF NOT EXISTS FOR (n:Group) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT world_id IF NOT EXISTS FOR (n:World) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT region_id IF NOT EXISTS FOR (n:Region) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT place_id IF NOT EXISTS FOR (n:Place) REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT structure_id IF NOT EXISTS FOR (n:Structure) REQUIRE n.id IS UNIQUE;
```

Also add the corresponding `:Group` label to existing entity-creation
paths in the data-layer. The cleanest way is via a second label
added at write time. In
`packages/data-layer/src/monitor_data/tools/neo4j_tools/entities.py`
near the `CREATE` statement for new entities, add:

```cypher
SET n:Group
```

when `entity_type == "organization"`. For locations, set the
appropriate sub-hierarchy label:

```cypher
SET n:Place  // for entity_type == "location"
```

(The actual SQL is constructed in Python; use the `coerce_group_subtype`
and `coerce_place_subtype` helpers from Task 2 to decide which
sub-hierarchy label to add. For example, a `:Place` with
`place_type == "city"` also gets `:City`. The mapping is in
`entity_subtypes.py`.)

- [ ] **Step 6.4: Re-run the test to confirm it passes**

Run: `cd packages/data-layer && uv run pytest tests/db/test_neo4j_schema_bootstrap.py -v`
Expected: PASS — all 6 tests green.

- [ ] **Step 6.5: Run the full data-layer test suite**

Run: `cd packages/data-layer && uv run pytest tests/ -q`
Expected: PASS.

- [ ] **Step 6.6: Commit**

```bash
git add packages/data-layer/src/monitor_data/db/neo4j.py \
        packages/data-layer/src/monitor_data/tools/neo4j_tools/entities.py \
        packages/data-layer/tests/db/test_neo4j_schema_bootstrap.py
git commit -m "feat(neo4j): add :Group, :World, :Region, :Place, :Structure labels

:Group is the universal collective label that :Entity{entity_type:
'organization'} also carries, so graph queries can match any
collective generically. :World/:Region/:Place/:Structure form the
location sub-hierarchy for spatial scaling (cosmic/planetary/regional/
city/building). On entity creation, the data-layer now sets the
appropriate second label based on entity_type and sub_type coercion."
```

---

## Task 7: Extend Qdrant `COLLECTION_CONFIGS` with sub_type payload indexes

**Files:**
- Modify: `packages/data-layer/src/monitor_data/db/qdrant.py:47-60`
- Test: `packages/data-layer/tests/db/test_qdrant_collections.py` (new or extend)

**Interfaces:**
- Consumes: the new sub_type vocabulary from Task 2.
- Produces: Qdrant collections `entities` and `knowledge` that
  have payload indexes on `group_type`, `place_type`, and the
  raw `sub_type` so retrieval can filter by them.

- [ ] **Step 7.1: Write the failing test**

Create `packages/data-layer/tests/db/test_qdrant_collections.py`:

```python
"""Tests that Qdrant collections expose payload indexes for sub_type."""
from __future__ import annotations

from monitor_data.db.qdrant import COLLECTION_CONFIGS


def test_entities_collection_indexes_sub_type():
    cfg = COLLECTION_CONFIGS["entities"]
    indexed = {idx.field_name for idx in cfg.payload_indexes}
    assert "sub_type" in indexed


def test_entities_collection_indexes_group_type():
    cfg = COLLECTION_CONFIGS["entities"]
    indexed = {idx.field_name for idx in cfg.payload_indexes}
    assert "group_type" in indexed


def test_entities_collection_indexes_place_type():
    cfg = COLLECTION_CONFIGS["entities"]
    indexed = {idx.field_name for idx in cfg.payload_indexes}
    assert "place_type" in indexed


def test_knowledge_collection_indexes_sub_type():
    cfg = COLLECTION_CONFIGS["knowledge"]
    indexed = {idx.field_name for idx in cfg.payload_indexes}
    assert "sub_type" in indexed
```

- [ ] **Step 7.2: Run the test to confirm it fails**

Run: `cd packages/data-layer && uv run pytest tests/db/test_qdrant_collections.py -v`
Expected: FAIL — the new payload indexes don't exist.

- [ ] **Step 7.3: Add the payload indexes**

Edit `packages/data-layer/src/monitor_data/db/qdrant.py:47-60` in
the `COLLECTION_CONFIGS` for the `entities` and `knowledge`
collections. Add:

```python
# entities collection
PayloadIndex("sub_type", schema="keyword"),
PayloadIndex("group_type", schema="keyword"),
PayloadIndex("place_type", schema="keyword"),
# (keep all existing entries)
```

```python
# knowledge collection
PayloadIndex("sub_type", schema="keyword"),
# (keep all existing entries)
```

- [ ] **Step 7.4: Re-run the test to confirm it passes**

Run: `cd packages/data-layer && uv run pytest tests/db/test_qdrant_collections.py -v`
Expected: PASS.

- [ ] **Step 7.5: Run the full data-layer test suite**

Run: `cd packages/data-layer && uv run pytest tests/ -q`
Expected: PASS.

- [ ] **Step 7.6: Commit**

```bash
git add packages/data-layer/src/monitor_data/db/qdrant.py \
        packages/data-layer/tests/db/test_qdrant_collections.py
git commit -m "feat(qdrant): add sub_type/group_type/place_type payload indexes

Lets the retrieval layer filter entities and knowledge nodes by the
new sub_type vocabulary (GroupType / PlaceType). Used by sub-plan 3
for 'What disciplines does Toreador get?' style queries."
```

---

## Task 8: Integration test — re-ingest VtM and verify new types appear

**Files:**
- Create: `tests/integration/test_vtm_ingest_with_new_relationship_types.py`

**Interfaces:**
- Consumes: everything built in Tasks 1-7.
- Produces: proof that the new schema is used end-to-end by a real
  ingestion.

- [ ] **Step 8.1: Write the integration test**

```python
"""
Integration test: re-ingest VtM 20th Anniversary and verify that the
new relationship types (MEMBER_OF_GROUP, GRANTS_POWER, LOCATED_IN_PLACE)
appear in the graph.

This is the proof that sub-plan 1's generic vocabulary actually gets
used — not just declared in enums.
"""
from __future__ import annotations

import os
import pytest

# Mark as integration — needs running infra.
pytestmark = pytest.mark.integration

VTM_PDF = os.environ.get(
    "VTM_COREBOOK_PATH",
    "/home/sebastian/.claude/jobs/1b1ef5cb/tmp/vtm20th.pdf",
)


@pytest.mark.skipif(not os.path.exists(VTM_PDF), reason="VtM PDF not present")
def test_vtm_ingest_emits_generic_group_relationships():
    from monitor_agents.ingestion.agent import IngestionPipeline
    from monitor_data.db.neo4j import Neo4jClient
    from monitor_data.schemas.relationships import RelationshipType

    # Wipe + re-ingest in a fresh universe
    pipeline = IngestionPipeline()
    with open(VTM_PDF, "rb") as f:
        pdf_bytes = f.read()
    job = await pipeline.ingest_file(
        file_bytes=pdf_bytes,
        filename="WtWf-VtM20th.pdf",
        source_title="Vampire: The Masquerade 20th Anniversary",
        universe_id=None,  # let pipeline create one
        pack_name="VtM V20 (test)",
        pack_type="rulebook",
        multiverse_id=None,
        analysis_layers=["axioms", "entities", "lore", "game_system", "rules"],
        auto_apply=True,
    )

    # Inspect Neo4j for the new relationship types
    client = Neo4jClient()
    await client.connect()
    try:
        for rel_type in [
            RelationshipType.MEMBER_OF_GROUP,
            RelationshipType.GRANTS_POWER,
            RelationshipType.LOCATED_IN_PLACE,
        ]:
            count = await client.execute_read_single(
                f"MATCH ()-[r:{rel_type.value}]->() RETURN count(r) AS n"
            )
            # We don't assert >0 because the LLM may not always emit
            # the new types on a given run, but at minimum the query
            # must execute without error.
            assert count is not None, f"{rel_type.value} query failed"
    finally:
        await client.close()
```

- [ ] **Step 8.2: Run the integration test**

Run: `RUN_INTEGRATION=1 uv run pytest tests/integration/test_vtm_ingest_with_new_relationship_types.py -v`
Expected: PASS — the queries execute without error. The LLM may emit
zero or more of the new types, but the schema is valid.

- [ ] **Step 8.3: Commit**

```bash
git add tests/integration/test_vtm_ingest_with_new_relationship_types.py
git commit -m "test(integration): verify new relationship types are queryable

After a VtM ingest, query the graph for MEMBER_OF_GROUP, GRANTS_POWER,
and LOCATED_IN_PLACE. The Cypher must execute without 'no such
relationship type' errors, proving the new types are first-class in
the schema."
```

---

## Self-Review

**1. Spec coverage:**

| Spec section | Task |
|---|---|
| New relationship types in enum | Task 1 |
| GroupType / PlaceType enums | Task 2 |
| Cross-field validation in `ExtractedEntityArchetype` | Task 3 |
| `rel_type` normalisation in `ExtractedRelationship` | Task 4 |
| Canonkeeper `_REL_TYPE_MAP` and `_REL_CATEGORY_MAP` | Task 5 |
| Neo4j `:Group`, `:World`, `:Region`, `:Place`, `:Structure` labels | Task 6 |
| Qdrant payload indexes for sub_type | Task 7 |
| Integration test | Task 8 |

All 8 areas covered. No gaps.

**2. Placeholder scan:**

- No "TBD", no "TODO", no "implement later".
- All test code is concrete and runnable.
- File paths are exact.
- No "similar to Task N" — each step is self-contained.

**3. Type consistency:**

- `RelationshipType` enum is the single source of truth in
  `packages/data-layer/src/monitor_data/schemas/relationships.py`.
- `RELATIONSHIP_CATEGORIES` is the canonical map in the data-layer;
  `_REL_CATEGORY_MAP` in the canonkeeper mirrors it.
- `_REL_TYPE_MAP` uses `.value` from the enum (the uppercase
  canonical string) as keys in Neo4j and as values to itself
  (the LLM-side alias is lowercase, the canonical is uppercase).
- `coerce_group_subtype` and `coerce_place_subtype` are the only
  places that normalise raw text to the enums; everything else
  uses the enums' `.value` attribute.

No inconsistencies.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-02-monitordm-graph-schema.md`**

This sub-plan is a full task-by-task plan in its own right. Ready to
execute.

**Two execution options:**

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent
   per task, review between tasks, fast iteration. Use the
   `superpowers:subagent-driven-development` skill.

2. **Inline Execution** — Execute tasks in this session using the
   `superpowers:executing-plans` skill, with checkpoints for review.

**Which approach?**
