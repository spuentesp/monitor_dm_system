# Phase 1 brief: stabilize master

> Read [README.md](README.md) first; its "Brief every agent gets" section applies here.

**Goal.** `origin/master` is green on every check including the real-stack job, cannot be
pushed to directly, and contains the three stranded fixes. Every later phase branches from the
result.

**Context.** Four of the last six pushes to master failed or were cancelled. The Weekly
Integration workflow fails in 17 seconds on `minio Error unauthorized` while pulling
`quay.io/minio/minio:latest`. Auth hardening exists only on one disk.

**Needs a person.** Tasks 1, 6 and 7 change shared state. Prepare them and ask before acting:
pushing a branch, changing branch protection, deleting branches, closing a PR.

## Tasks

1. **Auth hardening.** In the worktree `~/orca/workspaces/monitor_dm_system/rp_loops_overhaul`,
   branch `Sebastian/rp_loops_overhaul` holds commit `6632a00` unpushed plus 22 modified files
   uncommitted. Read the diff, run the checks, commit with a use case id, push, open a PR. Do
   not rewrite the work.
2. **Integration workflow.** In `.github/workflows/nightly-integration.yml` and
   `infra/docker-compose.yml`, make the stack start on a GitHub runner. Pin MinIO to a tag on a
   registry the runner can pull, or set `STORAGE_BACKEND=folder` for the integration job.
   Confirm a full run passes.
3. **PR #136** (`feat/loops-followup`, 4 commits, 76 behind). Rebase on master, resolve
   conflicts in the loop files, keep `test_story_arc_contract.py` passing, merge. This makes a
   story able to end and resume from its checkpoint.
4. **PR #135** (`fix/remove-bolted-ontology-and-backtrack-db`, 3 commits, 76 behind). Rebase,
   fix the failing `typecheck`, merge. This makes `/backtrack` undo a turn's writes.
5. **Agenda tick.** `packages/agents/src/monitor_agents/loops/story_loop.py` near line 480
   calls `self.call_tool("neo4j_tick_agendas", ...)`. `StoryLoop` has no `call_tool`. Replace
   it with a real tool call through the same client the rest of the file uses, and add a test
   that fails if the tool is not invoked.
6. **Branch hygiene.** List, then delete after confirmation: the 11 local `fix/*` branches
   whose upstream is gone, `local/lite-live`, `local/rpg-live`, and remote
   `fix/remove-death-in-space-and-ontology-content` once #135 is in. Close PR #117. Keep
   `backup/pre-quote-removal-99fb8d1` local and never push it.
7. **Protection.** Require the `CI` checks and the integration job on master, and disallow
   direct pushes.
8. **Route coverage test.** Add a test that walks every route registered in
   `packages/ui/backend/src/monitor_ui/main.py` and fails when a route has neither an auth
   dependency nor an entry in an explicit public allowlist.
9. **Docs.** Update `docs/STATUS.md` (header date, renumber the gap list, mark what merged)
   and the status line of `docs/architecture/MULTI_TENANCY_PLAN.md`, which still says not
   implemented.

## Out of scope

`Sebastian/gm_assist_overhaul`: it merged on 2026-11-10 as PR #137.

## Status, 2026-11-10

Task 1 merged as PR #138. Tasks 2, 3, 4, 5, 8 and 9, with Phase 0, are in PR #139. Tasks 6
and 7 follow its merge.

## Done when

Master is green including integration; #135, #136 and the hardening PR are merged; the agenda
test and route-coverage test exist and pass; `git branch -vv` shows no branch marked gone.
