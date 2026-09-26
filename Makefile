.DEFAULT_GOAL := help
.PHONY: help install test lint format typecheck verify api migrate migrate-down revision \
        frontend-install frontend-build frontend-test audit docker-build \
        print-nova-fetch-env print-nova-host-env configure-nova-smtp \
        smoke-nova-smtp smoke-nova-resend

# Prefer the project venv when it exists, so `make test` works without activating it.
PYTHON ?= $(shell test -x .venv/bin/python && echo .venv/bin/python || echo python3)
ENV_FILE ?= .env

help: ## Show the available targets
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-22s\033[0m %s\n", $$1, $$2}'

## --- development ---------------------------------------------------------- #

install: ## Install the backend with test dependencies
	$(PYTHON) -m pip install -e '.[dev]'

test: ## Run the Python test suite
	$(PYTHON) -m pytest

lint: ## Lint the Python sources
	$(PYTHON) -m ruff check .

format: ## Apply the formatter (not enforced in CI yet)
	$(PYTHON) -m ruff format .

typecheck: ## Type-check the Python sources
	$(PYTHON) -m mypy services/api/app

verify: lint typecheck test audit frontend-test ## Everything CI runs

api: ## Run the API with reload (http://localhost:8000)
	$(PYTHON) -m uvicorn app.main:app --app-dir services/api --reload

audit: ## Fail if Nova imports the SalesOS platform
	$(PYTHON) scripts/audit-coupling.py

## --- database ------------------------------------------------------------- #

migrate: ## Apply all migrations to NOVA_DATABASE_URL
	$(PYTHON) -m alembic -c alembic.ini upgrade head

migrate-down: ## Roll back the most recent migration
	$(PYTHON) -m alembic -c alembic.ini downgrade -1

revision: ## Create a revision from model changes (make revision m="add x")
	$(PYTHON) -m alembic -c alembic.ini revision --autogenerate -m "$(m)"

## --- frontend ------------------------------------------------------------- #

frontend-install: ## Install console dependencies from the lockfile
	npm --prefix apps/nova ci

frontend-build: ## Build the console into apps/nova/dist
	npm --prefix apps/nova run build

frontend-test: ## Static guardrails for the console
	npm --prefix apps/nova run test:static

## --- container ------------------------------------------------------------ #

docker-build: ## Build the single-container image (API + console)
	docker build -t nova-prospecting:local .

## --- deployment helpers --------------------------------------------------- #

print-nova-fetch-env: ## Print the fetch-only host environment block
	bash scripts/deploy/print-nova-fetch-env.sh

print-nova-host-env: ## Print the full prospecting host environment block
	bash scripts/deploy/print-nova-host-env.sh

configure-nova-smtp: ## Write SMTP mailbox secrets into ENV_FILE (interactive)
	$(PYTHON) scripts/deploy/configure-nova-smtp.py --env-file $(ENV_FILE)

smoke-nova-smtp: ## Verify SMTP mailbox logins (add ARGS="--send-test-to you@example")
	$(PYTHON) scripts/deploy/smoke-nova-smtp.py $(ARGS)

smoke-nova-resend: ## Verify the Resend configuration
	$(PYTHON) scripts/deploy/smoke-nova-resend.py $(ARGS)
