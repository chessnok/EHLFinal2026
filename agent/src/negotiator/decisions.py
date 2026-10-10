"""Client for the OpenAI Decisions API (public beta): a model picks one of our options, fast and cheap.

  POST {OPENAI_BASE_URL or https://api.openai.com/v1}/decisions
  {"model": "gpt-6-luna", "input": "<shared evidence>",
   "questions": [{"type": "choice", "name": "...", "instructions": "...",
                  "choices": [{"value": "...", "description": "..."}]}]}
  -> {"answers": [{"type": "choice", "name": "...", "choice": "<value>",
                   "probabilities": [{"value", "probability"}], "confidence": 0.0}]}

Settings: OPENAI_API_KEY (required), DECISIONS_MODEL (default gpt-6-luna; the only supported model), OPENAI_BASE_URL,
DECISIONS_TIMEOUT_S (default 20). Docs: https://developers.openai.com/api/docs/guides/decisions

Every call is recorded: a `decisions_call` event (question, choice, probabilities, confidence, latency, error) and
metrics (`decisions.calls`, `decisions.errors`, `decisions.seconds`).
"""

import os
import time
from dataclasses import dataclass, field

import httpx

from negotiator.telemetry import Recorder, log

DEFAULT_MODEL = "gpt-6-luna"


class DecisionError(RuntimeError):
    pass


@dataclass
class Choice:
    value: str
    probabilities: dict[str, float]
    confidence: float | None
    extras: dict[str, dict] = field(default_factory=dict)  # answers to the extra questions, by name


def predicate(name: str, instructions: str) -> dict:
    """An extra yes/no question: the answer is the probability that it holds."""
    return {"type": "predicate", "name": name, "instructions": instructions}


def score(name: str, instructions: str, levels: list[tuple[str, str]]) -> dict:
    """An extra graded question: `levels` are (label, description), lowest first; the answer is a (fractional) index."""
    return {
        "type": "score",
        "name": name,
        "instructions": instructions,
        "levels": [{"label": label, "description": desc} for label, desc in levels],
    }


def _extra(answer: dict) -> dict:
    """An extra answer, kept small for telemetry."""
    kind = answer.get("type")
    if kind == "predicate":
        return {"probability": answer.get("probability")}
    if kind == "score":
        return {
            "score": answer.get("score"),
            "confidence": answer.get("confidence"),
            "probabilities": {p.get("label"): p.get("probability") for p in answer.get("probabilities") or []},
        }
    return {"type": kind}


class DecisionsClient:
    def __init__(self, recorder: Recorder | None = None) -> None:
        self.api_key = os.environ.get("OPENAI_API_KEY", "")
        if not self.api_key:
            raise ValueError("the Decisions API needs OPENAI_API_KEY in the environment or .env")
        self.model = os.environ.get("DECISIONS_MODEL", DEFAULT_MODEL)
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.timeout = float(os.environ.get("DECISIONS_TIMEOUT_S", "20"))
        self.recorder = recorder
        self.http = httpx.Client(
            timeout=self.timeout,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )

    def describe(self) -> str:
        return f"openai-decisions:{self.model}"

    def choose(
        self,
        input_text: str,
        instructions: str,
        choices: list[dict],
        *,
        name: str = "choice",
        extra_questions: list[dict] | None = None,
        context: dict | None = None,
    ) -> Choice:
        """One `choice` question - `choices` are {"value", "description"} - plus optional extra questions on the same
        evidence (`predicate`, `score`), answered in the same call. Raises DecisionError if the choice fails; a failed
        extra question only leaves its answer out."""
        body = {
            "model": self.model,
            "input": input_text,
            "questions": [
                {"type": "choice", "name": name, "instructions": instructions, "choices": choices},
                *(extra_questions or []),
            ],
        }
        start = time.perf_counter()
        error, answer, answers = None, {}, []
        try:
            r = self.http.post(f"{self.base_url}/decisions", json=body)
            if r.status_code >= 400:
                raise DecisionError(f"HTTP {r.status_code}: {r.text[:300]}")
            answers = r.json().get("answers") or []
            answer = next((a for a in answers if a.get("name") == name), answers[0] if answers else {})
            if answer.get("type") == "refusal":
                raise DecisionError("the model refused to answer")
            value = answer.get("choice")
            if value not in {c["value"] for c in choices}:
                raise DecisionError(f"unexpected choice {value!r}")
            probs = {p.get("value"): p.get("probability") for p in answer.get("probabilities") or []}
            extras = {a.get("name"): _extra(a) for a in answers if a.get("name") != name}
            return Choice(value, probs, answer.get("confidence"), extras)
        except (httpx.HTTPError, ValueError, KeyError, DecisionError) as e:
            error = f"{type(e).__name__}: {e}"
            raise DecisionError(error) from e
        finally:
            extras = {a.get("name"): _extra(a) for a in answers if a.get("name") != name}
            self._record(name, time.perf_counter() - start, answer, extras, error, len(input_text), context, body)

    def _record(self, name, elapsed, answer, extras, error, input_chars, context, body=None) -> None:
        if self.recorder:
            m = self.recorder.metrics
            m.incr("decisions.calls")
            m.observe("decisions.seconds", elapsed)
            if error:
                m.incr("decisions.errors")
            self.recorder.event(
                "decisions_call",
                model=self.describe(),
                question=name,
                seconds=round(elapsed, 2),
                input_chars=input_chars,
                choice=answer.get("choice"),
                probabilities=answer.get("probabilities"),
                confidence=answer.get("confidence"),
                ok=error is None,
                error=error,
                _input=body,  # to the tracing sink only, not to events.jsonl
                **(context or {}),
            )
        if error:
            log.warning("Decisions API failed after %.1fs: %s", elapsed, error)
        else:
            log.debug(
                "Decisions API %.1fs -> %s (confidence %s)", elapsed, answer.get("choice"), answer.get("confidence")
            )
