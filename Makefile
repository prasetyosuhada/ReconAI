.PHONY: help setup db-up db-down db-clean db-reset migrate seed demo-data dev-backend dev-frontend test lint format build ci clean

# Default target
.DEFAULT_GOAL := help

## -----------------------------------------------------------------------------
## 🚀 ReconAI Management Commands
## -----------------------------------------------------------------------------

help: ## Show this help message
	@echo "ReconAI Development & Automation Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: ## Install dependencies for both backend (uv) and frontend (npm)
	@echo "--> Setting up environment..."
	@if [ ! -f .env ]; then cp .env.example .env && echo "Created .env from .env.example"; fi
	@echo "--> Installing backend dependencies..."
	cd backend && uv sync --all-groups
	@echo "--> Installing frontend dependencies..."
	cd frontend && npm install
	@echo "--> Setup complete!"

db-up: ## Start PostgreSQL database via Docker Compose
	@echo "--> Starting PostgreSQL database..."
	docker compose up -d

db-down: ## Stop PostgreSQL database container
	@echo "--> Stopping PostgreSQL database..."
	docker compose down

db-clean: ## Stop PostgreSQL container and wipe all database data (volumes)
	@echo "--> Removing PostgreSQL database and volume data..."
	docker compose down -v

db-reset: ## Reset database completely (wipe, recreate, migrate, seed)
	@$(MAKE) db-clean
	@$(MAKE) db-up
	@$(MAKE) migrate
	@$(MAKE) seed
	@echo "--> Database reset complete!"

migrate: ## Run Alembic database migrations
	@echo "--> Running Alembic migrations..."
	cd backend && uv run alembic upgrade head

seed: ## Seed initial Chart of Accounts (COA) data
	@echo "--> Seeding COA data..."
	cd backend && uv run python app/db/seed.py

demo-data: ## Generate sample mock invoices & bank statements
	@echo "--> Generating demo dataset..."
	python3 demo-data/create_demo_dataset.py

dev-backend: ## Run FastAPI backend server locally (port 8000)
	@echo "--> Starting FastAPI backend server..."
	cd backend && uv run uvicorn app.main:app --reload --port 8100

dev-frontend: ## Run Vite frontend development server
	@echo "--> Starting Vite frontend dev server..."
	cd frontend && npm run dev

test: ## Run backend unit and end-to-end test suite (pytest)
	@echo "--> Running pytest test suite..."
	cd backend && DATABASE_URL="sqlite:///:memory:" uv run pytest tests/ -v --tb=short

lint: ## Run code linter checks (Ruff for backend, Oxlint/Prettier for frontend)
	@echo "--> Linting backend..."
	cd backend && uv run ruff check .
	@echo "--> Checking backend formatting..."
	cd backend && uv run ruff format --check .
	@echo "--> Linting frontend..."
	cd frontend && npm run lint
	@echo "--> Checking frontend formatting..."
	cd frontend && npm run format:check

format: ## Auto-format codebases (Ruff for backend, Prettier for frontend)
	@echo "--> Formatting backend code..."
	cd backend && uv run ruff format .
	@echo "--> Formatting frontend code..."
	cd frontend && npm run format

build: ## Build frontend production bundle & check TypeScript types
	@echo "--> Building frontend production bundle..."
	cd frontend && npm run build

ci: lint test build ## Run full local CI check suite (lint + test + build)
	@echo "--> All local CI checks passed successfully! 🎉"

clean: ## Clean cache files, pycache, dist, and temporary test databases
	@echo "--> Cleaning cache and build artifacts..."
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +
	rm -rf frontend/dist
	rm -rf backend/storage/*
	@echo "--> Clean complete!"
