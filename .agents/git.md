# Git rules

## Commit messages: Conventional Commits

```
<type>(<scope>): <subject>

<body: why, not what — optional>

<footer: BREAKING CHANGE: ..., Refs: #123 — optional>
```

**Types**

| Type | Use for |
|---|---|
| `feat` | New user-facing behaviour |
| `fix` | Bug fix |
| `refactor` | Code change with no behaviour change |
| `perf` | Performance improvement |
| `test` | Adding or fixing tests only |
| `docs` | Documentation only (README, AGENTS.md, .agents/, comments) |
| `style` | Formatting only (ruff format, prettier); no logic |
| `build` | Dependencies, Dockerfiles, docker-compose, lockfiles |
| `ci` | CI pipelines |
| `chore` | Repo maintenance that fits nothing above (gitignore, tooling config) |
| `revert` | Reverting an earlier commit |

**Scopes** (optional, one per commit): `frontend`, `backend`, `db` (models/migrations), `infra` (Docker,
compose), `repo` (root files). Omit the scope when a change spans several areas.

**Subject**
- Imperative mood, lower case, no trailing period: `add item search endpoint`, not `Added item search.`
- At most 72 characters for the whole first line.
- Describe the effect, not the file: `fix(backend): return 404 for missing item`.

**Body**: wrap at 72 characters; explain the reason and any trade-off. Required for `BREAKING CHANGE`
(also mark the type with `!`: `feat(backend)!: rename /items to /products`).

**One logical change per commit.** Formatting-only changes go in their own `style` commit. A migration
goes in the same commit as the model change that needs it.

Examples:
```
feat(backend): add pagination to item listing
fix(frontend): keep form values after a failed create
build(infra): pin postgres to 17-alpine
feat(db): add items.archived_at column
docs: describe commit rules in .agents/git.md
```

## Branches

`<type>/<short-kebab-description>` from `main`, e.g. `feat/item-search`, `fix/cors-origins`.
Keep `main` deployable; merge through pull requests, squash when the branch history is noisy.

## Before committing

- Backend: `uv run ruff check . && uv run ruff format --check . && uv run pytest` (in `backend/`).
- Frontend: `pnpm lint && pnpm exec tsc --noEmit` (in `frontend/`).
- Never commit secrets (`.env`), data (`bmw_data/`), virtualenvs, `node_modules`, build output or caches.
- Do not commit or push unless asked; never force-push `main`.
