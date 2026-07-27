# =============================================================================
# MONITOR — Makefile
#
# Convenience targets for testing, linting, and running the project.
# All targets use `uv run` for Python and `npm` for frontend.
#
# Usage:
#   make test              # run all unit tests (hermetic, no services)
#   make test-unit         # same as above, explicit name
#   make test-fast         # unit tests, no coverage, fastest
#   make test-property     # hypothesis property-based tests
#   make test-contracts    # contract / invariant tests
#   make test-behavior     # agent loop choreography tests
#   make test-integration  # integration tests (auto-starts docker services)
#   make test-e2e          # end-to-end tests (testcontainers, needs docker daemon)
#   make test-mutation     # mutation tests via cosmic-ray (all 13 modules)
#   make test-mutation-one # mutation tests for one module: make test-mutation-one TARGET=resolver
#   make test-coverage     # unit tests with coverage report
#   make test-frontend     # vitest frontend component tests
#   make test-frontend-e2e # playwright frontend e2e tests
#   make test-all          # everything except integration/e2e/mutation (the fast suite)
#   make lint              # ruff check + layer dependency check
#   make format            # ruff format
#   make typecheck         # mypy strict type-check
#   make check             # lint + typecheck + unit tests (pre-push gate)
#   make dev               # start full dev stack (infra + backend + frontend)
#   make dev-stop          # stop the dev stack
#   make dev-status        # show what's running
#   make infra-up          # bring up only the docker infra (no backend/frontend)
#   make infra-down        # stop the docker infra
#   make infra-status      # show infra container status
#   make infra-restart     # restart infra containers (keeps volumes)
#   make infra-restart-volume # restart infra, WIPING volumes (use after password change)
#   make clean             # remove caches, coverage, .pyc files
# =============================================================================

.PHONY: test test-unit test-fast test-property test-contracts test-behavior \
        test-integration test-e2e test-mutation test-mutation-one \
        test-coverage test-frontend test-frontend-e2e test-all \
        lint format typecheck check \
        dev dev-stop dev-status \
        infra-up infra-down infra-status infra-restart infra-restart-volume \
        clean help

# ─── Variables ───────────────────────────────────────────────────────────────

PYTHON := uv run python
PYTEST := uv run pytest
RUFF   := uv run ruff
MYPY   := uv run mypy
NPM    := npm
FRONTEND_DIR := packages/ui/frontend

# Default mutation target (override with: make test-mutation-one TARGET=resolver)
TARGET :=

# ─── Test Targets ────────────────────────────────────────────────────────────

## Run all hermetic unit tests (no docker, no network, fake keys)
test: test-unit

test-unit:
	$(PYTEST) packages tests -q --tb=short

## Fastest unit test run — no coverage, no warnings, parallel
test-fast:
	$(PYTEST) packages tests -q --tb=line -p no:warnings

## Unit tests with branch coverage report
test-coverage:
	$(PYTEST) packages tests -q --tb=short \
		--cov=packages --cov-branch \
		--cov-report=term-missing

## Property-based tests (Hypothesis)
test-property:
	$(PYTEST) tests/property -q --tb=short

## Contract / invariant tests
test-contracts:
	$(PYTEST) tests/contracts -q --tb=short

## Behavior / choreography tests
test-behavior:
	$(PYTEST) tests/behavior -q --tb=short

## Integration tests — auto-starts docker services, runs, tears down
test-integration:
	./scripts/test_integration.sh

## End-to-end tests (testcontainers — needs docker daemon but no manual setup)
test-e2e:
	RUN_E2E=1 $(PYTEST) tests/e2e -q --tb=short

## Mutation tests — all 13 modules (slow, ~30+ min)
test-mutation:
	./scripts/run_mutations.sh

## Mutation tests — one module: make test-mutation-one TARGET=resolver
test-mutation-one:
	./scripts/run_mutations.sh $(TARGET)

## Frontend vitest unit/component tests
test-frontend:
	cd $(FRONTEND_DIR) && $(NPM) run test

## Frontend Playwright e2e tests (builds first, installs browsers if needed)
test-frontend-e2e:
	cd $(FRONTEND_DIR) && \
		npx playwright install --with-deps chromium 2>/dev/null || true && \
		npm run build && npx playwright test

## Run the full fast suite (unit + property + contract + behavior + frontend)
test-all: test-unit test-property test-contracts test-behavior test-frontend
	@echo "✓ All fast tests passed"

# ─── Quality Targets ─────────────────────────────────────────────────────────

## Lint: ruff check + layer dependency enforcement
lint:
	$(RUFF) check packages
	$(PYTHON) scripts/check_layer_dependencies.py

## Format code with ruff
format:
	$(RUFF) format packages

## Type-check with mypy (strict)
typecheck:
	$(MYPY) packages/*/src --cache-dir /tmp/mypy-cache

## Pre-push gate: lint + typecheck + unit tests
check: lint typecheck test-unit
	@echo "✓ Ready to push"

# ─── Dev Stack ────────────────────────────────────────────────────────────────

## Start the full dev stack (docker infra + backend + frontend)
dev:
	./dev.sh

## Stop the dev stack
dev-stop:
	./dev.sh stop

## Show dev stack status
dev-status:
	./dev.sh status

# ─── Infra-Only (no backend, no frontend) ─────────────────────────────────────
# Shared shell helpers (wait_for_port, compose_up, wait_ports, …) live in
# scripts/lib/compose_helpers.sh and are sourced by both `dev.sh` and these
# targets so there is a single source of truth for compose orchestration.

INFRA_SERVICES := neo4j mongodb qdrant minio postgres redis opensearch
INFRA_PORTS    := 7687:Neo4j 27017:MongoDB 5432:Postgres 6333:Qdrant 9000:MinIO 6379:Redis 9200:OpenSearch
COMPOSE_CMD    := docker compose --env-file .env -f infra/docker-compose.yml

## Bring up docker infra services and wait for their ports
infra-up:
	@bash -c 'source scripts/lib/compose_helpers.sh && compose_up "$(COMPOSE_CMD)" $(INFRA_SERVICES)'
	@bash -c 'source scripts/lib/compose_helpers.sh && wait_ports $(INFRA_PORTS)'

## Stop docker infra services (keeps volumes)
infra-down:
	@bash -c 'source scripts/lib/compose_helpers.sh && compose_stop "$(COMPOSE_CMD)" $(INFRA_SERVICES)'

## Show docker infra container status
infra-status:
	@bash -c 'source scripts/lib/compose_helpers.sh && compose_ps "$(COMPOSE_CMD)" $(INFRA_SERVICES)'

## Restart infra containers in place (keeps volumes)
infra-restart:
	$(COMPOSE_CMD) restart $(INFRA_SERVICES)

## Restart infra AND wipe volumes (use after changing NEO4J_PASSWORD)
infra-restart-volume:
	$(COMPOSE_CMD) down -v
	$(MAKE) infra-up

# ─── Misc ────────────────────────────────────────────────────────────────────

## Remove caches, coverage data, and generated files
clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml
	rm -rf packages/*/.pytest_cache packages/*/.mypy_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -f session-*.sqlite score-*.txt

## Show this help
help:
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*##"}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'