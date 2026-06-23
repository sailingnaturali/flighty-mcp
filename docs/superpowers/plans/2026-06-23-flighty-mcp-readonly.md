# flighty-mcp (read-only) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A clean, read-only MCP server that returns the owner's Flighty flights as geo-ready legs, to prime a future flight-animation map feature.

**Architecture:** Python FastMCP server reading the local Flighty SQLite DB in read-only mode. Layered into `schema.py` (column-presence detection), `db.py` (connection + access guard + owner resolution), `flights.py` (queries → leg dicts), and `server.py` (thin tool wrappers). TDD against a committed synthetic fixture DB; the real user DB never touches the repo or CI.

**Tech Stack:** Python ≥3.11, `uv`, `mcp[cli]` (FastMCP), stdlib `sqlite3`/`zoneinfo`, `pytest`, `ruff`.

## Global Constraints

- Python ≥ 3.11. Single runtime dependency: `mcp[cli]>=1.6.0`. No network calls.
- Read-only by construction: open SQLite as `file:{path}?mode=ro`. No write/mutation tools.
- Scope v1: owner's own flights only. No friends/status/delay/connection/search tools.
- DB path default: `~/Library/Containers/com.flightyapp.flighty/Data/Documents/MainFlightyDatabase.db`; override via `FLIGHTY_DB_PATH`.
- Owner override via `FLIGHTY_USER_ID`. Owner filter: `UserFlight.userId = <owner> AND UserFlight.isMyFlight = 1`.
- Tests must set `FLIGHTY_DB_PATH` to the fixture; never read the real DB in tests.
- License MIT. Package name `flighty_mcp`. Console script `flighty-mcp`.
- Leg country field uses `Airport.countryCode` (2-letter). Timestamps emitted in the airport's local timezone (`Airport.timeZoneIdentifier`); fall back to UTC `Z` if absent. `date` is the local departure date.
- Exclude `deleted` (NOT NULL) rows and, by default, `isArchived = 1`.

---

## File Structure

```
flighty-mcp/
  pyproject.toml                 # uv project, deps, console script, ruff
  README.md                      # setup incl. Full Disk Access requirement
  flighty_mcp/
    __init__.py
    __main__.py                  # python -m flighty_mcp -> server.main()
    errors.py                    # FlightyAccessError, FlightyOwnerError
    schema.py                    # PRAGMA-based column presence
    db.py                        # connect (ro), access guard, owner resolution
    flights.py                   # list_my_flights / get_flight / flight_stats
    server.py                    # FastMCP tool defs + main()
  tests/
    conftest.py                  # builds + points at the fixture DB
    fixtures/build_fixture.py    # constructs a synthetic Flighty-shaped DB
    test_schema.py
    test_db.py
    test_flights.py
    test_stats.py
  .github/workflows/ci.yml
```

---

## Task 1: Project scaffold + synthetic fixture

**Files:**
- Create: `pyproject.toml`, `flighty_mcp/__init__.py`, `flighty_mcp/errors.py`
- Create: `tests/fixtures/build_fixture.py`, `tests/conftest.py`, `tests/test_smoke.py`
- Create: `.github/workflows/ci.yml`, `.gitignore`

**Interfaces:**
- Produces: `build_fixture(path: str) -> None` — writes a synthetic Flighty-shaped SQLite DB to `path`.
- Produces: pytest fixture `fixture_db` (session-scoped) — yields the fixture DB path and sets `FLIGHTY_DB_PATH`.
- Produces: `flighty_mcp.errors.FlightyAccessError`, `flighty_mcp.errors.FlightyOwnerError` (both subclass `RuntimeError`).

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "flighty-mcp"
version = "0.1.0"
description = "Read-only MCP server exposing local Flighty flight data as geo-ready legs"
requires-python = ">=3.11"
license = { text = "MIT" }
dependencies = ["mcp[cli]>=1.6.0"]

[project.scripts]
flighty-mcp = "flighty_mcp.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["flighty_mcp"]

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.6"]

[tool.ruff]
line-length = 100
```

- [ ] **Step 2: Create `flighty_mcp/__init__.py` and `flighty_mcp/errors.py`**

`flighty_mcp/__init__.py`:
```python
"""Read-only MCP server for local Flighty flight data."""
__version__ = "0.1.0"
```

`flighty_mcp/errors.py`:
```python
"""Actionable error types surfaced to MCP clients."""


class FlightyAccessError(RuntimeError):
    """The Flighty database is missing or cannot be read (often Full Disk Access)."""


class FlightyOwnerError(RuntimeError):
    """The owner user could not be determined; set FLIGHTY_USER_ID."""
