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

## HARD RULE: confirm before spending practice quota

Practice sessions are a scarce team budget: 200 per team per rolling 24 hours, shared by everyone on the team. A
coding agent must **never** start anything that spends quota without an explicit "yes" from a human in the
conversation, for that specific run. No exceptions, no assumed consent, no carrying a previous "yes" over to a new run.

**What spends quota:** every new practice session, which means:
- `negotiator play <case>` on a practice case (`case:P…`);
- `negotiator run --set practice`;
- `make` targets or scripts that call either of these;
- `POST /v1/sessions` for a practice case.

**What does not spend quota:** `--set sandbox` (cases `case:D…`), the local `arena-sim`, read-only calls
(`me`, `cases`, `sessions`, `session`, `thread`), and the final.

**Before asking, the agent must:**

1. Run `negotiator me` and read the current balance (`used`, `left`, `resets_at`).
2. Ask for confirmation, stating:
   - the exact command;
   - which cases it plays and how many sessions it will spend;
   - the balance before and after the run;
   - when the quota resets.
3. Wait for an explicit yes. Silence, "ok, continue with the task" or approval of an earlier run do not count. If
   the answer is anything but a clear yes, do not run it.

Example of the required question:

> This spends practice quota: `uv run negotiator run --set practice --cases case:P01 case:P05 --strategy tactical`
> → 2 sessions. Balance now 197 / 200 left, after the run 195. Quota resets at 2026-10-11 12:47 UTC. Run it?

## Run registry and pushed code only

**Never run unpushed code on a limited run.** A practice run, or any run that spends quota, must use code that is
committed **and pushed**. Before starting it:
- `git status` is clean;
- `git log origin/main..HEAD` is empty, or the branch is pushed;
- note the hash from `git rev-parse --short HEAD`.

Without this nobody can reproduce or compare the result, and the quota spent on it is wasted. Free runs (sandbox,
local `arena-sim`) may use uncommitted code.

**Every run goes into the registry** [`agent/docs/runs.md`](agent/docs/runs.md): practice runs always, sandbox runs
when they inform a decision. One row per run, with these columns:
- commit;
- strategy;
- parameters (cases, `--llm`, flags);
- author;
- description;
- results (per-case scores and the mean);
- conclusions.

Add the row in the same change that discusses the result.

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
