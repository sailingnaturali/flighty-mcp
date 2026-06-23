# flighty-mcp

A read-only MCP server that exposes your personal Flighty app flight data as geo-ready legs with departure and arrival coordinates. Query your flight history by date, year, or flight number; browse aggregate stats (distance, unique airports/airlines, top routes).

Credit: inspired by [LukasHaas/flighty-mcp](https://github.com/LukasHaas/flighty-mcp) for the original idea.

## Tools

### `list_my_flights`

List your own flights as geo-ready legs (departure/arrival airports with coordinates).

**Arguments:**
- `year` (optional): Filter to a calendar year (e.g. 2025).
- `after` (optional): Only flights departing on/after this ISO date (YYYY-MM-DD).
- `before` (optional): Only flights departing before this ISO date (YYYY-MM-DD).
- `limit` (optional): Maximum number of legs to return (default 200, newest first).

**Returns:** List of leg objects with this structure:

```json
{
  "date": "2025-06-23",
  "flight_no": "UA194",
  "airline": {
    "iata": "UA",
    "name": "United Airlines"
  },
  "from": {
    "iata": "SFO",
    "city": "San Francisco",
    "country": "United States",
    "lat": 37.6213,
    "lon": -122.379
  },
  "to": {
    "iata": "JFK",
    "city": "New York",
    "country": "United States",
    "lat": 40.6413,
    "lon": -73.7781
  },
  "departure": "2025-06-23T10:30:00",
  "arrival": "2025-06-24T01:15:00Z"
}
```

### `get_flight`

Get your most recent flight leg matching a flight number (e.g. "UA194").

**Arguments:**
- `flight_no`: The flight number (case- and space-insensitive).

**Returns:** A single leg object (or null if no match found).

### `flight_stats`

Aggregate stats over your flights: counts, distance, unique airports/airlines, and top routes.

**Arguments:**
- `year` (optional): Filter stats to a calendar year. Omit for all-time.

**Returns:** Stats object with this structure:

```json
{
  "flights": 42,
  "distance_km": 18500.5,
  "unique_airports": 15,
  "unique_airlines": 5,
  "top_routes": [
    { "route": "SFO -> JFK", "count": 8 },
    { "route": "JFK -> SFO", "count": 7 }
  ],
  "top_airlines": [
    { "iata": "UA", "name": "United Airlines", "count": 12 }
  ],
  "year": "all_time"
}
```

### `animate_trip`

Build a flight-animator route link for your trip to a place.

Resolves the connected flights from your home (or `origin`) to `destination` and returns shareable links: `url` (one-way trip) and `round_trip_url` (there and back). May instead return a resolution prompt with status `ambiguous_destination`, `confirm_home`, or `no_match`.

**Arguments:**
- `destination`: Where the trip goes — IATA code, city, or country (e.g. "Japan", "NRT").
- `origin` (optional): Starting location — IATA code, city, or country. Defaults to your inferred home (most common departure airport).
- `after` (optional): ISO date (YYYY-MM-DD); only trips departing on/after it.
- `before` (optional): ISO date (YYYY-MM-DD); only trips departing before it.

**Example:** "animate my flight to Japan"

**Returns:** If successful, a dict with keys `status` (always "ok"), `url`, `round_trip_url` (if a return is found), `home`, `destination`, `stops` (summary), `start_date`, `end_date`, `leg_count`, and `home_confidence`. On ambiguity or mismatch, returns `status` with one of: `no_match` (no flights match criteria), `ambiguous_destination` (multiple cities match the destination), or `confirm_home` (inferred home confidence is low—returns top alternatives for confirmation).

**Route link format:** the `?d=` value is `base64url` of `{"v":1,"stops":[…]}` (the versioned envelope shared with flight-animator's decoder). Each stop carries `code`, `lat`, `lon`, `label`, and optional `arrive`/`depart` (ISO 8601). We always embed `lat`/`lon` so the animator needs no airport-table lookup and so points outside its bundled dataset still render — consumers should prefer the embedded coordinates over resolving the `code`.

## Installation

```bash
claude mcp add flighty -- uv --directory /path/to/flighty-mcp run flighty-mcp
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `FLIGHTY_DB_PATH` | `$HOME/Library/Containers/com.flightyapp.flighty/Data/Documents/MainFlightyDatabase.db` | Path to the Flighty app's SQLite database. |
| `FLIGHTY_USER_ID` | Auto-detected from `UserProfile` table | The Flighty user ID to query (normally auto-detected; set only if overriding). |
| `FLIGHT_ANIMATOR_BASE_URL` | `https://flights.sailingnaturali.com` | Base URL for `animate_trip` route links (consumed by the companion flight-animator app). |

## Full Disk Access Requirement

**Important:** The MCP server needs macOS Full Disk Access to read the Flighty database.

**Symptom:** If the server fails to connect or reads hang indefinitely, it's likely because Full Disk Access is missing.

**Solution:**
1. Open **System Preferences** → **Privacy & Security** → **Full Disk Access**.
2. Add the app that will launch this server:
   - If using **Claude Desktop**, add `Claude.app`.
   - If using **Claude Code CLI** or **Terminal**, add `/Applications/Terminal.app` (or whatever terminal app you use).
   - If using a different tool, add that application.
3. Restart the app (or kill and relaunch it).
4. Try again.

The database lives at `~/Library/Containers/com.flightyapp.flighty/Data/Documents/`, which is in your user's private container — Full Disk Access is required for any application to read it.
