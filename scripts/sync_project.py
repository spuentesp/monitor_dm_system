#!/usr/bin/env python3
"""
Unified GitHub Project & Issues Sync

Syncs use case YAML files to GitHub Project and Issues with:
- Automatic issue creation from use cases
- Project item creation and status management
- Dependency tracking (blocked/ready labels + GitHub native blocking)
- PR-based status updates (In Progress when PR open, Done when merged)

Usage:
    python scripts/sync_project.py                    # Full sync
    python scripts/sync_project.py --status           # Show current status
    python scripts/sync_project.py --ready            # Show ready items
    python scripts/sync_project.py --blocked          # Show blocked items
    python scripts/sync_project.py --dry-run          # Preview changes
    python scripts/sync_project.py --category data-layer  # Filter by category
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

PROJECT_NUMBER = 1
PROJECT_OWNER = "spuentesp"


def run_gh(args: list[str], check: bool = False) -> subprocess.CompletedProcess:
    """Run gh CLI command."""
    result = subprocess.run(["gh"] + args, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error: {result.stderr}", file=sys.stderr)
    return result


def run_graphql(query: str, variables: dict[str, Any] = None) -> dict:
    """Run GraphQL query via gh api."""
    args = ["api", "graphql", "-f", f"query={query}"]
    if variables:
        for k, v in variables.items():
            if isinstance(v, int):
                args.extend(["-F", f"{k}={v}"])
            else:
                args.extend(["-f", f"{k}={v}"])
    result = run_gh(args)
    if result.returncode != 0:
        return {"errors": [{"message": result.stderr}]}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"errors": [{"message": "Invalid JSON response"}]}


# =============================================================================
# DATA LOADING
# =============================================================================

def load_use_cases(category: str = None) -> dict[str, dict[str, Any]]:
    """Load all use case YAML files."""
    use_cases = {}

    for category_dir in USE_CASES_DIR.iterdir():
        if not category_dir.is_dir():
            continue
        if category and category_dir.name != category:
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
                        "summary": data.get("summary", ""),
                        "depends_on": data.get("depends_on", []),
                        "blocks": data.get("blocks", []),
                        "epic": data.get("epic", 0),
                        "file": str(yml_file),
                    }
            except (yaml.YAMLError, OSError):
                pass

    return use_cases


def get_all_issues() -> dict[str, dict[str, Any]]:
    """Get all GitHub issues keyed by use case ID."""
    result = run_gh([
        "issue", "list", "--state", "all", "--limit", "500",
        "--json", "number,title,state,labels,body"
    ])
    if result.returncode != 0:
        return {}

    issues = {}
    try:
        data = json.loads(result.stdout)
        for issue in data:
            title = issue.get("title", "")
            if ":" in title:
                uc_id = title.split(":")[0].strip()
                issues[uc_id] = {
                    "number": issue.get("number"),
                    "state": issue.get("state"),
                    "title": title,
                    "labels": [l.get("name") for l in issue.get("labels", [])],
                    "body": issue.get("body", ""),
                }
    except json.JSONDecodeError:
        pass

    return issues


def get_open_prs() -> dict[int, dict[str, Any]]:
    """Get open PRs and their linked issues."""
    result = run_gh([
        "pr", "list", "--state", "open", "--limit", "100",
        "--json", "number,title,body,headRefName"
    ])
    if result.returncode != 0:
        return {}

    prs = {}
    try:
        data = json.loads(result.stdout)
        for pr in data:
            body = pr.get("body", "") or ""
            # Extract linked issue (handles both #39 and owner/repo#39 formats)
            import re
            match = re.search(r"(?:Fixes|Closes|Resolves)\s*(?:[\w-]+/[\w-]+)?#(\d+)", body, re.IGNORECASE)
            linked_issue = int(match.group(1)) if match else None

            prs[pr["number"]] = {
                "title": pr.get("title"),
                "branch": pr.get("headRefName"),
                "linked_issue": linked_issue,
            }
    except json.JSONDecodeError:
        pass

    return prs


def get_issue_github_blocked(issue_number: int) -> int:
    """Get GitHub native blocked_by count for an issue."""
    result = run_gh([
        "api", f"repos/:owner/:repo/issues/{issue_number}",
        "--jq", ".issue_dependencies_summary.blocked_by // 0"
    ])
    try:
        return int(result.stdout.strip())
    except (ValueError, AttributeError):
        return 0


# =============================================================================
# STATUS COMPUTATION
# =============================================================================

def compute_status(
    uc_id: str,
    use_cases: dict[str, dict[str, Any]],
    issues: dict[str, dict[str, Any]],
    prs: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    """Compute the current status of a use case."""
    uc = use_cases.get(uc_id, {})
    issue = issues.get(uc_id, {})
    issue_number = issue.get("number")

    # Check if closed
    if issue.get("state") == "CLOSED":
        return {
            "id": uc_id,
            "status": "Done",
            "reason": "Issue closed",
            "issue_number": issue_number,
        }

    # Check for open PR
    has_open_pr = False
    pr_number = None
    if issue_number:
        for pr_num, pr_data in prs.items():
            if pr_data.get("linked_issue") == issue_number:
                has_open_pr = True
                pr_number = pr_num
                break

    if has_open_pr:
        return {
            "id": uc_id,
            "status": "In Progress",
            "reason": f"Open PR #{pr_number}",
            "issue_number": issue_number,
            "pr_number": pr_number,
        }

    # Check dependencies
    deps = uc.get("depends_on", [])
    unsatisfied = []
    for dep_id in deps:
        dep_issue = issues.get(dep_id, {})
        if dep_issue.get("state") != "CLOSED":
            unsatisfied.append(dep_id)

    # Check GitHub native blocking
    github_blocked = 0
    if issue_number:
        github_blocked = get_issue_github_blocked(issue_number)

    if unsatisfied or github_blocked > 0:
        return {
            "id": uc_id,
            "status": "Todo",
            "blocked": True,
            "reason": f"Blocked by: {', '.join(unsatisfied)}" if unsatisfied else f"GitHub blocked by {github_blocked}",
            "issue_number": issue_number,
            "unsatisfied_deps": unsatisfied,
            "github_blocked": github_blocked,
        }

    return {
        "id": uc_id,
        "status": "Todo",
        "blocked": False,
        "reason": "Ready to start",
        "issue_number": issue_number,
    }


# =============================================================================
# PROJECT SYNC
# =============================================================================

def get_project_metadata() -> dict[str, Any]:
    """Get project ID and field metadata."""
    query = """
    query($owner: String!, $number: Int!) {
      user(login: $owner) {
        projectV2(number: $number) {
          id
          fields(first: 20) {
            nodes {
              ... on ProjectV2SingleSelectField {
                id
                name
                options { id name }
              }
            }
          }
        }
      }
    }
    """
    result = run_graphql(query, {"owner": PROJECT_OWNER, "number": PROJECT_NUMBER})

    project = result.get("data", {}).get("user", {}).get("projectV2", {})
    if not project:
        return {}

    fields = {}
    for field in project.get("fields", {}).get("nodes", []):
        if field.get("name") == "Status":
            fields["status_field_id"] = field.get("id")
            fields["status_options"] = {
                opt["name"]: opt["id"]
                for opt in field.get("options", [])
            }

    return {
        "project_id": project.get("id"),
        **fields,
    }


def get_project_items(project_id: str) -> dict[int, str]:
    """Get project items keyed by issue number."""
    query = """
    query($projectId: ID!) {
      node(id: $projectId) {
        ... on ProjectV2 {
          items(first: 100) {
            nodes {
              id
              content {
                ... on Issue { number }
              }
            }
          }
        }
      }
    }
    """
    result = run_graphql(query, {"projectId": project_id})
    items = {}
    for node in result.get("data", {}).get("node", {}).get("items", {}).get("nodes", []):
        content = node.get("content", {})
        if content and content.get("number"):
            items[content["number"]] = node["id"]
    return items


def update_project_item_status(
    project_id: str,
    item_id: str,
    field_id: str,
    option_id: str,
    dry_run: bool = False,
) -> bool:
    """Update a project item's status."""
    if dry_run:
        return True

    query = """
    mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $optionId: String!) {
      updateProjectV2ItemFieldValue(input: {
        projectId: $projectId
        itemId: $itemId
        fieldId: $fieldId
        value: { singleSelectOptionId: $optionId }
      }) {
        projectV2Item { id }
      }
    }
    """
    result = run_graphql(query, {
        "projectId": project_id,
        "itemId": item_id,
        "fieldId": field_id,
        "optionId": option_id,
    })
    return "errors" not in result


