# Convenience targets. Tools (ruff, mypy, pytest, locust, alembic, uvicorn) are
# expected on PATH — activate the virtualenv first (see `make setup`) or prefix
# commands with your venv. On Windows use the documented PowerShell equivalents
# in the README (make is not required).

PYTHON ?= python
COMPOSE ?= docker compose
HOST ?= http://127.0.0.1:8000

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# --- Local environment ----------------------------------------------------
.PHONY: setup
setup: ## Create a venv and install the project with dev + load extras
	$(PYTHON) -m venv .venv
	./.venv/bin/pip install --upgrade pip
	./.venv/bin/pip install -e ".[dev,load]"

# --- Docker stack ---------------------------------------------------------
.PHONY: up
up: ## Build and start the full stack (API + Postgres + workers)
	$(COMPOSE) up --build -d

.PHONY: down
down: ## Stop the stack and remove volumes
	$(COMPOSE) down -v

.PHONY: logs
logs: ## Tail stack logs
	$(COMPOSE) logs -f

.PHONY: migrate
migrate: ## Run database migrations to head
	alembic upgrade head

.PHONY: seed
seed: ## Load fictional demonstration data
	$(PYTHON) -m scripts.seed

# --- Quality gates --------------------------------------------------------
.PHONY: lint
lint: ## Ruff lint
	ruff check .

.PHONY: format
format: ## Ruff format (write)
	ruff format .

.PHONY: format-check
format-check: ## Ruff format check (CI)
	ruff format --check .

.PHONY: typecheck
typecheck: ## mypy static type check
	mypy app

# --- Tests ----------------------------------------------------------------
.PHONY: test
test: ## Run the whole test suite
	pytest -q

.PHONY: test-unit
test-unit: ## Run unit tests only
	pytest -m unit -q

.PHONY: test-integration
test-integration: ## Run integration tests (needs PostgreSQL)
	pytest -m integration -q

.PHONY: test-api
test-api: ## Run API tests
	pytest -m api -q

.PHONY: test-concurrency
test-concurrency: ## Run concurrency tests (needs PostgreSQL)
	pytest -m concurrency -q

.PHONY: cov
cov: ## Run tests with coverage report
	pytest --cov=app --cov-report=term-missing

# --- App & demos ----------------------------------------------------------
.PHONY: run
run: ## Run the API locally (cross-platform event-loop runner)
	$(PYTHON) -m scripts.run_api

.PHONY: demo
demo: ## Run the end-to-end lifecycle demo against a running API
	$(PYTHON) -m scripts.demo

.PHONY: load-test
load-test: ## Run the Locust load test (headless, 30s)
	locust -f load_tests/locustfile.py --host $(HOST) --users 50 --spawn-rate 25 --run-time 30s --headless
