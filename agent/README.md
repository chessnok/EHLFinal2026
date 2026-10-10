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
| `negotiator play <case_id> [--strategy baseline]` | play one case, with telemetry and a report |
| `negotiator run --set sandbox\|practice [--cases …] [--parallel N]` | many cases in parallel (default: every hosted case of the set) |
| `negotiator final [--parallel 10]` | the Live Final: waits for each wave, plays its cases within the cap |
| `negotiator report [run_id\|latest]` · `stats` | rebuild a run's report · best/mean score per case across all runs |

Global options: `--url` (e.g. a local `arena-sim`), `--key`, `--json`, `-v`.

**Quota:** practice is 200 sessions per team per rolling 24 h; sandbox (`case:D01`, `case:D02`) and `arena-sim`
are free. Develop on sandbox and the simulator, spend practice deliberately.

```sh
uv run arena-sim serve --port 8100 --data ../negotiation-arena-kit/data          # local API, scripted supplier
uv run negotiator --url http://127.0.0.1:8100 register "Team" sim                  # a simulator key
uv run negotiator --url http://127.0.0.1:8100 --key <sim key> run --set practice
```

## Telemetry: `runs/<run_id>/`

| File | Content |
|---|---|
| `events.jsonl` | every event: `session_opened` (opening C per supplier), `plan`, `message_sent` (sheets with C), `reply` (status, terms, C, claim results, signals, latency), `attachment`, `thread_hold`, `decision`, `conflict`, `result` |
| `http.jsonl` | every HTTP attempt: endpoint, status, latency, retry, move id, pacing wait, practice quota left |
| `run.log` | the human-readable log (debug level) |
| `sessions/<sid>.json` | the whole case: case file, e-mails both ways, documents as text, decisions with rationale, result, the arena's trace and back office |
| `sessions/<sid>/` | the documents suppliers attached (quote PDF, cost breakdown XLSX, …) |
| `metrics.json` | counters (HTTP status, claim results, supplier statuses, timeouts, deals) and timings (supplier reply, decision delay after a reply, HTTP latency per endpoint, case duration) |
| `summary.json`, `report.md` | scores, C_open/C_deal/C_best/C_alt, price paths per thread, cost breakdown, claims, HTTP and timing tables |

## Architecture

```
config.py      settings from env / .env (ARENA_API_KEY, ARENA_URL, NEGOTIATOR_FINAL, …)
client.py      every endpoint; paced < 10 calls/s; safe retries with X-Move-Id; final-mode guard
telemetry.py   Recorder: events, HTTP log, metrics, transcripts, logging
data.py        data package in SQLite + facts.json; checkable Evidence (index moves, scorecard, notice, …)
session.py     Negotiation: threads, documents, costs (kit's C), send/accept/walk away, transcript
strategy/      Strategy protocol (prepare, decide, conclude, keepalive) and the baseline
runner.py      play_case (one worker per thread, keepalive, deadline), play_many, play_final
report.py      summary.json, report.md, statistics across runs
cli.py         the `negotiator` command
```

A strategy only decides; `Negotiation` performs and records. To add one, implement `prepare / decide / conclude /
keepalive` (see `strategy/base.py`) and register it in `strategy/__init__.py`.

**Baseline:** a target price from the lower of opening and current price minus an anchor per category goal
(floored at should-cost, plus the sustainable margin where squeezing the supplier costs C); up to three
checkable arguments (short notice vs. contract, index moves below the asked increase, weak scorecard,
should-cost, alternative quote, a cheaper rival in an RFQ); a concession schedule; three term sheets per round
(C-optimal terms, a pure price move on the supplier's terms, a shorter-payment variant at equal C); it holds a
thread on agreed / final offer / stall / close enough / last round and accepts the cheapest standing sheet that
beats the alternative.

## Tests

```sh
uv run pytest        # unit tests + end to end against a local arena-sim (started by the tests)
uv run ruff check . && uv run ruff format --check .
```
