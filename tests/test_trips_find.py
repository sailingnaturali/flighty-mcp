import sqlite3

from flighty_mcp.trips import find_trip

DAY = 86400


def _build_trip_db(path):
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE Airline (id TEXT, iata TEXT, name TEXT);
        CREATE TABLE Airport (id TEXT, iata TEXT, name TEXT, city TEXT, country TEXT,
            countryCode TEXT, latitude REAL, longitude REAL, timeZoneIdentifier TEXT);
        CREATE TABLE Flight (id TEXT, number TEXT, airlineId TEXT, departureAirportId TEXT,
            scheduledArrivalAirportId TEXT, departureScheduleGateOriginal INTEGER,
            arrivalScheduleGateOriginal INTEGER, distance REAL, deleted INTEGER);
        CREATE TABLE UserFlight (userId TEXT, flightId TEXT, isMyFlight INTEGER,
            isArchived INTEGER, deleted INTEGER, created INTEGER);
        CREATE TABLE Profile (userId TEXT, fullName TEXT, firstName TEXT);
        INSERT INTO Airline VALUES ('al','AC','Air Canada');
        INSERT INTO Airport VALUES ('yvr','YVR','Vancouver Intl','Vancouver','Canada','CA',49.19,-123.18,'America/Vancouver');
        INSERT INTO Airport VALUES ('sfo','SFO','SFO','San Francisco','United States','US',37.62,-122.38,'America/Los_Angeles');
        INSERT INTO Airport VALUES ('nrt','NRT','Narita','Tokyo','Japan','JP',35.76,140.39,'Asia/Tokyo');
        INSERT INTO Profile VALUES ('owner-1','Owner','Owner');
        """
    )
    base = 1_700_000_000  # well in the past relative to test runs
    flights = [
        ("f1", "AC1", "yvr", "sfo", base, base + 9000),
        ("f2", "AC2", "sfo", "nrt", base + 20000, base + 60000),
        ("f3", "AC3", "nrt", "sfo", base + 60000 + 7 * DAY, base + 60000 + 7 * DAY + 40000),
        ("f4", "AC4", "sfo", "yvr", base + 60000 + 7 * DAY + 60000, base + 60000 + 7 * DAY + 70000),
    ]
    con.executemany(
        "INSERT INTO Flight VALUES (?,?, 'al', ?, ?, ?, ?, 0, NULL)",
        [(fid, num, dep, arr, dts, ats) for fid, num, dep, arr, dts, ats in flights],
    )
    con.executemany(
        "INSERT INTO UserFlight VALUES ('owner-1', ?, 1, 0, NULL, 1)",
        [(f[0],) for f in flights],
    )
    con.commit()
    con.close()


def test_find_trip_ok_with_urls(tmp_path, monkeypatch):
    path = str(tmp_path / "trip.db")
    _build_trip_db(path)
    monkeypatch.setenv("FLIGHTY_DB_PATH", path)
    monkeypatch.delenv("FLIGHTY_USER_ID", raising=False)
    res = find_trip("Japan")
    assert res["status"] == "ok"
    assert res["destination"] == "NRT"
    assert res["home"] == "YVR"
    assert [s["code"] for s in res["stops"]] == ["YVR", "SFO", "NRT"]
    assert "?d=" in res["url"]
    assert res["round_trip_url"] is not None


def test_find_trip_origin_override(tmp_path, monkeypatch):
    path = str(tmp_path / "trip2.db")
    _build_trip_db(path)
    monkeypatch.setenv("FLIGHTY_DB_PATH", path)
    res = find_trip("Tokyo", origin="SFO")
    assert res["status"] == "ok"
    assert [s["code"] for s in res["stops"]] == ["SFO", "NRT"]
