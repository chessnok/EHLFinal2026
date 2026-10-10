# negotiator

Buyer agent toolkit for the [Tacto Negotiation Arena](../negotiation-arena-kit/README.md): a client for every
API endpoint, a runner that plays cases (RFQ threads in parallel, Live Final waves), full telemetry, reports and
statistics, and a baseline strategy to beat.

Python 3.12 (the arena starter kit requires it); the kit is a path dependency, so the published cost function
C and the quote-PDF parsing are exactly the arena's.

## Setup

```sh
cd agent
uv sync
# the key: ARENA_API_KEY in the repo-root .env (git-ignored); ARENA_URL defaults to https://arena.tacto.ai
uv run negotiator me
```

## Commands

| Command | What |
|---|---|
| `negotiator health` / `me` | arena up, data downloads / team, practice quota, best scores |
| `negotiator cases --set practice\|sandbox\|final` · `case <id>` | case files |
| `negotiator sessions --set …` · `session <sid>` · `thread <sid> <supplier>` · `backoffice <sid>` | our sessions, state, result + trace, threads, the supplier's back office |
| `negotiator attachment <sid> <attachment_id> -o FILE` | a supplier document |
| `negotiator board` | leaderboard (for people; refused in final mode) |
| `negotiator data` | download package v1 and the Sunday release into `agent/data/` |
| `negotiator play <case_id> [--strategy tactical\|baseline]` | play one case, with telemetry and a report |
| `negotiator run --set sandbox\|practice [--cases …] [--parallel N]` | many cases in parallel (default: every hosted case of the set) |
| `negotiator final [--parallel 10]` | the Live Final: waits for each wave, plays its cases within the cap |
| `negotiator report [run_id\|latest]` · `stats` | rebuild a run's report · best/mean score per case across all runs |
| `negotiator lessons [run_id\|latest]` | per case, worst first: score, cost blocks, the supplier's reasons per round, argument checks (also written as `lessons.md` after every run) |

Global options: `--url` (e.g. a local `arena-sim`), `--key`, `--json`, `-v`.

**Quota:** practice is 200 sessions per team per rolling 24 h; sandbox (`case:D01`, `case:D02`) and `arena-sim`
are free. Develop on sandbox and the simulator, spend practice deliberately.

```sh
uv run arena-sim serve --port 8100 --data ../negotiation-arena-kit/data          # local API, scripted supplier
uv run negotiator --url http://127.0.0.1:8100 register "Team" sim                  # a simulator key
uv run negotiator --url http://127.0.0.1:8100 --key <sim key> run --set practice
```

## Supplier simulator

`negotiator sim` is a local arena with suppliers fitted from our own replays: no practice session, no token, 12
cases in seconds. It ranks changes to the numbers (anchor, concessions, menus, arguments), not to the wording, and
its error is measured - see [`docs/simulator.md`](docs/simulator.md) before trusting a result.

```sh
uv run negotiator sim calibrate                          # fit from runs/ (again after every arena run)
uv run negotiator sim check                              # error on sessions the fit has not seen
uv run negotiator sim bench baseline tactical --reps 5   # strategies side by side, next to their arena scores
```

## LLM strategy and providers

`--strategy llm` adds a model on top of the baseline: before the session opens it profiles each supplier from
its dossier (letters, notes, news, negotiation history, credit index); each round it reads the reply and picks
stance, concession, lever and arguments, and writes the e-mail text. Code still builds every term sheet from C,
inserts the checked arguments, strips IDs and figures the model wrote, and falls back to the baseline move if
the model is slow or fails.

Switch the model with one string - `--llm <provider>:<model>` or `LLM=<provider>:<model>` in `.env`:

| Spec | Protocol | Key |
|---|---|---|
| `ollama:qwen3.6:latest` (default) | OpenAI-compatible, `http://localhost:11434/v1`, thinking off | – |
| `openai:<model>` | OpenAI | `OPENAI_API_KEY` |
| `openrouter:<vendor>/<model>` | OpenAI-compatible | `OPENROUTER_API_KEY` |
| `groq:` · `mistral:` · `deepseek:` · `together:` | OpenAI-compatible | `<PROVIDER>_API_KEY` |
| `compat:<model>` | any OpenAI-compatible endpoint at `LLM_BASE_URL` | `LLM_API_KEY` |
| `anthropic:<model>` | Anthropic messages | `ANTHROPIC_API_KEY` |

Tuning: `LLM_REASONING` (`none|low|medium|high`, sent as `reasoning_effort`), `LLM_TIMEOUT_S` (default 30: each
e-mail must reach the arena within 60 s of the reply), `LLM_PARALLEL` (concurrent calls, default 4).

```sh
uv run negotiator run --set sandbox --strategy llm
uv run negotiator play case:P05 --strategy llm --llm anthropic:claude-haiku-4-5
```

