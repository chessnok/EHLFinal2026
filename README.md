# EHL Final 2026 – Tacto Negotiation Arena

Our AI buyer agent for the [Tacto Negotiation Arena](negotiation-arena-kit/README.md). It reads the case file and
the data package, negotiates by e-mail with the arena's supplier bots (one thread per supplier, up to three term
sheets per e-mail) and closes the deal with the lowest **total cost C** for the buyer.

- **Final model:** strategy `tactical`, git tag `final-candidate-2026-10-11f` (commit `4bed477`). Commits after
  the tag change documentation only. `agent/src` is identical.
- **Last practice control run** (P-57, all 10 hosted practice cases, one session each):

  | P01 | P02 | P03 | P04 | P05 | P07 | P08 | P10 | P11 | P18 | mean |
  |---|---|---|---|---|---|---|---|---|---|---|
  | 0.924 | 0.733 | 0.923 | 0.860 | 0.865 | 0.740 | 0.659 | 0.647 | 0.710 | 0.685 | **0.775** |

  All 10 cases ended in a deal, none scored zero.
- Score per case = (C_open − C_deal) / (C_open − C_best). C comes from the arena's published cost function
  (`arena_kit.cost.total_cost`). It covers the price, payment terms, freight, index clause and index risk,
  quality, uncovered need and, for strategic suppliers, a charge for squeezing their margin.

---

## Contents