```

- [ ] **Step 3: Create the fixture builder `tests/fixtures/build_fixture.py`**

```python
"""Build a synthetic Flighty-shaped SQLite DB for tests. No real data."""
import sqlite3


def build_fixture(path: str) -> None:
    con = sqlite3.connect(path)
    c = con.cursor()
    c.executescript(
        """
        DROP TABLE IF EXISTS Flight;
        DROP TABLE IF EXISTS Airport;
        DROP TABLE IF EXISTS Airline;
        DROP TABLE IF EXISTS UserFlight;
        DROP TABLE IF EXISTS Profile;
        CREATE TABLE Airline (id TEXT, iata TEXT, name TEXT);
        CREATE TABLE Airport (
            id TEXT, iata TEXT, name TEXT, city TEXT, country TEXT,
            countryCode TEXT, latitude REAL, longitude REAL, timeZoneIdentifier TEXT
        );
        CREATE TABLE Flight (
            id TEXT, number TEXT, airlineId TEXT, departureAirportId TEXT,
            scheduledArrivalAirportId TEXT, departureScheduleGateOriginal INTEGER,
            arrivalScheduleGateOriginal INTEGER, distance REAL, deleted INTEGER
        );
        CREATE TABLE UserFlight (
            userId TEXT, flightId TEXT, isMyFlight INTEGER, isArchived INTEGER,
            deleted INTEGER, created INTEGER
        );
        CREATE TABLE Profile (userId TEXT, fullName TEXT, firstName TEXT);
        """
    )
    c.executemany("INSERT INTO Airline VALUES (?,?,?)", [
        ("al-ua", "UA", "United Airlines"),
        ("al-ba", "BA", "British Airways"),
        ("al-ac", "AC", "Air Canada"),
    ])
    # latitude/longitude/timezone are real so legs carry usable coords
    c.executemany("INSERT INTO Airport VALUES (?,?,?,?,?,?,?,?,?)", [
        ("ap-sfo", "SFO", "San Francisco Intl", "San Francisco", "United States", "US", 37.6213, -122.3790, "America/Los_Angeles"),
        ("ap-lhr", "LHR", "Heathrow", "London", "United Kingdom", "GB", 51.4700, -0.4543, "Europe/London"),
        ("ap-yvr", "YVR", "Vancouver Intl", "Vancouver", "Canada", "CA", 49.1939, -123.1844, "America/Vancouver"),
        ("ap-den", "DEN", "Denver Intl", "Denver", "United States", "US", 39.8561, -104.6737, "America/Denver"),
    ])
    OWNER, FRIEND, FAMILY = "owner-1", "friend-1", "family-1"
    c.executemany("INSERT INTO Profile VALUES (?,?,?)", [
        (OWNER, "Owner Person", "Owner"),
        (FRIEND, "Friend Person", "Friend"),
        (FAMILY, "Family Person", "Family"),
    ])
    # ts: 2025-06-15 ~14:30 PDT dep, ~22:15 BST arr (absolute UTC seconds)
    F = [
        # id, number, airlineId, depId, arrId, depTs, arrTs, distance, deleted
        ("f1", "UA194", "al-ua", "ap-sfo", "ap-lhr", 1750023000, 1750051200, 8616.0, None),
        ("f2", "BA930", "al-ba", "ap-lhr", "ap-sfo", 1718450000, 1718480000, 8616.0, None),  # 2024
        ("f3", "AC1725", "al-ac", "ap-den", "ap-yvr", 1752000000, 1752010000, 1840.0, None),  # archived
        ("f4", "UA100", "al-ua", "ap-sfo", "ap-den", 1751000000, 1751008000, 1530.0, None),   # friend
        ("f5", "AC8155", "al-ac", "ap-yvr", "ap-den", 1751500000, 1751510000, 1840.0, None),  # family
        ("f6", "UA200", "al-ua", "ap-sfo", "ap-lhr", 1753000000, None, None, None),           # null arr/distance
        ("f7", "UA999", "al-ua", "ap-sfo", "ap-den", 1740000000, 1740008000, 1530.0, 1),      # deleted flight
    ]
    c.executemany("INSERT INTO Flight VALUES (?,?,?,?,?,?,?,?,?)", F)
    UF = [
        # userId, flightId, isMyFlight, isArchived, deleted, created
        (OWNER, "f1", 1, 0, None, 1),
        (OWNER, "f2", 1, 0, None, 1),
        (OWNER, "f3", 1, 1, None, 1),     # archived -> excluded by default
        (FRIEND, "f4", 0, 0, None, 1),    # friend -> excluded
        (FAMILY, "f5", 1, 0, None, 1),    # family profile, isMyFlight=1 but not owner -> excluded
        (OWNER, "f6", 1, 0, None, 1),     # null arrival/distance
        (OWNER, "f7", 1, 0, None, 1),     # owner row but Flight deleted -> excluded
    ]
    c.executemany("INSERT INTO UserFlight VALUES (?,?,?,?,?,?)", UF)
    con.commit()
    con.close()


