#!/usr/bin/env python3
import shutil
import re
from pathlib import Path

# Mapping of epic IDs to the standardized target folder names
TARGET_EPICS = {
    0: "epic-0-data-layer-DL",
    1: "epic-1-world-M",
    2: "epic-2-ingestion-I",
    3: "epic-3-identity-M",
    4: "epic-4-autonomous-gm-P",
    5: "epic-5-rules-RS",
    6: "epic-6-timeline-Q",
    7: "epic-7-copilot-CF",
    8: "epic-8-planning-ST",
    9: "epic-9-docs-DOC",
    10: "epic-10-packs-MP"
}
SYSTEM_EPIC = "epic-11-system-SYS"
USE_CASES_DIR = Path("docs/use-cases")

def get_epic_id(yml_content):
    match = re.search(r'^epic:\s*(\d+)', yml_content, re.MULTILINE)
    if match:
        return int(match.group(1))
    return None

def main():
    # 1. Create the target directories
    for folder in TARGET_EPICS.values():
        (USE_CASES_DIR / folder).mkdir(exist_ok=True, parents=True)
    (USE_CASES_DIR / SYSTEM_EPIC).mkdir(exist_ok=True, parents=True)

    # 2. Find all use case folders (which contain a .yml file)
    moved_count = 0
    yml_files = list(USE_CASES_DIR.rglob("*.yml"))
    for yml_file in yml_files:
        if yml_file.name.startswith("_"):
            continue
            
        uc_dir = yml_file.parent
        # Skip if it's somehow directly in docs/use-cases or already deleted
        if uc_dir == USE_CASES_DIR or not uc_dir.exists():
            continue
            
        epic_id = get_epic_id(yml_file.read_text())
        if epic_id is not None and epic_id in TARGET_EPICS:
            target_folder = TARGET_EPICS[epic_id]
        else:
            target_folder = SYSTEM_EPIC
            
        target_path = USE_CASES_DIR / target_folder / uc_dir.name
        
        # If the folder is already in the right place, skip
        if uc_dir.parent.name == target_folder:
            continue
            
        # Move it
        if target_path.exists():
            print(f"Warning: {target_path} already exists, skipping move for {uc_dir}")
            continue
            
        shutil.move(str(uc_dir), str(target_path))
        moved_count += 1
        
    print(f"Moved {moved_count} use cases to standardized directories.")
    
    # 3. Clean up empty epic-* directories
    for path in USE_CASES_DIR.iterdir():
        if path.is_dir() and path.name.startswith("epic-") and path.name not in TARGET_EPICS.values() and path.name != SYSTEM_EPIC:
            # Check if empty (ignoring .md files like epic-1-play.md for now, we will just delete the md files too)
            # Actually, the python script earlier left epic-*.md files.
            # Let's just delete the directory if it contains no subdirectories.
            has_subdirs = any(x.is_dir() for x in path.iterdir())
            if not has_subdirs:
                shutil.rmtree(path)
                print(f"Deleted old splintered directory: {path.name}")
                # Also delete the associated .md if it exists (e.g. epic-1-play.md)
                md_file = USE_CASES_DIR / f"{path.name}.md"
                if md_file.exists():
                    md_file.unlink()

if __name__ == "__main__":
    main()
