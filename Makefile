# Local development: PostgreSQL in Docker, backend and frontend on the host with hot reload.
#   make db        start PostgreSQL (localhost:5432)
#   make backend   FastAPI dev server  -> http://localhost:8000/docs
#   make frontend  Next.js dev server  -> http://localhost:3000
# Run `make backend` and `make frontend` in separate terminals.

DATABASE_URL ?= postgresql+asyncpg://app:app@localhost:5432/app
BACKEND_URL ?= http://localhost:8000
export DATABASE_URL BACKEND_URL

.PHONY: db db-stop install migrate backend frontend test lint up down agent-sandbox agent-stats

db:
	docker compose up -d --wait db

db-stop:
	docker compose stop db

install:
	cd backend && uv sync
	cd frontend && pnpm install
	cd agent && uv sync

migrate:
	cd backend && uv run alembic upgrade head

backend: migrate
	cd backend && uv run fastapi dev src/app/main.py --port 8000

frontend:
	cd frontend && pnpm dev

test:
	cd backend && uv run pytest
	cd agent && uv run pytest

lint:
	cd backend && uv run ruff check . && uv run ruff format --check .
	cd frontend && pnpm lint && pnpm exec tsc --noEmit
	cd agent && uv run ruff check . && uv run ruff format --check .

# Negotiation arena agent (see agent/README.md)
agent-sandbox:
	cd agent && uv run negotiator run --set sandbox

agent-stats:
	cd agent && uv run negotiator stats

# Whole stack in Docker (production builds)
up:
	docker compose up -d --build --wait

down:
	docker compose down
