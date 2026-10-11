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


def test_a_5xx_after_an_outage_still_gets_its_retries() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) <= 5:
            raise httpx.ConnectError("down", request=request)
        if len(calls) <= 7:
            return httpx.Response(503, json={"detail": "busy"})
        return httpx.Response(200, json={"ok": True})

    assert _client(handler).request("GET", "/v1/me") == {"ok": True}


def test_connections_carry_tcp_keepalive() -> None:
    """A socket stranded by a network change fails in seconds, not at the 180 s read timeout."""
    import socket

    from negotiator.client import keepalive_options

    opts = keepalive_options()
    assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in opts
    assert len(opts) >= 2  # an idle time at least, on Linux and macOS
    client = ArenaClient(Settings.from_env(arena_url="http://arena.test", api_key="k"))
    assert client.http._transport._pool._socket_options == opts  # the default transport uses them