if __name__ == "__main__":
    import sys
    build_fixture(sys.argv[1])
    print("wrote", sys.argv[1])
```

- [ ] **Step 4: Create `tests/conftest.py`**

```python
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from tests.fixtures.build_fixture import build_fixture  # noqa: E402


@pytest.fixture(scope="session")
def fixture_db(tmp_path_factory):
    path = str(tmp_path_factory.mktemp("flighty") / "test.db")
    build_fixture(path)
    os.environ["FLIGHTY_DB_PATH"] = path
    os.environ.pop("FLIGHTY_USER_ID", None)
    yield path
```

- [ ] **Step 5: Create `tests/test_smoke.py`**

```python
import sqlite3


def test_fixture_builds_and_has_owner_flights(fixture_db):
    con = sqlite3.connect(fixture_db)
    n = con.execute(
        "SELECT COUNT(*) FROM UserFlight WHERE userId='owner-1' AND isMyFlight=1"
    ).fetchone()[0]
    con.close()
    assert n == 5  # f1,f2,f3,f6,f7 (f3 archived, f7 deleted-flight filtered later)
```

- [ ] **Step 6: Run the smoke test**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: PASS.

- [ ] **Step 7: Create `.gitignore` and `.github/workflows/ci.yml`**

`.gitignore`:
```
__pycache__/
*.pyc
.venv/
dist/
*.egg-info/
.DS_Store
.pytest_cache/
```

`.github/workflows/ci.yml`:
```yaml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv python install 3.11
      - run: uv sync
      - run: uv run ruff check .
      - run: uv run pytest -v
```

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml flighty_mcp tests .github .gitignore
git commit -m "scaffold flighty-mcp + synthetic test fixture"
```

---

## Task 2: Column-presence detection (`schema.py`)

**Files:**
- Create: `flighty_mcp/schema.py`
- Test: `tests/test_schema.py`

**Interfaces:**
- Produces: `table_columns(con, table) -> set[str]` — column names for a table (empty set if table absent).
- Produces: `has_columns(con, table, *names) -> bool`.

- [ ] **Step 1: Write the failing test `tests/test_schema.py`**

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: flighty_mcp.schema`.

- [ ] **Step 3: Implement `flighty_mcp/schema.py`**

```python
"""Detect which columns exist so queries survive Flighty schema drift."""
import sqlite3


def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    rows = con.execute("PRAGMA table_info(" + table + ")").fetchall()
    return {r[1] for r in rows}


def has_columns(con: sqlite3.Connection, table: str, *names: str) -> bool:
    present = table_columns(con, table)
    return all(n in present for n in names)
```

Note: `PRAGMA` cannot be parameterized; `table` is always a hard-coded literal from our own code, never user input.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_schema.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add flighty_mcp/schema.py tests/test_schema.py
git commit -m "add column-presence detection"
```

---

## Task 3: Connection, access guard, owner resolution (`db.py`)

**Files:**
- Create: `flighty_mcp/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `flighty_mcp.errors.FlightyAccessError`, `FlightyOwnerError`.
- Produces: `default_db_path() -> str`.
- Produces: `connect() -> sqlite3.Connection` — read-only; raises `FlightyAccessError` if missing/unreadable; `row_factory = sqlite3.Row`.
- Produces: `resolve_owner_id(con) -> str` — `FLIGHTY_USER_ID` if set, else userId with most `isMyFlight=1` rows, else most `UserFlight` rows; raises `FlightyOwnerError` if none.

- [ ] **Step 1: Write the failing test `tests/test_db.py`**

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_db.py -v`
Expected: FAIL with `ModuleNotFoundError: flighty_mcp.db`.

- [ ] **Step 3: Implement `flighty_mcp/db.py`**

