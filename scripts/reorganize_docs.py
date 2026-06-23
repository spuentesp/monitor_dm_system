#!/usr/bin/env python3
import os
import shutil
import re
from pathlib import Path

DOCS_DIR = Path("docs")
USE_CASES_DIR = DOCS_DIR / "use-cases"
BEHAVIORS_DIR = USE_CASES_DIR / "behaviors"
CONTRACTS_DIR = USE_CASES_DIR / "contracts"

def get_yml_info(yml_path: Path):
    content = yml_path.read_text()
    id_match = re.search(r'^id:\s*"?([A-Z0-9-]+)"?', content, re.MULTILINE)
    epic_match = re.search(r'^epic:\s*"?([0-9]+)"?', content, re.MULTILINE)
    category_match = re.search(r'^category:\s*"?([a-zA-Z-]+)"?', content, re.MULTILINE)
    
    uc_id = id_match.group(1) if id_match else yml_path.stem
    epic = epic_match.group(1) if epic_match else "unknown"
    category = category_match.group(1) if category_match else "misc"
    
    return uc_id, epic, category

def main():
    moved_count = 0
    yml_files = list(USE_CASES_DIR.rglob("*.yml"))
    
    for yml_path in yml_files:
        if yml_path.name == "_schema.yml":
            continue
            
        uc_id, epic, category = get_yml_info(yml_path)
        
        # Target directory: docs/use-cases/epic-{epic}-{category}/{uc_id}/
        target_dir = USE_CASES_DIR / f"epic-{epic}-{category}" / uc_id
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Move YAML
        target_yml = target_dir / f"{uc_id}.yml"
        if yml_path != target_yml:
            print(f"Moving {yml_path} -> {target_yml}")
            shutil.move(yml_path, target_yml)
            moved_count += 1
            
        # 2. Move Behavior
        behavior_file = BEHAVIORS_DIR / f"{uc_id}-behaviors.md"
        if behavior_file.exists():
            target_behavior = target_dir / f"{uc_id}-behavior.md"
            print(f"Moving {behavior_file} -> {target_behavior}")
            shutil.move(behavior_file, target_behavior)
            moved_count += 1
            
        # 3. Move Contract
        contract_file = CONTRACTS_DIR / f"{uc_id}-contracts.md"
        if contract_file.exists():
            target_contract = target_dir / f"{uc_id}-contract.md"
            print(f"Moving {contract_file} -> {target_contract}")
            shutil.move(contract_file, target_contract)
            moved_count += 1

    print(f"\nMigration complete. Moved {moved_count} files.")

if __name__ == "__main__":
    main()
