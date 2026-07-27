# scripts/ index

> One-liner per script. Generated for FINAL_FABLE T-026; regenerate when adding scripts.

## Live E2E replay suite

These exercise the running MONITOR backend through real narration flows.
See `docs/testing/REPLAYS.md` for the full guide; the entry point is
`run_e2e_replays.py`.

| Script | Purpose |
|--------|---------|
| `run_e2e_replays.py` | **Entry point.** Runs the live-narration / GM-assistant replay suite (forge + copilot + long_form + subsystem + char_creation + session_observe) and writes a combined report. Use `--only` / `--skip` to subset. |
| `e2e_full_loop.py` | **In-process full-loop harness.** Real `CharacterCreationLoop` + `bootstrap_story_scene` + real `SceneLoop` driven by `InstructablePlayer`. Runs against real Mongo+Neo4j with `--mock-llm` for hermetic mode. See `docs/testing/HARNESS_FULL_LOOP.md`. |
| `forge_replay.py` | Hits every `/forge*` + bootstrap surface (10 endpoints) and reports pass/fail per surface. |
| `long_form_narration.py` | 22-turn non-deterministic arc: char creation → social → lore → combat → puzzle → boss → extraction → epilogue. |
| `subsystem_replay.py` | 14-turn LLM-as-player run tagged by subsystem (relationship, lore, faction, negotiation, npc_voice). |
| `character_creation_replay.py` | 10-step full character-creation arc (species/class/stats/background/equipment/lock-in). |
| `live_copilot_observe.py` | Pre-existing: exercises CF-2..CF-7 GM co-pilot surfaces. |
| `live_session_observe.py` | Pre-existing: heuristic scripted + llm_actor passes with latency reporting. |
| `live_gameplay_smoke.py` | Pre-existing: shorter scripted/LLM smoke against the chat router. |

| Script | Purpose |
|--------|---------|
| `analyze_use_case_coverage.py` |  |
| `auto_label_and_comment.sh` | Auto-apply labels and optional checklist comments to a PR using gh. |
| `block_todo.sh` | Fail if TODO or FIXME markers are present outside docs and license files. |
| `check_commit_use_case.py` |  |
| `check_env_drift.sh` | Compare expected env keys with GitHub Actions secrets/variables without printing values. |
| `check_issue_dependencies.py` |  |
| `check_layer_dependencies.py` |  |
| `check_ontology_use_cases.py` |  |
| `check_use_case_implementation.py` |  |
| `cleanup_project_duplicates.sh` | Find and remove duplicate items from the MONITOR GitHub Project. |
| `create_github_project.sh` | Create (or reuse) a GitHub Project v2 for this repository and seed it with |
| `demo_perception.py` |  |
| `diagnose_neo4j_performance.py` |  |
| `enforce_branch_name.py` |  |
| `extract_missing_categories.py` | # {uc_id}: {uc_title} |
| `extract_specs.py` | Returns a dict mapping ID -> Epic directory path. |
| `install-shared-server.sh` | One-liner installer for LAIN shared server setup |
| `lain-mcp-proxy.sh` | LAIN MCP Proxy - Bridges HTTP server to stdio for MCP clients |
| `lain-server-manager.sh` | LAIN MCP Server Manager - Ensures singleton HTTP server for all agents |
| `live_gameplay_smoke.py` | Run live MONITOR playtests against the running backend. |
| `map_dependencies.py` |  |
| `migrate_relationship_properties.py` |  |
| `monitor` |  |
| `push_env_to_github.sh` | Sync required MONITOR environment variables into GitHub Actions using the gh CLI. |
| `queue_for_copilot.py` |  |
| `reorganize_docs.py` |  |
| `require_tests_for_code_changes.py` |  |
| `require_use_case_reference.py` |  |
| `rerun_failed_workflow.sh` | Rerun the latest failed GitHub Actions workflow for a PR or branch. |
| `run_full_pipeline.py` | Run the full IngestionPipeline end-to-end and report results. |
| `scaffold_ymls.py` | # {uc_id}: {title} |
| `seed_game_systems.py` | Seed a minimal game system to MongoDB for character creation. |
| `seed_gm_profiles.py` |  |
| `seed_llm_providers.py` |  |
| `seed_minimax_provider.py` |  |
| `seed_tone_system.py` |  |
| `seed_world.py` |  |
| `seed_zai_providers.py` |  |
| `setup-lain-mcp.sh` | Setup script for LAIN MCP server with GitHub Copilot and Continue.dev |
| `setup_env.sh` | Setup environment variables for MONITOR |
| `split_neo4j.py` | \nAuto-extracted module.\n |
| `split_tests.py` |  |
| `standardize_epics.py` | Mapping of epic IDs to the standardized target folder names |
| `sync_docs_to_wiki.sh` | Sync local documentation into the GitHub wiki for this repository. |
| `sync_github_blockers.sh` | Sync dependency relationships to GitHub issues. |
| `sync_issues_to_project.sh` | Sync GitHub issues to Project v2. |
| `sync_project.py` |  |
| `sync_use_cases_to_issues.py` |  |
| `test_llm_connectivity.py` | Test LLM connectivity via LLMRegistry with GitHub Models (current default). |
| `test_pipeline.py` | Manual step-by-step ingestion pipeline test. |
| `update_yaml_status.py` |  |
| `validate_game_systems.py` |  |
| `weekly_health_report.sh` | Generate a lightweight repo health report using gh. |