```python
"""Read-only access to the local Flighty SQLite database."""
import os
import sqlite3
import threading

from flighty_mcp.errors import FlightyAccessError, FlightyOwnerError

_DEFAULT = (
    "~/Library/Containers/com.flightyapp.flighty/Data/Documents/MainFlightyDatabase.db"
)


def default_db_path() -> str:
    return os.path.expanduser(os.environ.get("FLIGHTY_DB_PATH", _DEFAULT))


def _readable_or_raise(path: str, timeout: float = 5.0) -> None:
    """Fail fast if the DB is missing or a read stalls (e.g. missing Full Disk Access).

    macOS TCC can *hang* reads into an app container rather than erroring, so we
    probe in a worker thread and abandon it on timeout instead of blocking.
    """
    if not os.path.exists(path):
        raise FlightyAccessError(
            f"Flighty database not found at {path}. Is the Flighty app installed? "
            "Set FLIGHTY_DB_PATH to override the location."
        )
    result: dict = {}

    def probe() -> None:
        try:
            with open(path, "rb") as fh:
                fh.read(16)
            result["ok"] = True
        except Exception as exc:  # noqa: BLE001
            result["err"] = exc

    t = threading.Thread(target=probe, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise FlightyAccessError(
            f"Reading the Flighty database at {path} timed out. Grant Full Disk Access "
            "to the app launching this server (System Settings -> Privacy & Security -> "
            "Full Disk Access), then restart it."
        )
    if "err" in result:
        raise FlightyAccessError(
            f"Cannot read the Flighty database at {path}: {result['err']}. If this is a "
            "permissions error, grant Full Disk Access to the launching app."
        )


def connect() -> sqlite3.Connection:
    path = default_db_path()
    _readable_or_raise(path)
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout = 3000")
    return con


def resolve_owner_id(con: sqlite3.Connection) -> str:
    override = os.environ.get("FLIGHTY_USER_ID")
    if override:
        return override
    row = con.execute(
        "SELECT userId FROM UserFlight WHERE deleted IS NULL AND isMyFlight = 1 "
        "GROUP BY userId ORDER BY COUNT(*) DESC LIMIT 1"
    ).fetchone()
    if row and row[0]:
        return row[0]
    row = con.execute(
        "SELECT userId FROM UserFlight WHERE deleted IS NULL "
        "GROUP BY userId ORDER BY COUNT(*) DESC LIMIT 1"
    ).fetchone()
    if row and row[0]:
        return row[0]
    raise FlightyOwnerError(
        "Could not determine the Flighty owner. Set FLIGHTY_USER_ID to your user id."
    )
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add flighty_mcp/db.py tests/test_db.py
git commit -m "add read-only connect, access guard, owner resolution"
```

---

## Task 4: `list_my_flights` (core leg query) (`flights.py`)

**Files:**
- Create: `flighty_mcp/flights.py`
- Test: `tests/test_flights.py`

**Interfaces:**
- Consumes: `db.connect`, `db.resolve_owner_id`, `schema.table_columns`.
- Produces: `list_my_flights(year=None, after=None, before=None, limit=200) -> list[dict]` returning leg dicts:
  `{"date","flight_no","airline":{"iata","name"},"from":{...},"to":{...},"departure","arrival"}`
  where `from`/`to` are `{"iata","city","country","lat","lon"}`.
- Produces helper: `to_local_iso(ts, tzid) -> str | None` and `local_date(ts, tzid) -> str | None`.

- [ ] **Step 1: Write the failing test `tests/test_flights.py`**

```python
from flighty_mcp.flights import list_my_flights, to_local_iso


def _by_no(legs):
    return {leg["flight_no"]: leg for leg in legs}


def test_lists_only_owner_active_flights(fixture_db):
    legs = list_my_flights()
    nos = {leg["flight_no"] for leg in legs}
    # f1,f2,f6 are owner, not archived, not deleted; f3 archived, f4 friend,
    # f5 family, f7 deleted-flight all excluded.
    assert nos == {"UA194", "BA930", "UA200"}


def test_legs_carry_coordinates_and_country_code(fixture_db):
    leg = _by_no(list_my_flights())["UA194"]
    assert leg["from"]["iata"] == "SFO"
    assert leg["to"]["iata"] == "LHR"
    assert leg["from"]["country"] == "US"
    assert leg["to"]["country"] == "GB"
    assert round(leg["from"]["lat"], 2) == 37.62
    assert round(leg["to"]["lon"], 2) == -0.45


def test_departure_is_airport_local_time(fixture_db):
    leg = _by_no(list_my_flights())["UA194"]
    # 1750023000 in America/Los_Angeles is 2025-06-15 (PDT, -07:00)
    assert leg["departure"].startswith("2025-06-15T")
    assert leg["departure"].endswith("-07:00")
    assert leg["date"] == "2025-06-15"


def test_null_arrival_and_distance_degrade_to_none(fixture_db):
    leg = _by_no(list_my_flights())["UA200"]
    assert leg["arrival"] is None


def test_year_filter(fixture_db):
    nos = {leg["flight_no"] for leg in list_my_flights(year=2024)}
    assert nos == {"BA930"}


def test_after_before_filter(fixture_db):
    nos = {leg["flight_no"] for leg in list_my_flights(after="2025-01-01", before="2025-07-01")}
    assert nos == {"UA194"}


def test_to_local_iso_falls_back_to_utc_z():
    assert to_local_iso(1750023000, None).endswith("Z")
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_flights.py -v`
Expected: FAIL with `ModuleNotFoundError: flighty_mcp.flights`.

