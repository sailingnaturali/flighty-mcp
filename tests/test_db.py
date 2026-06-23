import os

import pytest

from flighty_mcp.db import connect, resolve_owner_id
from flighty_mcp.errors import FlightyAccessError


def test_connect_reads_fixture(fixture_db):
    con = connect()
    assert con.execute("SELECT COUNT(*) FROM Flight").fetchone()[0] >= 1
    con.close()


def test_connect_missing_db_raises_access_error(monkeypatch, tmp_path):
    monkeypatch.setenv("FLIGHTY_DB_PATH", str(tmp_path / "nope.db"))
    with pytest.raises(FlightyAccessError):
        connect()


def test_resolve_owner_prefers_most_ismyflight(fixture_db):
    con = connect()
    assert resolve_owner_id(con) == "owner-1"
    con.close()


def test_resolve_owner_env_override(fixture_db, monkeypatch):
    monkeypatch.setenv("FLIGHTY_USER_ID", "custom-id")
    con = connect()
    assert resolve_owner_id(con) == "custom-id"
    con.close()
    monkeypatch.delenv("FLIGHTY_USER_ID", raising=False)
