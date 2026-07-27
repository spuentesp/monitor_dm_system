#!/usr/bin/env bash
# =============================================================================
# MONITOR — Unified test runner script
#
# A convenience wrapper around pytest that provides subcommands for each
# test category.  Mirrors the Makefile targets for developers who prefer
# scripts over make.
#
# Usage:
#   ./scripts/test.sh                  # unit tests (default)
#   ./scripts/test.sh unit              # unit tests
#   ./scripts/test.sh fast             # unit tests, no coverage, fastest
#   ./scripts/test.sh property         # hypothesis property-based tests
#   ./scripts/test.sh contracts        # contract / invariant tests
#   ./scripts/test.sh behavior         # agent loop choreography tests
#   ./scripts/test.sh integration       # integration tests (auto-starts docker)
#   ./scripts/test.sh e2e              # end-to-end tests (testcontainers)
#   ./scripts/test.sh mutation         # mutation tests (all 13 modules)
#   ./scripts/test.sh mutation resolver # mutation tests for one module
#   ./scripts/test.sh coverage          # unit tests with coverage report
#   ./scripts/test.sh frontend          # vitest frontend component tests
#   ./scripts/test.sh frontend-e2e      # playwright frontend e2e tests
#   ./scripts/test.sh all              # full fast suite (no integration/e2e)
#   ./scripts/test.sh lint             # ruff + layer dependency check
#   ./scripts/test.sh typecheck        # mypy strict type-check
#   ./scripts/test.sh check            # lint + typecheck + unit tests (pre-push)
#   ./scripts/test.sh --list           # list available subcommands
#   ./scripts/test.sh --help           # show this help
#
# Environment variables:
#   RUN_INTEGRATION=1   enable integration tests (set automatically by 'integration')
#   RUN_E2E=1           enable e2e tests (set automatically by 'e2e')
#   MONITOR_LLM_TIMEOUT LLM request timeout in seconds (default 120)
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTEST="uv run pytest"
RUFF="uv run ruff"
PYTHON="uv run python"
MYPY="uv run mypy"
FRONTEND_DIR="packages/ui/frontend"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✔${NC}  $*"; }
info() { echo -e "${CYAN}→${NC}  $*"; }
warn() { echo -e "${YELLOW}!${NC}  $*"; }
err()  { echo -e "${RED}✘${NC}  $*" >&2; }

# ─── Subcommands ─────────────────────────────────────────────────────────────

cmd_unit() {
    info "Running unit tests (hermetic, no services needed)..."
    $PYTEST packages tests -q --tb=short
    ok "Unit tests passed"
}

cmd_fast() {
    info "Running fast unit tests (no coverage, no warnings)..."
    $PYTEST packages tests -q --tb=line -p no:warnings
    ok "Fast tests passed"
}

cmd_property() {
    info "Running property-based tests (Hypothesis)..."
    $PYTEST tests/property -q --tb=short
    ok "Property tests passed"
}

cmd_contracts() {
    info "Running contract / invariant tests..."
    $PYTEST tests/contracts -q --tb=short
    ok "Contract tests passed"
}

cmd_behavior() {
    info "Running behavior / choreography tests..."
    $PYTEST tests/behavior -q --tb=short
    ok "Behavior tests passed"
}

cmd_integration() {
    info "Running integration tests (auto-starts docker services)..."
    ./scripts/test_integration.sh
}

cmd_e2e() {
    info "Running end-to-end tests (testcontainers)..."
    RUN_E2E=1 $PYTEST tests/e2e -q --tb=short
    ok "E2E tests passed"
}

cmd_mutation() {
    local target="${1:-}"
    if [[ -n "$target" ]]; then
        info "Running mutation tests for module: $target..."
        ./scripts/run_mutations.sh "$target"
    else
        info "Running mutation tests for all modules..."
        ./scripts/run_mutations.sh
    fi
}

cmd_coverage() {
    info "Running unit tests with coverage..."
    $PYTEST packages tests -q --tb=short \
        --cov=packages --cov-branch \
        --cov-report=term-missing
    ok "Coverage report generated"
}

cmd_frontend() {
    info "Running frontend vitest tests..."
    cd "$FRONTEND_DIR"
    npm run test
    cd "$REPO_ROOT"
    ok "Frontend tests passed"
}

cmd_frontend_e2e() {
    info "Running frontend Playwright e2e tests..."
    cd "$FRONTEND_DIR"
    npx playwright install --with-deps chromium 2>/dev/null || true
    npm run build
    npx playwright test
    cd "$REPO_ROOT"
    ok "Frontend e2e tests passed"
}

