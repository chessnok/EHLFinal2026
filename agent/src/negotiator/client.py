"""Instrumented client for every endpoint of the arena API v1 (see negotiation-arena-kit/brief/api.md).

- Paced below the 10 calls/s limit per key, across all threads.
- Every POST carries an X-Move-Id; retries (dropped connection, 5xx, short 429) reuse it, so the arena
  answers what it already did instead of playing a move twice.
- Every attempt is written to the run's http.jsonl with its latency; counters go to the metrics.
- In final mode the live feed, leaderboard and results raise: the agent must not read them.
"""

import threading
import time
import uuid
from typing import Any

import httpx

from negotiator.config import Settings
from negotiator.telemetry import Recorder, log

TIMEOUT_S = 180.0  # a supplier reply can take about a minute, plus queueing on the session
CALLS_PER_SECOND = 9.0
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_RETRY_AFTER_S = 5
REMAINING_HEADER = "X-Practice-Remaining"
USER_AGENT = "negotiator/0.1 (Undeterministic Tornado)"


class ArenaError(Exception):
    def __init__(self, status: int, detail: Any, method: str = "", path: str = "") -> None:
        super().__init__(f"{method} {path} -> HTTP {status}: {detail}")
        self.status, self.detail, self.method, self.path = status, detail, method, path

    @property
    def quota_used_up(self) -> bool:
        return self.status == 429 and str(self.detail).startswith("practice limit")


class ForbiddenInFinal(RuntimeError):
    """The Live Final forbids the agent from reading the live feed, leaderboard and results."""


class _Pacer:
    """Spaces calls evenly across all threads of the process."""

    def __init__(self, rate: float) -> None:
        self.interval, self._next, self._lock = 1.0 / rate, 0.0, threading.Lock()

    def wait(self) -> float:
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next - now)
            self._next = max(now, self._next) + self.interval
        if delay:
            time.sleep(delay)
        return delay


