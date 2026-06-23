#!/usr/bin/env python3
"""
Queue use cases for GitHub Copilot based on dependency order.

This script:
1. Loads all YAML use cases
2. Finds issues whose dependencies are all "done"
3. Labels them for Copilot to pick up
4. Respects budget limits

Usage:
    python scripts/queue_for_copilot.py              # Queue 1 issue
    python scripts/queue_for_copilot.py --max 3      # Queue up to 3 issues
    python scripts/queue_for_copilot.py --dry-run    # Preview without changes
    python scripts/queue_for_copilot.py --status     # Show queue status
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml

# Budget limits
MAX_COPILOT_PRS_PER_MONTH = 30

# Priority order for sorting
PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def run_gh(args: list[str], check: bool = True) -> str:
    """Run a gh CLI command and return stdout."""
    result = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Warning: gh command failed: {' '.join(args)}")
        print(f"  stderr: {result.stderr}")
    return result.stdout.strip()


def get_use_cases() -> dict:
    """Load all YAML use cases from docs/use-cases/."""
    cases = {}
    use_cases_dir = Path("docs/use-cases")

    if not use_cases_dir.exists():
        print(f"Error: {use_cases_dir} not found")
        sys.exit(1)

    for f in use_cases_dir.rglob("*.yml"):
        try:
            data = yaml.safe_load(f.read_text())
            if data and "id" in data:
                cases[data["id"]] = data
        except Exception as e:
            print(f"Warning: Could not parse {f}: {e}")

    return cases


def get_existing_prs() -> list[str]:
    """Get list of open PR titles to avoid duplicate work."""
    result = run_gh(["pr", "list", "--state", "open", "--json", "title"])
    prs = json.loads(result) if result else []
    return [pr["title"] for pr in prs]


def get_issues_with_label(label: str) -> list[dict]:
    """Get issues with a specific label."""
    result = run_gh(
        ["issue", "list", "--label", label, "--state", "open", "--json", "number,title"]
    )
    return json.loads(result) if result else []


def get_copilot_pr_count_this_month() -> int:
    """Count Copilot PRs created this month."""
    month_start = datetime.now().strftime("%Y-%m-01")
    result = run_gh(
        [
            "pr",
            "list",
            "--author",
            "app/github-copilot",
            "--state",
            "all",
            "--search",
            f"created:>={month_start}",
            "--json",
            "number",
        ],
        check=False,
    )
    prs = json.loads(result) if result else []
    return len(prs)


def find_ready_issues(cases: dict) -> list[tuple]:
    """Find issues whose dependencies are all done."""
    ready = []

    for id, case in cases.items():
        status = case.get("status", "todo")
        if status == "done":
            continue

        deps = case.get("depends_on", [])
        deps_done = all(cases.get(d, {}).get("status") == "done" for d in deps)

        if deps_done:
            priority = case.get("priority", "medium")
            ready.append((priority, id, case))

    # Sort by priority
    ready.sort(key=lambda x: PRIORITY_ORDER.get(x[0], 2))
    return ready


def find_github_issue(use_case_id: str) -> int | None:
    """Find GitHub issue number for a use case ID."""
    result = run_gh(
        [
            "issue",
            "list",
            "--search",
            f'"{use_case_id}" in:title',
            "--state",
            "open",
            "--json",
            "number,title",
            "--limit",
            "5",
        ]
    )
    issues = json.loads(result) if result else []

    for issue in issues:
        if issue["title"].startswith(f"{use_case_id}:"):
            return issue["number"]
    return None


def label_issue(issue_num: int, labels: list[str], dry_run: bool = False) -> None:
    """Add labels to an issue."""
    for label in labels:
        if dry_run:
            print(f"    [DRY RUN] Would add label '{label}'")
        else:
            run_gh(["issue", "edit", str(issue_num), "--add-label", label])


def show_status():
    """Display current queue status."""
    print("=" * 60)
    print("COPILOT QUEUE STATUS")
    print("=" * 60)

    # Budget status
    pr_count = get_copilot_pr_count_this_month()
    remaining = MAX_COPILOT_PRS_PER_MONTH - pr_count
    print(f"\nBudget: {pr_count}/{MAX_COPILOT_PRS_PER_MONTH} PRs this month")
    print(f"Remaining: {remaining}")

    if remaining <= 0:
        print("  ⚠️  BUDGET EXHAUSTED")

    # Issues in queue
    labeled = get_issues_with_label("copilot")
    print(f"\nIssues labeled for Copilot: {len(labeled)}")
    for issue in labeled:
        print(f"  #{issue['number']}: {issue['title']}")

    # Ready issues
    cases = get_use_cases()
    ready = find_ready_issues(cases)
    print(f"\nReady to queue (dependencies met): {len(ready)}")
    for priority, id, case in ready[:10]:
        print(f"  [{priority}] {id}: {case.get('title', 'No title')}")

    if len(ready) > 10:
        print(f"  ... and {len(ready) - 10} more")


def main():
    parser = argparse.ArgumentParser(description="Queue use cases for GitHub Copilot")
    parser.add_argument(
        "--max", type=int, default=1, help="Max issues to queue (default: 1)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without making changes"
    )
    parser.add_argument(
        "--status", action="store_true", help="Show queue status and exit"
    )
    parser.add_argument("--force", action="store_true", help="Ignore budget limits")

    args = parser.parse_args()

    if args.status:
        show_status()
        return

    # Check budget
    pr_count = get_copilot_pr_count_this_month()
    remaining = MAX_COPILOT_PRS_PER_MONTH - pr_count

    print(f"Budget: {pr_count}/{MAX_COPILOT_PRS_PER_MONTH} PRs this month")

    if remaining <= 0 and not args.force:
        print("Budget exhausted! Use --force to override.")
        sys.exit(0)

    # Load use cases
    cases = get_use_cases()
    print(f"Loaded {len(cases)} use cases")

    # Find ready issues
    ready = find_ready_issues(cases)
    print(f"Found {len(ready)} ready issues (dependencies met)")

    # Get existing PRs and labeled issues
    existing_prs = get_existing_prs()
    already_labeled = get_issues_with_label("copilot")

    queued = 0
    for priority, use_case_id, case in ready:
        if queued >= args.max:
            break

        # Skip if PR already exists
        if any(use_case_id in pr for pr in existing_prs):
            print(f"  Skipping {use_case_id}: PR already exists")
            continue

        # Skip if already labeled
        if any(use_case_id in issue.get("title", "") for issue in already_labeled):
            print(f"  Skipping {use_case_id}: already labeled for Copilot")
            continue

        # Find GitHub issue
        issue_num = find_github_issue(use_case_id)
        if issue_num:
            print(f"  Labeling #{issue_num} ({use_case_id}) for Copilot")
            label_issue(
                issue_num, ["copilot", "ready-for-copilot"], dry_run=args.dry_run
            )
            queued += 1
        else:
            print(f"  Warning: Could not find GitHub issue for {use_case_id}")

    print(f"\nQueued {queued} issues for Copilot")

    if args.dry_run:
        print("\n[DRY RUN] No changes were made")


if __name__ == "__main__":
    main()
