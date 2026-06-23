# flighty-mcp — `animate_trip` route emitter (flight-animator coupling)

**Date:** 2026-06-23
**Status:** Approved design, pre-implementation
**Author:** Bryan + Claude
**Builds on:** the shipped read-only flighty-mcp (`list_my_flights`/`get_flight`/`flight_stats`)
**Couples to:** `flight-animator` (`docs/superpowers/specs/2026-06-23-flight-animator-design.md`)

## Purpose

Add one tool, `animate_trip`, that turns a destination-oriented natural request
("animate my flight to Japan") into a **flight-animator `?d=` route URL** built from the
owner's own flight history. The MCP resolves the trip and returns ready-to-share URLs; the
calling agent handles any conversational disambiguation (the tool returns structured data, it
does not converse).

The flight-animator consumes an ordered list of **stops** (nodes); flighty-mcp stores
**legs** (edges). This feature bridges that gap: find the connected run of legs that forms
"the trip to X", collapse it into stops, and encode the animator payload.

## Non-goals (v1)

- No new conversational ability in the tool itself — disambiguation is returned as data.
- No free-text temporal parsing ("last week"); the agent maps that to `after`/`before`.
- No writing/mutation; read-only is preserved.
- No ground/non-flown segments; a trip is a connected run of **flights** only.
- The animator app is not built or called here; this feature only produces the URL/payload.

## The tool

```
animate_trip(destination: str, origin: str | None = None,
             after: str | None = None, before: str | None = None) -> dict
```

- `destination` (required): IATA code, city, or country (case-insensitive), matched against
  airports the owner has actually flown **into**.
- `origin` (optional): same matching, against airports flown **from**; constrains/trims the
  trip start. If omitted, the trip's natural start is found by the backward walk.
- `after`/`before` (optional, ISO `YYYY-MM-DD`): restrict which occurrence of the trip to use.

### Return shapes

`ok`:
```jsonc
{
  "status": "ok",
  "url": "https://flights.sailingnaturali.com/?d=<base64url>",      // one-way (default)
  "round_trip_url": "https://flights.sailingnaturali.com/?d=<...>", // or null if no return run
  "home": "YVR",                 // origin used, or inferred home
  "home_confidence": 0.92,       // share of departures when inferred; 1.0 if origin given
  "destination": "NRT",
  "stops": [                     // human-readable summary of the one-way route
    {"code": "YVR", "label": "Vancouver", "depart": "2026-04-02T13:10:00-07:00"},
    {"code": "SFO", "label": "San Francisco", "arrive": "...", "depart": "..."},
    {"code": "NRT", "label": "Tokyo", "arrive": "2026-04-03T16:40:00+09:00"}
  ],
  "start_date": "2026-04-02",
  "end_date": "2026-04-03",
  "leg_count": 2
}
```

`ambiguous_destination` — the phrase matched **distinct places across different trips**:
```jsonc
{"status": "ambiguous_destination",
 "candidates": [{"code": "NRT", "city": "Tokyo", "country": "JP", "most_recent": "2026-04-03"},
                {"code": "KIX", "city": "Osaka", "country": "JP", "most_recent": "2024-09-11"}]}
```

`confirm_home` — no `origin` given **and** inferred home is low-confidence (< 0.4 share),
so the natural start / round trip can't be trusted:
```jsonc
{"status": "confirm_home", "inferred_home": "YVR", "home_confidence": 0.31,
 "alternatives": ["SEA", "YYC"]}
```

`no_match` — destination (or a supplied origin) not found in the owner's flown history:
```jsonc
{"status": "no_match", "field": "destination", "query": "Reykjavik"}
```

## Trip-finding algorithm

Works entirely off the owner's legs (the existing leg query, fetched **chronologically
ascending** with coords + airport-local ISO `departure`/`arrival` + city/country/iata).

1. **Resolve destination → airport set.** Match `destination` against airports that appear as
   an **arrival** in the owner's legs, in priority order: exact IATA (3 letters) → city
   (case-insensitive equals, then contains) → country (ISO-2 code or name). Empty → `no_match`.
2. **Resolve origin** (if given) the same way against **departure** airports. Empty → `no_match`
   (`field:"origin"`).
3. **Gather candidate arrival legs** — owner legs whose arrival airport ∈ destination set,
   filtered to `[after, before)` if provided.
4. **Disambiguate place vs occurrence.**
   - If the candidates span **>1 distinct destination airport** → `ambiguous_destination`
     (one entry per distinct airport, each with its most-recent date).
   - Otherwise (single destination airport, possibly multiple dates) → **auto-pick the
     occurrence**: the soonest **upcoming** arrival (departure timestamp in the future); else
     the **most recent** past arrival. (The agent narrows further via `after`/`before`.)
5. **Walk backward to build the outbound trip.** Let `T` = the chosen arrival leg. Start
   `trip=[T]`, `cur=T`. Repeat: find the owner leg `prev` with the latest departure such that
   `prev.arrival_airport == cur.departure_airport` and
   `0 ≤ (cur.departure_ts − prev.arrival_ts) ≤ SAME_TRIP_GAP` (default **24h**). If found,
   prepend and set `cur=prev`; if `origin` was given and `prev.departure_airport == origin`,
   stop. If none found, stop. If `origin` was given but never reached in the run → `no_match`
   (`field:"origin"`).
