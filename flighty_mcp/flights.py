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
    f.arrivalScheduleGateOriginal   AS arr_ts
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
