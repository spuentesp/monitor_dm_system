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

    Case-insensitive, whitespace/dash-normalised, never raises. The
    LLM may emit a game-system-specific term like "warp_council" or
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
