#!/usr/bin/env python3
"""
Seed the extensible Tone System into MongoDB.

This script is a thin wrapper around `ensure_tone_builtins()` from the
monitor_data initialization module. It is kept for backward compatibility
and for manual/deployment use, but all actual seeding logic now lives in
`monitor_data.initialization.ensure_tone_builtins`.

On every call, this script will:
- Ensure the 6 built-in ToneProfiles exist in MongoDB
- Ensure the default ToneLibrary exists
- Ensure the 6 built-in TagDefinitions exist

Safe to run multiple times (idempotent).

Usage:
    python scripts/seed_tone_system.py

Or import and call directly:
    from monitor_data.initialization.ensure_tone_builtins import ensure_tone_builtins
    ensure_tone_builtins()
"""
# ruff: noqa: E402

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "packages" / "data-layer" / "src"))

from monitor_data.initialization.ensure_tone_builtins import ensure_tone_builtins


if __name__ == "__main__":
    print("Seeding Tone System (via ensure_tone_builtins)...")
    ensure_tone_builtins()
    print("\nDone.")