- [ ] **Step 3: Implement `flighty_mcp/flights.py`**

```python
"""Owner flight queries shaped as geo-ready legs."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flighty_mcp.db import connect, resolve_owner_id

_LEG_SELECT = """
SELECT
    f.number               AS flight_no,
    al.iata                AS airline_iata,
    al.name                AS airline_name,
    dep.iata               AS dep_iata,
    dep.city               AS dep_city,
    dep.countryCode        AS dep_country,
    dep.latitude           AS dep_lat,
    dep.longitude          AS dep_lon,
    dep.timeZoneIdentifier AS dep_tz,
    arr.iata               AS arr_iata,
    arr.city               AS arr_city,
    arr.countryCode        AS arr_country,
    arr.latitude           AS arr_lat,
    arr.longitude          AS arr_lon,
    arr.timeZoneIdentifier AS arr_tz,
    f.departureScheduleGateOriginal AS dep_ts,
    f.arrivalScheduleGateOriginal   AS arr_ts,
    f.distance             AS distance_km
FROM UserFlight uf
JOIN Flight f   ON f.id = uf.flightId
JOIN Airport dep ON dep.id = f.departureAirportId
JOIN Airport arr ON arr.id = f.scheduledArrivalAirportId
JOIN Airline al ON al.id = f.airlineId
WHERE uf.deleted IS NULL AND f.deleted IS NULL
  AND uf.userId = ? AND uf.isMyFlight = 1
"""


def to_local_iso(ts: int | None, tzid: str | None) -> str | None:
    """Unix seconds -> ISO 8601 in the airport's local tz; UTC 'Z' if tz unknown."""
    if ts is None:
        return None
    if tzid:
        try:
            return datetime.fromtimestamp(ts, ZoneInfo(tzid)).isoformat()
        except (ZoneInfoNotFoundError, ValueError):
            pass
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def local_date(ts: int | None, tzid: str | None) -> str | None:
    iso = to_local_iso(ts, tzid)
    return iso[:10] if iso else None


def _row_to_leg(r) -> dict:
    return {
        "date": local_date(r["dep_ts"], r["dep_tz"]),
        "flight_no": r["flight_no"],
        "airline": {"iata": r["airline_iata"], "name": r["airline_name"]},
        "from": {
            "iata": r["dep_iata"], "city": r["dep_city"], "country": r["dep_country"],
            "lat": r["dep_lat"], "lon": r["dep_lon"],
        },
        "to": {
            "iata": r["arr_iata"], "city": r["arr_city"], "country": r["arr_country"],
            "lat": r["arr_lat"], "lon": r["arr_lon"],
        },
        "departure": to_local_iso(r["dep_ts"], r["dep_tz"]),
        "arrival": to_local_iso(r["arr_ts"], r["arr_tz"]),
    }


def list_my_flights(
    year: int | None = None,
    after: str | None = None,
    before: str | None = None,
    limit: int = 200,
    include_archived: bool = False,
) -> list[dict]:
    con = connect()
    try:
        owner = resolve_owner_id(con)
        query = _LEG_SELECT
        params: list = [owner]
        if not include_archived:
            query += " AND uf.isArchived = 0"
        if year is not None:
            start = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp())
            end = int(datetime(year + 1, 1, 1, tzinfo=timezone.utc).timestamp())
            query += " AND f.departureScheduleGateOriginal >= ? AND f.departureScheduleGateOriginal < ?"
            params += [start, end]
        if after is not None:
            query += " AND f.departureScheduleGateOriginal >= ?"
            params.append(int(datetime.fromisoformat(after).replace(tzinfo=timezone.utc).timestamp()))
        if before is not None:
            query += " AND f.departureScheduleGateOriginal < ?"
            params.append(int(datetime.fromisoformat(before).replace(tzinfo=timezone.utc).timestamp()))
        query += " ORDER BY f.departureScheduleGateOriginal DESC LIMIT ?"
        params.append(limit)
        return [_row_to_leg(r) for r in con.execute(query, params).fetchall()]
    finally:
        con.close()
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_flights.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add flighty_mcp/flights.py tests/test_flights.py
git commit -m "add list_my_flights leg query with local-time and filters"
```

---

## Task 5: `get_flight`

**Files:**
- Modify: `flighty_mcp/flights.py` (append `get_flight`)
- Test: `tests/test_flights.py` (append)

**Interfaces:**
- Produces: `get_flight(flight_no: str) -> dict | None` — most recent owner leg matching a flight number (case/space-insensitive), or `None`.

