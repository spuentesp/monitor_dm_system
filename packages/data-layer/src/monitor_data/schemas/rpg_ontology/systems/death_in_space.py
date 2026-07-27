"""
Death in Space RPG — typed ontology implementation.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only + monitor_data.schemas.rpg_ontology.base

Source
------
*Death in Space Core Rules* (2022), MORK BORG Publishing.
ISBN: 978-91-988176-0-1

System Summary
--------------
Death in Space is a gritty sci-fi RPG set in a decaying space station called
the Ypsilon 14 Ring.  Characters are desperate drifters fighting for survival
in a dying universe.

Core Mechanics:
  - Roll d20 under attribute (lower is riskier)
  - Attributes: BODY, DEX, SAVVY, TECH (-3 to +3)
  - HP = max(1, BODY + 6)
  - Cosmic Rot: 0-10 scale — cosmic mutations, powers, and corruption

This module registers **DEATH_IN_SPACE** with the ``GameSystemRegistry``
at import time.

Usage
-----
::

    from monitor_data.schemas.rpg_ontology.systems.death_in_space import (
        DISCharacterSheet,
        DISWeapon,
        DISArmor,
        DISOrigin,
        DEATH_IN_SPACE,
    )

    sheet = DISCharacterSheet(
        entity_id=uuid4(),
        character_name="Zyx the Wanderer",
        body=1, dex=2, savvy=-1, tech=0,
        hp=7, max_hp=7,
        origin=DISOrigin.CONTRACTOR,
        drive="Find my lost crew",
    )
"""

from __future__ import annotations

from enum import Enum, StrEnum
from typing import ClassVar

from pydantic import Field, model_validator

from monitor_data.schemas.rpg_ontology.base import (
    AttributeSpec,
    BaseArmor,
    BaseCharacterSheet,
    BaseEquipmentItem,
    BaseGameSystem,
    BaseWeapon,
    GameSystemRegistry,
    ItemType,
    ResourceSpec,
)

# ---------------------------------------------------------------------------
# System-level enums
# ---------------------------------------------------------------------------

SYSTEM_ID = "death_in_space"


class DISDamageDie(StrEnum):
    """Legal damage dice in Death in Space."""

    D2 = "d2"  # improvised / unarmed
    D4 = "d4"
    D6 = "d6"
    D8 = "d8"
    D10 = "d10"
    D12 = "d12"


class DISArmorProtection(int, Enum):
    """Protection values for Death in Space armor."""

    NONE = 0  # unarmored (built-in baseline, not worn armor)
    LIGHT = 1  # light suit, padded jacket
    MEDIUM = 2  # security armor, combat suit
    HEAVY = 3  # environmental suit, military plate


class DISOrigin(StrEnum):
    """
    Character origins (backgrounds) from the Death in Space core rules.

    Origins grant starting skills, define the character's past, and sometimes
    provide a unique ability or starting item.
    """

    CONTRACTOR = "contractor"  # Corporate enforcer / debt collector
    CULTIST = "cultist"  # Void-worshipping true believer
    DRIFTER = "drifter"  # Homeless wanderer of the ring
    ENGINEER = "engineer"  # Station maintenance and repair
    GLADIATOR = "gladiator"  # Pit fighter from the Arena districts
    GEARHEAD = "gearhead"  # Ship mechanic / technician
    MINER = "miner"  # Ore extraction and hard labor
    MEDIC = "medic"  # Battlefield field surgeon
    PIRATE = "pirate"  # Void raider and opportunist
    RESEARCHER = "researcher"  # Scientist stranded in the ring
    SOLDIER = "soldier"  # Former military (any faction)
    TRADER = "trader"  # Merchant, fence, and scrounger


class DISSkill(StrEnum):
    """
    Skills from Death in Space (core rules).

    Skills give +2 to relevant attribute rolls.
    """

    SHARP = "Sharp"  # Perception and awareness
    SNEAKY = "Sneaky"  # Stealth and deception
    TOUGH = "Tough"  # Endurance and pain tolerance
    TINKER = "Tinker"  # Repair and jury-rig technology
    COMMAND = "Command"  # Leadership and persuasion
    MEDIC_SKILL = "Medic"  # First aid and surgery
    PILOT = "Pilot"  # Spacecraft and vehicle handling
    TRADE = "Trade"  # Commerce, haggling, and contacts
    MUSCLE = "Muscle"  # Brute strength applications
    SCAVENGE = "Scavenge"  # Finding useful junk in wreckage


