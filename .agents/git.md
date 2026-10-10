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
| `build` | Dependencies, lockfiles, Makefile, the submodule pin |
| `ci` | CI pipelines |
| `chore` | Repo maintenance that fits nothing above (gitignore, tooling config) |
| `revert` | Reverting an earlier commit |

**Scopes** (optional, one per commit): `agent` (the negotiator package), `strategy` (negotiation logic in
`agent/src/negotiator/strategy/`), `kit` (the submodule pin), `repo` (root files). Omit the scope when a
change spans several areas.

**Subject**
- Imperative mood, lower case, no trailing period: `add item search endpoint`, not `Added item search.`
- At most 72 characters for the whole first line.
- Describe the effect, not the file: `fix(agent): retry a dropped reply with the same move id`.

**Body**: wrap at 72 characters; explain the reason and any trade-off. Required for `BREAKING CHANGE`
(also mark the type with `!`: `feat(agent)!: rename the run command to play-set`).

**One logical change per commit.** Formatting-only changes go in their own `style` commit. A strategy
change and the tests that pin its behaviour go in the same commit.

Examples:
```
feat(strategy): ask for a cost breakdown before the second offer
fix(agent): keep held RFQ threads alive while others negotiate
build(kit): update negotiation-arena-kit to the Sunday release
test(agent): cover the final-mode guard
docs: describe commit rules in .agents/git.md
```

## Branches

`<type>/<short-kebab-description>` from `main`, e.g. `feat/llm-strategy`, `fix/keepalive-timing`.
Keep `main` deployable; merge through pull requests, squash when the branch history is noisy.

## Before committing

- `make test && make lint` (ruff and pytest in `agent/`).
- Never commit secrets (`.env`, API keys), data (`bmw_data/`, `agent/data/`), run telemetry (`agent/runs/`),
  virtualenvs or caches.
- Commit, pull and push regularly without being asked (see AGENTS.md, Rules); never push to `main` directly and
  never force-push it.