- [ ] **Step 1: Add failing tests to `tests/test_flights.py`**

```python
from flighty_mcp.flights import get_flight


def test_get_flight_matches_case_and_space_insensitive(fixture_db):
    leg = get_flight("ua 194")
    assert leg is not None and leg["flight_no"] == "UA194"


def test_get_flight_unknown_returns_none(fixture_db):
    assert get_flight("ZZ000") is None


def test_get_flight_excludes_friend_flights(fixture_db):
    # UA100 belongs to the friend, not the owner
    assert get_flight("UA100") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_flights.py -k get_flight -v`
Expected: FAIL with `ImportError: cannot import name 'get_flight'`.

- [ ] **Step 3: Append `get_flight` to `flighty_mcp/flights.py`**

```python
def get_flight(flight_no: str) -> dict | None:
    con = connect()
    try:
        owner = resolve_owner_id(con)
        query = (
            _LEG_SELECT
            + " AND UPPER(REPLACE(f.number,' ','')) = UPPER(REPLACE(?,' ',''))"
            + " ORDER BY f.departureScheduleGateOriginal DESC LIMIT 1"
        )
        row = con.execute(query, [owner, flight_no]).fetchone()
        return _row_to_leg(row) if row else None
    finally:
        con.close()
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_flights.py -k get_flight -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add flighty_mcp/flights.py tests/test_flights.py
git commit -m "add get_flight lookup by flight number"
```

---

## Task 6: `flight_stats`

**Files:**
- Create: `flighty_mcp/stats.py`
- Test: `tests/test_stats.py`

**Interfaces:**
- Consumes: `db.connect`, `db.resolve_owner_id`, `schema.has_columns`.
- Produces: `flight_stats(year=None) -> dict` with keys `flights:int`, `distance_km:float`,
  `unique_airports:int`, `unique_airlines:int`, `top_routes:list[{route,count}]`,
  `top_airlines:list[{iata,name,count}]`, `year:int|str`.

- [ ] **Step 1: Write the failing test `tests/test_stats.py`**

```python
from flighty_mcp.stats import flight_stats


def test_stats_counts_owner_active_flights(fixture_db):
    s = flight_stats()
    assert s["flights"] == 3  # UA194, BA930, UA200
    assert s["unique_airlines"] == 2  # UA, BA
    assert s["year"] == "all_time"


def test_stats_sums_distance_ignoring_nulls(fixture_db):
    s = flight_stats()
    assert s["distance_km"] == 8616.0 + 8616.0  # UA200 distance is NULL


def test_stats_top_routes_present(fixture_db):
    routes = {r["route"] for r in flight_stats()["top_routes"]}
    assert "SFO -> LHR" in routes


def test_stats_year_filter(fixture_db):
    s = flight_stats(year=2024)
    assert s["flights"] == 1 and s["year"] == 2024
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_stats.py -v`
Expected: FAIL with `ModuleNotFoundError: flighty_mcp.stats`.

- [ ] **Step 3: Implement `flighty_mcp/stats.py`**

```python
"""Aggregate statistics over the owner's flights (stable columns only)."""
from datetime import datetime, timezone

from flighty_mcp.db import connect, resolve_owner_id

_BASE = """
FROM UserFlight uf
JOIN Flight f    ON f.id = uf.flightId
JOIN Airport dep ON dep.id = f.departureAirportId
JOIN Airport arr ON arr.id = f.scheduledArrivalAirportId
JOIN Airline al  ON al.id = f.airlineId
WHERE uf.deleted IS NULL AND f.deleted IS NULL
  AND uf.userId = ? AND uf.isMyFlight = 1 AND uf.isArchived = 0
"""


def flight_stats(year: int | None = None) -> dict:
    con = connect()
    try:
        owner = resolve_owner_id(con)
        where = _BASE
        params: list = [owner]
        if year is not None:
            start = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp())
            end = int(datetime(year + 1, 1, 1, tzinfo=timezone.utc).timestamp())
            where += " AND f.departureScheduleGateOriginal >= ? AND f.departureScheduleGateOriginal < ?"
            params += [start, end]

        agg = con.execute(
            "SELECT COUNT(*) AS flights, COALESCE(SUM(f.distance),0) AS distance_km, "
            "COUNT(DISTINCT dep.id) AS dep_ap, COUNT(DISTINCT arr.id) AS arr_ap, "
            "COUNT(DISTINCT al.id) AS airlines " + where,
            params,
        ).fetchone()
        routes = con.execute(
            "SELECT dep.iata || ' -> ' || arr.iata AS route, COUNT(*) AS count "
            + where + " GROUP BY route ORDER BY count DESC LIMIT 5",
            params,
        ).fetchall()
        airlines = con.execute(
            "SELECT al.iata AS iata, al.name AS name, COUNT(*) AS count "
            + where + " GROUP BY al.id ORDER BY count DESC LIMIT 5",
            params,
        ).fetchall()

        uniq_airports = con.execute(
            "SELECT COUNT(*) FROM (SELECT dep.id AS x " + where
            + " UNION SELECT arr.id " + where + ")",
            params + params,
        ).fetchone()[0]

        return {
            "flights": agg["flights"],
            "distance_km": float(agg["distance_km"]),
            "unique_airports": uniq_airports,
            "unique_airlines": agg["airlines"],
            "top_routes": [{"route": r["route"], "count": r["count"]} for r in routes],
            "top_airlines": [
                {"iata": a["iata"], "name": a["name"], "count": a["count"]} for a in airlines
            ],
            "year": year if year is not None else "all_time",
        }
    finally:
        con.close()
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_stats.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add flighty_mcp/stats.py tests/test_stats.py
git commit -m "add flight_stats aggregates"
```

