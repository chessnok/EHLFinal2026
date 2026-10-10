"""Optional Langfuse tracing: every telemetry event of a run, also sent to Langfuse.

On when LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set (LANGFUSE_HOST for a self-hosted or regional
server); off and free otherwise. One Langfuse session per run, one trace per case, and in it, in order: the
supplier's quotes, each model call (prompt, output, tokens, cost where measured), each decision, each e-mail both
ways, and the result with the arena's score. It works the same against the arena, the sandbox and a simulator.

It only writes, in the background: nothing here reads the live feed, and a slow or unreachable Langfuse never
delays a move - an error is logged once and tracing stops for the run.
"""

import logging
import os

log = logging.getLogger("negotiator.tracing")

GENERATIONS = {"llm_call", "decisions_call"}
OUTPUT_FIELDS = {
    "session_opened": ("opening", "c_alt"),
    "message_sent": ("subject", "body", "term_sheets", "refs"),
    "reply": ("status", "terms", "body", "claim_results", "missing_fields", "signals", "c", "attachments"),
    "decision": ("action", "sheets", "term_sheet_id"),
    "result": ("deal", "supplier_id", "terms", "score", "c_open", "c_deal", "c_alt", "c_best", "cost_breakdown",
               "end_reason", "must_haves_ok", "rounds", "replay_url"),
    "llm_call": ("output",),
    "decisions_call": ("choice", "probabilities", "confidence"),
}  # fmt: skip
SKIP = {"ts", "t", "kind", "session_id", "case_id"}


def enabled() -> bool:
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))


def sink_from_env(run_id: str) -> "LangfuseSink | None":
    """A sink for this run if Langfuse is configured and importable, else None."""
    if not enabled():
        return None
    try:
        from langfuse import Langfuse

        return LangfuseSink(run_id, Langfuse())
    except Exception as e:  # tracing must never stop a run
        log.warning("Langfuse tracing is off: %s", e)
        return None


class LangfuseSink:
    def __init__(self, run_id: str, client) -> None:
        self.run_id, self.client, self.failed = run_id, client, False
        self.case_of: dict[str, str] = {}  # session id -> case id
        self.titles: dict[str, str] = {}  # case id -> "case:P01 · strategy"
        self.waiting: dict[str, list] = {}  # events of a session whose case is not known yet

    def _title(self, kind: str, f: dict) -> str:
        who, rnd = f.get("supplier_id"), f.get("round")
        tail = f" r{rnd}" if rnd is not None else ""
        if kind == "message_sent":
            return f"buyer -> {who}{tail}"
        if kind == "reply":
            return f"{who} -> buyer{tail} [{f.get('status')}]"
        if kind == "llm_call":
            return f"llm: {f.get('purpose')}"
        if kind == "decisions_call":
            return f"decision model: {f.get('question')}"
        return f"{kind}{' ' + who if who else ''}{tail}"

    def event(self, kind: str, fields: dict, private: dict) -> None:
        if self.failed:
            return
        try:
            self._send(kind, fields, private)
        except Exception as e:
            self.failed = True
            log.warning("Langfuse tracing stopped for this run: %s", e)

    def _send(self, kind: str, f: dict, private: dict) -> None:
        from langfuse import propagate_attributes

        # one trace per case of the run: model calls name the case, some session events only the session
        sid, case = f.get("session_id"), f.get("case_id")
        if sid and case and sid not in self.case_of:
            self.case_of[sid] = case
            for held in self.waiting.pop(sid, []):
                self._send(*held)
        case = case or self.case_of.get(sid)
        if sid and not case:
            self.waiting.setdefault(sid, []).append((kind, f, private))
            return
        if case and f.get("strategy") and case not in self.titles:
            self.titles[case] = f"{case} · {f['strategy']}"
        trace_id = self.client.create_trace_id(seed=f"{self.run_id}/{case or 'run'}")
        context = {"trace_id": trace_id}
        out_keys = OUTPUT_FIELDS.get(kind, ())
        output = {k: f[k] for k in out_keys if f.get(k) is not None} or None
        meta = {k: v for k, v in f.items() if k not in SKIP and k not in out_keys and v is not None}
        name = self.titles.get(case, case) if case else f"run {self.run_id}"
        with propagate_attributes(session_id=self.run_id, trace_name=name):
            if kind in GENERATIONS:
                usage = {"input": f.get("prompt_tokens"), "output": f.get("completion_tokens")}
                cost = f.get("cost_usd")
                self.client.start_observation(
                    trace_context=context,
                    name=self._title(kind, f),
                    as_type="generation",
                    model=str(f.get("model", "")).split(":", 1)[-1],
                    input=private.get("_input"),
                    output=output,
                    metadata=meta,
                    usage_details={k: v for k, v in usage.items() if v is not None} or None,
                    cost_details={"total": cost} if cost is not None else None,  # only what the provider measured
                    level="ERROR" if f.get("ok") is False else None,
                    status_message=f.get("error"),
                ).end()
            elif kind in OUTPUT_FIELDS:
                rationale = f.get("rationale") if kind == "decision" else None
                self.client.start_observation(
                    trace_context=context, name=self._title(kind, f), input=rationale, output=output, metadata=meta
                ).end()
            else:
                level = "ERROR" if kind in ("case_error", "case_failed") else None
                self.client.create_event(trace_context=context, name=self._title(kind, f), metadata=meta, level=level)
        if kind == "result" and f.get("score") is not None:
            self.client.create_score(trace_id=trace_id, name="arena_score", value=float(f["score"]))
            if f.get("saved_eur") is not None:
                self.client.create_score(trace_id=trace_id, name="saved_eur", value=float(f["saved_eur"]))

    def close(self) -> None:
        try:
            self.client.flush()
        except Exception as e:
            log.warning("Langfuse flush failed: %s", e)
