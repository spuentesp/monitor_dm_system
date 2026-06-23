#!/usr/bin/env python3
"""
Comprehensive Use Case Testing Analysis Script.

This script analyzes all use cases in the MONITOR system and maps them to existing tests,
identifying gaps and creating a prioritized testing roadmap.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict
import json


class UseCaseAnalyzer:
    """Analyze use case coverage across the MONITOR system."""

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root)
        self.use_cases_dir = self.workspace_root / "docs" / "use-cases"
        self.tests_dir = self.workspace_root / "tests"

        # Data structures
        self.all_use_cases: Dict[str, Dict] = {}
        self.tested_use_cases: Set[str] = set()
        self.use_case_to_tests: Dict[str, List[str]] = defaultdict(list)
        self.epic_mapping: Dict[str, List[str]] = defaultdict(list)

    def discover_all_use_cases(self) -> Dict[str, Dict]:
        """Discover all use cases from the docs/use-cases directory."""
        print("=" * 80)
        print("STEP 1: Discovering all use cases...")
        print("=" * 80)

        # Pattern to match use case directories (DL-*, M-*, P-*, Q-*, I-*, SYS-*, CF-*, ST-*, RS-*, MP-*)
        use_case_pattern = re.compile(r'^([A-Z]+)-\d+$')

        for epic_dir in sorted(self.use_cases_dir.iterdir()):
            if not epic_dir.is_dir():
                continue

            # Extract epic name from directory
            epic_name = epic_dir.name.replace("epic-", "")

            for use_case_dir in sorted(epic_dir.iterdir()):
                if not use_case_dir.is_dir():
                    continue

                use_case_name = use_case_dir.name
                match = use_case_pattern.match(use_case_name)

                if match:
                    use_case_id = match.group(1)

                    # Check for specification file
                    spec_file = use_case_dir / f"{use_case_name}-specification.md"
                    has_spec = spec_file.exists()

                    # Check for behavior file
                    behavior_file = use_case_dir / f"{use_case_name}-behavior.md"
                    has_behavior = behavior_file.exists()

                    # Check for contract file
                    contract_file = use_case_dir / f"{use_case_name}-contract.md"
                    has_contract = contract_file.exists()

                    self.all_use_cases[use_case_id] = {
                        "id": use_case_id,
                        "name": use_case_name,
                        "epic": epic_name,
                        "has_spec": has_spec,
                        "has_behavior": has_behavior,
                        "has_contract": has_contract,
                        "directory": str(use_case_dir)
                    }

                    self.epic_mapping[epic_name].append(use_case_id)

        print(f"✓ Discovered {len(self.all_use_cases)} use cases across {len(self.epic_mapping)} epics\n")
        return self.all_use_cases

    def discover_all_tests(self) -> Dict[str, List[str]]:
        """Discover all test files and map them to use cases."""
        print("=" * 80)
        print("STEP 2: Discovering all test files...")
        print("=" * 80)

        # Pattern to match test file names with use case IDs
        # Matches: test_M_13_behavior.py, test_P_1_behavior.py, etc.
        test_pattern = re.compile(r'^test_([A-Z]+_\d+).*\.py$')

        # Also check for patterns like test_M_1_M_2_behavior.py
        multi_test_pattern = re.compile(r'^test_([A-Z]+_\d+_[A-Z]+\d+).*\.py$')

        test_count = 0

        # Check tests/behavior/ directory
        behavior_dir = self.tests_dir / "behavior"
        if behavior_dir.exists():
            for test_file in sorted(behavior_dir.glob("test_*.py")):
                if test_file.is_file():
                    match = test_pattern.match(test_file.name)
                    if match:
                        use_case_ref = match.group(1)
                        # Convert M_13 to M-13 format
                        use_case_id = use_case_ref.replace('_', '-')

                        if use_case_id in self.all_use_cases:
                            self.tested_use_cases.add(use_case_id)
                            self.use_case_to_tests[use_case_id].append(str(test_file))
                            test_count += 1
                            print(f"  ✓ Found test for {use_case_id}: {test_file.name}")

                    # Check for multi-use case tests
                    multi_match = multi_test_pattern.match(test_file.name)
                    if multi_match:
                        use_case_refs = multi_match.group(1)
                        # Split and convert M_1_M_2 to M-1 and M-2
                        parts = use_case_ref.split('_')
                        for i in range(0, len(parts), 2):
                            if i + 1 < len(parts):
                                use_case_id = f"{parts[i]}-{parts[i+1]}"
                                if use_case_id in self.all_use_cases:
                                    self.tested_use_cases.add(use_case_id)
                                    self.use_case_to_tests[use_case_id].append(str(test_file))
                                    print(f"  ✓ Found test for {use_case_id}: {test_file.name}")

        # Check packages/*/tests/ directories
        packages_dir = self.workspace_root / "packages"
        if packages_dir.exists():
            for package_dir in packages_dir.iterdir():
                if package_dir.is_dir():
                    tests_subdir = package_dir / "tests"
                    if tests_subdir.exists():
                        for test_file in sorted(tests_subdir.glob("test_*.py")):
                            # Look for use case references in test content
                            test_count += 1

        print(f"✓ Discovered {test_count} test files\n")
        return self.use_case_to_tests

    def analyze_gaps(self) -> Tuple[List[str], Dict[str, List[str]]]:
        """Identify use cases without tests."""
        print("=" * 80)
        print("STEP 3: Analyzing coverage gaps...")
        print("=" * 80)

        untested_use_cases = []
        untested_by_epic: Dict[str, List[str]] = defaultdict(list)

        for use_case_id, use_case_info in self.all_use_cases.items():
            if use_case_id not in self.tested_use_cases:
                untested_use_cases.append(use_case_id)
                untested_by_epic[use_case_info["epic"]].append(use_case_id)

        coverage_pct = (len(self.tested_use_cases) / len(self.all_use_cases)) * 100 if self.all_use_cases else 0

        print(f"  Total use cases: {len(self.all_use_cases)}")
        print(f"  Tested use cases: {len(self.tested_use_cases)}")
        print(f"  Untested use cases: {len(untested_use_cases)}")
        print(f"  Coverage: {coverage_pct:.1f}%\n")

        return untested_use_cases, untested_by_epic

    def generate_prioritized_plan(self) -> List[Dict]:
        """Generate a prioritized testing plan."""
        print("=" * 80)
        print("STEP 4: Generating prioritized testing plan...")
        print("=" * 80)

        # Core foundation use cases (highest priority)
        core_foundation = [
            "M-1", "M-2", "M-13",  # World/Identity creation
            "P-1", "P-2", "P-3", "P-4",  # Core gameplay
            "SYS-1", "SYS-2", "SYS-3",  # System lifecycle
        ]

        # Next critical use cases
        critical_use_cases = [
            "M-3", "M-4", "M-5", "M-6",  # Basic entity management
            "P-5", "P-6", "P-7",  # Advanced gameplay
            "I-1", "I-2", "I-3",  # Ingestion
        ]

        plan = [
            {
                "phase": 1,
                "name": "Core Foundation",
                "use_cases": [uc for uc in core_foundation if uc in self.all_use_cases and uc not in self.tested_use_cases],
                "description": "Essential use cases for the system to function",
                "estimated_tests": len([uc for uc in core_foundation if uc in self.all_use_cases and uc not in self.tested_use_cases]) * 5
            },
            {
                "phase": 2,
                "name": "Critical Features",
                "use_cases": [uc for uc in critical_use_cases if uc in self.all_use_cases and uc not in self.tested_use_cases],
                "description": "Important features for core gameplay",
                "estimated_tests": len([uc for uc in critical_use_cases if uc in self.all_use_cases and uc not in self.tested_use_cases]) * 3
            },
            {
                "phase": 3,
                "name": "Data Layer Infrastructure",
                "use_cases": [uc for uc, info in self.all_use_cases.items()
                             if uc.startswith("DL-") and uc not in self.tested_use_cases],
                "description": "Data layer operations and MCP tools",
                "estimated_tests": len([uc for uc in self.all_use_cases.keys() if uc.startswith("DL-") and uc not in self.tested_use_cases]) * 2
            },
            {
                "phase": 4,
                "name": "Identity & Query",
                "use_cases": [uc for uc in self.all_use_cases.keys()
                             if (uc.startswith("M-") or uc.startswith("Q-")) and uc not in self.tested_use_cases
                             and uc not in core_foundation and uc not in critical_use_cases],
                "description": "Character management and query operations",
                "estimated_tests": len([uc for uc in self.all_use_cases.keys()
                                      if (uc.startswith("M-") or uc.startswith("Q-")) and uc not in self.tested_use_cases
                                      and uc not in core_foundation and uc not in critical_use_cases]) * 2
            },
            {
                "phase": 5,
                "name": "Advanced Features",
                "use_cases": [uc for uc in self.all_use_cases.keys()
                             if uc.startswith(("I-", "CF-", "ST-", "RS-", "MP-")) and uc not in self.tested_use_cases
                             and uc not in critical_use_cases],
                "description": "Ingestion, co-pilot, story planning, rules, and packs",
                "estimated_tests": len([uc for uc in self.all_use_cases.keys()
                                      if uc.startswith(("I-", "CF-", "ST-", "RS-", "MP-")) and uc not in self.tested_use_cases
                                      and uc not in critical_use_cases]) * 2
            },
            {
                "phase": 6,
                "name": "Remaining Use Cases",
                "use_cases": [uc for uc in self.all_use_cases.keys()
                             if uc not in self.tested_use_cases
                             and uc not in [uc for phase in [1, 2, 3, 4, 5]
                                          for uc in self._get_phase_use_cases(phase)]],
                "description": "All remaining untested use cases",
                "estimated_tests": 0  # Will be calculated
            }
        ]

        # Calculate phase 6 tests
        phase_6_ucs = plan[5]["use_cases"]
        plan[5]["estimated_tests"] = len(phase_6_ucs) * 2

        total_tests = sum(phase["estimated_tests"] for phase in plan)
        print(f"✓ Generated {len(plan)} phases with ~{total_tests} estimated tests\n")

        return plan

    def _get_phase_use_cases(self, phase_num: int) -> List[str]:
        """Helper to get use cases for a given phase."""
        # This would need to be implemented based on the plan
        return []

    def generate_report(self) -> str:
        """Generate a comprehensive testing roadmap report."""
        print("=" * 80)
        print("STEP 5: Generating comprehensive report...")
        print("=" * 80)

        # Discover data
        self.discover_all_use_cases()
        self.discover_all_tests()
        untested, untested_by_epic = self.analyze_gaps()
        plan = self.generate_prioritized_plan()

        # Build report
        report_lines = [
            "# MONITOR System Testing Roadmap",
            "",
            f"**Generated:** {self._get_timestamp()}",
            "",
            "## Executive Summary",
            "",
            f"- **Total Use Cases:** {len(self.all_use_cases)}",
            f"- **Tested Use Cases:** {len(self.tested_use_cases)}",
            f"- **Untested Use Cases:** {len(untested)}",
            f"- **Current Coverage:** {(len(self.tested_use_cases) / len(self.all_use_cases) * 100):.1f}%",
            f"- **Target Coverage:** 85%",
            f"- **Gap:** {len(untested)} use cases to test",
            "",
            "## Epic Breakdown",
            "",
        ]

        # Sort epics by name
        for epic_name in sorted(self.epic_mapping.keys()):
            use_cases = self.epic_mapping[epic_name]
            tested = len([uc for uc in use_cases if uc in self.tested_use_cases])
            total = len(use_cases)
            pct = (tested / total * 100) if total > 0 else 0

            report_lines.append(f"### {epic_name}")
            report_lines.append(f"- Use Cases: {total}")
            report_lines.append(f"- Tested: {tested}")
            report_lines.append(f"- Coverage: {pct:.1f}%")

            if untested_by_epic.get(epic_name):
                report_lines.append(f"- Untested: {', '.join(untested_by_epic[epic_name])}")

            report_lines.append("")

        # Add prioritized plan
        report_lines.extend([
            "## Prioritized Testing Plan",
            "",
        ])

        for phase in plan:
            if not phase["use_cases"]:
                continue

            report_lines.append(f"### Phase {phase['phase']}: {phase['name']}")
            report_lines.append(f"**Description:** {phase['description']}")
            report_lines.append(f"**Use Cases ({len(phase['use_cases'])}):** {', '.join(phase['use_cases'])}")
            report_lines.append(f"**Estimated Tests:** ~{phase['estimated_tests']}")
            report_lines.append("")

        # Add tested use cases section
        report_lines.extend([
            "## Currently Tested Use Cases",
            "",
        ])

        for use_case_id in sorted(self.tested_use_cases):
            tests = self.use_case_to_tests.get(use_case_id, [])
            test_names = [Path(t).name for t in tests]
            report_lines.append(f"- **{use_case_id}**: {', '.join(test_names)}")

        report_lines.append("")

        # Add untested use cases section
        report_lines.extend([
            "## Untested Use Cases (by Epic)",
            "",
        ])

        for epic_name in sorted(untested_by_epic.keys()):
            if untested_by_epic[epic_name]:
                report_lines.append(f"### {epic_name}")
                for uc in sorted(untested_by_epic[epic_name]):
                    report_lines.append(f"- {uc}")
                report_lines.append("")

        # Add actionable next steps
        report_lines.extend([
            "## Actionable Next Steps",
            "",
            "### Immediate Actions (This Sprint)",
            "",
            "1. **Complete Phase 1 Testing**",
            f"   - Focus on: {', '.join(plan[0]['use_cases']) if plan[0]['use_cases'] else 'None (all complete!)'}",
            f"   - Estimated effort: {plan[0]['estimated_tests']} tests",
            "",
            "2. **Review Existing Test Coverage**",
            "   - Run: `uv run pytest packages/ --cov=packages/ --cov-report=term-missing`",
            "   - Identify modules with < 50% coverage",
            "   - Map modules to use cases",
            "",
            "3. **Create Test Templates**",
            "   - Use existing behavior tests as templates",
            "   - Follow naming convention: `test_<USE_CASE>_behavior.py`",
            "   - Include unit tests and integration tests",
            "",
            "### Medium-term Actions (Next 2-3 Sprints)",
            "",
            f"1. **Complete Phase 2 & 3**",
            f"   - Phase 2: {len(plan[1]['use_cases'])} use cases, ~{plan[1]['estimated_tests']} tests",
            f"   - Phase 3: {len(plan[2]['use_cases'])} use cases, ~{plan[2]['estimated_tests']} tests",
            "",
            "2. **Improve Coverage in Key Modules**",
            "   - Focus on agents package (SceneLoop, ContextAssembly, Narrator)",
            "   - Focus on data-layer MCP tools",
            "   - Aim for 85%+ coverage in core modules",
            "",
            "### Long-term Actions (Ongoing)",
            "",
            f"1. **Complete Phases 4-6**",
            f"   - Remaining: {len(untested) - len(plan[0]['use_cases']) - len(plan[1]['use_cases']) - len(plan[2]['use_cases'])} use cases",
            "",
            "2. **Maintain Test Coverage**",
            "   - Enforce test requirements in PR reviews",
            "   - Use CI gates to reject code without tests",
            "   - Update tests when use cases change",
            "",
            "## Coverage Analysis",
            "",
            "### Low-Coverage Modules",
            "",
            "To identify low-coverage modules, run:",
            "```bash",
            "uv run pytest packages/ --cov=packages/ --cov-report=term-missing --cov-report=html",
            "```",
            "",
            "Then focus on modules with < 50% coverage:",
            "",
            "- **packages/agents/**: Agent orchestration and LLM calls",
            "  - Test: SceneLoop, ContextAssembly, Narrator agents",
            "  - Use cases: P-1, P-2, P-3, P-4, P-5, P-6",
            "",
            "- **packages/data-layer/src/monitor_data/tools/**: MCP tools",
            "  - Test: All MCP tool functions",
            "  - Use cases: DL-1 through DL-26",
            "",
            "- **packages/cli/**: CLI commands",
            "  - Test: Command handlers and user interaction",
            "  - Use cases: SYS-1, SYS-2, SYS-3, M-1, M-2, P-1",
            "",
            "## Test Function Recommendations",
            "",
            "For each untested use case, create the following test functions:",
            "",
            "1. **Schema Validation Tests**",
            "   - Test that Pydantic schemas validate correctly",
            "   - Test required fields and optional fields",
            "   - Test invalid inputs",
            "",
            "2. **Function Existence Tests**",
            "   - Verify that MCP tools exist and are callable",
            "   - Verify that agent methods exist",
            "",
            "3. **Happy Path Tests**",
            "   - Test successful execution with valid inputs",
            "   - Verify expected outputs",
            "",
            "4. **Error Path Tests**",
            "   - Test error handling for invalid inputs",
            "   - Test error handling for missing dependencies",
            "",
            "5. **Integration Tests** (where applicable)",
            "   - Test end-to-end workflows",
            "   - Test cross-layer interactions",
            "",
            "## Example Test Template",
            "",
            "```python",
            '# tests/behavior/test_<USE_CASE>_behavior.py',
            '"""Behavior tests for <USE_CASE>: <Use Case Name>."""',
            '',
            'from __future__ import annotations',
            '',
            'import pytest',
            'from uuid import uuid4',
            'from unittest.mock import patch, MagicMock',
            '',
            '# Import relevant schemas and functions',
            '',
            '',
            'class Test<USE_CASE_ID>HappyPath:',
            '    """Scenario 1: Happy path tests."""',
            '',
            '    def test_<function_name>_exists(self):',
            '        """Test that the function exists."""',
            '        assert <function_name> is not None',
            '',
            '    def test_<operation>_success(self):',
            '        """Test successful <operation>."""',
            '        # Arrange',
            '        # Act',
            '        # Assert',
            '        pass',
            '',
            '',
            'class Test<USE_CASE_ID>ErrorPaths:',
            '    """Scenario 2: Error path tests."""',
            '',
            '    def test_<operation>_with_invalid_input(self):',
            '        """Test <operation> with invalid input."""',
            '        with pytest.raises(ValueError):',
            '            # Arrange & Act',
            '            pass',
            '```',
            "",
            "---",
            "",
            "*This report is auto-generated. Update as use cases and tests evolve.*",
        ])

        report = "\n".join(report_lines)

        # Save report
        report_file = self.workspace_root / "TESTING_ROADMAP.md"
        report_file.write_text(report)

        print(f"✓ Generated comprehensive report: {report_file}\n")

        return report

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    def print_summary(self):
        """Print a summary of the analysis."""
        print("\n" + "=" * 80)
        print("ANALYSIS COMPLETE - SUMMARY")
        print("=" * 80)
        print(f"Total Use Cases: {len(self.all_use_cases)}")
        print(f"Tested Use Cases: {len(self.tested_use_cases)}")
        print(f"Untested Use Cases: {len(self.all_use_cases) - len(self.tested_use_cases)}")
        print(f"Current Coverage: {(len(self.tested_use_cases) / len(self.all_use_cases) * 100):.1f}%")
        print(f"Target Coverage: 85%")
        print(f"\nReport saved to: TESTING_ROADMAP.md")
        print("=" * 80)


def main():
    """Main entry point."""
    workspace_root = os.getcwd()
    analyzer = UseCaseAnalyzer(workspace_root)
    analyzer.generate_report()
    analyzer.print_summary()


if __name__ == "__main__":
    main()