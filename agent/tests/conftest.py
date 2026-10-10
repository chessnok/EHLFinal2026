import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from negotiator.config import REPO_ROOT, Settings
from negotiator.data import WorldData

DATA = REPO_ROOT / "negotiation-arena-kit" / "data"
SIM_BIN = Path(sys.executable).parent / "arena-sim"


@pytest.fixture(scope="session")
def world() -> WorldData:
    return WorldData(DATA)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def sim(tmp_path_factory) -> Settings:
    """arena-sim from the starter kit on a free port, without the 60 s clock, and a simulator key."""
    port = _free_port()
    proc = subprocess.Popen(
        [str(SIM_BIN), "serve", "--port", str(port), "--no-clock", "--data", str(DATA)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{url}/health", timeout=1).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            pytest.skip("arena-sim did not start")
        key = httpx.post(
            f"{url}/v1/register",
            json={"team_name": "pytest", "event_code": "sim"},
            headers={"X-Move-Id": "pytest-register"},
        ).json()["api_key"]
        runs = tmp_path_factory.mktemp("runs")
        os.environ.pop("NEGOTIATOR_FINAL", None)
        yield Settings.from_env(arena_url=url, api_key=key, runs_dir=Path(runs))
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
