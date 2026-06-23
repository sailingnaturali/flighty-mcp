"""Owner flight queries shaped as geo-ready legs."""
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flighty_mcp.db import connect, resolve_owner_id
from flighty_mcp.filters import iso_date_to_ts, year_bounds

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
    f.arrivalScheduleGateOriginal   AS arr_ts
FROM UserFlight uf
JOIN Flight f   ON f.id = uf.flightId
JOIN Airport dep ON dep.id = f.departureAirportId
JOIN Airport arr ON arr.id = f.scheduledArrivalAirportId
JOIN Airline al ON al.id = f.airlineId
WHERE uf.deleted IS NULL AND f.deleted IS NULL
  AND uf.userId = ? AND uf.isMyFlight = 1
"""


@dataclass
class Leg:
    flight_no: str
    airline_iata: str | None
    airline_name: str | None
    dep_id: str
    dep_code: str | None
    dep_city: str | None
    dep_country: str | None        # 2-letter countryCode
    dep_country_name: str | None
    dep_lat: float | None
    dep_lon: float | None
    dep_tz: str | None
    arr_id: str
    arr_code: str | None
    arr_city: str | None
    arr_country: str | None
    arr_country_name: str | None
    arr_lat: float | None
    arr_lon: float | None
    arr_tz: str | None
    dep_ts: int
    arr_ts: int | None


_TRIP_LEG_SELECT = """
SELECT
    f.number AS flight_no,
    al.iata AS airline_iata, al.name AS airline_name,
    dep.id AS dep_id, dep.iata AS dep_code, dep.city AS dep_city,
    dep.countryCode AS dep_country, dep.country AS dep_country_name,
    dep.latitude AS dep_lat, dep.longitude AS dep_lon, dep.timeZoneIdentifier AS dep_tz,
    arr.id AS arr_id, arr.iata AS arr_code, arr.city AS arr_city,
    arr.countryCode AS arr_country, arr.country AS arr_country_name,
    arr.latitude AS arr_lat, arr.longitude AS arr_lon, arr.timeZoneIdentifier AS arr_tz,
    f.departureScheduleGateOriginal AS dep_ts,
    f.arrivalScheduleGateOriginal AS arr_ts
FROM UserFlight uf
JOIN Flight f   ON f.id = uf.flightId
JOIN Airport dep ON dep.id = f.departureAirportId
JOIN Airport arr ON arr.id = f.scheduledArrivalAirportId
JOIN Airline al ON al.id = f.airlineId
WHERE uf.deleted IS NULL AND f.deleted IS NULL
  AND uf.userId = ? AND uf.isMyFlight = 1
  AND f.departureScheduleGateOriginal IS NOT NULL
ORDER BY f.departureScheduleGateOriginal ASC
"""


def owner_legs_asc(con: sqlite3.Connection, owner: str) -> list[Leg]:
    """Owner's full-history legs, ascending by departure, NULL-departure legs excluded."""
    rows = con.execute(_TRIP_LEG_SELECT, [owner]).fetchall()
    return [
        Leg(
            flight_no=r["flight_no"],
            airline_iata=r["airline_iata"], airline_name=r["airline_name"],
            dep_id=r["dep_id"], dep_code=r["dep_code"], dep_city=r["dep_city"],
            dep_country=r["dep_country"], dep_country_name=r["dep_country_name"],
            dep_lat=r["dep_lat"], dep_lon=r["dep_lon"], dep_tz=r["dep_tz"],
            arr_id=r["arr_id"], arr_code=r["arr_code"], arr_city=r["arr_city"],
            arr_country=r["arr_country"], arr_country_name=r["arr_country_name"],
            arr_lat=r["arr_lat"], arr_lon=r["arr_lon"], arr_tz=r["arr_tz"],
            dep_ts=r["dep_ts"], arr_ts=r["arr_ts"],
        )
        for r in rows
    ]


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
    upcoming_only: bool = False,
    limit: int = 200,
) -> list[dict]:
    con = connect()
    try:
        owner = resolve_owner_id(con)
        query = _LEG_SELECT
        params: list = [owner]
        if upcoming_only:
            query += " AND uf.isArchived = 0"
        if year is not None:
            start, end = year_bounds(year)
            query += " AND f.departureScheduleGateOriginal >= ? AND f.departureScheduleGateOriginal < ?"
            params += [start, end]
        if after is not None:
            query += " AND f.departureScheduleGateOriginal >= ?"
            params.append(iso_date_to_ts(after, "after"))
        if before is not None:
            query += " AND f.departureScheduleGateOriginal < ?"
            params.append(iso_date_to_ts(before, "before"))
        query += " ORDER BY f.departureScheduleGateOriginal DESC LIMIT ?"
        params.append(limit)
        return [_row_to_leg(r) for r in con.execute(query, params).fetchall()]
    finally:
        con.close()


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
