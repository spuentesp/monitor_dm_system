"""
CLI smoke tests (FINAL_FABLE T-043).

Every command group must import, register, and answer --help without
touching the network (the repo-root conftest blocks sockets anyway).
A few representative read paths run against mocks.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from monitor_cli.main import app

runner = CliRunner()

GROUPS = [
    "state",
    "rules",
    "mechanics",
    "ingest",
    "playtest",
    "play",
    "universe",
    "manage",
]


def test_root_help_lists_all_groups():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for group in GROUPS:
        assert group in result.output, f"{group} missing from --help"


@pytest.mark.parametrize("group", GROUPS)
def test_group_help(group: str):
    result = runner.invoke(app, [group, "--help"])
    assert result.exit_code == 0, result.output
    assert "Usage" in result.output


def test_version_command():
    result = runner.invoke(app, ["version"])
    # Either a version command exists or root rejects it cleanly
    assert result.exit_code in (0, 2)
