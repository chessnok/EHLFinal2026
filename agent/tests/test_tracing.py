"""Langfuse tracing: off without keys, one trace per case, and never in the way of a run."""

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from negotiator.telemetry import Recorder
from negotiator.tracing import LangfuseSink, enabled


def test_off_without_keys(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert not enabled()
    recorder = Recorder(tmp_path, "pytest")
    assert recorder.sink is None
    recorder.event("llm_call", purpose="x", _input={"user": "secret prompt"})
    recorder.close()
    assert "secret prompt" not in (recorder.dir / "events.jsonl").read_text()  # prompts stay out of the event log


def test_a_case_is_one_trace_with_calls_and_e_mails() -> None:
    from langfuse import Langfuse

    exporter = InMemorySpanExporter()
    client = Langfuse(public_key="pk-test", secret_key="sk-test", host="http://127.0.0.1:9", span_exporter=exporter)
    sink = LangfuseSink("run-1", client)
    sink.event("attachment", {"session_id": "s1", "name": "quote.pdf"}, {})  # before the case is known: held back
    sink.event("session_opened", {"session_id": "s1", "case_id": "case:P01", "strategy": "llm", "opening": {}}, {})
    sink.event("llm_call", {"case_id": "case:P01", "purpose": "move", "model": "openai:m", "output": "{}", "ok": True,
                            "prompt_tokens": 10, "completion_tokens": 2}, {"_input": {"user": "hello"}})  # fmt: skip
    sink.event("message_sent", {"session_id": "s1", "case_id": "case:P01", "supplier_id": "sup:1", "round": 1,
                                "body": "Dear supplier"}, {})  # fmt: skip
    sink.event("reply", {"session_id": "s1", "case_id": "case:P01", "supplier_id": "sup:1", "round": 1,
                         "status": "open", "body": "Dear buyer"}, {})  # fmt: skip
    sink.event("session_opened", {"session_id": "s2", "case_id": "case:P02", "strategy": "llm"}, {})
    client.flush()
    assert not sink.failed
    spans = exporter.get_finished_spans()
    names = [s.name for s in spans]
    assert {"llm: move", "buyer -> sup:1 r1", "sup:1 -> buyer r1 [open]", "attachment"} <= set(names)
    first = {s.context.trace_id for s in spans if s.name != "session_opened" or "P02" not in str(s.attributes)}
    by_trace = {}
    for s in spans:
        by_trace.setdefault(s.context.trace_id, []).append(s.name)
    assert len(by_trace) == 2 and max(len(v) for v in by_trace.values()) == 5 and first


def test_a_failing_sink_does_not_stop_the_run() -> None:
    class Broken:
        def create_trace_id(self, **_):
            raise RuntimeError("down")

    sink = LangfuseSink("run-1", Broken())
    sink.event("reply", {"session_id": "s1", "case_id": "case:P01"}, {})
    sink.event("reply", {"session_id": "s1", "case_id": "case:P01"}, {})
    assert sink.failed
