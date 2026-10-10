"""The llm strategy end to end on arena-sim with a scripted model: it plays every case on tactical's mechanics."""

from negotiator.client import ArenaClient
from negotiator.config import Settings
from negotiator.data import WorldData
from negotiator.llm import LLMError
from negotiator.report import write_report
from negotiator.runner import play_many
from negotiator.strategy import LLMStrategy
from negotiator.telemetry import Recorder


class ScriptedLLM:
    """Profiles fail (the strategy must cope), moves trade the index clause and leak a figure and a budget."""

    def __init__(self) -> None:
        self.calls = 0

    def describe(self) -> str:
        return "scripted:test"

    def json(self, system: str, user: str, *, purpose: str = "llm", **_) -> dict:
        if purpose == "profile":
            raise LLMError("no profile in tests")
        self.calls += 1
        if self.calls % 5 == 0:
            raise LLMError("slow model")  # falls back to the tactical move
        return {
            "stance": "trade",
            "concession": 0.2,
            "lever": "index_clause",
            "evidence": [0],
            "ask_cost_breakdown": True,
            "question": "Could you confirm the lead time?",
            "message": "Thank you for your offer. We can pay EUR 12.50 at most. Our budget is tight. "
            "Please consider the options below.",
            "reason": "test",
        }


def test_llm_closes_every_sim_case_on_tactical_mechanics(sim: Settings, world: WorldData) -> None:
    recorder = Recorder(sim.runs_dir, "pytest-llm")
    client = ArenaClient(sim, recorder)
    case_ids = [c["case_id"] for c in client.cases("practice")]
    model = ScriptedLLM()
    outcomes = play_many(client, recorder, case_ids, lambda: LLMStrategy(world, model), world, parallel=3)
    recorder.close()
    summary = write_report(recorder.dir, outcomes)

    assert summary["cases"] == len(case_ids) and not summary["failed"], summary["failed"]
    assert all(o["deal"] and o["must_haves_ok"] is not False for o in summary["outcomes"]), [
        (o["case_id"], o["deal"], o["end_reason"], o["score"]) for o in summary["outcomes"]
    ]
    assert summary["claims"].get("contradicted", 0) == 0
    assert model.calls > 0
    sent = [
        line
        for path in (recorder.dir / "sessions").glob("*.md")
        for line in path.read_text(encoding="utf-8").splitlines()
        if "why we moved" not in line  # our telemetry keeps the model's raw answer; the e-mails must not
    ]
    assert not any("budget" in line.lower() for line in sent)  # position leaks never reach the supplier
    assert not any("12.50 at most" in line for line in sent)  # nor figures the model wrote
