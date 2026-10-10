# AGENTS.md

Instructions for coding agents (Claude Code reads this via the `CLAUDE.md` symlink).

## Repository

Our buyer agent for the Tacto Negotiation Arena (EHL Final 2026).

| Path | What |
|---|---|
| `agent/` | `negotiator`: arena API client, runner, telemetry, reports, strategies (Python 3.12, uv) |
| `negotiation-arena-kit/` | git submodule: brief, API docs, data package, starter kit (read-only, do not edit) |
| `bmw_data/` | Source data, git-ignored; never commit it or copy values from it into code |

## Commands

```sh
make install                                   # submodule + uv sync
make test && make lint                         # pytest (incl. arena-sim end to end), ruff
cd agent && uv run negotiator --help           # every API call, play/run/final, report, stats
```

Arena: the key is `ARENA_API_KEY` in the root `.env`. Practice is limited to 200 sessions a day - develop on
`--set sandbox` and the local `arena-sim`; never hard-code values from the data package or replays into code.
During the Live Final the agent must not read the live feed, leaderboard or results (`NEGOTIATOR_FINAL=1`
blocks them in the client).

## Rules

Read the file for the area you touch before changing it:

- [`.agents/git.md`](.agents/git.md) — commit messages (Conventional Commits), branches, pre-commit checks
- [`agent/README.md`](agent/README.md) — package architecture, telemetry layout, how to add a strategy

General: keep changes scoped to the request, match the surrounding code's style, run the checks above for every
area you changed, and do not commit or push unless asked.

Costs: report an LLM cost only when the provider measured it (`cost_usd` on the `llm_call` event, e.g.
`claude-code`). When it did not (OpenAI-compatible endpoints return tokens, not money), write
`APPROX-NOT-MEASURED` in place of the amount and give the token counts; never a figure computed from a
remembered price list.
