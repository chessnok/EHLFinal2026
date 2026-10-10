# AGENTS.md

Instructions for coding agents (Claude Code reads this via the `CLAUDE.md` symlink).

## Repository

Monorepo with two fully independent apps and PostgreSQL, run together with Docker Compose. Frontend and backend
share no code or tooling and talk over HTTP only (`/api/*`, proxied by the Next.js server).

| Path | What |
|---|---|
| `frontend/` | Next.js 16 · React 19 · TypeScript · Tailwind v4 · pnpm; UI style in `frontend/DESIGN.md` |
| `backend/` | Python 3.13 · uv · FastAPI · SQLAlchemy 2 async · Alembic; layered api → services → repositories |
| `docker-compose.yml` | `db` (postgres:17), `backend`, `frontend`; split networks (frontend cannot reach db) |
| `bmw_data/` | Source data, git-ignored; never commit it or copy values from it into code |

## Commands

```sh
docker compose up --build                       # whole stack: :3000 frontend, :8000 backend, :5432 db
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check .
cd frontend && pnpm lint && pnpm exec tsc --noEmit && pnpm build
```

## Rules

Read the file for the area you touch before changing it:

- [`.agents/git.md`](.agents/git.md) — commit messages (Conventional Commits), branches, pre-commit checks
- [`.agents/backend.md`](.agents/backend.md) — layer boundaries, migrations, Python style
- [`.agents/frontend.md`](.agents/frontend.md) — design tokens, API access, Next.js conventions

General: keep changes scoped to the request, match the surrounding code's style, run the checks above for every
area you changed, and do not commit or push unless asked.
