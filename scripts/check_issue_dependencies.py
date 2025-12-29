#!/usr/bin/env python3
"""
Check if a use case's dependencies are satisfied.

Reads YAML files from docs/use-cases/ and checks GitHub issues to determine
if all dependencies for a given use case are completed (issue closed).

Usage:
    python scripts/check_issue_dependencies.py DL-4
    python scripts/check_issue_dependencies.py --all
    python scripts/check_issue_dependencies.py --ready  # Show only ready-to-work items
    python scripts/check_issue_dependencies.py --blocked  # Show only blocked items
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
USE_CASES_DIR = ROOT / "docs" / "use-cases"


def run_gh(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a gh CLI command."""
    result = subprocess.run(
        ["gh"] + args,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        print(f"Error running gh {' '.join(args)}: {result.stderr}", file=sys.stderr)
    return result


def get_issue_dependencies(issue_number: int) -> dict[str, Any]:
    """Get GitHub native issue dependencies for an issue."""
    result = run_gh(
        ["api", f"repos/:owner/:repo/issues/{issue_number}",
         "--jq", ".issue_dependencies_summary"],
        check=False,
    )
    if result.returncode != 0:
        return {"blocked_by": 0, "blocking": 0}

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"blocked_by": 0, "blocking": 0}


def get_all_issues() -> dict[str, dict[str, Any]]:
    """Get all issues from GitHub, keyed by use case ID."""
    result = run_gh(
        ["issue", "list", "--state", "all", "--limit", "500", "--json",
         "number,title,state,labels"],
        check=False,
    )
    if result.returncode != 0:
        return {}

    issues = {}
    try:
        data = json.loads(result.stdout)
        for issue in data:
            title = issue.get("title", "")
            # Extract ID from title like "DL-4: Manage Stories..."
            if ":" in title:
                use_case_id = title.split(":")[0].strip()
                issues[use_case_id] = {
                    "number": issue.get("number"),
                    "state": issue.get("state"),
                    "title": title,
                    "labels": [l.get("name") for l in issue.get("labels", [])],
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
                        "file": str(yml_file),
                    }
            except (yaml.YAMLError, OSError) as e:
                print(f"Warning: Could not load {yml_file}: {e}", file=sys.stderr)

    return use_cases


def check_dependencies(
    use_case_id: str,
    use_cases: dict[str, dict[str, Any]],
    issues: dict[str, dict[str, Any]],
    check_github_deps: bool = True,
) -> dict[str, Any]:
    """Check if a use case's dependencies are satisfied.

    Checks both YAML-defined dependencies AND GitHub native blocking relationships.
    """
    if use_case_id not in use_cases:
        return {
            "id": use_case_id,
            "found": False,
            "error": f"Use case {use_case_id} not found in YAML files",
        }

    uc = use_cases[use_case_id]
    deps = uc.get("depends_on", [])

    # Check each YAML dependency
    satisfied = []
    unsatisfied = []
    missing_issues = []

    for dep_id in deps:
        if dep_id not in issues:
            missing_issues.append(dep_id)
        elif issues[dep_id]["state"] == "CLOSED":
            satisfied.append(dep_id)
        else:
            unsatisfied.append({
                "id": dep_id,
                "issue": issues[dep_id]["number"],
                "state": issues[dep_id]["state"],
            })

    # Get issue info for this use case
    issue_info = issues.get(use_case_id, {})
    issue_number = issue_info.get("number")

    # Check GitHub native blocking relationships
    github_blocked_by = 0
    if check_github_deps and issue_number:
        gh_deps = get_issue_dependencies(issue_number)
        github_blocked_by = gh_deps.get("blocked_by", 0)

    # An issue can start if:
    # 1. All YAML dependencies are satisfied (closed)
    # 2. No GitHub native blockers remain
    yaml_ok = len(unsatisfied) == 0 and len(missing_issues) == 0
    github_ok = github_blocked_by == 0

    return {
        "id": use_case_id,
        "found": True,
        "title": uc["title"],
        "priority": uc["priority"],
        "issue_number": issue_number,
        "issue_state": issue_info.get("state"),
        "dependencies": deps,
        "satisfied": satisfied,
        "unsatisfied": unsatisfied,
        "missing_issues": missing_issues,
        "github_blocked_by": github_blocked_by,
        "can_start": yaml_ok and github_ok,
        "blocks": uc.get("blocks", []),
    }


