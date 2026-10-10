"""End to end against arena-sim: the client, the runner, telemetry and the report."""

import json

import pytest

from negotiator.client import ArenaClient, ArenaError, ForbiddenInFinal
from negotiator.config import Settings
from negotiator.data import WorldData
from negotiator.report import write_report
from negotiator.runner import play_many
from negotiator.strategy import STRATEGIES, BaselineStrategy
from negotiator.strategy.experiments import TACTICS
from negotiator.strategy.playbook import VARIANTS
from negotiator.telemetry import Recorder


def test_every_sim_case_closes_with_telemetry(sim: Settings, world: WorldData) -> None:
    recorder = Recorder(sim.runs_dir, "pytest")
    client = ArenaClient(sim, recorder)
    case_ids = [c["case_id"] for c in client.cases("practice")]
    outcomes = play_many(client, recorder, case_ids, lambda: BaselineStrategy(world), world, parallel=3)
    recorder.close()
    summary = write_report(recorder.dir, outcomes)

    assert summary["cases"] == len(case_ids) and not summary["failed"]
    assert all(o["deal"] and o["score"] is not None for o in summary["outcomes"])
    assert summary["claims"].get("contradicted", 0) == 0
    assert summary["claims"].get("duplicate", 0) == 0
    for name in ("events.jsonl", "http.jsonl", "metrics.json", "summary.json", "report.md", "run.log"):
        assert (recorder.dir / name).is_file(), name
    kinds = {json.loads(line)["kind"] for line in (recorder.dir / "events.jsonl").read_text().splitlines()}
    assert {"session_opened", "plan", "message_sent", "reply", "decision", "result"} <= kinds
    transcript = json.loads(next((recorder.dir / "sessions").glob("*.json")).read_text())
    assert transcript["case"] and transcript["decisions"] and transcript["outcome"]["c_deal"]


@pytest.mark.parametrize("name", list(TACTICS))
def test_every_experiment_closes_a_sim_case(sim: Settings, world: WorldData, name: str) -> None:
    recorder = Recorder(sim.runs_dir, f"pytest-{name}")
    client = ArenaClient(sim, recorder)
    case_id = client.cases("practice")[0]["case_id"]
    outcomes = play_many(client, recorder, [case_id], lambda: STRATEGIES[name](world, None), world, parallel=1)
    recorder.close()
    assert outcomes[0]["deal"] and outcomes[0]["strategy"] == name
    sent = [json.loads(x) for x in (recorder.dir / "events.jsonl").read_text().splitlines()]
    assert any(e["kind"] == "experiment" and e["tactic"] == name for e in sent)


@pytest.mark.parametrize("name", list(VARIANTS))
def test_every_playbook_variant_plays_a_sim_case(sim: Settings, world: WorldData, name: str) -> None:
    recorder = Recorder(sim.runs_dir, f"pytest-{name}")
    client = ArenaClient(sim, recorder)
    case_id = client.cases("practice")[0]["case_id"]
    outcomes = play_many(client, recorder, [case_id], lambda: STRATEGIES[name](world, None), world, parallel=1)
    recorder.close()
    assert outcomes[0]["strategy"] == name
    # the scripted supplier walks away from any offer below its final one: the closing offer costs the deal there
    assert outcomes[0]["deal"] == (VARIANTS[name].probe == "off")


def test_invalid_message_is_a_422(sim: Settings) -> None:
    client = ArenaClient(sim)
    session = client.open_session("case:S01")
    supplier = next(iter(session["threads"]))
    with pytest.raises(ArenaError) as err:
        client.send_message(session["session_id"], supplier, {"body": "x", "term_sheets": [{"terms": {}}]})
    assert err.value.status == 422
    client.walk_away(session["session_id"], supplier)


def test_final_mode_blocks_the_live_feed(sim: Settings) -> None:
    client = ArenaClient(Settings(**{**sim.__dict__, "final_mode": True}))
    with pytest.raises(ForbiddenInFinal):
        client.leaderboard("final")
    with pytest.raises(ForbiddenInFinal):
        client.results()
