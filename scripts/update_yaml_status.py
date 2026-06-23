#!/usr/bin/env python3
"""
Update YAML status fields based on verified implementation status.

Usage: python scripts/update_yaml_status.py [--dry-run]
"""

import re
import sys
from pathlib import Path

# Status mapping based on ACCURATE_IMPLEMENTATION_STATUS.md
# Format: "use_case_id": "status"
IMPLEMENTATION_STATUS = {
    # === DATA LAYER (DL) - ~85% complete ===
    "DL-1": "done",
    "DL-2": "done",
    "DL-3": "done",
    "DL-4": "done",
    "DL-5": "done",
    "DL-6": "done",
    "DL-7": "done",
    "DL-8": "done",
    "DL-9": "done",
    "DL-10": "done",
    "DL-11": "done",
    "DL-12": "done",
    "DL-13": "done",
    "DL-14": "done",
    "DL-15": "in-progress",  # Party management working
    "DL-16": "in-progress",  # Inventory & splits
    "DL-17": "todo",         # Entity templates - NOT FOUND
    "DL-18": "in-progress",  # Change log (partial)
    "DL-19": "in-progress",  # Historical queries (partial)
    "DL-20": "done",         # Game systems
    "DL-21": "todo",         # Random tables - schema exists, tools missing
    "DL-22": "in-progress",  # Card decks (partial)
    "DL-23": "todo",         # Snapshots - data layer ready, UI missing
    "DL-24": "done",         # Turn resolutions (dice)
    "DL-25": "in-progress",  # Combat state (partial)
    "DL-26": "in-progress",  # Character working state (partial),

    # === PLAY (P) - Core ~95%, Extended ~70% ===
    "P-1": "done",
    "P-2": "done",
    "P-3": "done",
    "P-4": "done",
    "P-5": "done",
    "P-6": "in-progress",    # End story - flow exists, not polished
    "P-7": "in-progress",    # Canonize facts - scene-level works
    "P-8": "done",
    "P-9": "done",
    "P-10": "done",          # Combat mode
    "P-11": "done",          # Conversation mode
    "P-12": "in-progress",   # Switch scene - exists, edge cases
    "P-13": "done",
    "P-14": "todo",          # Flashback - NOT FOUND
    "P-15": "todo",          # Autonomous PC - NOT FOUND
    "P-16": "in-progress",   # Combat encounter - loop exists
    "P-17": "in-progress",   # Social encounter - loop exists
    "P-18": "done",
    "P-19": "in-progress",   # Procedural scene population
    "P-20": "in-progress",   # Forced narrative pushback
    "P-21": "in-progress",   # Progression/leveling

    # === MANAGEMENT (M) - ~60% ===
    "M-1": "done",
    "M-2": "done",
    "M-3": "done",
    "M-4": "done",
    "M-5": "done",
    "M-6": "in-progress",    # Entity management works, bulk ops missing
    "M-7": "in-progress",
    "M-8": "in-progress",
    "M-9": "in-progress",
    "M-10": "done",
    "M-11": "in-progress",
    "M-12": "done",
    "M-13": "done",
    "M-14": "in-progress",
    "M-15": "done",
    "M-16": "in-progress",
    "M-17": "in-progress",
    "M-18": "in-progress",
    "M-19": "in-progress",
    "M-20": "in-progress",
    "M-21": "in-progress",
    "M-22": "in-progress",
    "M-23": "in-progress",
    "M-24": "in-progress",
    "M-25": "in-progress",
    "M-26": "in-progress",
    "M-27": "in-progress",
    "M-28": "in-progress",
    "M-29": "in-progress",
    "M-30": "in-progress",
    "M-31": "todo",          # Entity templates - NOT FOUND (note: different from epic-3 which is actor mode)
    "M-32": "in-progress",   # Archetypes - basic CRUD only
    "M-33": "todo",          # Random tables - NOT FOUND
    "M-34": "todo",          # Snapshots - data layer ready, UI missing
    "M-35": "todo",          # Fork - NOT FOUND

    # === QUERY (Q) - ~50% ===
    "Q-1": "in-progress",     # Basic works, advanced filters incomplete
    "Q-2": "in-progress",
    "Q-3": "in-progress",
    "Q-4": "in-progress",
    "Q-5": "in-progress",
    "Q-6": "in-progress",
    "Q-7": "in-progress",
    "Q-8": "in-progress",
    "Q-9": "in-progress",
    "Q-10": "todo",          # Audit trail - partial
    "Q-11": "todo",          # Graph explorer - NOT FOUND

    # === INGESTION (I) - ~75% ===
    "I-1": "done",
    "I-2": "done",
    "I-3": "done",
    "I-4": "done",
    "I-5": "done",
    "I-6": "done",
    "I-7": "done",
    "I-8": "done",
    "I-9": "done",
    "I-10": "done",
    "I-11": "done",
    "I-12": "done",
    "I-13": "in-progress",
    "I-14": "in-progress",
    "I-15": "in-progress",
    "I-16": "in-progress",

    # === SYSTEM (SYS) - ~70% ===
    "SYS-1": "done",
    "SYS-2": "done",
    "SYS-3": "done",
    "SYS-4": "done",
    "SYS-5": "in-progress",
    "SYS-6": "in-progress",
    "SYS-7": "in-progress",
    "SYS-8": "in-progress",
    "SYS-9": "in-progress",
    "SYS-10": "in-progress",
    "SYS-11": "todo",        # Error recovery - basic only
    "SYS-12": "todo",        # Observability - basic only

    # === CO-PILOT (CF) - ~40% ===
    "CF-1": "in-progress",    # Session recording works
    "CF-2": "in-progress",
    "CF-3": "in-progress",
    "CF-4": "todo",          # Plot hooks - NOT FOUND
    "CF-5": "in-progress",    # Contradiction detection - partial
    "CF-6": "todo",          # Player handouts - NOT FOUND
    "CF-7": "todo",          # Session prep - NOT FOUND
    "CF-8": "todo",          # Procedural generation - NOT FOUND

    # === STORY (ST) - ~30% ===
    "ST-1": "in-progress",   # Basic loop exists
    "ST-2": "in-progress",
    "ST-3": "in-progress",
    "ST-4": "in-progress",
    "ST-5": "in-progress",
    "ST-6": "in-progress",    # Random encounters - connected
    "ST-7": "in-progress",   # Scheduled events - partial
    "ST-8": "todo",          # Auto planning - NOT FOUND

    # === RULES (RS) - ~60% ===
    "RS-1": "in-progress",
    "RS-2": "in-progress",
    "RS-3": "in-progress",
    "RS-4": "in-progress",
    "RS-5": "in-progress",    # Card mechanics - partial
    "RS-6": "in-progress",
    "RS-7": "in-progress",
    "RS-8": "in-progress",

    # === PACKS (MP) - ~50% ===
    "MP-1": "in-progress",
    "MP-2": "in-progress",
    "MP-3": "in-progress",
    "MP-4": "in-progress",
    "MP-5": "in-progress",
    "MP-6": "in-progress",
    "MP-7": "in-progress",
    "MP-8": "in-progress",
    "MP-9": "in-progress",

    # === DOCS ===
    "DOC-1": "in-progress",
}