class ArenaClient:
    def __init__(
        self,
        settings: Settings,
        recorder: Recorder | None = None,
        *,
        retries: int = 3,
        timeout: float = TIMEOUT_S,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.settings, self.recorder, self.retries = settings, recorder, retries
        headers = {"User-Agent": USER_AGENT}
        if settings.api_key:
            headers["X-API-Key"] = settings.api_key
        self.http = httpx.Client(base_url=settings.arena_url, headers=headers, timeout=timeout, transport=transport)
        self.pacer = _Pacer(CALLS_PER_SECOND)
        self.practice_remaining: int | None = None

    # ------------------------------------------------------------------ core
    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict | None = None,
        params: dict | None = None,
        raw: bool = False,
        context: dict | None = None,
    ):
        move_id = uuid.uuid4().hex if method == "POST" else None
        headers = {"X-Move-Id": move_id} if move_id else {}
        endpoint = _endpoint(path)
        response = None
        for attempt in range(self.retries + 1):
            waited = self.pacer.wait()
            start = time.perf_counter()
            error = None
            try:
                response = self.http.request(method, path, json=body, params=params, headers=headers)
            except httpx.TransportError as exc:
                error = f"{type(exc).__name__}: {exc}"
            elapsed = time.perf_counter() - start
            self._record(
                method,
                path,
                endpoint,
                response if error is None else None,
                elapsed,
                attempt,
                move_id,
                waited,
                error,
                context,
            )
            if error is not None:
                if attempt == self.retries:
                    raise ArenaError(0, error, method, path)
                time.sleep(0.5 * 2**attempt)
                continue
            retry_after = response.headers.get("Retry-After", "")
            short = retry_after.isdigit() and int(retry_after) <= MAX_RETRY_AFTER_S
            retryable = response.status_code in RETRY_STATUS and not (response.status_code == 429 and not short)
            if not retryable or attempt == self.retries:
                break
            if self.recorder:
                self.recorder.metrics.incr("http.retry")
            time.sleep(float(retry_after) if retry_after.isdigit() else 0.5 * 2**attempt)

        assert response is not None
        if (left := response.headers.get(REMAINING_HEADER, "")).isdigit():
            self.practice_remaining = int(left)
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except (ValueError, AttributeError):
                detail = response.text
            raise ArenaError(response.status_code, detail, method, path)
        if raw:
            return response.content
        return response.json() if response.content else None

    def _record(self, method, path, endpoint, response, elapsed, attempt, move_id, waited, error, context):
        status = response.status_code if response is not None else 0
        if self.recorder:
            m = self.recorder.metrics
            m.incr("http.calls")
            m.incr(f"http.status.{status}")
            m.observe(f"http.latency.{method} {endpoint}", elapsed)
            if waited:
                m.observe("http.pacing_wait", waited)
            self.recorder.http(
                method=method,
                path=path,
                endpoint=endpoint,
                status=status,
                ms=round(elapsed * 1000, 1),
                attempt=attempt,
                move_id=move_id,
                paced_ms=round(waited * 1000, 1),
                error=error,
                bytes=len(response.content) if response is not None else 0,
                practice_remaining=response.headers.get(REMAINING_HEADER) if response is not None else None,
                **(context or {}),
            )
        level = "warning" if status >= 400 or error else "debug"
        getattr(log, level)(
            "%s %s -> %s in %.0f ms%s",
            method,
            path,
            status or error,
            elapsed * 1000,
            f" (retry {attempt})" if attempt else "",
        )

    def _guard_live_feed(self, what: str) -> None:
        if self.settings.final_mode:
            raise ForbiddenInFinal(f"{what} is off limits for the agent during the Live Final")

    # ------------------------------------------------------------------ public, no key
    def health(self) -> dict:
        return self.request("GET", "/health")

    def data_index(self) -> dict:
        """The data downloads: the package, and the Sunday release once public."""
        return self.request("GET", "/v1/data")

    def download_data(self, name: str = "package") -> bytes:
        return self.request("GET", f"/v1/data/{name}.zip", raw=True)

    # ------------------------------------------------------------------ team
    def me(self) -> dict:
        """Team, practice quota (used/left/resets_at) and best score per practice case."""
        return self.request("GET", "/v1/me")

    def register(self, team_name: str, event_code: str) -> dict:
        """arena-sim only: the hosted arena issues keys through /apply."""
        return self.request("POST", "/v1/register", body={"team_name": team_name, "event_code": event_code})

    def cases(self, set_: str = "practice") -> list[dict]:
        """Case files: practice (hosted ones carry hosted=true), sandbox, final (wave by wave)."""
        return self.request("GET", "/v1/cases", params={"set": set_})

    def sessions(self, set_: str = "practice") -> list[dict]:
        return self.request("GET", "/v1/sessions", params={"set": set_})

    # ------------------------------------------------------------------ a negotiation
    def open_session(self, case_id: str) -> dict:
        """Opens a case: session_id, case, threads (each supplier's quote e-mail), opening."""
        return self.request("POST", "/v1/sessions", body={"case_id": case_id}, context={"case_id": case_id})

    def session(self, session_id: str) -> dict:
        """State; after the end also result, trace and replay_url."""
        return self.request("GET", f"/v1/sessions/{session_id}", context={"session_id": session_id})

    def thread(self, session_id: str, supplier_id: str) -> dict:
        return self.request(
            "GET",
            f"/v1/sessions/{session_id}/threads/{supplier_id}",
            context={"session_id": session_id, "supplier_id": supplier_id},
        )

    def send_message(self, session_id: str, supplier_id: str, message: dict) -> dict:
        """An e-mail to one supplier; returns its reply. With `action` it closes the case."""
        return self.request(
            "POST",
            f"/v1/sessions/{session_id}/threads/{supplier_id}/messages",
            body={"message": message},
            context={"session_id": session_id, "supplier_id": supplier_id},
        )

    def accept(self, session_id: str, supplier_id: str, term_sheet_id: str) -> dict:
        return self.send_message(
            session_id, supplier_id, {"action": {"type": "accept", "term_sheet_id": term_sheet_id}}
        )

    def walk_away(self, session_id: str, supplier_id: str) -> dict:
        return self.send_message(session_id, supplier_id, {"action": {"type": "walk_away"}})

    def attachment(self, session_id: str, attachment_id: str) -> bytes:
        return self.request(
            "GET",
            f"/v1/sessions/{session_id}/attachments/{attachment_id}",
            raw=True,
            context={"session_id": session_id, "attachment_id": attachment_id},
        )

    def backoffice(self, session_id: str) -> dict:
        """The supplier's roles talking internally; only after the case (final: after the final)."""
        return self.request("GET", f"/v1/sessions/{session_id}/backoffice", context={"session_id": session_id})

    # ------------------------------------------------------------------ the structured path
    def move(self, session_id: str, supplier_id: str, move: dict) -> dict:
        """{"type": "offer", "offer_id", "terms", "claims": [{"type", "refs", "asserted"}], "text"}"""
        return self.request(
            "POST",
            f"/v1/sessions/{session_id}/moves",
            body={"supplier_id": supplier_id, "move": move},
            context={"session_id": session_id, "supplier_id": supplier_id},
        )

    def accept_offer(self, session_id: str, offer_id: str) -> dict:
        return self.request(
            "POST",
            f"/v1/sessions/{session_id}/accept",
            body={"offer_id": offer_id},
            context={"session_id": session_id},
        )

    def walk_away_structured(self, session_id: str) -> dict:
        return self.request("POST", f"/v1/sessions/{session_id}/walk_away", context={"session_id": session_id})

    # ------------------------------------------------------------------ for people, not for the agent in the final
    def leaderboard(self, set_: str = "practice") -> dict:
        self._guard_live_feed("the leaderboard")
        return self.request("GET", "/v1/leaderboard", params={"set": set_})

    def results(self, team_name: str | None = None) -> dict:
        self._guard_live_feed("the results")
        return self.request("GET", f"/v1/results/{team_name}" if team_name else "/v1/results")

    def replay_url(self, session_id: str) -> str:
        return f"{self.settings.arena_url}/replay/{session_id}"

    def close(self) -> None:
        self.http.close()


def _endpoint(path: str) -> str:
    """The path with ids replaced, for latency metrics per endpoint."""
    parts = path.split("?")[0].strip("/").split("/")
    names = {2: "{sid}", 4: "{supplier}"} if len(parts) > 2 and parts[1] == "sessions" else {}
    if len(parts) > 4 and parts[3] == "attachments":
        names = {2: "{sid}", 4: "{attachment}"}
    return "/" + "/".join(names.get(i, p) for i, p in enumerate(parts))
