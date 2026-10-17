"""Meta-tests for scripts/mutation_diff.py (T_val — visible suite).

Extraction is tested against a real cosmic_ray.WorkDB built in a tmp dir and
against synthetic unified-diff text; no Cosmic Ray run happens in these tests.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "mutation_diff.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("mutation_diff", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Register before exec_module: dataclasses resolves string annotations via
    # sys.modules[cls.__module__], which is None for unregistered dynamic modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


md = _load_mod()


def test_parse_hunk_ranges_zero_context_diff() -> None:
    diff = (
        "diff --git a/packages/agents/src/monitor_agents/narrator/agent.py "
        "b/packages/agents/src/monitor_agents/narrator/agent.py\n"
        "--- a/packages/agents/src/monitor_agents/narrator/agent.py\n"
        "+++ b/packages/agents/src/monitor_agents/narrator/agent.py\n"
        "@@ -10,0 +11,2 @@\n"
        "+added_line_11\n"
        "+added_line_12\n"
        "@@ -40 +42 @@\n"
        "-old\n"
        "+new_line_42\n"
    )
    ranges = md.parse_hunk_ranges(diff)
    assert ranges["packages/agents/src/monitor_agents/narrator/agent.py"] == {11, 12, 42}


def test_parse_hunk_ranges_empty_new_side() -> None:
    diff = (
        "--- a/packages/agents/src/x.py\n"
        "+++ b/packages/agents/src/x.py\n"
        "@@ -5,2 +4,0 @@\n"
        "-deleted_a\n"
        "-deleted_b\n"
    )
    assert md.parse_hunk_ranges(diff) == {"packages/agents/src/x.py": set()}


def test_extract_survivors_reads_workdb(tmp_path: Path) -> None:
    from cosmic_ray.work_db import WorkDB
    from cosmic_ray.work_item import (
        MutationSpec,
        TestOutcome,
        WorkerOutcome,
        WorkItem,
        WorkResult,
    )

    db_path = tmp_path / "session.sqlite3"
    db = WorkDB(db_path, WorkDB.Mode.create)
    try:
        survivor_spec = MutationSpec(
            module_path=Path("packages/agents/src/monitor_agents/narrator/agent.py"),
            operator_name="core/Number",
            occurrence=0,
            start_pos=(11, 4),
            end_pos=(11, 8),
            definition_name="render_draft",
        )
        killed_spec = MutationSpec(
            module_path=Path("packages/agents/src/monitor_agents/narrator/agent.py"),
            operator_name="core/String",
            occurrence=1,
            start_pos=(42, 4),
            end_pos=(42, 9),
            definition_name="render_draft",
        )
        db.add_work_item(WorkItem.single("job-survivor", survivor_spec))
        db.add_work_item(WorkItem.single("job-killed", killed_spec))
        db.set_result(
            "job-survivor",
            WorkResult(worker_outcome=WorkerOutcome.NORMAL, test_outcome=TestOutcome.SURVIVED),
        )
        db.set_result(
            "job-killed",
            WorkResult(worker_outcome=WorkerOutcome.NORMAL, test_outcome=TestOutcome.KILLED),
        )
    finally:
        db.close()

    survivors = md.extract_survivors(db_path)
    assert len(survivors) == 1
    only = survivors[0]
    assert only.module_path == "packages/agents/src/monitor_agents/narrator/agent.py"
    assert only.operator_name == "core/Number"
    assert only.occurrence == 0
    assert only.line == 11
    assert only.definition_name == "render_draft"


def test_extract_survivors_ignores_incompetent_and_pending(tmp_path: Path) -> None:
    from cosmic_ray.work_db import WorkDB
    from cosmic_ray.work_item import (
        MutationSpec,
        TestOutcome,
        WorkerOutcome,
        WorkItem,
        WorkResult,
    )

    db_path = tmp_path / "session.sqlite3"
    db = WorkDB(db_path, WorkDB.Mode.create)
    try:
        spec = MutationSpec(
            module_path=Path("packages/data-layer/src/monitor_data/db/neo4j.py"),
            operator_name="core/Deletion",
            occurrence=3,
            start_pos=(7, 0),
            end_pos=(7, 10),
        )
        db.add_work_item(WorkItem.single("job-incompetent", spec))
        db.add_work_item(
            WorkItem.single(
                "job-pending",
                MutationSpec(
                    module_path=Path("packages/data-layer/src/monitor_data/db/neo4j.py"),
                    operator_name="core/Deletion",
                    occurrence=4,
                    start_pos=(9, 0),
                    end_pos=(9, 10),
                ),
            )
        )
        db.set_result(
            "job-incompetent",
            WorkResult(worker_outcome=WorkerOutcome.NORMAL, test_outcome=TestOutcome.INCOMPETENT),
        )
    finally:
        db.close()

    assert md.extract_survivors(db_path) == []


def test_filter_in_diff_splits_by_hunk_lines() -> None:
    inside = md.Survivor("packages/agents/src/monitor_agents/narrator/agent.py", "core/Number", 0, 11, "f")
    outside = md.Survivor("packages/agents/src/monitor_agents/narrator/agent.py", "core/String", 1, 90, "f")
    hunks = {"packages/agents/src/monitor_agents/narrator/agent.py": {11, 12}}
    in_diff, out = md.filter_in_diff([inside, outside], hunks)
    assert in_diff == [inside]
    assert out == [outside]


def test_out_of_diff_survivor_only_warns(tmp_path: Path) -> None:
    survivor = md.Survivor("packages/agents/src/x.py", "core/Number", 0, 99, "f")
    hunks = {"packages/agents/src/x.py": {10}}
    in_diff, outside = md.filter_in_diff([survivor], hunks)
    assert in_diff == []
    assert outside == [survivor]
    # With no in-diff survivors, the gate is green regardless of pre-existing debt.
    assert md.evaluate_gate(in_diff, outside, allowlist={}) == 0


def test_gate_fails_on_unallowlisted_in_diff_survivor() -> None:
    survivor = md.Survivor("packages/agents/src/x.py", "core/Number", 0, 10, "f")
    assert md.evaluate_gate([survivor], [], allowlist={}) == 1


def test_gate_allowlist_entry_passes() -> None:
    survivor = md.Survivor("packages/agents/src/x.py", "core/Number", 0, 10, "f")
    key = ("packages/agents/src/x.py", "core/Number", 0, 10)
    assert md.evaluate_gate([survivor], [], allowlist={key: "equivalent mutant: flip has no effect"}) == 0


def test_load_allowlist_roundtrip(tmp_path: Path) -> None:
    allow = tmp_path / "allow.toml"
    allow.write_text(
        '[[survivors]]\n'
        'module_path = "packages/agents/src/x.py"\n'
        'operator_name = "core/Number"\n'
        'occurrence = 0\n'
        'line = 12\n'
        'justification = "equivalent mutant: constant is unused"\n'
    )
    loaded = md.load_allowlist(allow)
    assert loaded == {("packages/agents/src/x.py", "core/Number", 0, 12): "equivalent mutant: constant is unused"}


def test_allowlist_entry_without_justification_is_error(tmp_path: Path) -> None:
    allow = tmp_path / "allow.toml"
    allow.write_text(
        '[[survivors]]\n'
        'module_path = "packages/agents/src/x.py"\n'
        'operator_name = "core/Number"\n'
        'occurrence = 0\n'
        'line = 12\n'
    )
    with pytest.raises(md.AllowlistError, match="justification"):
        md.load_allowlist(allow)


def test_changed_production_files_excludes_deletions(tmp_path: Path) -> None:
    """Deleting dead code must not send the gate hunting for mutants in a
    file that no longer exists (cosmic-ray init aborts on missing modules)."""
    import subprocess as sp

    repo = tmp_path / "repo"
    (repo / "packages" / "pkg" / "src").mkdir(parents=True)
    mod = repo / "packages" / "pkg" / "src" / "gone.py"
    mod.write_text("x = 1\n")
    for cmd in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "t@t"],
        ["git", "config", "user.name", "t"],
    ):
        sp.run(cmd, cwd=repo, check=True, capture_output=True)
    sp.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    sp.run(["git", "commit", "-qm", "seed"], cwd=repo, check=True, capture_output=True)
    sp.run(["git", "rm", "-q", "packages/pkg/src/gone.py"], cwd=repo, check=True, capture_output=True)
    sp.run(["git", "commit", "-qm", "delete"], cwd=repo, check=True, capture_output=True)

    changed = md.changed_production_files("HEAD~1", repo)
    assert changed == [], f"deleted modules must be excluded, got {changed}"


def test_no_production_changes_short_circuits(monkeypatch) -> None:
    """Review Focus pin: docs-only / empty diffs exit 0 without ever invoking
    Cosmic Ray (zero mutation minutes)."""
    calls = []
    monkeypatch.setattr(md, "changed_production_files", lambda base, root: [])
    monkeypatch.setattr(md, "run_session", lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError("run_session must not be called")))
    code = md.main(["--base", "HEAD"])
    assert code == 0
    assert calls == []


def test_load_allowlist_missing_file_is_config_error(tmp_path: Path) -> None:
    with pytest.raises(md.AllowlistError, match="allowlist"):
        md.load_allowlist(tmp_path / "nope.toml")


def test_load_allowlist_bad_toml_is_config_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.toml"
    bad.write_text("survivors = [unclosed\n")
    with pytest.raises(md.AllowlistError, match="allowlist"):
        md.load_allowlist(bad)


def test_load_allowlist_non_string_justification_is_rejected(tmp_path: Path) -> None:
    allow = tmp_path / "allow.toml"
    allow.write_text(
        '[[survivors]]\n'
        'module_path = "m.py"\n'
        'operator_name = "core/Number"\n'
        'occurrence = 0\n'
        'line = 3\n'
        'justification = 5\n'
    )
    with pytest.raises(md.AllowlistError, match="justification"):
        md.load_allowlist(allow)


def test_run_session_budget_exceeded_raises_actionable_error(tmp_path: Path, monkeypatch) -> None:
    """A hung cosmic-ray run must surface as a budget error (exit 2 upstream),
    never a false survivor verdict or an unbounded hang."""
    import subprocess as sp

    config = tmp_path / "cfg.toml"
    config.write_text('[cosmic-ray]\nmodule-path = "m.py"\ntest-command = "true"\n')

    def fake_run(*args, **kwargs):
        raise sp.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 3))

    monkeypatch.setattr(md, "_run_process_group", fake_run)
    with pytest.raises(RuntimeError, match="mutation budget exceeded"):
        md.run_session(config, tmp_path)


def test_write_generated_config_names_are_unique_per_module(tmp_path: Path) -> None:
    root = tmp_path
    a = tmp_path / "packages" / "one" / "agent.py"
    b = tmp_path / "packages" / "two" / "agent.py"
    a.parent.mkdir(parents=True)
    b.parent.mkdir(parents=True)
    a.write_text("x = 1\n")
    b.write_text("y = 2\n")
    (tmp_path / "packages" / "one" / "pyproject.toml").write_text("[project]\nname='one'\n")
    (tmp_path / "packages" / "two" / "pyproject.toml").write_text("[project]\nname='two'\n")
    cfg_a = md.write_generated_config(Path("packages/one/agent.py"), root, tmp_path)
    cfg_b = md.write_generated_config(Path("packages/two/agent.py"), root, tmp_path)
    assert cfg_a != cfg_b, "modules sharing a basename must get distinct generated configs"


def test_run_session_writes_session_outside_config_dir(tmp_path: Path) -> None:
    import subprocess as sp

    config = tmp_path / "cosmic-ray-x.toml"
    config.write_text('[cosmic-ray]\nmodule-path = "m.py"\ntest-command = "true"\n')
    import unittest.mock as um

    def fake_run(cmd, *args, **kwargs):
        return sp.CompletedProcess(cmd, 0, "", "")

    with um.patch.object(md, "_run_process_group", side_effect=fake_run):
        db = md.run_session(config, tmp_path, session_dir=tmp_path / "sessions")
    assert db.parent == tmp_path / "sessions"
    assert db.name.endswith(".session.sqlite3")


def test_extract_survivors_rejects_anomalous_worker_outcomes(tmp_path: Path) -> None:
    """I1 pin: a session where tests never ran (worker exception / no-test /
    skipped) must be a config error (exit 2), never a silent zero-survivor pass."""
    from cosmic_ray.work_db import WorkDB
    from cosmic_ray.work_item import (
        MutationSpec,
        WorkerOutcome,
        WorkItem,
        WorkResult,
    )

    db_path = tmp_path / "session.sqlite3"
    db = WorkDB(db_path, WorkDB.Mode.create)
    try:
        spec = MutationSpec(
            module_path=Path("m.py"),
            operator_name="core/Number",
            occurrence=0,
            start_pos=(3, 0),
            end_pos=(3, 5),
        )
        db.add_work_item(WorkItem.single("job-exception", spec))
        db.set_result(
            "job-exception",
            WorkResult(worker_outcome=WorkerOutcome.EXCEPTION, output="boom"),
        )
    finally:
        db.close()
    with pytest.raises(RuntimeError, match="did not run cleanly"):
        md.extract_survivors(db_path)


def test_run_session_requires_green_baseline(tmp_path: Path, monkeypatch) -> None:
    """I1 pin: the unmutated test-command must pass before any mutant runs —
    a broken test-command must never mark every mutant 'killed'."""
    config = tmp_path / "cfg.toml"
    config.write_text(
        '[cosmic-ray]\nmodule-path = "m.py"\ntest-command = "false"\n'
    )
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        # The baseline runs the shell test-command ("false" -> rc 1); the
        # cosmic-ray subcommands are lists and would otherwise "succeed".
        rc = 1 if isinstance(cmd, str) else 0
        return type("P", (), {"returncode": rc, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(md, "_run_process_group", fake_run)
    with pytest.raises(RuntimeError, match="baseline"):
        md.run_session(config, tmp_path)
    assert not any("exec" in c for c in calls), "exec must not run when the baseline is red"


def test_allowlist_entries_are_line_anchored(tmp_path: Path) -> None:
    """I5 pin: an allowlist entry only covers the mutant at its recorded line —
    occurrence renumbering must not whitelist an unrelated survivor."""
    allow = tmp_path / "allow.toml"
    allow.write_text(
        '[[survivors]]\n'
        'module_path = "m.py"\n'
        'operator_name = "core/Number"\n'
        'occurrence = 0\n'
        'line = 10\n'
        'justification = "equivalent mutant: constant unused"\n'
    )
    loaded = md.load_allowlist(allow)
    anchored = md.Survivor("m.py", "core/Number", 0, 10, "f")
    drifted = md.Survivor("m.py", "core/Number", 0, 42, "f")
    assert md.evaluate_gate([anchored], [], allowlist=loaded) == 0
    assert md.evaluate_gate([drifted], [], allowlist=loaded) == 1


def test_allowlist_is_validated_before_mutation_runs(monkeypatch, tmp_path: Path) -> None:
    """Minor pin: a malformed allowlist must fail fast (exit 2), before any
    expensive mutation session runs."""
    monkeypatch.setattr(md, "changed_production_files", lambda base, root: [Path("packages/x.py")])
    monkeypatch.setattr(md, "git_diff_u0", lambda *a, **k: "")
    monkeypatch.setattr(md, "parse_hunk_ranges", lambda *a, **k: {})
    monkeypatch.setattr(
        md, "run_session",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no mutation run before allowlist validation")),
    )
    monkeypatch.setattr(md, "load_known_configs", lambda root: {})
    monkeypatch.setattr(md, "write_generated_config", lambda *a, **k: Path("x.toml"))
    bad = tmp_path / "bad_allow.toml"
    bad.write_text("survivors = [unclosed\n")
    code = md.main(["--base", "HEAD", "--allowlist", str(bad)])
    assert code == 2


def test_group_kill_reaps_grandchildren(tmp_path: Path) -> None:
    """A budget timeout must kill the whole process group: killing only the
    'uv run' wrapper leaks cosmic-ray/pytest grandchildren on the runner."""
    import os
    import subprocess
    import time

    pidfile = tmp_path / "grandchild.pid"
    cmd = f"sleep 30 & echo $! > {pidfile}; wait"
    with pytest.raises(subprocess.TimeoutExpired):
        md._run_process_group(cmd, tmp_path, timeout=1, shell=True)
    assert pidfile.exists(), "grandchild must have started"
    pid = int(pidfile.read_text().strip())
    deadline = time.time() + 5
    alive = True
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError):
            alive = False
            break
        stat = Path(f"/proc/{pid}/stat")
        if stat.exists() and stat.read_text().split()[2] == "Z":
            alive = False
            break
        time.sleep(0.1)
    assert not alive, f"grandchild {pid} survived the group kill (would leak on CI runners)"