def sync_labels(issue_number: int, blocked: bool, dry_run: bool = False) -> None:
    """Sync blocked/ready labels on an issue."""
    if dry_run:
        return

    if blocked:
        run_gh(["issue", "edit", str(issue_number), "--add-label", "blocked", "--remove-label", "ready"])
    else:
        run_gh(["issue", "edit", str(issue_number), "--add-label", "ready", "--remove-label", "blocked"])


# =============================================================================
# MAIN
# =============================================================================

def print_status_table(statuses: list[dict], verbose: bool = False) -> None:
    """Print status table."""
    # Group by status
    done = [s for s in statuses if s["status"] == "Done"]
    in_progress = [s for s in statuses if s["status"] == "In Progress"]
    blocked = [s for s in statuses if s["status"] == "Todo" and s.get("blocked")]
    ready = [s for s in statuses if s["status"] == "Todo" and not s.get("blocked")]

    if done:
        print("\n✅ DONE:")
        for s in done:
            print(f"   #{s.get('issue_number', '?'):3} {s['id']}")

    if in_progress:
        print("\n🔄 IN PROGRESS:")
        for s in in_progress:
            pr = f" (PR #{s.get('pr_number')})" if s.get("pr_number") else ""
            print(f"   #{s.get('issue_number', '?'):3} {s['id']}{pr}")

    if ready:
        print("\n🟢 READY:")
        for s in ready:
            print(f"   #{s.get('issue_number', '?'):3} {s['id']}")

    if blocked:
        print("\n🔴 BLOCKED:")
        for s in blocked:
            reason = s.get("reason", "")
            print(f"   #{s.get('issue_number', '?'):3} {s['id']}: {reason}")

    print(f"\nSummary: {len(done)} done, {len(in_progress)} in progress, {len(ready)} ready, {len(blocked)} blocked")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync GitHub Project & Issues")
    parser.add_argument("--status", "-s", action="store_true", help="Show current status")
    parser.add_argument("--ready", "-r", action="store_true", help="Show only ready items")
    parser.add_argument("--blocked", "-b", action="store_true", help="Show only blocked items")
    parser.add_argument("--sync", action="store_true", help="Sync project status from current state")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes")
    parser.add_argument("--category", "-c", help="Filter by category")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Default to status if no action specified
    if not any([args.status, args.ready, args.blocked, args.sync]):
        args.status = True

    print("Loading data...", file=sys.stderr)
    use_cases = load_use_cases(args.category)
    issues = get_all_issues()
    prs = get_open_prs()
    print(f"  {len(use_cases)} use cases, {len(issues)} issues, {len(prs)} open PRs", file=sys.stderr)

    # Compute status for all use cases
    statuses = []
    for uc_id in sorted(use_cases.keys()):
        status = compute_status(uc_id, use_cases, issues, prs)
        status["title"] = use_cases[uc_id].get("title", "")
        status["priority"] = use_cases[uc_id].get("priority", "")
        statuses.append(status)

    # Filter if needed
    if args.ready:
        statuses = [s for s in statuses if s["status"] == "Todo" and not s.get("blocked")]
    elif args.blocked:
        statuses = [s for s in statuses if s["status"] == "Todo" and s.get("blocked")]

    # Show status
    if args.status or args.ready or args.blocked:
        print_status_table(statuses, args.verbose)

    # Sync project
    if args.sync:
        print("\nSyncing project...", file=sys.stderr)
        meta = get_project_metadata()
        if not meta.get("project_id"):
            print("❌ Could not find project", file=sys.stderr)
            return 1

        project_items = get_project_items(meta["project_id"])
        print(f"  Project has {len(project_items)} items", file=sys.stderr)

        updated = 0
        for status in statuses:
            issue_num = status.get("issue_number")
            if not issue_num:
                continue

            item_id = project_items.get(issue_num)
            if not item_id:
                continue

            target_status = status["status"]
            option_id = meta.get("status_options", {}).get(target_status)
            if not option_id:
                continue

            action = "[DRY-RUN] Would update" if args.dry_run else "Updating"
            print(f"  {action} #{issue_num} → {target_status}")

            if update_project_item_status(
                meta["project_id"],
                item_id,
                meta["status_field_id"],
                option_id,
                dry_run=args.dry_run,
            ):
                updated += 1

            # Also sync labels
            if status["status"] == "Todo":
                sync_labels(issue_num, status.get("blocked", False), dry_run=args.dry_run)

        print(f"\n{'Would update' if args.dry_run else 'Updated'} {updated} items")

    return 0


if __name__ == "__main__":
    sys.exit(main())
