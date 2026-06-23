# MONITOR Testing Strategy

## Overview

Testing strategy organized into 8 layers, each providing a different type of confidence. Higher layers build upon lower ones.

```
┌─────────────────────────────────────────────────────────┐
│ Layer 8: Runtime Assertions (production invariants)     │
├─────────────────────────────────────────────────────────┤
│ Layer 7: Formal Specs (TLA+, safety/liveness)          │
├─────────────────────────────────────────────────────────┤
│ Layer 6: Deterministic Simulation (concurrency, faults) │
├─────────────────────────────────────────────────────────┤
│ Layer 5: Differential Tests (vs legacy/reference)       │
├─────────────────────────────────────────────────────────┤
│ Layer 4: Stateful/Model-Based (workflows, state)        │
├─────────────────────────────────────────────────────────┤
│ Layer 3: Property-Based (generative, edge cases)        │
├─────────────────────────────────────────────────────────┤
│ Layer 2: Contract Tests (API, schemas, invariants)      │
├─────────────────────────────────────────────────────────┤
│ Layer 1: Pure Unit Tests (helpers, validators)         │
└─────────────────────────────────────────────────────────┘
```

---

## Layer 1: Pure Unit Tests

**Purpose**: Test pure functions, helpers, validators, and simple rules in isolation.

**Characteristics**:
- No I/O, no external dependencies
- Deterministic, fast execution
- Test one thing per function

### Test Files

| File | Purpose | Coverage |
|------|---------|----------|
| `tests/test_chat_persistence_cache.py` | Cache eviction, TTL logic | Helpers |
| `tests/test_chat_router_ooc.py` | OOC message routing | Router helpers |
| `tests/test_ui_startup_recovery.py` | Startup state recovery | Error handlers |

### TODO Items

- [ ] Extract and test pure validation functions from schemas
- [ ] Test date/time helpers for timezone handling
- [ ] Test UUID generation helpers
- [ ] Test string sanitization functions

---

## Layer 2: Contract Tests

**Purpose**: Verify API boundaries, schema contracts, and invariant enforcement.

**Characteristics**:
- Test preconditions/postconditions
- Verify invariant preservation
- Cover all schema validation rules

### Test Files

| File | Tests | Coverage |
|------|-------|----------|
| `tests/contracts/test_definitions_contracts.py` | 13 | Universe, Entity contracts |
| `tests/contracts/test_fact_contracts.py` | 18 | Fact preconditions, CanonKeeper exclusivity |
| `tests/contracts/test_invariants.py` | 40 | All 6 system invariants |
| `tests/contracts/test_layer_direction.py` | 26 | Layer dependency enforcement |
| `tests/contracts/test_resolution_contracts.py` | 30 | Resolution pre/post/conditions |
| `tests/contracts/test_scene_contracts.py` | 28 | Scene status transitions |

**Total: 155 tests** (131 currently passing before property fix)

### Invariant Map

| Invariant | Description | Tests |
|-----------|-------------|-------|
| INV-1 | CanonKeeperExclusivity | Only CanonKeeper writes to Neo4j |
| INV-2 | SceneAtomicity | Scenes are atomic canon boundaries |
| INV-3 | LayerDirection | Dependencies flow CLI→Agents→DataLayer |
| INV-4 | TurnFlow | USER_INPUT→RESOLVE→NARRATE sequence |
| INV-5 | SceneStatusTransition | Valid scene status transitions |
| INV-6 | ProposedChangeWorkflow | PENDING→REVIEW→COMMIT workflow |

### TODO Items

- [ ] Add contract tests for all MCP tool preconditions
- [ ] Add contract tests for ProposedChange status transitions
- [ ] Add contract tests for TurnResponse invariants
- [ ] Add contract tests for FactResponse invariants

---

## Layer 3: Property-Based Tests

**Purpose**: Test invariants across randomly generated inputs, find edge cases.

**Characteristics**:
- Hypothesis-based generation
- Test thousands of inputs automatically
- Verify properties hold for all valid inputs

### Test Files

| File | Tests | Status |
|------|-------|--------|
| `tests/property/test_resolution_properties.py` | 16 | ✓ Fixed |

**All property tests now passing (16 tests)**

### What Was Fixed

- `st.text(min_length=...)` → `st.text(min_size=...)` (Hypothesis uses `min_size`)
- Invalid filter strategies that produced no valid examples
- Pydantic validation for whitespace-only strings

### TODO Items

- [ ] Add property tests for FactCreate preconditions
- [ ] Add property tests for SceneResponse validation
- [ ] Add property tests for turn sequence generation
- [ ] Add more edge case coverage for dice mechanics

---

## Layer 4: Stateful/Model-Based Tests

**Purpose**: Test workflows, state machines, and multi-step processes.

**Characteristics**:
- Test state transitions
- Verify workflow correctness
- Test authorization and permissions

### Test Files

