"""The arena client: a dropped network is tried again with the same X-Move-Id for a while, not three quick times."""

import httpx
import pytest

from negotiator import client as client_mod
from negotiator.client import ArenaClient, ArenaError
from negotiator.config import Settings


def _client(handler, **kw) -> ArenaClient:
    settings = Settings.from_env(arena_url="http://arena.test", api_key="k")
    return ArenaClient(settings, transport=httpx.MockTransport(handler), **kw)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(client_mod.time, "sleep", lambda s: None)


def test_a_dropped_network_is_tried_again_with_the_same_move_id() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["X-Move-Id"])
        if len(seen) <= 6:  # more than the three quick retries: a DNS outage of some seconds
            raise httpx.ConnectError("nodename nor servname provided", request=request)
        return httpx.Response(200, json={"ok": True})

    assert _client(handler).request("POST", "/v1/sessions/x/threads/s/messages", body={}) == {"ok": True}
    assert len(seen) == 7 and len(set(seen)) == 1


def test_a_network_that_stays_down_ends_in_an_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    with pytest.raises(ArenaError) as e:
        _client(handler, transport_retry_s=0.0).request("GET", "/v1/me")
    assert e.value.status == 0
