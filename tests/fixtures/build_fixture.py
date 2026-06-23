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
