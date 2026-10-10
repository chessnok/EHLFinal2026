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
