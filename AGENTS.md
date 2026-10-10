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

Before a practice run, try a change to the numbers on `negotiator sim bench` (suppliers fitted from our replays,
no quota); it cannot judge wording, and a difference under 0.08 is noise - see `agent/docs/simulator.md`.

## Benchmarks

Every benchmark run (any `negotiator run` / `play` on sandbox or practice that is used to judge a strategy) gets a
record in `agent/docs/benchmarks/<date>-<strategy>-<model>.md` (e.g. `2026-10-10-lowball-none.md`; `none` when the
strategy uses no LLM), in the same change as the code it measures. Copy the layout of an existing record:

- **Result and cost first:** score per case and mean; the deal's cost `C_deal` in EUR; what the run cost us (practice
  sessions spent, LLM tokens, wall time).
- **Strategy:** its file, a one-line description, the parameters it ran with and the commit - so a later change to
  the strategy can be told apart from the old numbers.
- **Runs:** set and cases, run ID(s) under `agent/runs/`.

A repeat on the same day with the same parameters adds a row to that record; changed parameters or a new day get a
new file. Never rewrite old numbers. Add a line for the run to the overview in `agent/docs/benchmarks/README.md`.
A strategy without an LLM gets the same replies for the same e-mails, so one run is enough; with an LLM the text
varies - compare means over at least three repetitions. Start runs one at a time: the key allows 10 open sessions.

## Rules

Read the file for the area you touch before changing it:

- [`.agents/git.md`](.agents/git.md) — commit messages (Conventional Commits), branches, pre-commit checks
- [`agent/README.md`](agent/README.md) — package architecture, telemetry layout, how to add a strategy
- [`agent/docs/benchmarks/`](agent/docs/benchmarks/) — one record per benchmark run (see Benchmarks above)

General: keep changes scoped to the request, match the surrounding code's style, run the checks above for every
area you changed, and do not commit or push unless asked.

Costs: report an LLM cost only when the provider measured it (`cost_usd` on the `llm_call` event, e.g.
`claude-code`). When it did not (OpenAI-compatible endpoints return tokens, not money), write
`APPROX-NOT-MEASURED` in place of the amount and give the token counts; never a figure computed from a
remembered price list.
