# 2026-10-11 · tactical-llm · gpt-4o, gpt-4o-mini, claude haiku

## Result and cost

| Run | Strategy and model | E-mail budget | D01 | D02 | Mean | Texts used | Seconds per e-mail (mean / max) |
|---|---|---|---|---|---|---|---|
| `20261011-014212-sandbox-tactical` | `tactical` (control) | – | 0.649 | 0.587 | 0.618 | – | – |
| `20261011-014635-sandbox-tactical-llm` | `tactical-llm`, `claude-code:haiku` | 10 s | 0.649 | 0.587 | 0.618 | 0 of 9 (8 timeouts, 1 validator) | 8.0 / 8.8 |
| `20261011-014826-sandbox-tactical-llm` | `tactical-llm`, `claude-code:haiku` | 40 s | 0.649 | 0.587 | 0.618 | 8 of 9 (1 validator) | 11.4 / 14.5 |
| `20261011-020324-sandbox-tactical-llm` | `tactical-llm`, `compat:gpt-4o-mini` | 10 s | 0.649 | 0.587 | 0.618 | 6 of 9 (3 validator) | 2.8 / 5.3 |
| `20261011-020725-sandbox-tactical-llm+reader` | `tactical-llm+reader`, `compat:gpt-4o` | 10 s | 0.649 | 0.587 | 0.618 | 4 of 7 (3 validator) | 2.7 / 3.2 |

Practice, `20261011-020857-practice-tactical-llm+reader` (`compat:gpt-4o`, 10 s): P11 0.672 (C_deal 753,660), P08
0.507 (C_deal 1,046,948); `tactical` in P-27: 0.672 and 0.550.

Run cost: 2 practice sessions; LLM cost APPROX-NOT-MEASURED (OpenAI-compatible endpoint; sandbox gpt-4o-mini run
15,374 prompt and 677 completion tokens, gpt-4o run 17,321 and 1,105; haiku at 40 s 29,280 and 16,709); about
3 minutes wall time per run.

## Strategy

`strategy/written.py`, `writer.py`, `reader.py`; names `tactical-llm` and `tactical-llm+reader`; commit `3fbf436`.
`tactical` decides every number, sheet, cited ID, hold and accept; a model rewrites the e-mail text and (with
`+reader`) may add a lever the regular expressions missed. A text is checked in code before it is sent; a failed
check, an error or a spent budget sends tactical's template.

| Parameter | Value |
|---|---|
| `LLM_MESSAGE_BUDGET_S` | 10 (40 in one haiku run) |
| `WRITER_TIMEOUT_S`, `READER_TIMEOUT_S` | 8, 4 |

## Notes

- The e-mail budget held in every run: no e-mail took longer than its budget.
- The `openai` preset fails on gpt-4o and gpt-4o-mini with HTTP 400 (it sends `reasoning_effort`); the `compat`
  preset with `LLM_BASE_URL` works.
- One run per model: the texts vary between runs, the scores here did not.
