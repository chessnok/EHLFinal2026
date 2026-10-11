"""The Sunday release unpacks into one more top-level folder; it must still be loaded."""

import json

from negotiator.config import Settings
from negotiator.data import WorldData
from negotiator.data import _release_root as release_root


def test_release_one_folder_down_is_loaded(tmp_path) -> None:
    inner = tmp_path / "release-sunday" / "release-sunday"
    inner.mkdir(parents=True)
    (inner / "facts.json").write_text(json.dumps({"news:test-release": {"topic": "insolvency"}}), encoding="utf-8")
    assert release_root(tmp_path / "release-sunday") == inner
    world = WorldData(Settings.from_env().data_dir, tmp_path / "release-sunday")
    assert world.release == inner and "news:test-release" in world.facts


def test_missing_release_is_none(tmp_path) -> None:
    assert release_root(tmp_path / "nothing-here") is None
    (tmp_path / "empty").mkdir()
    assert release_root(tmp_path / "empty") is None