---

## Task 7: Schema-drift regression test

**Files:**
- Test: `tests/test_schema_drift.py`
- Modify (only if test reveals a gap): `flighty_mcp/flights.py`

**Interfaces:**
- Consumes: `flights.list_my_flights`. No new production interface unless a gap is found.

This task proves the portability claim: a Flighty DB missing the optional `distance`
column must still return legs (distance is not part of a leg, so `list_my_flights`
must not select it — it doesn't — but this locks the behavior in).

- [ ] **Step 1: Write the failing/guard test `tests/test_schema_drift.py`**

```python
import os
import sqlite3

from flighty_mcp.flights import list_my_flights


def _build_no_distance(path):
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE Airline (id TEXT, iata TEXT, name TEXT);
        CREATE TABLE Airport (id TEXT, iata TEXT, name TEXT, city TEXT, country TEXT,
            countryCode TEXT, latitude REAL, longitude REAL, timeZoneIdentifier TEXT);
        CREATE TABLE Flight (id TEXT, number TEXT, airlineId TEXT, departureAirportId TEXT,
            scheduledArrivalAirportId TEXT, departureScheduleGateOriginal INTEGER,
            arrivalScheduleGateOriginal INTEGER, deleted INTEGER);  -- no 'distance'
        CREATE TABLE UserFlight (userId TEXT, flightId TEXT, isMyFlight INTEGER,
            isArchived INTEGER, deleted INTEGER, created INTEGER);
        CREATE TABLE Profile (userId TEXT, fullName TEXT, firstName TEXT);
        INSERT INTO Airline VALUES ('al-ua','UA','United');
        INSERT INTO Airport VALUES ('a1','SFO','SFO','San Francisco','United States','US',37.6,-122.4,'America/Los_Angeles');
        INSERT INTO Airport VALUES ('a2','LHR','LHR','London','United Kingdom','GB',51.5,-0.45,'Europe/London');
        INSERT INTO Flight VALUES ('f1','UA194','al-ua','a1','a2',1750023000,1750051200,NULL);
        INSERT INTO UserFlight VALUES ('owner-1','f1',1,0,NULL,1);
        """
    )
    con.commit()
    con.close()


def test_list_my_flights_works_without_distance_column(tmp_path, monkeypatch):
    path = str(tmp_path / "nodist.db")
    _build_no_distance(path)
    monkeypatch.setenv("FLIGHTY_DB_PATH", path)
    legs = list_my_flights()
    assert legs and legs[0]["flight_no"] == "UA194"
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/test_schema_drift.py -v`
Expected: PASS (the leg query never selects `distance`, so a missing column is fine).
If it FAILS because the query touched a missing column, remove that column from
`_LEG_SELECT` in `flighty_mcp/flights.py` and re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/test_schema_drift.py
git commit -m "lock in schema-drift tolerance for list_my_flights"
```

---

## Task 8: MCP server + tools (`server.py`)

**Files:**
- Create: `flighty_mcp/server.py`, `flighty_mcp/__main__.py`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `flights.list_my_flights`, `flights.get_flight`, `stats.flight_stats`.
- Produces: `mcp` (FastMCP instance) with tools `list_my_flights`, `get_flight`, `flight_stats`; `main()` entrypoint.

- [ ] **Step 1: Write the failing test `tests/test_server.py`**

```python
import asyncio


def test_tools_registered():
    from flighty_mcp.server import mcp

    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {"list_my_flights", "get_flight", "flight_stats"} <= names
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_server.py -v`
Expected: FAIL with `ModuleNotFoundError: flighty_mcp.server`.

- [ ] **Step 3: Implement `flighty_mcp/server.py`**

```python
"""FastMCP server exposing read-only Flighty flight data."""
from mcp.server.fastmcp import FastMCP

from flighty_mcp import flights, stats

mcp = FastMCP("flighty")


@mcp.tool()
def list_my_flights(
    year: int | None = None,
    after: str | None = None,
    before: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """List your own flights as geo-ready legs (departure/arrival airports with coordinates).

    Args:
        year: Filter to a calendar year (e.g. 2025).
        after: Only flights departing on/after this ISO date (YYYY-MM-DD).
        before: Only flights departing before this ISO date (YYYY-MM-DD).
        limit: Maximum number of legs to return (default 200, newest first).
    """
    return flights.list_my_flights(year=year, after=after, before=before, limit=limit)


@mcp.tool()
def get_flight(flight_no: str) -> dict | None:
    """Get your most recent flight leg matching a flight number (e.g. "UA194").

    Args:
        flight_no: The flight number (case- and space-insensitive).
    """
    return flights.get_flight(flight_no)


@mcp.tool()
def flight_stats(year: int | None = None) -> dict:
    """Aggregate stats over your flights: counts, distance, unique airports/airlines, top routes.

    Args:
        year: Filter stats to a calendar year. Omit for all-time.
    """
    return stats.flight_stats(year=year)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
```

`flighty_mcp/__main__.py`:
```python
from flighty_mcp.server import main

main()
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_server.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite + lint**

Run: `uv run ruff check . && uv run pytest -v`
Expected: all tests PASS, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add flighty_mcp/server.py flighty_mcp/__main__.py tests/test_server.py
git commit -m "add FastMCP server with read-only flight tools"
```

---

## Task 9: README + live smoke + register the MCP

**Files:**
- Create: `README.md`, `LICENSE`

**Interfaces:** none (docs + operational wiring).

- [ ] **Step 1: Write `LICENSE`** — standard MIT text, copyright holder "Bryan Clark".

- [ ] **Step 2: Write `README.md`**

Cover: what it is (read-only Flighty → geo-ready legs), the three tools with the leg
shape, **Full Disk Access requirement** (with the symptom: reads hang without it; grant
to the launching app — terminal/Claude Code host or Claude Desktop — then restart),
config table (`FLIGHTY_DB_PATH`, `FLIGHTY_USER_ID`), install:

```bash
claude mcp add flighty -- uv --directory /path/to/flighty-mcp run flighty-mcp
```

and a one-line credit to `LukasHaas/flighty-mcp` for the original idea. Keep any
"why" section ≤8 lines.

- [ ] **Step 3: Live smoke test against the real DB** (manual, requires Full Disk Access)

Run: `cd ~/src/sailingnaturali/flighty-mcp && FLIGHTY_DB_PATH="$HOME/Library/Containers/com.flightyapp.flighty/Data/Documents/MainFlightyDatabase.db" uv run python -c "from flighty_mcp.flights import list_my_flights; import json; print(json.dumps(list_my_flights(limit=2), indent=2))"`
Expected: two real legs with coordinates, owner's flights only. (~535-flight owner set.)

- [ ] **Step 4: Re-register the MCP to point at this server**

The existing `flighty` MCP registration points at the old upstream path. Update it:

```bash
claude mcp remove flighty 2>/dev/null
claude mcp add flighty -- uv --directory ~/src/sailingnaturali/flighty-mcp run flighty-mcp
claude mcp list | grep flighty
```
Expected: `flighty: ... - ✔ Connected`.

- [ ] **Step 5: Commit**

```bash
git add README.md LICENSE
git commit -m "add README (incl. Full Disk Access) and MIT license"
```

---

## Self-Review

- **Spec coverage:** read-only ✓ (mode=ro, no write tools); 3 tools ✓ (Tasks 4–6, 8);
  leg shape with coords ✓ (Task 4); owner-only via `isMyFlight`+userId ✓ (Task 3, refined
  per data finding); schema robustness ✓ (Tasks 2, 7); FDA fail-fast ✓ (Task 3); config
  env vars ✓ (Task 3); fixture-based TDD + CI ✓ (Task 1); README/FDA setup ✓ (Task 9).
- **Decision recorded:** owner set = `userId = owner AND isMyFlight = 1` (your ~535
  flights), excluding family-profile rows; switch to `isMyFlight = 1` alone for the
  family-inclusive 662 set if desired.
- **Type consistency:** leg dict keys identical across `_row_to_leg`, tests, and tool
  docstrings; `flight_stats` keys identical across `stats.py` and `test_stats.py`.
- **Placeholder scan:** none — every code step is complete; Task 9 README is prose-by-design.
- **Note:** `unique_airports` uses a UNION subquery with `params + params` (the `where`
  clause appears twice); verified the parameter count matches.
```