class DISWeaponProperty(StrEnum):
    """Special weapon properties."""

    ENERGY = "energy"  # Bypasses some armor ratings
    EXPLOSIVE = "explosive"  # AOE damage
    HEAVY = "heavy"  # Requires BODY +1 or higher to use
    SILENT = "silent"  # No noise when fired / used
    SLOW = "slow"  # Requires action to reload per shot
    THROWN = "thrown"  # Can be used melee or thrown
    TWO_HANDED = "two_handed"  # Requires both hands


# ---------------------------------------------------------------------------
# Typed item schemas
# ---------------------------------------------------------------------------


class DISWeapon(BaseWeapon):
    """
    Death in Space weapon — typed damage die + energy/physical distinction.

    Examples from core rules (p.38-39):
      Plasma Cutter  d6  energy  short range
      Scrapper's Pistol  d6  ranged  30m
      Combat Knife   d4  melee
      Assault Rifle  d10  ranged  100m  slow
    """

    damage_formula: DISDamageDie = Field(description="Damage die (d2, d4, d6, d8, d10, d12)")
    properties: list[DISWeaponProperty] = Field(default_factory=list)
    range_m: int | None = Field(None, ge=0)
    is_ranged: bool = Field(default=False)

    @model_validator(mode="after")
    def ranged_needs_range(self) -> DISWeapon:
        if self.is_ranged and self.range_m is None:
            raise ValueError("Ranged weapons must specify range_m")
        return self


class DISArmor(BaseArmor):
    """
    Death in Space armor — protection 0-3 scale.

    Examples from core rules (p.40):
      Padded Jacket  protection=1  (Light)
      Security Armor protection=2  (Medium)
      Full Environ.  protection=3  (Heavy)
    """

    protection: DISArmorProtection = Field(
        description="Damage reduction value (0=none, 1=light, 2=medium, 3=heavy)",
    )
    blocks_cosmic_rot: bool = Field(
        default=False,
        description="Some environmental suits also block Cosmic Rot exposure",
    )


class DISEquipmentItem(BaseEquipmentItem):
    """Generic Death in Space equipment (not weapon or armor)."""

    uses: int | None = Field(
        None,
        ge=1,
        description="Number of uses before depleted (None = unlimited)",
    )
    requires_power: bool = Field(
        default=False,
        description="Requires a power cell or reactor to function",
    )


# ---------------------------------------------------------------------------
# Ship schema (space vessel — unique to Death in Space)
# ---------------------------------------------------------------------------


class DISShipClass(StrEnum):
    """Ship class tiers."""

    SHUTTLE = "shuttle"  # 2 crew max
    FREIGHTER = "freighter"  # 4-6 crew
    WARSHIP = "warship"  # 8-20 crew
    STATION = "station"  # Fixed — Ypsilon 14-style mega structures


class DISDriveType(StrEnum):
    """Omega Drive variants."""

    STANDARD = "standard"  # Basic FTL drive
    MILITARY = "military"  # Faster, more power draw
    EXPERIMENTAL = "experimental"  # Partially functional void drive
    BROKEN = "broken"  # Drifting on thrusters only


class DISShipModule(StrEnum):
    """Installable ship modules."""

    MEDICAL_BAY = "medical_bay"
    CARGO_BAY = "cargo_bay"
    WEAPONS_TURRET = "weapons_turret"
    SENSOR_ARRAY = "sensor_array"
    BOARDING_CLAMP = "boarding_clamp"
    SMUGGLING_HOLD = "smuggling_hold"
    ENGINEERING_LAB = "engineering_lab"
    PASSENGER_QUARTERS = "passenger_quarters"


class DISShipSheet(BaseEquipmentItem):
    """
    Death in Space ship sheet.

    Ships are not characters, but they are owned by parties and have their own
    stats.  They are stored in the equipment catalog under item_type=VEHICLE.
    """

    item_type: ItemType = Field(default=ItemType.VEHICLE)
    ship_class: DISShipClass
    hull_points: int = Field(ge=1, description="Current HP of the ship")
    max_hull_points: int = Field(ge=1)
    crew_capacity: int = Field(ge=1)
    drive_type: DISDriveType = Field(default=DISDriveType.STANDARD)
    drive_condition: int = Field(
        ge=0,
        le=6,
        default=6,
        description="Drive integrity 0-6 (6=fully functional, 0=destroyed)",
    )
    modules: list[DISShipModule] = Field(default_factory=list)
    cargo_units: int = Field(ge=0, default=0)
    credits_debt: int = Field(
        ge=0,
        default=0,
        description="Loan/debt owed on this ship",
    )

    @model_validator(mode="after")
    def hp_lte_max(self) -> DISShipSheet:
        if self.hull_points > self.max_hull_points:
            raise ValueError(f"hull_points ({self.hull_points}) cannot exceed max_hull_points ({self.max_hull_points})")
        return self