def update_yaml_file(filepath: Path, new_status: str) -> bool:
    """Update status field in a YAML file."""
    try:
        content = filepath.read_text()
        
        # Pattern to match the status line in YAML
        # Matches: status: "todo" or status: "done" etc.
        pattern = r'(^status:\s*)"[^"]*"(\s*)$'
        
        if re.search(pattern, content, re.MULTILINE):
            new_content = re.sub(
                pattern,
                rf'\g<1>"{new_status}"\g<2>',
                content,
                flags=re.MULTILINE
            )
            filepath.write_text(new_content)
            return True
        return False
    except Exception as e:
        print(f"Error updating {filepath}: {e}")
        return False


def main():
    dry_run = "--dry-run" in sys.argv
    
    docs_path = Path("docs/use-cases")
    updated = 0
    skipped = 0
    errors = 0
    
    # Find all YAML files
    for yaml_file in docs_path.rglob("*.yml"):
        # Extract ID from filename (e.g., "P-1.yml" -> "P-1")
        filename = yaml_file.stem
        
        if filename in IMPLEMENTATION_STATUS:
            new_status = IMPLEMENTATION_STATUS[filename]
            
            if dry_run:
                print(f"[DRY RUN] Would update {yaml_file}: {filename} -> {new_status}")
            else:
                if update_yaml_file(yaml_file, new_status):
                    print(f"Updated {yaml_file}: {filename} -> {new_status}")
                    updated += 1
                else:
                    print(f"Skipped {yaml_file}: no status field found")
                    skipped += 1
        else:
            # Check if file has a use case ID in the content
            try:
                content = yaml_file.read_text()
                id_match = re.search(r'^id:\s*"([A-Z]+-\d+)"', content, re.MULTILINE)
                if id_match:
                    uc_id = id_match.group(1)
                    if uc_id in IMPLEMENTATION_STATUS:
                        new_status = IMPLEMENTATION_STATUS[uc_id]
                        if dry_run:
                            print(f"[DRY RUN] Would update {yaml_file}: {uc_id} -> {new_status}")
                        else:
                            if update_yaml_file(yaml_file, new_status):
                                print(f"Updated {yaml_file}: {uc_id} -> {new_status}")
                                updated += 1
                            else:
                                skipped += 1
            except Exception as e:
                print(f"Error reading {yaml_file}: {e}")
                errors += 1
    
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Summary:")
    print(f"  Updated: {updated}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors:  {errors}")


if __name__ == "__main__":
    main()