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

## Ideas tried

[`agent/docs/TRYED.md`](agent/docs/TRYED.md) lists every idea we have tried: what it was, where it was measured, and
the result - worked (and why), failed (and why), or unknown. Read it before proposing a change, so nobody tests the
same idea twice. Add or update a row in the same change that tries an idea: when the code for it lands (result
"unknown") and again when a run has settled it. Ideas that came from reading replays and were never played go in as
"unknown" too.

## Case triage: where to spend work and attempts

Before working on a strategy or asking for practice sessions, fill this table from the arena's live page
(`https://arena.tacto.ai/live`) and `negotiator me`. Five numbers per case: **ours** (our best score), **house**
(Tacto's house agent), **best** (the best team), **tried** (teams that played it), **beaten** (teams above the house).

Put each case in the first category that fits, and sort inside a category by the gap `best − ours`:

1. **Below the house.** A fault in our agent. First priority.
2. **Above the house, far from the best, and many of the teams that tried beat the house.** There is a known lever
   we do not use. Second priority.
3. **Close to the best, or a high house score that few teams beat.** A ceiling. Spend no attempts.

As of 10 October 2026: house, best, tried and beaten from the live page at about 21:05; ours from `negotiator me` at
22:30. Refresh both before using it.

| Category | Case | Lever, goal | Ours | House | Best | Tried | Beaten | Gap to best |
|---|---|---|---|---|---|---|---|---|
| 1 | P08 | raw material, leverage | 0.626 | 0.75 | 0.91 | 22 | 1 | 0.284 |
| 1 | P02 | price increase, stabilise | 0.686 | 0.74 | 0.85 | 21 | 1 | 0.164 |
| 1 | P07 | bundling, routine | 0.721 | 0.78 | 0.81 | 21 | 1 | 0.089 |
| 1 | P01 | price increase, stabilise | 0.917 | 0.97 | 0.99 | 22 | 2 | 0.073 |
| 1 | P10 | capacity, secure_supply | 0.647 | 0.69 | 0.70 | 22 | 3 | 0.053 |
| 1 | P03 | renewal, stabilise | 0.905 | 0.92 | 0.94 | 21 | 1 | 0.035 |
| 2 | P11 | quality, quality_first | 0.692 | 0.31 | 0.81 | 20 | 17 | 0.118 |
| 2 | P05 | RFQ, leverage | 0.839 | 0.56 | 0.92 | 21 | 12 | 0.081 |
| 2 | P18 | raw material, leverage | 0.618 | 0.39 | 0.68 | 20 | 17 | 0.062 |
| 3 | P04 | renewal, routine | 0.860 | 0.86 | 0.87 | 21 | 14 | 0.010 |

We are below the house on six cases. Four of them are `stabilise` or `secure_supply` cases (see the next section).
P01, P10 and P03 are in category 1 by the rule and within 0.08 of the best team.

## Firmness follows the case goal

How hard the agent pushes on price depends on the case's `category_goal`, not on the supplier's opening:

- **`leverage`** (raw material, RFQ): push. Only price and terms count in C.
- **`stabilise` and `secure_supply`:** do not push the price below what the supplier can live on. C carries a
  relationship charge for every margin point the deal leaves the supplier below its sustainable margin
  (`RELATIONSHIP_GOALS` in `arena_kit/cost.py`), so a lower price can cost more than it saves.

Measured on P02 (`stabilise`), [`agent/docs/runs.md`](agent/docs/runs.md) P-13 and P-15:

| Deal price | Relationship charge | Score |
|---|---|---|
| EUR 358.45 | 56,127 | 0.686 |
| EUR 345.39 | 179,204 | 0.000 (C above C_open) |

Our own cost estimate had the charge at 0 in both deals. Until that estimate is fixed, a strategy change that lowers
prices must be checked on the `stabilise` and `secure_supply` cases before it is used anywhere.

## Rules

Read the file for the area you touch before changing it:

- [`.agents/git.md`](.agents/git.md) — commit messages (Conventional Commits), branches, pre-commit checks
- [`agent/README.md`](agent/README.md) — package architecture, telemetry layout, how to add a strategy
- [`agent/docs/benchmarks/`](agent/docs/benchmarks/) — one record per benchmark run (see Benchmarks above)
- [`agent/docs/knowledge/competitions-info.md`](agent/docs/knowledge/competitions-info.md) — scoring, practice and
  final rules from the arena's FAQ that the brief does not state; read it before changing how we score, close or run
- [`agent/docs/TRYED.md`](agent/docs/TRYED.md) — every idea tried and what came of it (see Ideas tried above)
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
