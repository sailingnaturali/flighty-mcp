"""Aggregate statistics over the owner's flights (stable columns only)."""
from flighty_mcp.db import connect, resolve_owner_id
from flighty_mcp.filters import year_bounds
from flighty_mcp.schema import has_columns

_BASE = """
FROM UserFlight uf
JOIN Flight f    ON f.id = uf.flightId
JOIN Airport dep ON dep.id = f.departureAirportId
JOIN Airport arr ON arr.id = f.scheduledArrivalAirportId
JOIN Airline al  ON al.id = f.airlineId
WHERE uf.deleted IS NULL AND f.deleted IS NULL
  AND uf.userId = ? AND uf.isMyFlight = 1
"""


def flight_stats(year: int | None = None, upcoming_only: bool = False) -> dict:
    con = connect()
    try:
        owner = resolve_owner_id(con)
        where = _BASE
        params: list = [owner]
        if upcoming_only:
            where += " AND uf.isArchived = 0"
        if year is not None:
            start, end = year_bounds(year)
            where += " AND f.departureScheduleGateOriginal >= ? AND f.departureScheduleGateOriginal < ?"
            params += [start, end]

        # dist_expr is built only from the two hard-coded strings below — never user input.
        dist_expr = "COALESCE(SUM(f.distance), 0)" if has_columns(con, "Flight", "distance") else "0"
        agg = con.execute(
            f"SELECT COUNT(*) AS flights, {dist_expr} AS distance_km, "
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
