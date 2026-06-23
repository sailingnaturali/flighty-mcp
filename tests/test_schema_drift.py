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