1. [Repository layout](#1-repository-layout)
2. [Setup](#2-setup)
3. [Environment variables](#3-environment-variables-no-values-in-the-repo)
4. [Running the agent](#4-running-the-agent)
5. [The pipeline, end to end](#5-the-pipeline-end-to-end)
6. [The strategy in one page](#6-the-strategy-in-one-page)
7. [How a change gets into the final model](#7-how-a-change-gets-into-the-final-model)
8. [Telemetry and reports](#8-telemetry-and-reports)
9. [Tests and lint](#9-tests-and-lint)
10. [Documentation map](#10-documentation-map)

---

## 1. Repository layout

```
EHLFinal2026/
├── README.md                 this file: the whole project and the pipeline
├── Makefile                  make install | me | sandbox | stats | report | final | test | lint
├── .env.example              the environment variables, without values (copy to .env, git-ignored)
├── AGENTS.md / CLAUDE.md     working rules for the coding agents on this repo
├── negotiation-arena-kit/    git submodule (read-only): brief, API docs, data package, starter kit with the
│                             published cost function C and the quote-PDF parser
└── agent/                    our agent, the Python package `negotiator` (Python 3.12, uv)
    ├── src/negotiator/       the code (section 5)
    ├── tests/                unit tests and end-to-end tests against a local fake arena / simulator
    ├── docs/                 run log, game plan, cost model, bot mechanics, analyses (section 10)
    ├── data/                 downloaded data package + Sunday release (git-ignored), analysis notes
    ├── runs/                 telemetry of every arena run (git-ignored)
    └── README.md             detailed reference: every CLI command, LLM providers, simulator, telemetry files
```

## 2. Setup

```sh
git clone --recurse-submodules git@github.com:chessnok/EHLFinal2026.git   # or: git submodule update --init
cd EHLFinal2026
cp .env.example .env            # fill in ARENA_API_KEY; .env is git-ignored, never commit it
make install                    # git submodule update --init && cd agent && uv sync
make me                         # the arena answers with our team: the key works
cd agent && uv run negotiator data   # data package v1 + the Sunday release (after 08:00 on final day)
```

Requirements: Python 3.12 and [uv](https://docs.astral.sh/uv/). The starter kit is a path dependency, so C and
the quote-PDF parsing are exactly the arena's own.

## 3. Environment variables (no values in the repo)

The agent reads `.env` from the working directory, `agent/` and the repo root. Real environment variables win.

| Variable | Needed | What |
|---|---|---|
| `ARENA_API_KEY` | **yes** | the team's arena key |
| `ARENA_URL` | no | default `https://arena.tacto.ai`; a local simulator for development |
| `NEGOTIATOR_FINAL` | **for the final** | `1` = Live Final mode: `negotiator final` only runs with it; leaderboard, results and the live feed are refused |
| `NEGOTIATOR_DATA` · `NEGOTIATOR_RELEASE` · `NEGOTIATOR_RUNS` | no | data package, Sunday release and run folders (defaults: the submodule's `data/`, `agent/data/release-sunday`, `agent/runs`) |
| `LLM`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_REASONING`, `LLM_TIMEOUT_S`, `LLM_PARALLEL` | no | only for the LLM strategies (`llm`, `tactical-llm`). **The final model `tactical` uses no language model** |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` | no | optional tracing; nothing is sent without them |

## 4. Running the agent

```sh
cd agent
uv run negotiator me                                        # team, practice quota, best scores
uv run negotiator run --set sandbox                         # free sandbox cases D01, D02
uv run negotiator play case:P05                             # one practice case (quota: 200 per 24 h)
uv run negotiator run --set practice --parallel 5           # all hosted practice cases
uv run negotiator run --set practice --strategy tactical+no_hedged_series --cases case:P08   # a flag variant
uv run negotiator stats                                     # best / mean score per case across all runs
```

**The Live Final** (Sunday 12:00, 5 waves × 8 minutes, hidden cases, one try each). Start it before 12:00 and
leave it running. It polls the case list, answers 403 "no wave yet" by waiting, and plays every case of a wave
in parallel:

```powershell
# PowerShell
$env:NEGOTIATOR_FINAL="1"; uv run negotiator final          # --strategy tactical --parallel 10 are the defaults
```
```sh
# bash
NEGOTIATOR_FINAL=1 make final
```

Final checklist:
- Run only one instance.
- No practice or sandbox runs from anyone during the final: 10 open sessions is the arena's limit.
- The laptop is on power and does not sleep.
- The Sunday release is downloaded.

## 5. The pipeline, end to end

```
 data package + Sunday release ─┐
 case file (goal, need, must-haves, alternative, term options)
 quotes (e-mail + PDF standard terms) ─┤
                                      ▼
 ┌────────── PREPARE (once per case, milliseconds, no LLM) ──────────────────────────────────────────┐
 │ data.py        CSVs → in-memory SQLite + facts.json: orders, indices, scorecards, contracts,       │
 │                forecasts, should-costs, notices; checkable Evidence with arena IDs                  │
 │ profile.py     supplier traits from call notes, letters, news, history: cash_short, hedged,        │
 │                open_book, wants_volume, approval_ladder, below_cost, price_frozen, …                │
 │ groundtruth.py the supplier's floor (lower bound) and our walk-away (upper bound)                   │
 │ tactical.prepare  per supplier: policy from the category goal, target C (first ask), bounds,       │
 │                the levers it asks for, the evidence pool, the margin-charge estimate (strategic)    │
 └────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                      ▼
 ┌────────── EVERY ROUND, PER THREAD (own 60 s clock, runner.py: one worker per supplier) ────────────┐
 │ 1 read      reply_parser.py: questions, wishes, conditions, its figures, drivers, hedges, signals  │
 │             (final / approval / frozen price); claim results (verified, duplicate, "not our         │
 │             reality") → what is spent and what is banned                                            │
 │ 2 believe   belief.py: the supplier's floor re-estimated as value to the supplier after each reply │
 │ 3 decide    next ask in C: patient Boulware curve over the rounds left, capped by reciprocity      │
 │             (no move from it → no move from us), minimum step; the dynamic upper bound              │
 │ 4 offer     menu.py: up to 3 term sheets of EQUAL C for us that differ in what they give the       │
 │             supplier (its requested levers, its own structure, a pure price move)                   │
 │ 5 argue     up to 3 checkable claims (the arena reads 3 per e-mail, each ID once per case)         │
 │ 6 write     template e-mail; conduct.py drops any sentence the data does not support               │
 │ 7 guard     guards.py before every send / accept: valid sheets and IDs, must-haves, alternative,   │
 │             never above C_open                                                                      │
 └────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                      ▼
 CLOSE: accept the cheapest standing offer that is within the stop margin of the expected floor, or a
 final offer that beats C_open and the alternative. Never bid against a final offer. Walk away only where
 the alternative is cheaper. In an RFQ the losing threads are closed.
                                      ▼
 AFTER: sessions/<sid>.json (everything), report.md, lessons.md, chats.md → docs/runs.md (the run log)
```

| Module | Role |
|---|---|
| `config.py` | settings from env / `.env` |
| `client.py` | every arena endpoint; paced under 10 calls/s; safe retries with `X-Move-Id`; the final-mode guard |
| `runner.py` | `play_case` (a worker per thread, keepalive, deadline), `play_many`, `play_final` (waves) |
| `session.py` | `Negotiation`: threads, documents, costs (the kit's C), send / accept / walk away, transcript |
| `data.py` | the data package and the Sunday release; `evidence_*` helpers that compute checkable arguments |
| `profile.py` | supplier traits from text patterns |
| `groundtruth.py` · `belief.py` | the floor before the first move · the live floor estimate after every reply |
| `ledger.py` · `menu.py` | the argument ledger · the equal-C menu of term sheets |
| `reply_parser.py` | every supplier e-mail as data; logged as `reply_facts` |
| `conduct.py` | the conduct rules (honest, sourced, no bluff) and the check that enforces them |
| `guards.py` | hard rules before every send and accept |
| `strategy/tactical.py` | **the final strategy** (sections 6 and 7) |
| `strategy/baseline.py`, `playbook.py`, `experiments.py`, `llm_strategy.py`, `written.py`, `decided.py` | earlier or comparison strategies, kept for measurement |
| `writer.py` · `reader.py` · `llm.py` | optional LLM wording and reading (`tactical-llm`), checked and with a template fallback |
| `sim/` | the local supplier simulator: fit from our own runs, local arena, bench |
| `report.py` · `lessons.py` · `chats.py` · `telemetry.py` · `tracing.py` | reports, run log, readable chats, events, optional Langfuse |

## 6. The strategy in one page

**Fixed frame (code, never negotiable):**
- Never state what the data does not show. Every number we cite carries its arena ID, and the arena checks each one.
- Never close above the opening cost C_open or above the alternative.
- Never bid against a supplier's final offer.
- Keep every must-have, read on the terms the deal would really close on.
- Cite each data ID once per case and at most 3 claims per e-mail.

**Head and mouth are separate.** Everything is computed in C, the score's currency, before every e-mail. The text
only states the computed facts.
- **Policy per category goal:**
  - leverage: deep first ask;
  - routine: moderate;
  - quality_first: quality levers;
  - stabilise and secure_supply: shallow, because squeezing a strategic supplier below its sustainable margin
    costs us C.
- **Profile adjustments:** cash-short → a faster-payment option; wants volume → a longer commitment;
  hedged → no index-fall argument on the hedged series.
- **Dynamic bounds:** the floor estimate is recomputed after every reply. The upper bound is what we accept at
  most, and it is never said.
- **Patience:** small, reciprocal steps. The supplier moves first, and we hold where it held. We keep the
  conversation going while the supplier still moves.
- **"Yes only on terms that cost us little, never on price":**
  - A condition the supplier asks for is granted at our price when it costs us at most 0.2 % of C (`cheap_yes`).
  - Every menu option costs us the same, so whichever the supplier picks, we pay the same.

**Default flags of `tactical` (each one measured on practice before it went on):**

| Flag | What | Measured |
|---|---|---|
| `clause_rel_only` | the index clause counts as the supplier's request only for strategic goals when its quote names the series | P-49 |
| `cheap_yes` | yes to its condition at our price when it costs us ≤ 0.2 % of C | P-49 |
| `fast_pay` | in an RFQ, a 14-day payment option at option A's C for a supplier that asks for faster payment | P-50/P-52: P05 0.824 → 0.865 |
| `no_hedged_series` | a supplier that bought its material forward hears no argument on that series ("not our reality"), and the slot goes to the next argument | P-57: P08 0.626 → 0.659 |

Other flags exist for experiments and are off. Turn one on with `--strategy tactical+<flag>`.

## 7. How a change gets into the final model

1. **Build it as a flag, off by default.**
2. **Offline replay** of the last control run. A first-diverging-turn check per case shows which cases a flag
   changes at all.
3. **Sandbox** (free) and the **simulator** (`negotiator sim bench`). The simulator ranked practice variants
   wrongly (rank correlation −0.55), so it only finds candidates and never decides.
4. **Practice** (quota) decides. The practice bots are nearly deterministic, so one session per changed case is
   close to exact.
5. **Adopt** only if no case loses more than 0.02 and no case newly scores zero. Every run is a row in
   [`agent/docs/runs.md`](agent/docs/runs.md) (P-1 … P-57, sandbox S-*), adopted or not, with the reason.

Rejected on practice (kept as flags, off):
- answering every sentence of the supplier (`respond_all`, `respond_lite`);
- a justified-rise argument;
- a higher first offer (`soft_anchor`);
- a framework-contract double-count argument;
- deeper guessed anchors, alternative structures and persistent steps.

Some only lost the cases they changed. Others traded a case won for a case lost.

## 8. Telemetry and reports

Every run writes `agent/runs/<run_id>/` (git-ignored):

| File | Content |
|---|---|
| `events.jsonl` | every move and reply, with C and claim results |
| `http.jsonl` | every HTTP call |
| `run.log` | the human-readable log |
| `sessions/<sid>.json` | the whole case, including the arena's trace and back office |
| `sessions/<sid>.md`, `chats.md` | readable e-mail threads |
| `metrics.json` | counters and timings |
| `summary.json`, `report.md`, `lessons.md` | scores, cost breakdowns, what each case taught |

`negotiator report`, `stats`, `lessons` and `chats` rebuild them. Details: [`agent/README.md`](agent/README.md).

## 9. Tests and lint

```sh
make test     # cd agent && uv run pytest   (unit tests + end to end against a local fake arena / simulator)
make lint     # ruff check + ruff format --check
```

## 10. Documentation map

| File | What |
|---|---|
| [`agent/README.md`](agent/README.md) | full CLI reference, simulator, LLM providers, telemetry, architecture |
| [`agent/docs/runs.md`](agent/docs/runs.md) | every practice and sandbox run with code, question, result, decision |
| [`agent/docs/gameplan-2026-10-11.md`](agent/docs/gameplan-2026-10-11.md) | the final-day plan and timeline |
| [`agent/docs/cost-model.md`](agent/docs/cost-model.md) | the cost function C, term by term |
| [`agent/docs/bot-mechanics.md`](agent/docs/bot-mechanics.md) | how the supplier bots react, measured from our replays |
| [`agent/docs/strategies.md`](agent/docs/strategies.md) · [`agent/docs/TRYED.md`](agent/docs/TRYED.md) | the strategies and what was tried |
| [`agent/docs/simulator.md`](agent/docs/simulator.md) | the simulator and its measured error |
| [`negotiation-arena-kit/brief/`](negotiation-arena-kit/brief/) | the rules: brief, API, submission |
