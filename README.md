# EHL monorepo

Two independent apps plus PostgreSQL, orchestrated with Docker Compose. Frontend and backend share no code,
dependencies or tooling; they talk over HTTP only.

```
frontend/   Next.js 16 · React 19 · TypeScript · Tailwind v4 · pnpm   (DESIGN.md = UI style reference)
backend/    Python 3.13 · uv · FastAPI · SQLAlchemy 2 (async) · Alembic
docker-compose.yml   db (postgres:17) · backend · frontend
```

## Run everything

```sh
cp .env.example .env        # optional: override ports and DB credentials
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000/api, OpenAPI docs at http://localhost:8000/docs
- PostgreSQL: localhost:5432 (`app`/`app`)

The backend container runs `alembic upgrade head` on start. The frontend proxies `/api/*` to the backend, so
the browser only ever talks to the frontend. Networks are split: the frontend can reach the backend but not
the database.

## Develop locally (database in Docker, apps on the host)

```sh
git submodule update --init   # negotiation-arena-kit/
make install                  # uv sync + pnpm install
make db                       # PostgreSQL on localhost:5432
make backend                  # terminal 1: migrations + fastapi dev  -> http://localhost:8000/docs
make frontend                 # terminal 2: next dev                  -> http://localhost:3000
make test && make lint
```

Both dev servers reload on save. `make up` / `make down` run the whole stack in Docker instead.

## Backend: three layers

```
src/app/
  api/            presentation: routes, request/response handling, dependency wiring (deps.py)
  services/       business logic and rules; raises ServiceError subclasses, mapped to HTTP in main.py
  repositories/   data access: SQLAlchemy queries, nothing else
  models/         ORM models (tables)
  schemas/        Pydantic DTOs for the API
  core/           settings and database engine/session
```

Each request gets a session (`core/database.py`) → repository → service → route. Services never touch HTTP or
SQL directly, so they are unit-tested with an in-memory fake repository (`tests/test_item_service.py`).
`items` is an example resource showing the pattern end to end.

```sh
cd backend
uv sync
uv run pytest
uv run ruff check . && uv run ruff format .
DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app uv run fastapi dev src/app/main.py
uv run alembic revision --autogenerate -m "describe change"   # after changing models
uv run alembic upgrade head
```

## Frontend

```sh
cd frontend
pnpm install
BACKEND_URL=http://localhost:8000 pnpm dev   # http://localhost:3000
pnpm lint && pnpm build
```

Design tokens from `frontend/DESIGN.md` live in `src/app/globals.css` (`@theme` plus `card`, `btn-*`, `input`,
`badge` utilities). `BACKEND_URL` is read at build time; the Docker image is built with
`BACKEND_URL=http://backend:8000`.