6. **Infer home** (for labeling + round trip): the owner's most-common **departure** airport
   overall; `home_confidence` = its share of departures. If `origin` given, `home = origin`,
   confidence `1.0`. If no `origin` and confidence < 0.4 → `confirm_home`.
7. **Round-trip return run.** Find the next owner leg departing the destination airport with
   departure after `T.arrival_ts`; walk **forward** while connected (≤ `SAME_TRIP_GAP`). If
   that run ends back at `home` → it is the return; otherwise `round_trip_url = null`.

`SAME_TRIP_GAP` is a single tunable constant (default 24h) defined in one place.

## Edge → node transform

Given ordered trip legs `L1..Ln`:
- `stops[0]` = `L1.from`: `{code, lat, lon, label, depart: L1.departure}` (no `arrive`).
- for `i` in `1..n`: stop = `Li.to`: `{code, lat, lon, label, arrive: Li.arrival,
  depart: L(i+1).departure}` — within a trip `Li.to == L(i+1).from`, so it is one shared stop.
- last stop = `Ln.to`: `arrive` only.
- **Round trip:** concatenate outbound + return legs first, then transform. The destination
  becomes the pivot stop carrying `arrive` (landing) and `depart` (leaving after the stay),
  i.e. a long dwell; home appears at both ends.

`label` = the airport's **city**. `lat`/`lon` are always embedded so the app needs no lookup.
Timestamps are the legs' existing airport-local ISO 8601 strings (with offset), reused verbatim.

## Payload contract (shared with flight-animator)

The `?d=` value is `base64url(JSON.stringify(stops))`, with no padding, where `stops` is:
```jsonc
Array<{
  code?: string,   // IATA, uppercase
  lat: number,
  lon: number,
  label: string,   // city
  arrive?: string, // ISO 8601 with offset; omitted on the first stop
  depart?: string  // ISO 8601 with offset; omitted on the last stop
}>
```
URL = `${BASE}/?d=<enc>`. `BASE` defaults to `https://flights.sailingnaturali.com`, overridable
via env `FLIGHT_ANIMATOR_BASE_URL`.

**Dwell semantics (pinned):** dwell at a stop = `depart − arrive` of **that same stop**. The
flight-animator spec is updated to match (its prior "next stop's depart" wording was corrected).
This payload schema is the canonical contract; the animator's decoder and the
flighty-mcp encoder must agree, enforced by a shared **golden vector** (a fixed `stops` array
and its exact base64url string) tested on both sides.

## Module layout

```
flighty_mcp/
  trips.py      # resolve origin/destination, pick occurrence, backward/forward connected walk
  animator.py   # edge->node transform + base64url payload + URL assembly
  server.py     # + animate_trip tool (thin wrapper)
```

- `trips.py` depends on `db.py` (connection, owner) and an internal helper that returns all
  owner legs ascending (reuse the existing leg SQL, ordered ASC; no archived/upcoming filter —
  full history). It is pure logic over that list otherwise.
- `animator.py` is pure: `stops_from_legs(legs) -> list[stop]` and
  `encode_route(stops, base_url) -> str`. No DB, no network.
- `server.py`'s `animate_trip` validates args, calls `trips.find_trip(...)`, and on success
  calls `animator` for both the one-way and round-trip URLs.

## Error handling

- Unresolvable `destination`/`origin` → `no_match` with the offending field + query.
- Destination spanning multiple places → `ambiguous_destination` with candidates.
- Low-confidence home with no `origin` → `confirm_home`.
- A single isolated leg (no connected predecessors) is still a valid one-stop-pair trip
  (origin → destination) — not an error.
- Bad `after`/`before` reuse the shared `iso_date_to_ts` clear error.
- Read errors / missing DB reuse the existing fail-fast Full Disk Access guard.

## Testing & CI

TDD against the synthetic fixture, extended with a multi-leg connected trip
(e.g. `YVR→SFO→NRT`), a matching **return** run (`NRT→...→YVR`) after a multi-day stay, a
**second** Japan airport on a different trip (to exercise `ambiguous_destination`), and a
disconnected pair. Coverage:
- `trips`: destination/origin resolution (code/city/country), occurrence pick
  (upcoming-pref → recency), backward walk with the 24h threshold, origin trimming, home
  inference + `confirm_home`, return-run detection, `no_match`.
- `animator`: edge→node shaping (first/middle/last/pivot stops), and a **golden encode
  vector** — a fixed `stops` array → exact base64url string (the cross-repo contract anchor).
- `server`: `animate_trip` returns each status shape; both URLs present on `ok`.
CI unchanged (uv + pytest + ruff).

## Open items resolved in implementation

- Exact `home_confidence` formula edge cases (ties, single-airport histories).
- Final `SAME_TRIP_GAP` value after eyeballing real trips (default 24h).
- The golden-vector bytes (fixed once, mirrored into the animator repo's tests).
```
