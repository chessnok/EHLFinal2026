"""The Live Final's loop: a failed poll or a failed opening must not cost a wave's cases."""

import json
from types import SimpleNamespace

from negotiator import runner
from negotiator.client import ArenaError
from negotiator.telemetry import Recorder


def events(recorder: Recorder, kind: str) -> list[dict]:
    rows = [json.loads(x) for x in (recorder.dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    return [r for r in rows if r["kind"] == kind]


class FinalCases:
    """`GET /v1/cases?set=final` as a script: one answer (or error) per poll, the last one repeated."""

    def __init__(self, *answers) -> None:
        self.settings = SimpleNamespace(final_mode=True)
        self.answers, self.polls = list(answers), 0

    def cases(self, set_: str) -> list[dict]:
        assert set_ == "final"
        answer = self.answers[min(self.polls, len(self.answers) - 1)]
        self.polls += 1
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_the_final_loop_survives_a_failed_poll(tmp_path, monkeypatch) -> None:
    """A 5xx, a transport error (the client raises them as ArenaError, status 0) or a bad body while the case
    list is read: the loop polls again instead of ending the final. A 403 is still 'no wave yet'."""
    played = []
    monkeypatch.setattr(runner, "play_case", lambda client, rec, case_id, *a, **k: played.append(case_id) or {})
    wave = [{"case_id": "case:F01", "wave": 1, "open": True, "seconds_left": 300}]
    client = FinalCases(
        ArenaError(503, "unavailable", "GET", "/v1/cases"),
        ArenaError(0, "ConnectError: refused", "GET", "/v1/cases"),
        ArenaError(403, "the final has not started", "GET", "/v1/cases"),
        ValueError("not JSON"),
        wave,
        [{**wave[0], "open": False, "seconds_left": 0}],
    )
    recorder = Recorder(tmp_path, "final")
    out = runner.play_final(client, recorder, lambda: None, waves=1, poll=0.0)  # type: ignore[arg-type]
    recorder.close()
    assert played == ["case:F01"] and out == [{}]
    assert [e["status"] for e in events(recorder, "final_poll_failed")] == [503, 0, None]
