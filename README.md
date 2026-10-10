# EHL Final 2026 – Tacto Negotiation Arena

Our AI buyer agent for the [Tacto Negotiation Arena](negotiation-arena-kit/README.md): it reads the case file
and the data package, negotiates by e-mail with the arena's supplier bots and closes the cheapest total deal.

```
agent/                   negotiator: API client, runner, telemetry, reports, strategies (Python 3.12, uv)
negotiation-arena-kit/   git submodule: brief, API docs, data package, starter kit (read-only)
```

## Setup

```sh
git clone --recurse-submodules git@github.com:chessnok/EHLFinal2026.git   # or: git submodule update --init
cp .env.example .env                                                       # then fill in the keys; git-ignored
make install
make me                                                                     # team and practice quota
```

## Play

```sh
make sandbox                                    # the free sandbox cases against real supplier bots
cd agent && uv run negotiator play case:P05     # one practice case (200 per team per 24 h)
cd agent && uv run negotiator run --set practice --parallel 4
make stats                                      # best and mean score per case across all runs
NEGOTIATOR_FINAL=1 make final                   # Live Final: waits for each wave, plays it in parallel
```

Every run writes its telemetry, transcripts and a report to `agent/runs/<run_id>/` (git-ignored). Details,
the architecture and the baseline strategy: [`agent/README.md`](agent/README.md). The rules of the game:
[`negotiation-arena-kit/brief/brief.md`](negotiation-arena-kit/brief/brief.md).

```sh
make test && make lint
```
