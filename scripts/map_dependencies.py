#!/usr/bin/env python3
"""
Map and visualize use case dependencies.

Reads YAML files from docs/use-cases/ and generates dependency graphs
in various formats (ASCII, Mermaid, DOT).

Usage:
    python scripts/map_dependencies.py
    python scripts/map_dependencies.py --format mermaid
    python scripts/map_dependencies.py --format dot
    python scripts/map_dependencies.py --category data-layer
    python scripts/map_dependencies.py --output deps.md
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
USE_CASES_DIR = ROOT / "docs" / "use-cases"


def get_all_issues() -> dict[str, dict[str, Any]]:
    """Get all issues from GitHub, keyed by use case ID."""
    result = subprocess.run(
        ["gh", "issue", "list", "--state", "all", "--limit", "500", "--json",
         "number,title,state"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return {}

    issues = {}
    try:
        data = json.loads(result.stdout)
        for issue in data:
            title = issue.get("title", "")
            if ":" in title:
                use_case_id = title.split(":")[0].strip()
                issues[use_case_id] = {
                    "number": issue.get("number"),
                    "state": issue.get("state"),
                }
    except json.JSONDecodeError:
        pass

    return issues


def load_all_use_cases() -> dict[str, dict[str, Any]]:
    """Load all use case YAML files."""
    use_cases = {}

    for category_dir in USE_CASES_DIR.iterdir():
        if not category_dir.is_dir():
            continue

        for yml_file in category_dir.glob("*.yml"):
            if yml_file.name.startswith("_"):
                continue

            try:
                with open(yml_file) as f:
                    data = yaml.safe_load(f)

                if data and "id" in data:
                    use_cases[data["id"]] = {
                        "id": data["id"],
                        "title": data.get("title", ""),
                        "category": data.get("category", ""),
                        "priority": data.get("priority", "medium"),
                        "depends_on": data.get("depends_on", []),
                        "blocks": data.get("blocks", []),
                    }
            except (yaml.YAMLError, OSError):
                pass

    return use_cases


def build_graph(
    use_cases: dict[str, dict[str, Any]],
    category: str | None = None,
) -> tuple[set[str], list[tuple[str, str]]]:
    """Build dependency graph as nodes and edges."""
    nodes = set()
    edges = []  # (from, to) where from depends on to

    for uc_id, uc in use_cases.items():
        if category and uc.get("category") != category:
            continue

        nodes.add(uc_id)

        for dep in uc.get("depends_on", []):
            nodes.add(dep)
            edges.append((uc_id, dep))

    return nodes, edges


def topological_sort(
    nodes: set[str],
    edges: list[tuple[str, str]],
) -> list[str]:
    """Topological sort of nodes based on dependency edges."""
    # Build adjacency list and in-degree count
    adj = defaultdict(list)
    in_degree = defaultdict(int)

    for node in nodes:
        in_degree[node] = 0

    for from_node, to_node in edges:
        adj[to_node].append(from_node)
        in_degree[from_node] += 1

    # Kahn's algorithm
    queue = [n for n in nodes if in_degree[n] == 0]
    result = []

    while queue:
        queue.sort()  # Alphabetical for determinism
        node = queue.pop(0)
        result.append(node)

        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return result


def generate_ascii(
    use_cases: dict[str, dict[str, Any]],
    nodes: set[str],
    edges: list[tuple[str, str]],
    issues: dict[str, dict[str, Any]],
) -> str:
    """Generate ASCII representation of dependency graph."""
    lines = []
    lines.append("=" * 70)
    lines.append("DEPENDENCY GRAPH")
    lines.append("=" * 70)
    lines.append("")

    # Group by category
    by_category = defaultdict(list)
    for node in sorted(nodes):
        uc = use_cases.get(node, {})
        cat = uc.get("category", "other")
        by_category[cat].append(node)

    # Build reverse lookup
    depends_on = defaultdict(list)
    blocks = defaultdict(list)
    for from_node, to_node in edges:
        depends_on[from_node].append(to_node)
        blocks[to_node].append(from_node)

    for category in sorted(by_category.keys()):
        lines.append(f"\n[{category.upper()}]")
        lines.append("-" * 40)

        for node in sorted(by_category[category]):
            uc = use_cases.get(node, {})
            issue = issues.get(node, {})
            state = issue.get("state", "?")
            state_icon = "✅" if state == "CLOSED" else "⬜" if state == "OPEN" else "?"

            title = uc.get("title", "")[:35]
            issue_num = f"#{issue.get('number')}" if issue.get("number") else ""

            lines.append(f"  {state_icon} {node}: {title} {issue_num}")

            deps = depends_on.get(node, [])
            if deps:
                dep_status = []
                for d in deps:
                    d_state = issues.get(d, {}).get("state", "?")
                    icon = "✓" if d_state == "CLOSED" else "✗"
                    dep_status.append(f"{icon}{d}")
                lines.append(f"      └─ needs: {', '.join(dep_status)}")

    lines.append("")
    lines.append("=" * 70)
    lines.append("Legend: ✅ = Completed, ⬜ = Open, ✓ = Dep satisfied, ✗ = Dep pending")
    lines.append("=" * 70)

    return "\n".join(lines)


def generate_mermaid(
    use_cases: dict[str, dict[str, Any]],
    nodes: set[str],
    edges: list[tuple[str, str]],
    issues: dict[str, dict[str, Any]],
) -> str:
    """Generate Mermaid flowchart of dependency graph."""
    lines = []
    lines.append("```mermaid")
    lines.append("flowchart TD")
    lines.append("")

    # Define node styles based on status
    lines.append("    %% Styling")
    lines.append("    classDef done fill:#90EE90,stroke:#228B22")
    lines.append("    classDef open fill:#FFE4B5,stroke:#FF8C00")
    lines.append("    classDef blocked fill:#FFB6C1,stroke:#DC143C")
    lines.append("")

    # Group nodes by category using subgraphs
    by_category = defaultdict(list)
    for node in nodes:
        uc = use_cases.get(node, {})
        cat = uc.get("category", "other")
        by_category[cat].append(node)

    # Determine blocked nodes
    blocked = set()
    for from_node, to_node in edges:
        to_state = issues.get(to_node, {}).get("state", "OPEN")
        if to_state != "CLOSED":
            blocked.add(from_node)

    lines.append("    %% Nodes")
    for category in sorted(by_category.keys()):
        cat_name = category.replace("-", "_")
        lines.append(f"    subgraph {cat_name}[{category}]")
        for node in sorted(by_category[category]):
            uc = use_cases.get(node, {})
            title = uc.get("title", "")[:25].replace('"', "'")
            node_id = node.replace("-", "_")
            lines.append(f'        {node_id}["{node}:<br/>{title}"]')
        lines.append("    end")
        lines.append("")

    # Edges
    lines.append("    %% Dependencies")
    for from_node, to_node in edges:
        from_id = from_node.replace("-", "_")
        to_id = to_node.replace("-", "_")
        lines.append(f"    {from_id} --> {to_id}")

    lines.append("")

    # Apply classes
    lines.append("    %% Status classes")
    done_nodes = []
    open_nodes = []
    blocked_nodes = []

    for node in nodes:
        node_id = node.replace("-", "_")
        state = issues.get(node, {}).get("state", "OPEN")
        if state == "CLOSED":
            done_nodes.append(node_id)
        elif node in blocked:
            blocked_nodes.append(node_id)
        else:
            open_nodes.append(node_id)

    if done_nodes:
        lines.append(f"    class {','.join(done_nodes)} done")
    if open_nodes:
        lines.append(f"    class {','.join(open_nodes)} open")
    if blocked_nodes:
        lines.append(f"    class {','.join(blocked_nodes)} blocked")

    lines.append("```")

    return "\n".join(lines)


def generate_dot(
    use_cases: dict[str, dict[str, Any]],
    nodes: set[str],
    edges: list[tuple[str, str]],
    issues: dict[str, dict[str, Any]],
) -> str:
    """Generate DOT/Graphviz representation."""
    lines = []
    lines.append("digraph dependencies {")
    lines.append("    rankdir=TB;")
    lines.append("    node [shape=box, style=filled];")
    lines.append("")

    # Determine blocked nodes
    blocked = set()
    for from_node, to_node in edges:
        to_state = issues.get(to_node, {}).get("state", "OPEN")
        if to_state != "CLOSED":
            blocked.add(from_node)

    # Nodes with colors
    for node in sorted(nodes):
        uc = use_cases.get(node, {})
        title = uc.get("title", "")[:30].replace('"', '\\"')
        state = issues.get(node, {}).get("state", "OPEN")

        if state == "CLOSED":
            color = "palegreen"
        elif node in blocked:
            color = "lightcoral"
        else:
            color = "lightyellow"

        lines.append(f'    "{node}" [label="{node}\\n{title}", fillcolor={color}];')

    lines.append("")

    # Edges
    for from_node, to_node in edges:
        lines.append(f'    "{from_node}" -> "{to_node}";')

    lines.append("}")

    return "\n".join(lines)


def generate_json(
    use_cases: dict[str, dict[str, Any]],
    nodes: set[str],
    edges: list[tuple[str, str]],
    issues: dict[str, dict[str, Any]],
) -> str:
    """Generate JSON representation of the dependency graph."""
    # Determine blocked nodes
    blocked = set()
    for from_node, to_node in edges:
        to_state = issues.get(to_node, {}).get("state", "OPEN")
        if to_state != "CLOSED":
            blocked.add(from_node)

    graph = {
        "nodes": [],
        "edges": [{"from": e[0], "to": e[1]} for e in edges],
    }

    for node in sorted(nodes):
        uc = use_cases.get(node, {})
        issue = issues.get(node, {})
        state = issue.get("state", "UNKNOWN")

        node_data = {
            "id": node,
            "title": uc.get("title", ""),
            "category": uc.get("category", ""),
            "priority": uc.get("priority", ""),
            "issue_number": issue.get("number"),
            "state": state,
            "blocked": node in blocked,
            "can_start": state != "CLOSED" and node not in blocked,
            "depends_on": uc.get("depends_on", []),
            "blocks": uc.get("blocks", []),
        }
        graph["nodes"].append(node_data)

    return json.dumps(graph, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Map and visualize use case dependencies"
    )
    parser.add_argument(
        "--format", "-f",
        choices=["ascii", "mermaid", "dot", "json"],
        default="ascii",
        help="Output format (default: ascii)",
    )
    parser.add_argument(
        "--category", "-c",
        help="Filter by category (e.g., data-layer)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file (default: stdout)",
    )
    parser.add_argument(
        "--no-issues",
        action="store_true",
        help="Skip fetching GitHub issue status",
    )

    args = parser.parse_args()

    # Load data
    print("Loading use cases...", file=sys.stderr)
    use_cases = load_all_use_cases()
    print(f"Found {len(use_cases)} use cases", file=sys.stderr)

    if args.no_issues:
        issues = {}
    else:
        print("Fetching GitHub issues...", file=sys.stderr)
        issues = get_all_issues()
        print(f"Found {len(issues)} issues", file=sys.stderr)

    # Build graph
    nodes, edges = build_graph(use_cases, args.category)
    print(f"Graph: {len(nodes)} nodes, {len(edges)} edges", file=sys.stderr)

    # Generate output
    if args.format == "ascii":
        output = generate_ascii(use_cases, nodes, edges, issues)
    elif args.format == "mermaid":
        output = generate_mermaid(use_cases, nodes, edges, issues)
    elif args.format == "dot":
        output = generate_dot(use_cases, nodes, edges, issues)
    elif args.format == "json":
        output = generate_json(use_cases, nodes, edges, issues)
    else:
        output = ""

    # Write output
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Written to {args.output}", file=sys.stderr)
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
