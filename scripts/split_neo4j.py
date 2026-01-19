import os

SOURCE = "packages/data-layer/src/monitor_data/tools/neo4j_tools_legacy.py"
DEST_DIR = "packages/data-layer/src/monitor_data/tools/neo4j_tools"

def extract_section(start_line, end_line, dest_file):
    with open(SOURCE, "r") as f:
        lines = f.readlines()
    
    # Get imports from top (approx 1-100)
    imports = []
    for line in lines[:100]:
        if line.startswith("import") or line.startswith("from"):
            imports.append(line)
            
    content = lines[start_line-1:end_line]
    
    # Add json import if missing (critical for fixes)
    if "import json\n" not in imports:
        imports.insert(0, "import json\n")
        
    with open(f"{DEST_DIR}/{dest_file}", "w") as f:
        f.write('"""\nAuto-extracted module.\n"""\n\n')
        f.writelines(imports)
        f.write("\n\n")
        f.writelines(content)
    print(f"Created {dest_file}")

if __name__ == "__main__":
    # Facts: 1139 - 2022
    extract_section(1139, 2022, "facts.py")
    
    # Stories: 2023 - 2898
    extract_section(2023, 2898, "stories.py")
    
    # Parties: 2899 - 3562
    extract_section(2899, 3562, "parties.py")
    
    # Relationships: 3563 - End
    # Read file len
    with open(SOURCE, "r") as f:
        total_lines = len(f.readlines())
    extract_section(3563, total_lines, "relationships.py")
