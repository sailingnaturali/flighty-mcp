# flighty-mcp — read-only flight-data MCP server

**Date:** 2026-06-23
**Status:** Approved design, pre-implementation
**Author:** Bryan + Claude

## Purpose

A clean, **read-only** MCP server that exposes flight data from the local Flighty
macOS app (its SQLite database) to AI assistants. Scoped to **the owner's own
flights**. The primary near-term consumer is a future "flight animation" map
feature, so every flight is returned as a **geo-ready leg** carrying departure and
arrival coordinates.

This is a fresh build, not a fork of `LukasHaas/flighty-mcp`. Upstream is brittle
(no tests, stale issues/PRs, a schema-fragile `SELECT` that broke listing on
renamed columns, and write tools we don't want). We keep the good idea (read the
local SQLite) and rebuild it small, tested, and portable. README credits upstream
for inspiration.

## Non-goals (v1)

- No write/mutation tools (no `add_flight`). Read-only by construction.
- No friends' flights, no flight status/delay/connection tools, no airport/airline
  search. These come later as separate increments.
- No network calls (no AirLabs or any external API).

## Context / facts established

- DB path: `~/Library/Containers/com.flightyapp.flighty/Data/Documents/MainFlightyDatabase.db`
  (~11.6 MB SQLite), overridable via `FLIGHTY_DB_PATH`.
- The `Airport` table has `latitude`/`longitude` → map animation is feasible
  directly from this data.
- ~635 flights, 701 `UserFlight` links (701 includes friends; owner is a subset).
- **macOS Full Disk Access is required.** Without it, reads into the app container
  do not error — macOS TCC **hangs** the syscall. FDA must be granted to the app
  that launches the server (the terminal/Claude host; Claude Desktop needs its own
  grant). With FDA, a `mode=ro` query runs in <1s. The server must fail fast with a
  clear FDA message rather than block.

## Architecture

Python, `uv` + `mcp[cli]` (FastMCP), MIT license — matches the existing `*-mcp`
repos. Layered so each unit has one purpose and is testable in isolation:

```
flighty_mcp/
  server.py    # FastMCP tool definitions (thin wrappers over flights.py)
  db.py        # read-only connect, guarded readability check, owner detection
  schema.py    # PRAGMA-based column-presence detection (version portability)
  flights.py   # queries → flight-leg dicts (the real logic)
tests/
  fixtures/test.db   # tiny synthetic SQLite, committed; never the real DB
  test_*.py
README.md
pyproject.toml
.github/workflows/ci.yml
```

- `db.py` owns connection lifecycle and the owner-userId resolution. It opens
  `file:{path}?mode=ro` with a short `busy_timeout`.
- `schema.py` reads `PRAGMA table_info` once and reports which columns exist, so
  query builders select only present columns.
- `flights.py` builds and runs the leg query and shapes rows into the leg dict. It
  depends on `db.py` (connection + owner id) and `schema.py` (column guards).
- `server.py` defines the three tools and does nothing but validate args and call
  `flights.py`.

## Tools (3, read-only, owner's flights only)

```
list_my_flights(year=None, after=None, before=None, limit=200) -> [leg]
get_flight(flight_no)                                          -> leg | null
flight_stats(year=None) -> {flights, distance_km, unique_airports,
                            unique_airlines, top_routes, top_airlines}
```

- `list_my_flights`: owner's flights, newest first. `year` filters to a calendar
  year; `after`/`before` are ISO dates (`YYYY-MM-DD`). Excludes friends, deleted,
  and (by default) archived flights.
- `get_flight`: most recent leg matching a flight number (case/space-insensitive).
- `flight_stats`: aggregate counts over owner's flights, optional year filter.
  Uses only stable columns (no weather/delay-forecast fields).

### Leg shape

```jsonc
{
  "date": "2025-04-15",
  "flight_no": "UA194",
  "airline": { "iata": "UA", "name": "United" },
  "from": { "iata": "SFO", "city": "San Francisco", "country": "US",
            "lat": 37.62, "lon": -122.38 },
  "to":   { "iata": "LHR", "city": "London", "country": "GB",
            "lat": 51.47, "lon": -0.45 },
  "departure": "2025-04-15T14:30:00Z",  // null if Flighty has no time
  "arrival":   "2025-04-15T22:15:00Z"   // null if absent
}
```