## Telemetry: `runs/<run_id>/`

| File | Content |
|---|---|
| `events.jsonl` | every event: `session_opened` (opening C per supplier), `plan`, `message_sent` (sheets with C), `reply` (status, terms, C, claim results, signals, latency), `attachment`, `thread_hold`, `decision`, `conflict`, `result` |
| `http.jsonl` | every HTTP attempt: endpoint, status, latency, retry, move id, pacing wait, practice quota left |
| `run.log` | the human-readable log (debug level) |
| `sessions/<sid>.json` | the whole case: case file, e-mails both ways, documents as text, decisions with rationale, result, the arena's trace and back office |
| `sessions/<sid>/` | the documents suppliers attached (quote PDF, cost breakdown XLSX, …) |
| `metrics.json` | counters (HTTP status, claim results, supplier statuses, timeouts, deals, LLM calls, errors, tokens, fallbacks) and timings (supplier reply, decision delay after a reply, HTTP latency per endpoint, LLM latency per purpose, case duration) |
| `events.jsonl` → `llm_call`, `profile` | every model call (purpose, model, latency, tokens, output) and each supplier profile |
| `summary.json`, `report.md` | scores, C_open/C_deal/C_best/C_alt, price paths per thread, cost breakdown, claims, HTTP and timing tables |

## Architecture

```
config.py      settings from env / .env (ARENA_API_KEY, ARENA_URL, NEGOTIATOR_FINAL, …)
client.py      every endpoint; paced < 10 calls/s; safe retries with X-Move-Id; final-mode guard
telemetry.py   Recorder: events, HTTP log, metrics, transcripts, logging
data.py        data package in SQLite + facts.json; checkable Evidence (index moves, scorecard, notice, …)
profile.py     supplier traits from notes, letters, news, history (cash-short, approval ladder, hedged, …)
guards.py      hard rules before every send and accept: must-haves, alternative, valid sheets and IDs
lessons.py     lessons.md: what each case taught
session.py     Negotiation: threads, documents, costs (kit's C), send/accept/walk away, transcript
llm.py         one client for OpenAI-compatible and Anthropic APIs, switched by `provider:model`; telemetry
sim/           the supplier simulator: pricing fit, supplier model, calibration from runs/, local arena, bench
strategy/      Strategy protocol (prepare, decide, conclude, keepalive), baseline, llm_strategy
runner.py      play_case (one worker per thread, keepalive, deadline), play_many, play_final
report.py      summary.json, report.md, statistics across runs
cli.py         the `negotiator` command
```

A strategy only decides; `Negotiation` performs and records. To add one, implement `prepare / decide / conclude /
keepalive` (see `strategy/base.py`) and register it in `strategy/__init__.py`.

**Tactical (default):** the category goal sets the policy (anchor depth, Boulware beta, reciprocity, which
levers to trade); the supplier's profile adjusts it. Concessions are counted in C: Boulware over the rounds the
round limit and the clock leave, capped tit-for-tat by the supplier's last move (no move from it, no move from us;
a half step after two stalls; the third settles the thread). Each round sends up to three sheets of equal C: our
C-optimal terms, a trade the supplier values (early payment for the cash-short, a long commitment for those who want
volume), a pure price move. Arguments are chosen by profile; irrelevant or contradicted kinds are dropped. A final
offer is probed once only when walking would cost little. The guards (`guards.py`) refuse any accept that breaks a
must-have (read on the quote PDF's standard terms; unknown counts as broken) or loses to the alternative. The tactics
are inspired by ASTRA (Kwon et al., [DSincerity/ASTRA-NegoAgent](https://github.com/DSincerity/ASTRA-NegoAgent)):
opponent modelling, an optimiser over the cost function, offers of equal value, tit-for-tat - no code taken.

**Baseline:** a target price from the lower of opening and current price minus an anchor per category goal
(floored at should-cost, plus the sustainable margin where squeezing the supplier costs C); up to three
checkable arguments (short notice vs. contract, index moves below the asked increase, weak scorecard,
should-cost, alternative quote, a cheaper rival in an RFQ); a concession schedule; three term sheets per round
(C-optimal terms, a pure price move on the supplier's terms, a shorter-payment variant at equal C); it holds a
thread on agreed / final offer / stall / close enough / last round and accepts the cheapest standing sheet that
beats the alternative.

**Experiments** (`strategy/experiments.py`): the baseline with exactly one tactic changed each - `lowball` (a deeper
anchor), `questions` (three questions per e-mail), `polite` / `shelby` (tone), `budget` (a ceiling "set by
management" that we do not cross), `trade` (no move without a move, said so). They exist to measure a tactic, not to
win; the runs are in [`docs/benchmarks/`](docs/benchmarks/).

## Tests

```sh
uv run pytest        # unit tests + end to end against a local arena-sim (started by the tests)
uv run ruff check . && uv run ruff format --check .
```
