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
- [`agent/docs/benchmarks/`](agent/docs/benchmarks/) — one record per benchmark run (see Benchmarks above)
- [`agent/docs/knowledge/competitions-info.md`](agent/docs/knowledge/competitions-info.md) — scoring, practice and
  final rules from the arena's FAQ that the brief does not state; read it before changing how we score, close or run
- [`agent/docs/backlog.md`](agent/docs/backlog.md) — where the current strategy loses score, and the 7/3 holdout

Files hold measured data only: a number in a doc, a benchmark record or a comment is something a run on the arena
(or a named tool run, e.g. `negotiator sim check`) actually returned, with its source. No predictions, forecasts or
expected scores in files - say them in the conversation, and write the result down once the run has verified it.

General: keep changes scoped to the request, match the surrounding code's style, run the checks above for every
area you changed.

Commit, pull and push regularly, without waiting to be asked - several people and agents work in this repository at
once, and a limited run needs pushed code:
- **pull** before you start and before every push: `git fetch`, then merge `origin/main` into your branch;
- **commit** every finished logical change as soon as `make test && make lint` pass - do not let work pile up;
- **push** your branch after every commit.

Work on a branch, never push to `main` directly and never force-push it (see [`.agents/git.md`](.agents/git.md)).

Costs: report an LLM cost only when the provider measured it (`cost_usd` on the `llm_call` event, e.g.
`claude-code`). When it did not (OpenAI-compatible endpoints return tokens, not money), write
`APPROX-NOT-MEASURED` in place of the amount and give the token counts; never a figure computed from a
remembered price list.