Timestamps are stored as Unix seconds in the DB and emitted as ISO 8601 UTC. Date
derives from the best available departure timestamp.

## Schema robustness

- `schema.py` detects column presence via `PRAGMA table_info` and query builders
  include only columns that exist. This is what makes the server survive Flighty
  schema changes — the exact failure mode that broke upstream
  (`no such column: f.arrivalWeatherCondition`). Our lean set already avoids the
  fragile weather/delay columns; column-detection covers anything else that drifts.
- Required core columns (stable): `Flight.number`, `Flight.airlineId`,
  `Flight.departureAirportId`, `Flight.scheduledArrivalAirportId`,
  `Flight.departureScheduleGateOriginal`, `Flight.arrivalScheduleGateOriginal`,
  `Flight.distance`; `Airport.iata/city/country/latitude/longitude/name`;
  `Airline.iata/name`; `UserFlight.userId/isArchived/deleted`. If a core column is
  genuinely absent, the affected field is emitted as `null` (server still returns
  legs) rather than erroring.

## Owner detection (approach A)

"Owner's flights only" requires resolving which `userId` is the local user in a DB
that also holds friends.

1. **Explicit override first:** if `FLIGHTY_USER_ID` is set, use it verbatim.
2. **Explicit signal:** during implementation, investigate the schema for a
   first-class "this is me" marker (e.g. an `Account` table, a `Profile.isMe`/local
   flag). Use it if one exists.
3. **Fallback heuristic:** otherwise, the userId appearing most in
   `ConnectedFriendRelationship` (sender ∪ receiver), then the userId with the most
   `UserFlight` rows — matching upstream's heuristic as a last resort.

If no owner can be resolved, raise a clear error suggesting `FLIGHTY_USER_ID`.

## Error handling

- **DB missing:** clear error naming the path and that Flighty must be installed
  (or `FLIGHTY_DB_PATH` set).
- **DB unreadable / access stalls:** a fast guarded check at connect time
  (existence + `os.access` + a tiny read under a short `busy_timeout`). On failure,
  raise **"grant Full Disk Access to the app launching this server"** rather than
  blocking. Never hang.
- **Owner unresolved:** error with the `FLIGHTY_USER_ID` hint.
- All tool errors are returned as MCP tool errors with actionable messages.

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `FLIGHTY_DB_PATH` | No | Override the default Flighty DB path. |
| `FLIGHTY_USER_ID` | No | Force the owner userId (skips detection). |

## Testing & CI

- **TDD.** Tests run against a committed **synthetic fixture** SQLite
  (`tests/fixtures/test.db`) built with the minimal schema (Flight, Airport,
  Airline, UserFlight, Ticket, Profile, ConnectedFriendRelationship) and a few rows:
  an owner, one friend, and a handful of flights with real coordinates. The real
  user DB never touches the repo or CI. Tests set `FLIGHTY_DB_PATH` to the fixture.
- **Coverage:** owner-only filtering (friend rows excluded), coordinates present on
  legs, `year`/`after`/`before` filters, archived excluded by default, stats math
  (counts, distance, top routes/airlines), a **column-omitted** case proving
  schema-detection degrades to `null`, and owner detection (override + heuristic).
- **CI:** GitHub Actions — `uv`, `pytest`, `ruff`.

## Setup (README)

- Note the **Full Disk Access** requirement up front (with the symptom: a hang if
  missing).
- `claude mcp add flighty -- uv --directory /path/to/flighty-mcp run -m flighty_mcp`
  (exact entrypoint finalized in the plan).

## Open items resolved in implementation

- Exact owner "me" signal in the Flighty schema (approach A, step 2).
- Final module entrypoint / `pyproject` script wiring.
- Replacing the currently-registered `flighty` MCP (upstream) with this server.
```
