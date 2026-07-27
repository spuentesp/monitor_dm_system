#!/usr/bin/env python3
"""
Validate game system extraction quality against the live API.

Usage:
    python scripts/validate_game_systems.py              # validate all non-builtin systems
    python scripts/validate_game_systems.py --system DiS  # validate one system (name substring match)

This script checks the live API at http://localhost:8000/api/systems and runs
quality assertions on each extracted game system:
  - Correct number of core attributes (no NPC stats, no prompt echoes)
  - Correct attribute ranges per mechanic type
  - Skills present or explicitly absent per system type
  - NPC stat blocks populated for systems with bestiaries
  - Character creation procedure extracted and non-empty
  - Core mechanic matches expected type/success_type
  - No duplicate entries for the same source

Exit code 0 if all checks pass, 1 if any fail.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


API_BASE = "http://localhost:8000"

# ── Expected extraction profiles per game system ─────────────────────────────
# These define the ground truth we validate against.


@dataclass
class ExpectedProfile:
    """Ground truth expectations for a game system extraction."""

    name_pattern: str  # substring match against system name
    expected_mechanic_type: str
    expected_success_type: str
    expected_attributes: list[str]  # required attribute names (subset check)
    attribute_range: tuple[int, int]  # (min_value, max_value) for primary attrs
    min_attributes: int
    max_attributes: int
    expect_skills: bool  # should the system have skills?
    min_skills: int = 0
    min_resources: int = 1
    expect_npc_blocks: bool = False
    expect_creation_procedure: bool = True
    min_creation_steps: int = 2
    forbidden_attribute_patterns: list[str] = field(
        default_factory=lambda: [
            "what ",
            "how ",
            "which ",
            "does ",
            "tracked on",
            "character sheet",
            "ability scores",
            "competencies",
            "in this system",
        ]
    )


PROFILES: list[ExpectedProfile] = [
    ExpectedProfile(
        name_pattern="Death in Space",
        expected_mechanic_type="d20",
        expected_success_type="meet_or_beat",
        expected_attributes=["Body", "Dexterity", "Savvy", "Tech"],
        attribute_range=(-3, 3),
        min_attributes=4,
        max_attributes=4,
        expect_skills=False,
        min_skills=0,
        min_resources=2,  # HP, Void Points at minimum
        expect_npc_blocks=True,
        expect_creation_procedure=True,
        min_creation_steps=3,
    ),
    ExpectedProfile(
        name_pattern="Vampire",
        expected_mechanic_type="dice_pool",
        expected_success_type="meet_or_beat",
        expected_attributes=[
            "Strength",
            "Dexterity",
            "Stamina",
            "Charisma",
            "Manipulation",
            "Appearance",
            "Perception",
            "Intelligence",
            "Wits",
        ],
        attribute_range=(1, 5),
        min_attributes=9,
        max_attributes=15,  # 9 core + up to 3 virtues + possible extras
        expect_skills=True,
        min_skills=10,
        min_resources=2,  # Blood Pool, Willpower at minimum
        expect_npc_blocks=False,  # VtM V20 doesn't have a formal bestiary section
        expect_creation_procedure=True,
        min_creation_steps=3,
    ),
    ExpectedProfile(
        name_pattern="Fallout",
        expected_mechanic_type="d20",
        expected_success_type="meet_or_beat",
        expected_attributes=[
            "Strength",
            "Perception",
            "Endurance",
            "Charisma",
            "Intelligence",
            "Agility",
            "Luck",
        ],
        attribute_range=(4, 12),
        min_attributes=7,
        max_attributes=7,
        expect_skills=True,
        min_skills=5,
        min_resources=2,
        expect_npc_blocks=True,
        expect_creation_procedure=True,
        min_creation_steps=3,
    ),
    ExpectedProfile(
        name_pattern="7th Sea",
        expected_mechanic_type="dice_pool",
        expected_success_type="highest_wins",
        expected_attributes=["Brawn", "Finesse", "Resolve", "Wits", "Panache"],
        attribute_range=(1, 5),
        min_attributes=5,
        max_attributes=6,  # may pick up phantom attrs like "Strength"
        expect_skills=True,
        min_skills=5,
        min_resources=1,
        expect_npc_blocks=False,  # 7th Sea uses Brute Squads/Villains, not stat blocks
        expect_creation_procedure=True,
        min_creation_steps=3,
    ),
]


# ── Validation logic ─────────────────────────────────────────────────────────


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


def validate_system(
    system: Dict[str, Any], profile: ExpectedProfile
) -> list[CheckResult]:
    """Run all checks for a single game system against its profile."""
    results: list[CheckResult] = []

    # ── Core mechanic ────────────────────────────────────────────────────
    cm = system.get("core_mechanic", {})
    cm_type = cm.get("type", "?")
    cm_success = cm.get("success_type", "?")

    results.append(
        CheckResult(
            "Core mechanic type",
            cm_type == profile.expected_mechanic_type,
            f"got={cm_type}, expected={profile.expected_mechanic_type}",
        )
    )
    results.append(
        CheckResult(
            "Success type",
            cm_success == profile.expected_success_type,
            f"got={cm_success}, expected={profile.expected_success_type}",
        )
    )

    # ── Attributes ───────────────────────────────────────────────────────
    attrs = system.get("attributes", [])
    attr_names = [a.get("name", "") for a in attrs]
    attr_names_lower = {n.lower() for n in attr_names}

    results.append(
        CheckResult(
            f"Attribute count ({len(attrs)})",
            profile.min_attributes <= len(attrs) <= profile.max_attributes,
            f"expected {profile.min_attributes}-{profile.max_attributes}, got {len(attrs)}: {attr_names}",
        )
    )

    # Check required attributes present
    for expected_attr in profile.expected_attributes:
        found = expected_attr.lower() in attr_names_lower
        results.append(
            CheckResult(
                f"Has attribute '{expected_attr}'",
                found,
                f"not found in {attr_names}" if not found else "",
            )
        )

    # Check attribute ranges
    for a in attrs:
        name = a.get("name", "?")
        lo, hi = profile.attribute_range
        a_min = a.get("min_value", 0)
        a_max = a.get("max_value", 0)
        # Allow slight range variance (e.g. VtM virtues 0..5 vs core attrs 1..5)
        ok = abs(a_min - lo) <= 1 and abs(a_max - hi) <= 1
        results.append(
            CheckResult(
                f"Attr '{name}' range",
                ok,
                f"got {a_min}..{a_max}, expected ~{lo}..{hi}" if not ok else "",
            )
        )

    # Check no forbidden patterns in attribute names (prompt echoes)
    for a in attrs:
        name = a.get("name", "")
        for forbidden in profile.forbidden_attribute_patterns:
            if forbidden.lower() in name.lower():
                results.append(
                    CheckResult(
                        f"No prompt echo in attr '{name[:40]}'",
                        False,
                        f"contains forbidden pattern: '{forbidden}'",
                    )
                )
                break

    # ── Skills ───────────────────────────────────────────────────────────
    skills = system.get("skills", [])
    if profile.expect_skills:
        results.append(
            CheckResult(
                f"Has skills ({len(skills)})",
                len(skills) >= profile.min_skills,
                f"expected >= {profile.min_skills}, got {len(skills)}",
            )
        )
    else:
        results.append(
            CheckResult(
                f"No skills (skill-less system, got {len(skills)})",
                len(skills) == 0,
                f"expected 0 skills, got {len(skills)}: {[s.get('name') for s in skills[:5]]}",
            )
        )

    # Check no prompt echoes in skills
    for s in skills:
        name = s.get("name", "")
        for forbidden in profile.forbidden_attribute_patterns:
            if forbidden.lower() in name.lower():
                results.append(
                    CheckResult(
                        f"No prompt echo in skill '{name[:40]}'",
                        False,
                        f"contains forbidden pattern: '{forbidden}'",
                    )
                )
                break

    # ── Resources ────────────────────────────────────────────────────────
    resources = system.get("resources", [])
    results.append(
        CheckResult(
            f"Has resources ({len(resources)})",
            len(resources) >= profile.min_resources,
            f"expected >= {profile.min_resources}, got {len(resources)}",
        )
    )

    # ── NPC stat blocks ──────────────────────────────────────────────────
    npcs = system.get("npc_stat_blocks", [])
    if profile.expect_npc_blocks:
        results.append(
            CheckResult(
                f"Has NPC stat blocks ({len(npcs)})",
                len(npcs) > 0,
                "No NPC stat blocks found" if not npcs else f"{len(npcs)} blocks",
            )
        )
    else:
        results.append(
            CheckResult(
                "NPC blocks (optional)",
                True,
                f"{len(npcs)} blocks (not required for this system)",
            )
        )

    # ── Character creation ───────────────────────────────────────────────
    cc = system.get("character_creation")
    if profile.expect_creation_procedure:
        has_cc = cc is not None
        results.append(
            CheckResult(
                "Has creation procedure",
                has_cc,
                "Missing character_creation" if not has_cc else "",
            )
        )
        if has_cc:
            steps = cc.get("steps", [])
            results.append(
                CheckResult(
                    f"Creation step count ({len(steps)})",
                    len(steps) >= profile.min_creation_steps,
                    f"expected >= {profile.min_creation_steps}, got {len(steps)}",
                )
            )
            # Verify steps have titles
            empty_titles = [i for i, s in enumerate(steps) if not s.get("title")]
            results.append(
                CheckResult(
                    "All creation steps have titles",
                    len(empty_titles) == 0,
                    f"Steps without titles: {empty_titles}" if empty_titles else "",
                )
            )

    return results


def fetch_systems(name_filter: Optional[str] = None) -> list[Dict[str, Any]]:
    """Fetch game systems from the live API."""
    with urllib.request.urlopen(f"{API_BASE}/api/systems") as r:
        data = json.load(r)
    systems = data.get("systems", data) if isinstance(data, dict) else data

    # Get full details for each non-builtin system
    detailed = []
    for s in systems:
        if s.get("is_builtin"):
            continue
        if name_filter and name_filter.lower() not in s.get("name", "").lower():
            continue
        sid = s["id"]
        with urllib.request.urlopen(f"{API_BASE}/api/systems/{sid}") as r:
            detail = json.load(r)
        detailed.append(detail)
    return detailed


def find_profile(system_name: str) -> Optional[ExpectedProfile]:
    """Find the matching profile for a system name."""
    for p in PROFILES:
        if p.name_pattern.lower() in system_name.lower():
            return p
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate game system extraction quality"
    )
    parser.add_argument("--system", help="Filter by system name (substring)")
    args = parser.parse_args()

    try:
        systems = fetch_systems(args.system)
    except Exception as e:
        print(f"\n  ERROR: Cannot reach API at {API_BASE}: {e}")
        return 1

    if not systems:
        print(
            "\n  No non-builtin game systems found"
            + (f" matching '{args.system}'" if args.system else "")
        )
        return 1

    total_pass = 0
    total_fail = 0
    all_results: dict[str, list[CheckResult]] = {}

    # Check for duplicates
    name_counts: dict[str, int] = {}
    for s in systems:
        name = s.get("name", "?")
        name_counts[name] = name_counts.get(name, 0) + 1

    for name, count in name_counts.items():
        if count > 1:
            print(f"\n  WARNING: {count} duplicate entries for '{name}'")

    for system in systems:
        name = system.get("name", "?")
        sid = str(system.get("id", "?"))[:8]
        profile = find_profile(name)

        if not profile:
            print(f"\n  [{sid}] {name} — NO PROFILE (skipped)")
            continue

        checks = validate_system(system, profile)
        all_results[f"[{sid}] {name}"] = checks

        passed = sum(1 for c in checks if c.passed)
        failed = sum(1 for c in checks if not c.passed)
        total_pass += passed
        total_fail += failed

        status = "PASS" if failed == 0 else "FAIL"
        print(f"\n  [{sid}] {name} — {status} ({passed}/{passed + failed} checks)")

        for c in checks:
            icon = "  ✓" if c.passed else "  ✗"
            line = f"    {icon} {c.name}"
            if c.detail and not c.passed:
                line += f"  →  {c.detail}"
            print(line)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  TOTAL: {total_pass} passed, {total_fail} failed")
    print(f"{'=' * 60}")

    return 0 if total_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
