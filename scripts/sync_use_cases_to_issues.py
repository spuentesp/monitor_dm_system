#!/usr/bin/env python3
"""
Sync use case YAML files to GitHub Issues.

Reads YAML files from docs/use-cases/ and creates/updates GitHub issues.
Uses the 'gh' CLI for GitHub API operations.

Usage:
    python scripts/sync_use_cases_to_issues.py
    python scripts/sync_use_cases_to_issues.py --dry-run
    python scripts/sync_use_cases_to_issues.py --filter "DL-*"
    python scripts/sync_use_cases_to_issues.py --category data-layer
"""

from __future__ import annotations

import argparse
import fnmatch
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


def get_project_id(owner: str, project_number: int) -> str | None:
    """Get project node ID from project number."""
    result = run_gh(
        ["project", "list", "--owner", owner, "--format", "json"],
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
        for project in data.get("projects", []):
            if project.get("number") == project_number:
                return project.get("id")
    except json.JSONDecodeError:
        pass
    return None


def add_issue_to_project(project_number: int, owner: str, issue_url: str) -> bool:
    """Add an issue to a GitHub project."""
    result = run_gh(
        ["project", "item-add", str(project_number), "--owner", owner, "--url", issue_url],
        check=False,
    )
    return result.returncode == 0


def get_repo_info() -> tuple[str, str]:
    """Get owner/repo from git remote."""
    result = subprocess.run(
        ["git", "config", "--get", "remote.origin.url"],
        capture_output=True,
        text=True,
    )
    url = result.stdout.strip()

    # Parse github.com:owner/repo or github.com/owner/repo
    import re

    match = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", url)
    if match:
        return match.group(1), match.group(2).replace(".git", "")
    raise ValueError(f"Could not parse GitHub remote: {url}")


def load_use_case(path: Path) -> dict[str, Any] | None:
    """Load and validate a use case YAML file."""
    if path.name.startswith("_"):
        return None  # Skip schema and other meta files

    try:
        with open(path) as f:
            data = yaml.safe_load(f)

        # Validate required fields
        required = ["id", "title", "category", "epic", "summary", "acceptance_criteria"]
        missing = [f for f in required if f not in data]
        if missing:
            print(f"Warning: {path.name} missing required fields: {missing}")
            return None

        data["_path"] = str(path)
        return data
    except yaml.YAMLError as e:
        print(f"Error parsing {path}: {e}", file=sys.stderr)
        return None


def load_all_use_cases(
    filter_pattern: str | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    """Load all use case YAML files."""
    use_cases = []

    for yml_path in USE_CASES_DIR.rglob("*.yml"):
        uc = load_use_case(yml_path)
        if uc is None:
            continue

        # Apply filters
        if filter_pattern and not fnmatch.fnmatch(uc["id"], filter_pattern):
            continue
        if category and uc["category"] != category:
            continue

        use_cases.append(uc)

    # Sort by ID
    use_cases.sort(key=lambda x: x["id"])
    return use_cases


def format_issue_body(uc: dict[str, Any]) -> str:
    """Format use case data as GitHub issue body."""
    lines = []

    # Header with metadata
    lines.append(f"**Category:** {uc['category']} | **Epic:** {uc['epic']} | **Priority:** {uc.get('priority', 'medium')}")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append(uc["summary"].strip())
    lines.append("")

    # Acceptance Criteria
    lines.append("## Acceptance Criteria")
    for criterion in uc["acceptance_criteria"]:
        lines.append(f"- [ ] {criterion}")
    lines.append("")

    # Dependencies
    if uc.get("depends_on"):
        lines.append("## Dependencies")
        lines.append("This use case depends on:")
        for dep in uc["depends_on"]:
            lines.append(f"- {dep}")
        lines.append("")

    if uc.get("blocks"):
        lines.append("## Blocks")
        lines.append("This use case blocks:")
        for blocked in uc["blocks"]:
            lines.append(f"- {blocked}")
        lines.append("")

    # Implementation Details
    if impl := uc.get("implementation"):
        lines.append("## Implementation")
        lines.append(f"**Layer:** {impl.get('layer', 'N/A')}")
        lines.append("")

        if files := impl.get("files"):
            if files.get("create"):
                lines.append("**Files to create:**")
                for f in files["create"]:
                    lines.append(f"- `{f}`")
            if files.get("modify"):
                lines.append("**Files to modify:**")
                for f in files["modify"]:
                    lines.append(f"- `{f}`")
            lines.append("")

        if db_ops := impl.get("database_operations"):
            for db, ops in db_ops.items():
                lines.append(f"**{db.upper()} Operations:**")
                for op in ops:
                    auth = ", ".join(op.get("authority", ["*"]))
                    lines.append(f"- `{op['name']}` (authority: {auth})")
                lines.append("")

        if notes := impl.get("notes"):
            lines.append("**Notes:**")
            lines.append(notes.strip())
            lines.append("")

    # Testing
    if testing := uc.get("testing"):
        lines.append("## Testing Requirements")
        lines.append(f"**Minimum coverage:** {testing.get('coverage_minimum', 80)}%")
        lines.append("")

        if unit := testing.get("unit_tests"):
            lines.append("**Unit tests:**")
            for t in unit[:5]:  # Show first 5
                lines.append(f"- {t}")
            if len(unit) > 5:
                lines.append(f"- ... and {len(unit) - 5} more")
            lines.append("")

        if integration := testing.get("integration_tests"):
            lines.append("**Integration tests:**")
            for t in integration:
                lines.append(f"- {t}")
            lines.append("")

    # References
    if refs := uc.get("references"):
        lines.append("## References")
        if docs := refs.get("docs"):
            lines.append("**Documentation:**")
            for d in docs:
                lines.append(f"- [{d}]({d})")
        if code := refs.get("code"):
            lines.append("**Code:**")
            for c in code:
                lines.append(f"- `{c}`")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append(f"*Generated from `{uc['_path']}`*")

    return "\n".join(lines)


def get_existing_milestones() -> set[str]:
    """Get all existing milestone titles."""
    result = run_gh(
        ["api", "repos/{owner}/{repo}/milestones", "--jq", ".[].title"],
        check=False,
    )
    if result.returncode != 0:
        return set()
    return set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()


def find_existing_issue(uc_id: str) -> int | None:
    """Find existing issue by use case ID in title."""
    # Search both open and closed issues
    result = run_gh(
        ["issue", "list", "--search", f"{uc_id} in:title", "--state", "all", "--json", "number,title", "--limit", "20"],
        check=False,
    )
    if result.returncode != 0:
        return None

    try:
        issues = json.loads(result.stdout)
        for issue in issues:
            # Match exact ID at start of title
            if issue["title"].startswith(f"{uc_id}:") or issue["title"].startswith(f"{uc_id} "):
                return issue["number"]
    except json.JSONDecodeError:
        pass

    return None


def create_issue(
    uc: dict[str, Any],
    dry_run: bool = False,
    existing_milestones: set[str] | None = None,
    skip_milestone: bool = False,
) -> tuple[int | None, str | None]:
    """Create a new GitHub issue from use case. Returns (issue_number, issue_url)."""
    title = f"{uc['id']}: {uc['title']}"
    body = format_issue_body(uc)

    # Prepare labels
    labels = uc.get("github", {}).get("labels", [])
    if not labels:
        labels = [f"epic-{uc['epic']}", uc["category"]]

    # Check milestone
    milestone = uc.get("github", {}).get("milestone") if not skip_milestone else None
    if milestone and existing_milestones is not None:
        if milestone not in existing_milestones:
            print(f"    ⚠️  Milestone '{milestone}' not found, skipping")
            milestone = None

    if dry_run:
        print(f"  [DRY-RUN] Would create issue: {title}")
        print(f"            Labels: {', '.join(labels)}")
        if milestone:
            print(f"            Milestone: {milestone}")
        return None, None

    # Create issue
    args = ["issue", "create", "--title", title, "--body", body]
    for label in labels:
        args.extend(["--label", label])

    if milestone:
        args.extend(["--milestone", milestone])

    result = run_gh(args, check=False)
    if result.returncode == 0:
        # Extract issue number from URL
        url = result.stdout.strip()
        if "/issues/" in url:
            return int(url.split("/issues/")[-1]), url
    else:
        print(f"    Error creating issue: {result.stderr.strip()}")

    return None, None


def update_issue(issue_number: int, uc: dict[str, Any], dry_run: bool = False) -> bool:
    """Update an existing GitHub issue."""
    title = f"{uc['id']}: {uc['title']}"
    body = format_issue_body(uc)

    if dry_run:
        print(f"  [DRY-RUN] Would update issue #{issue_number}: {title}")
        return True

    result = run_gh(
        ["issue", "edit", str(issue_number), "--title", title, "--body", body],
        check=False,
    )
    return result.returncode == 0


def ensure_labels_exist(use_cases: list[dict[str, Any]], dry_run: bool = False) -> None:
    """Ensure all required labels exist in the repository."""
    # Collect all unique labels
    all_labels: set[str] = set()
    for uc in use_cases:
        labels = uc.get("github", {}).get("labels", [])
        all_labels.update(labels)
        # Add default labels
        all_labels.add(f"epic-{uc['epic']}")
        all_labels.add(uc["category"])

    # Get existing labels
    result = run_gh(["label", "list", "--json", "name"], check=False)
    existing = set()
    if result.returncode == 0:
        try:
            existing = {l["name"] for l in json.loads(result.stdout)}
        except json.JSONDecodeError:
            pass

    # Create missing labels
    label_colors = {
        "epic-0": "1d76db",
        "epic-1": "0e8a16",
        "epic-2": "fbca04",
        "epic-3": "d93f0b",
        "epic-4": "5319e7",
        "epic-5": "006b75",
        "epic-6": "b60205",
        "epic-7": "0052cc",
        "epic-8": "ff7619",
        "epic-9": "84b6eb",
        "data-layer": "1d76db",
        "play": "0e8a16",
        "manage": "fbca04",
        "query": "5319e7",
        "ingest": "006b75",
        "system": "b60205",
        "co-pilot": "0052cc",
        "story": "ff7619",
        "rules": "d93f0b",
        "docs": "84b6eb",
        "priority-high": "b60205",
        "priority-medium": "fbca04",
        "priority-low": "0e8a16",
        "neo4j": "008cc1",
        "mongodb": "00ed64",
        "qdrant": "dc477d",
    }

    missing = all_labels - existing
    for label in sorted(missing):
        color = label_colors.get(label, "ededed")
        if dry_run:
            print(f"  [DRY-RUN] Would create label: {label}")
        else:
            run_gh(["label", "create", label, "--color", color, "--force"], check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync use cases to GitHub issues")
    parser.add_argument("--dry-run", action="store_true", help="Preview without making changes")
    parser.add_argument("--filter", type=str, help="Filter by ID pattern (e.g., 'DL-*')")
    parser.add_argument("--category", type=str, help="Filter by category")
    parser.add_argument("--create-only", action="store_true", help="Only create new, don't update existing")
    parser.add_argument("--update-only", action="store_true", help="Only update existing, don't create new")
    parser.add_argument("--skip-milestone", action="store_true", help="Skip milestone assignment")
    parser.add_argument("--check-only", action="store_true", help="Only check for duplicates, don't create/update")
    parser.add_argument("--project", type=int, help="Add created issues to this project number")
    args = parser.parse_args()

    print("=" * 70)
    print("  MONITOR Use Case → GitHub Issue Sync")
    print("=" * 70)
    if args.dry_run:
        print("  Mode: DRY RUN (no changes will be made)")
    if args.check_only:
        print("  Mode: CHECK ONLY (listing existing issues)")
    print()

    # Load use cases
    print("→ Loading use cases...")
    use_cases = load_all_use_cases(filter_pattern=args.filter, category=args.category)
    print(f"  Found {len(use_cases)} use cases")

    if not use_cases:
        print("  No use cases to process.")
        return 0

    # Load existing milestones
    existing_milestones: set[str] = set()
    if not args.skip_milestone and not args.check_only:
        print()
        print("→ Loading milestones...")
        existing_milestones = get_existing_milestones()
        if existing_milestones:
            print(f"  Found milestones: {', '.join(sorted(existing_milestones))}")
        else:
            print("  No milestones found (will skip milestone assignment)")

    # Get project info if specified
    project_owner: str | None = None
    if args.project and not args.check_only:
        print()
        print(f"→ Loading project #{args.project}...")
        project_owner, _ = get_repo_info()
        project_id = get_project_id(project_owner, args.project)
        if project_id:
            print(f"  ✓ Found project #{args.project} (owner: {project_owner})")
        else:
            print(f"  ⚠️  Project #{args.project} not found, skipping project linking")
            project_owner = None

    # Ensure labels exist
    if not args.check_only:
        print()
        print("→ Ensuring labels exist...")
        ensure_labels_exist(use_cases, dry_run=args.dry_run)

    # Process each use case
    print()
    print("→ Processing use cases...")
    created = 0
    updated = 0
    skipped = 0
    added_to_project = 0
    existing_issues: list[tuple[str, int]] = []

    for uc in use_cases:
        uc_id = uc["id"]
        existing = find_existing_issue(uc_id)

        if existing:
            existing_issues.append((uc_id, existing))
            if args.check_only:
                print(f"  {uc_id}: EXISTS as #{existing}")
                skipped += 1
            elif args.create_only:
                print(f"  {uc_id}: Skipping (exists as #{existing})")
                skipped += 1
            else:
                print(f"  {uc_id}: Updating #{existing}...")
                if update_issue(existing, uc, dry_run=args.dry_run):
                    updated += 1
                else:
                    print(f"    Failed to update")
        else:
            if args.check_only:
                print(f"  {uc_id}: NOT FOUND")
            elif args.update_only:
                print(f"  {uc_id}: Skipping (no existing issue)")
                skipped += 1
            else:
                print(f"  {uc_id}: Creating...")
                issue_num, issue_url = create_issue(
                    uc,
                    dry_run=args.dry_run,
                    existing_milestones=existing_milestones,
                    skip_milestone=args.skip_milestone,
                )
                if issue_num:
                    created += 1
                    # Add to project if specified
                    if project_owner and issue_url:
                        if add_issue_to_project(args.project, project_owner, issue_url):
                            added_to_project += 1
                            print(f"    ✓ Added to project")
                        else:
                            print(f"    ⚠️  Failed to add to project")
                elif args.dry_run:
                    created += 1  # Count dry-run as success

    # Summary
    print()
    print("=" * 70)
    if args.check_only:
        print(f"  CHECK COMPLETE")
        print(f"  Existing issues: {len(existing_issues)}, Missing: {len(use_cases) - len(existing_issues)}")
        if existing_issues:
            print()
            print("  Existing issues:")
            for uc_id, issue_num in existing_issues:
                print(f"    - {uc_id}: #{issue_num}")
    elif args.dry_run:
        print(f"  DRY RUN COMPLETE")
        print(f"  Would create: {created}, Would update: {updated}, Skipped: {skipped}")
        if args.project:
            print(f"  Would add to project #{args.project}: {created}")
    else:
        print(f"  Sync complete!")
        print(f"  Created: {created}, Updated: {updated}, Skipped: {skipped}")
        if args.project:
            print(f"  Added to project: {added_to_project}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
