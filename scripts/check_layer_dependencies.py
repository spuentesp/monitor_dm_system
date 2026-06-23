#!/usr/bin/env python3
"""
Guardrail: enforce MONITOR's layer boundaries to prevent agent pollution.

Rules:
  - Layer 3 (packages/cli) MUST NOT import monitor_data (Layer 1) directly.
  - Layer 2 (packages/agents) MUST NOT import monitor_cli (Layer 3).
  - Layer 1 (packages/data-layer) MUST NOT import monitor_agents or monitor_cli.

The script searches for forbidden import strings and exits non-zero on violation.

Usage:
    python3 scripts/check_layer_dependencies.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Rule:
    name: str
    base: Path
    forbidden: tuple[str, ...]


RULES: tuple[Rule, ...] = (
    Rule(
        name="cli-cannot-import-data-layer",
        base=ROOT / "packages" / "cli",
        forbidden=("monitor_data",),
    ),
    Rule(
        name="agents-cannot-import-cli",
        base=ROOT / "packages" / "agents",
        forbidden=("monitor_cli",),
    ),
    Rule(
        name="data-layer-cannot-import-agents-or-cli",
        base=ROOT / "packages" / "data-layer",
        forbidden=("monitor_agents", "monitor_cli"),
    ),
)


def find_violations(rule: Rule) -> list[Path]:
    """Return files under rule.base that contain forbidden import statements."""
    hits: list[Path] = []
    for path in rule.base.rglob("*.py"):
        try:
            lines = path.read_text().splitlines()
        except (UnicodeDecodeError, OSError):
            continue

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for fob in rule.forbidden:
                if stripped.startswith(f"import {fob}") or stripped.startswith(
                    f"from {fob} "
                ):
                    hits.append(path)
                    break
            else:
                continue
            break
    return hits


def main() -> int:
    failed = False
    for rule in RULES:
        violations = find_violations(rule)
        if not violations:
            continue
        failed = True
        print(f"[FAIL] {rule.name}")
        for path in violations:
            rel = path.relative_to(ROOT)
            print(f"  - {rel}")

    if failed:
        print("\nGuardrail failed: fix forbidden imports before proceeding.")
        return 1

    print("All layer dependency checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
