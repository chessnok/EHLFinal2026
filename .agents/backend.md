# Backend rules (`backend/`)

Python 3.13, uv, FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL.

## Layers — dependencies point downwards only

```
api/           routes, HTTP status codes, request/response models, Depends wiring (api/deps.py)
  ↓
services/      business rules; raises services/exceptions.py errors (never HTTPException)
  ↓
repositories/  SQLAlchemy queries only; no business rules, no HTTP
  ↓
models/        ORM tables          schemas/  Pydantic DTOs          core/  settings, engine, session
```

- Routes call services, never repositories or the session directly (health check excepted).
- Services take repositories in their constructor; they never import FastAPI or build SQL.
- Repositories `flush()`, never `commit()`; the request-scoped session in `core/database.py` commits.
- Map new error types to HTTP codes in `ERROR_STATUS` in `main.py`.
- New resource = model + schema + repository + service + route module + `api/router.py` entry + tests.

## Database

- Every model change ships with a migration: `uv run alembic revision --autogenerate -m "<what>"`; read the
  generated file before committing. Register new models in `models/__init__.py` so autogenerate sees them.
- Configuration only through `core/config.py` (env vars); no hard-coded URLs or credentials.

## Code style

- `ruff check` and `ruff format` clean (line length 100); type hints everywhere.
- Tests: services with in-memory fake repositories; API through `TestClient` with the SQLite session override
  in `tests/conftest.py`.
- Add dependencies with `uv add` (or `uv add --dev`), never by editing the lockfile.
