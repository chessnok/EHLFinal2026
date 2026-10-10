"""Settings from the environment, with `.env` files as defaults (real environment variables win)."""

import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # agent/
REPO_ROOT = PACKAGE_ROOT.parent


def load_env_files() -> None:
    """Read KEY=VALUE lines from .env in the working directory, agent/ and the repo root."""
    seen = set()
    for path in (Path.cwd() / ".env", PACKAGE_ROOT / ".env", REPO_ROOT / ".env"):
        path = path.resolve()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        for line in path.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            key, value = key.strip(), value.strip().strip("\"'")
            if sep and key and value and not key.startswith("#"):
                os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    arena_url: str
    api_key: str | None
    data_dir: Path  # the data package v1 (facts.json, data/*.csv, correspondence/)
    release_dir: Path  # the Sunday release, once downloaded
    runs_dir: Path  # telemetry, transcripts and reports, one folder per run
    final_mode: bool  # Live Final: the live feed, leaderboard and results are off limits

    @classmethod
    def from_env(cls, **overrides) -> "Settings":
        load_env_files()
        env = os.environ
        settings = cls(
            arena_url=env.get("ARENA_URL", "https://arena.tacto.ai").rstrip("/"),
            api_key=env.get("ARENA_API_KEY") or None,
            data_dir=Path(env.get("NEGOTIATOR_DATA", REPO_ROOT / "negotiation-arena-kit" / "data")),
            release_dir=Path(env.get("NEGOTIATOR_RELEASE", PACKAGE_ROOT / "data" / "release-sunday")),
            runs_dir=Path(env.get("NEGOTIATOR_RUNS", PACKAGE_ROOT / "runs")),
            final_mode=env.get("NEGOTIATOR_FINAL", "0") == "1",
        )
        return cls(**{**settings.__dict__, **overrides}) if overrides else settings