| File | Tests | Coverage |
|------|-------|----------|
| `tests/test_pack_library_locking.py` | 3 | Pack clone/update locking |
| `tests/test_plot_threads.py` | 12 | Plot thread delta detection |
| `tests/test_proposal_review.py` | 12 | CanonKeeper review workflow |
| `tests/test_ingestion_edge_cases.py` | 15 | Pack deduplication, merging |
| `tests/test_ingest_router_locking.py` | 5 | Router locking mechanism |
| `tests/test_temporal_contradiction_gap.py` | 8 | Temporal validation |

**Total: ~55 tests** (many currently failing)

### Workflows Covered

| Workflow | Status | Notes |
|----------|--------|-------|
| Pack Ingestion | Partial | Fails on deduplication logic |
| CanonKeeper Review | Partial | Review pending status issues |
| Plot Thread Delta | Partial | Delta detection works, dedup fails |
| Temporal Contradiction | Works | Detects gaps correctly |

### TODO Items

- [ ] Fix `test_proposal_review.py` failures
- [ ] Fix `test_pack_library_locking.py` failures
- [ ] Fix `test_plot_threads.py` failures
- [ ] Add state machine tests for SceneStatus transitions

---

## Layer 5: Differential Tests

**Purpose**: Compare against reference implementations or known good outputs.

**Characteristics**:
- Compare new implementation vs legacy
- Use reference libraries as golden
- Test deterministic outputs

### Status

Not yet implemented.

### TODO Items

- [ ] Create differential tests for dice roll calculations
- [ ] Compare turn sequence generation vs reference
- [ ] Compare fact canonization vs expected outputs

---

## Layer 6: Deterministic Simulation

**Purpose**: Test concurrency, networking, storage, and fault tolerance.

**Characteristics**:
- Simulate failures
- Test retry logic
- Verify eventual consistency

### Status

Not yet implemented.

### TODO Items

- [ ] Add concurrent Neo4j write simulation tests
- [ ] Add MongoDB replica故障 simulation
- [ ] Add retry/backoff logic tests
- [ ] Add message queue ordering tests

---

## Layer 7: Formal Specifications

**Purpose**: Verify critical protocols, safety properties, and impossible states.

**Characteristics**:
- TLA+ specifications
- Safety/liveness proofs
- Protocol correctness

### TLA+ Specs

| File | Description | Status |
|------|-------------|--------|
| `specs/canon_keeper.tla` | CanonKeeper write authority | ✓ Created |
| `specs/layer_direction.tla` | Layer dependency rules | ✓ Created |
| `specs/proposed_change_workflow.tla` | Change workflow states | ✓ Created |
| `specs/scene_atomicity.tla` | Scene atomicity rules | ✓ Created |
| `specs/turn_flow.tla` | Turn phase ordering | ✓ Created |

### TODO Items

- [ ] Add model checking tests that validate TLA+ specs
- [ ] Add impossible state detection tests
- [ ] Add safety property verification tests

---

## Layer 8: Runtime Assertions

**Purpose**: Active invariants in production that catch violations early.

**Characteristics**:
- Always-on checks in production
- Fail-fast on invariant violations
- Provide actionable errors

### Status

Partial - invariants defined but not enforced at runtime.

### TODO Items

- [ ] Add runtime invariant checks in MCP tool handlers
- [ ] Add assert_layer_direction() calls in import paths
- [ ] Add CanonKeeper authority checks at Neo4j write points
- [ ] Add scene atomicity checks before scene completion

---

## Execution Commands

```bash
# Layer 1: Unit tests
uv run pytest tests/test_chat_persistence_cache.py tests/test_chat_router_ooc.py -v

# Layer 2: Contract tests (131 passing)
uv run pytest tests/contracts/ -v

# Layer 3: Property-based (needs fixing)
uv run pytest tests/property/ -v

# Layer 4: Stateful tests (39 failing)
uv run pytest tests/test_proposal_review.py tests/test_pack_library_locking.py -v

# Full deterministic suite (excludes broken property tests)
uv run pytest tests/ --ignore=tests/property/test_resolution_properties.py -v

# Full suite including known-broken tests
uv run pytest tests/ -v
```

---

## Testing Philosophy

> "If all tests pass, the application works as expected."

This means:
1. **Complete coverage**: Every feature has tests
2. **Deterministic**: Same input → Same output, every time
3. **Isolated**: Tests don't depend on each other
4. **Fast**: Full suite runs in < 5 minutes
5. **Verifiable**: Tests prove correctness, not just presence

---

## Test Quality Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Contract tests | 200+ | 131 |
| Property-based tests | 100+ | 16 ✓ Fixed |
| Stateful tests | 100+ | ~55 |
| Execution time | < 5 min | ~4 min |
| Deterministic | 100% | 98% |

### Summary

- **147 contract + property tests passing** (up from 131)
- **308 total tests passing** (up from 292)
- Property tests fixed and passing after syntax corrections

---

## Priority Order for Fixing

1. **Layer 2 contracts** (131 passing) - Keep passing, add coverage
2. **Layer 3 property** (broken) - Fix syntax errors, expand coverage
3. **Layer 4 stateful** (39 failing) - Fix failing tests
4. **Layers 5-8** (not implemented) - Design and add