def print_status(result: dict[str, Any], verbose: bool = False) -> None:
    """Print the dependency check result."""
    if not result.get("found"):
        print(f"  {result['id']}: {result.get('error', 'Not found')}")
        return

    status_icon = "✅" if result["can_start"] else "🚫"
    issue_ref = f"#{result['issue_number']}" if result.get("issue_number") else "(no issue)"
    state = result.get("issue_state", "")
    state_str = f" [{state}]" if state else ""

    print(f"{status_icon} {result['id']}: {result['title'][:50]} {issue_ref}{state_str}")

    if verbose or not result["can_start"]:
        if result["satisfied"]:
            print(f"   ✓ Satisfied: {', '.join(result['satisfied'])}")
        if result["unsatisfied"]:
            blocked_str = ", ".join(
                f"{u['id']} (#{u['issue']} {u['state']})"
                for u in result["unsatisfied"]
            )
            print(f"   ✗ YAML deps blocked by: {blocked_str}")
        if result["missing_issues"]:
            print(f"   ⚠ Missing issues: {', '.join(result['missing_issues'])}")
        if result.get("github_blocked_by", 0) > 0:
            print(f"   ✗ GitHub blocked by: {result['github_blocked_by']} issue(s)")

    if verbose and result["blocks"]:
        print(f"   → Blocks: {', '.join(result['blocks'])}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check if use case dependencies are satisfied"
    )
    parser.add_argument(
        "use_case_id",
        nargs="?",
        help="Use case ID to check (e.g., DL-4)",
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Check all use cases",
    )
    parser.add_argument(
        "--ready", "-r",
        action="store_true",
        help="Show only use cases ready to work on (deps satisfied, not closed)",
    )
    parser.add_argument(
        "--blocked", "-b",
        action="store_true",
        help="Show only blocked use cases",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed dependency info",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "--category", "-c",
        help="Filter by category (e.g., data-layer, play)",
    )

    args = parser.parse_args()

    if not args.use_case_id and not args.all and not args.ready and not args.blocked:
        parser.print_help()
        return 1

    # Load data
    print("Loading use cases and issues...", file=sys.stderr)
    use_cases = load_all_use_cases()
    issues = get_all_issues()
    print(f"Found {len(use_cases)} use cases, {len(issues)} issues", file=sys.stderr)

    # Filter by category if specified
    if args.category:
        use_cases = {
            k: v for k, v in use_cases.items()
            if v.get("category") == args.category
        }

    # Determine which use cases to check
    if args.use_case_id:
        ids_to_check = [args.use_case_id]
    else:
        ids_to_check = sorted(use_cases.keys())

    # Check dependencies
    results = []
    for uc_id in ids_to_check:
        result = check_dependencies(uc_id, use_cases, issues)

        # Apply filters
        if args.ready:
            # Ready = can start AND not already closed
            if not result.get("can_start") or result.get("issue_state") == "CLOSED":
                continue
        elif args.blocked:
            if result.get("can_start") or result.get("issue_state") == "CLOSED":
                continue

        results.append(result)

    # Output
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        if args.ready:
            print("\n🟢 Ready to work on (dependencies satisfied, not closed):\n")
        elif args.blocked:
            print("\n🔴 Blocked (waiting on dependencies):\n")
        else:
            print("\n📋 Dependency Status:\n")

        for result in results:
            print_status(result, verbose=args.verbose)

        print()

        # Summary
        ready = sum(1 for r in results if r.get("can_start") and r.get("issue_state") != "CLOSED")
        blocked = sum(1 for r in results if not r.get("can_start") and r.get("issue_state") != "CLOSED")
        closed = sum(1 for r in results if r.get("issue_state") == "CLOSED")

        print(f"Summary: {ready} ready, {blocked} blocked, {closed} completed")

    return 0


if __name__ == "__main__":
    sys.exit(main())