cmd_all() {
    info "Running full fast suite (unit + property + contract + behavior + frontend)..."
    cmd_unit
    cmd_property
    cmd_contracts
    cmd_behavior
    cmd_frontend
    ok "All fast tests passed"
}

cmd_lint() {
    info "Running lint (ruff + layer dependency check)..."
    $RUFF check packages
    $PYTHON scripts/check_layer_dependencies.py
    ok "Lint passed"
}

cmd_typecheck() {
    info "Running type-check (mypy strict)..."
    $MYPY packages/*/src --cache-dir /tmp/mypy-cache
    ok "Type-check passed"
}

cmd_check() {
    info "Running pre-push gate (lint + typecheck + unit tests)..."
    cmd_lint
    cmd_typecheck
    cmd_unit
    ok "Ready to push"
}

# ─── Help / List ──────────────────────────────────────────────────────────────

cmd_list() {
    echo "Available subcommands:"
    echo "  unit            Unit tests (hermetic, no services)"
    echo "  fast            Unit tests, no coverage, fastest"
    echo "  property        Hypothesis property-based tests"
    echo "  contracts       Contract / invariant tests"
    echo "  behavior        Agent loop choreography tests"
    echo "  integration     Integration tests (auto-starts docker)"
    echo "  e2e             End-to-end tests (testcontainers)"
    echo "  mutation [mod]  Mutation tests (all or one module)"
    echo "  coverage        Unit tests with coverage report"
    echo "  frontend        Vitest frontend component tests"
    echo "  frontend-e2e    Playwright frontend e2e tests"
    echo "  all             Full fast suite (no integration/e2e)"
    echo "  lint            Ruff + layer dependency check"
    echo "  typecheck       Mypy strict type-check"
    echo "  check           Lint + typecheck + unit tests (pre-push)"
}

cmd_help() {
    cat << 'EOF'
MONITOR — Unified test runner

Usage: ./scripts/test.sh [subcommand] [args]

Subcommands:
  unit            Unit tests (hermetic, no services needed)
  fast            Unit tests, no coverage, no warnings — fastest
  property        Hypothesis property-based tests
  contracts       Contract / invariant tests
  behavior        Agent loop choreography tests
  integration     Integration tests — auto-starts docker services, tears down after
  e2e             End-to-end tests (testcontainers — needs docker daemon)
  mutation [mod]  Mutation tests via cosmic-ray (all 13 modules, or one by name)
  coverage        Unit tests with branch coverage report
  frontend        Vitest frontend component tests
  frontend-e2e    Playwright frontend e2e tests (builds first)
  all             Full fast suite: unit + property + contract + behavior + frontend
  lint            Ruff check + layer dependency enforcement
  typecheck       Mypy strict type-check
  check           Pre-push gate: lint + typecheck + unit tests

Environment:
  RUN_INTEGRATION=1   Enable integration tests (set automatically by 'integration')
  RUN_E2E=1           Enable e2e tests (set automatically by 'e2e')
  MONITOR_LLM_TIMEOUT LLM request timeout in seconds (default 120)

Examples:
  ./scripts/test.sh                      # run unit tests
  ./scripts/test.sh mutation resolver    # mutation test one module
  ./scripts/test.sh check                # pre-push gate
  ./scripts/test.sh all                  # full fast suite
EOF
}

# ─── Main ────────────────────────────────────────────────────────────────────

SUBCMD="${1:-unit}"
shift || true

case "$SUBCMD" in
    unit|test)         cmd_unit "$@" ;;
    fast)              cmd_fast "$@" ;;
    property)          cmd_property "$@" ;;
    contracts|contract) cmd_contracts "$@" ;;
    behavior)          cmd_behavior "$@" ;;
    integration|int)   cmd_integration "$@" ;;
    e2e)               cmd_e2e "$@" ;;
    mutation|mut)      cmd_mutation "$@" ;;
    coverage|cov)      cmd_coverage "$@" ;;
    frontend|fe)       cmd_frontend "$@" ;;
    frontend-e2e|fe-e2e) cmd_frontend_e2e "$@" ;;
    all)               cmd_all "$@" ;;
    lint)              cmd_lint "$@" ;;
    typecheck|mypy)    cmd_typecheck "$@" ;;
    check)             cmd_check "$@" ;;
    --list|list)       cmd_list ;;
    --help|help|-h)    cmd_help ;;
    *)
        err "Unknown subcommand: $SUBCMD"
        echo ""
        cmd_list
        exit 1
        ;;
esac