# ---------------------------------------------------------------------------
# Cosmic Powers (gained via Cosmic Rot)
# ---------------------------------------------------------------------------


class DISCosmicPower(StrEnum):
    """
    Cosmic powers unlocked by Cosmic Rot exposure (core rules p.22-23).

    Powers are gained at certain rot thresholds and become permanent mutations.
    They confer both an ability AND a physical mark of corruption.
    """

    VOID_SENSE = "Void Sense"
    DRIFT_STEP = "Drift Step"  # Teleport short distances
    RADIATION_SKIN = "Radiation Skin"  # Immune to some radiation
    PSYCHIC_SCREAM = "Psychic Scream"
    MASS_BENDING = "Mass Bending"  # Reduce own mass briefly
    ZERO_G_MASTER = "Zero-G Master"
    HIVE_MIND = "Hive Mind"  # Brief psychic link
    VOID_STEP = "Void Step"  # Pass through thin barriers
    ENTROPY_BURST = "Entropy Burst"  # Accelerate decay in objects
    FINAL_VOID = "Final Void"  # Rot=10: apocalyptic power


# ---------------------------------------------------------------------------
# Character sheet — the core typed schema
# ---------------------------------------------------------------------------


class DISCharacterSheet(BaseCharacterSheet):
    """
    Death in Space character sheet — fully typed and rule-validated.

    Replaces the old ``properties: Dict[str, Any]`` with proper fields.
    Every field has its legal range enforced by Pydantic validators.

    Attribute rules (core rules p.10-11):
      - All four attributes start at 0 and are modified during character creation
      - Valid range: -3 to +3
      - BODY affects HP (HP = max(1, BODY + 6))
      - DEX affects initiative and ranged attacks
      - SAVVY affects social skills and perception
      - TECH affects hacking, repair, and technical actions

    Character creation order:
      1. Choose origin → grants skill bonuses
      2. Write your drive
      3. Generate attributes (roll 2d6 on a -3 to +3 table, or point-buy)
      4. Calculate HP = max(1, BODY + 6)
      5. Choose starting gear (from origin pack)
      6. Name your character
    """

    system_id: ClassVar[str] = SYSTEM_ID

    # Core attributes (-3 to +3)
    body: int = Field(ge=-3, le=3, description="Physical power and durability")
    dex: int = Field(ge=-3, le=3, description="Agility and reflexes")
    savvy: int = Field(ge=-3, le=3, description="Intuition, wits, and persuasion")
    tech: int = Field(ge=-3, le=3, description="Technical skill and hacking")

    # Hit Points
    hp: int = Field(ge=0, description="Current Hit Points (0 = incapacitated)")
    max_hp: int = Field(ge=1, description="Maximum HP = max(1, BODY + 6)")

    # Cosmic Rot — 0-10 scale
    cosmic_rot: int = Field(
        ge=0,
        le=10,
        default=0,
        description=("Cosmic Rot accumulation (0=clean, 10=fully corrupted). Powers unlocked at 3, 6, and 9."),
    )
    cosmic_powers: list[DISCosmicPower] = Field(
        default_factory=list,
        description="Powers gained from Cosmic Rot exposure",
    )
    cosmic_marks: list[str] = Field(
        default_factory=list,
        description="Physical corruption marks (free text, e.g. 'glowing eyes')",
    )

    # Background and motivation
    origin: DISOrigin | None = Field(
        None,
        description="Character background/career before the campaign",
    )
    drive: str | None = Field(
        None,
        max_length=200,
        description="Personal motivation — why your character pushes forward",
    )

    # Skills
    skills: list[DISSkill] = Field(
        default_factory=list,
        description="Known skills; each grants +2 to relevant attribute rolls",
    )

    # Gear summary (names only — detailed items in EquipmentCatalog)
    gear_names: list[str] = Field(
        default_factory=list,
        description="Names of carried gear items (links to equipment_catalog)",
    )

    # Economy
    credits: int = Field(ge=0, default=0, description="Cash credits carried")
    debt: int = Field(ge=0, default=0, description="Total debt owed")

    # Conditions
    conditions: list[str] = Field(
        default_factory=list,
        description="Active conditions, e.g. ['Bleeding', 'Zero-G disoriented']",
    )

    # ---------------------------------------------------------------------------
    # Validators
    # ---------------------------------------------------------------------------

    @model_validator(mode="after")
    def validate_max_hp(self) -> DISCharacterSheet:
        """HP = max(1, BODY + 6) — enforced at creation, not on updates."""
        expected = max(1, self.body + 6)
        if self.max_hp != expected:
            raise ValueError(
                f"max_hp must be {expected} (= max(1, BODY + 6) where BODY={self.body}), got {self.max_hp}"
            )
        return self

    @model_validator(mode="after")
    def validate_hp_lte_max(self) -> DISCharacterSheet:
        if self.hp > self.max_hp:
            raise ValueError(f"hp ({self.hp}) cannot exceed max_hp ({self.max_hp})")
        return self

    @model_validator(mode="after")
    def validate_cosmic_powers_gated_by_rot(self) -> DISCharacterSheet:
        """
        Powers are unlocked at rot thresholds:
          rot 3+ → may have 1 power
          rot 6+ → may have 2 powers
          rot 9+ → may have 3 powers
        """
        max_powers = self.cosmic_rot // 3
        if len(self.cosmic_powers) > max_powers:
            raise ValueError(
                f"cosmic_rot={self.cosmic_rot} allows at most {max_powers} power(s), but got {len(self.cosmic_powers)}"
            )
        return self

    @model_validator(mode="after")
    def validate_no_duplicate_skills(self) -> DISCharacterSheet:
        if len(self.skills) != len(set(self.skills)):
            raise ValueError("skills list contains duplicates")
        return self

    # ---------------------------------------------------------------------------
    # Computed property helpers
    # ---------------------------------------------------------------------------

    @property
    def stat_total(self) -> int:
        """Sum of all four attributes (useful for balance checking)."""
        return self.body + self.dex + self.savvy + self.tech

    @property
    def is_incapacitated(self) -> bool:
        return self.hp <= 0

    @property
    def is_fully_corrupted(self) -> bool:
        return self.cosmic_rot >= 10

    def power_slots_available(self) -> int:
        """Number of additional power slots unlocked by current cosmic_rot."""
        return (self.cosmic_rot // 3) - len(self.cosmic_powers)


# ---------------------------------------------------------------------------
# System definition — registered with GameSystemRegistry at import
# ---------------------------------------------------------------------------

DEATH_IN_SPACE = BaseGameSystem(
    system_id=SYSTEM_ID,
    system_name="Death in Space",
    version="1.0",
    description=(
        "Gritty sci-fi RPG set in the Ypsilon 14 Ring — a decaying space station "
        "in a dying universe.  Characters are desperate drifters fighting for "
        "survival against corporate enforcers, void cults, and each other."
    ),
    publisher="MORK BORG Publishing",
    core_mechanic_formula="d20 + attribute ≥ 12 (or versus opposing roll)",
    attributes=[
        AttributeSpec(
            name="Body",
            abbreviation="BODY",
            min_value=-3,
            max_value=3,
            default_value=0,
            description="Physical power, endurance, and raw toughness",
        ),
        AttributeSpec(
            name="Dexterity",
            abbreviation="DEX",
            min_value=-3,
            max_value=3,
            default_value=0,
            description="Agility, reflexes, and hand-eye coordination",
        ),
        AttributeSpec(
            name="Savvy",
            abbreviation="SAVVY",
            min_value=-3,
            max_value=3,
            default_value=0,
            description="Street wisdom, intuition, and persuasive ability",
        ),
        AttributeSpec(
            name="Tech",
            abbreviation="TECH",
            min_value=-3,
            max_value=3,
            default_value=0,
            description="Technical expertise, hacking, and device operation",
        ),
    ],
    resources=[
        ResourceSpec(
            name="Hit Points",
            abbreviation="HP",
            min_value=0,
            max_formula="max(1, BODY + 6)",
            depleted_effect="Incapacitated — make a BODY roll or die",
            recovers_on="Medical bay treatment or rest with medic",
        ),
        ResourceSpec(
            name="Cosmic Rot",
            abbreviation="ROT",
            min_value=0,
            max_formula="10",  # hard cap
            depleted_effect="At 10: full corruption — character becomes an NPC void creature",
            recovers_on="Extremely rare — void purification ritual",
        ),
        ResourceSpec(
            name="Credits",
            abbreviation="CR",
            min_value=0,
            max_formula=None,  # unlimited
            depleted_effect="Broke — NPC faction debt pressure",
        ),
    ],
    schema_class=("monitor_data.schemas.rpg_ontology.systems.death_in_space.DISCharacterSheet"),
)

# Auto-register at import time
_registry = GameSystemRegistry()
_registry.register(DEATH_IN_SPACE, DISCharacterSheet)
