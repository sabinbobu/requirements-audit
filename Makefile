# Canonical commands. Run `make help` to list them.
.DEFAULT_GOAL := help
.PHONY: help install lock sync hooks lint format typecheck test test-fast eval check up down logs clean corpus ingest query audit benchmark

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Create the venv and install all groups (dev + eval)
	uv sync --all-groups

sync: ## Install runtime + dev deps from the lockfile
	uv sync

lock: ## Re-resolve and update uv.lock
	uv lock

hooks: ## Install pre-commit git hooks
	uv run pre-commit install

lint: ## Lint with ruff
	uv run ruff check .

format: ## Format with ruff
	uv run ruff format .

typecheck: ## Static type-check with mypy
	uv run mypy

test: ## Run the full test suite
	uv run pytest

test-fast: ## Run tests, skipping slow + eval markers
	uv run pytest -m "not slow and not eval"

eval: ## Run the evaluation gate
	uv run pytest -m eval

check: lint typecheck test ## Lint + typecheck + test (what CI runs)

up: ## Start qdrant + langfuse
	docker compose up -d

down: ## Stop the dev services
	docker compose down

logs: ## Tail dev service logs
	docker compose logs -f

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache dist build *.egg-info

corpus: ## Regenerate the synthetic corpus + ground-truth files (deterministic)
	uv run python -m requirements_audit.corpus

ingest: ## Build the index from a corpus (CORPUS=corpus/)
	uv run requirements-audit ingest $(or $(CORPUS),corpus/)

query: ## Ask a question (Q="...")
	uv run requirements-audit query "$(Q)"

audit: ## Sweep the corpus for contradictions
	uv run requirements-audit audit

benchmark: ## Run retrieval benchmarks (DB=..., OUT=, STRATEGIES="lexical dense hybrid", EMBEDDER=auto|hash|openai)
	uv run requirements-audit benchmark --db $(or $(DB),data/requirements.sqlite) $(if $(OUT),--output $(OUT),) $(foreach s,$(STRATEGIES),-s $(s)) $(if $(EMBEDDER),--embedder $(EMBEDDER),)
