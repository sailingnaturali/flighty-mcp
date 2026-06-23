import sqlite3

from flighty_mcp.schema import has_columns, table_columns


def test_table_columns_reports_present_columns(fixture_db):
    con = sqlite3.connect(fixture_db)
    cols = table_columns(con, "Flight")
    con.close()
    assert {"number", "distance", "departureScheduleGateOriginal"} <= cols


def test_table_columns_empty_for_missing_table(fixture_db):
    con = sqlite3.connect(fixture_db)
    assert table_columns(con, "DoesNotExist") == set()
    con.close()


def test_has_columns(fixture_db):
    con = sqlite3.connect(fixture_db)
    assert has_columns(con, "Flight", "number", "distance")
    assert not has_columns(con, "Flight", "number", "nope")
    con.close()
