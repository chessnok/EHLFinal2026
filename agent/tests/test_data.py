from negotiator.client import _endpoint
from negotiator.data import WorldData


def test_tables_load(world: WorldData) -> None:
    tables = world.tables()
    assert tables["po_lines"] == 5400
    assert tables["index_values"] > 2000


def test_index_change_matches_the_published_example(world: WorldData) -> None:
    earlier, later, pct = world.index_change("PPI-D351")
    assert (earlier, later) == ("idx:PPI-D351@2025-08", "idx:PPI-D351@2026-08")
    assert round(pct, 1) == -3.7  # the figure in the kit's worked example


def test_evidence_is_checkable(world: WorldData) -> None:
    evidence = world.evidence_indices(["part:310010"], asked_pct=9.5)
    assert evidence and all(world.fact(ref) for e in evidence for ref in e.refs)
    notice = world.evidence_notice("doc:20260911-70110-P01", "sup:70110")
    assert notice and notice[0].meta == {"given": 51, "agreed": 90}


def test_case_facts_stay_in_their_case(world: WorldData) -> None:
    """The final plays cases in parallel on one WorldData: a hidden case's facts belong to that case alone."""
    a = world.with_case({"facts": {"doc:HIDDEN-A": {"type": "doc"}}})
    b = world.with_case({"facts": {"doc:HIDDEN-B": {"type": "doc"}}})
    assert a.fact("doc:HIDDEN-A") and not a.fact("doc:HIDDEN-B")
    assert b.fact("doc:HIDDEN-B") and not b.fact("doc:HIDDEN-A")
    assert not world.fact("doc:HIDDEN-A") and not world.fact("doc:HIDDEN-B")
    assert a.fact("idx:PPI-D351@2026-08") and a.db is world.db  # the package's facts and tables are shared
    assert world.with_case({}).facts == world.facts


def test_read_only_queries(world: WorldData) -> None:
    try:
        world.query("DELETE FROM parts")
    except ValueError:
        pass
    else:
        raise AssertionError("writes must be refused")


def test_endpoint_names_hide_ids() -> None:
    assert _endpoint("/v1/sessions/s1/threads/sup:1/messages") == "/v1/sessions/{sid}/threads/{supplier}/messages"
    assert _endpoint("/v1/sessions/s1/attachments/att:1") == "/v1/sessions/{sid}/attachments/{attachment}"
    assert _endpoint("/v1/cases") == "/v1/cases"


def test_a_release_unpacked_in_its_own_folder_is_read(world: WorldData, tmp_path) -> None:
    """The download unpacks the zip's top folder: release-sunday/release-sunday/facts.json."""
    inner = tmp_path / "release-sunday" / "release-sunday"
    (inner / "data").mkdir(parents=True)
    (inner / "facts.json").write_text('{"news:TEST-1": {"kind": "news"}}', encoding="utf-8")
    for release in (tmp_path / "release-sunday", inner):
        data = WorldData(world.root, release)
        assert data.release == inner and "news:TEST-1" in data.facts
    assert WorldData(world.root, tmp_path / "missing").release is None
