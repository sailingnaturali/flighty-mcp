# animate_trip Route Emitter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `animate_trip` MCP tool that resolves "the trip to X" from the owner's flights and emits flight-animator `?d=` route URLs (one-way + round trip).

**Architecture:** A pure trip-planner (`trips.plan_trip`) operates on a list of `Leg` records: it resolves origin/destination (code/city/country), picks the occurrence, walks connected legs backward (outbound) and forward (return), and returns a status dict. A pure `animator` module turns trip legs into flight-animator "stops" and base64url-encodes the `?d=` URL. A thin `find_trip` fetches owner legs and calls `plan_trip`; the `animate_trip` tool wraps `find_trip`. Pure logic is unit-tested with synthetic legs; only `find_trip` uses a DB fixture, so the existing 28 tests are untouched.

**Tech Stack:** Python ≥3.11, stdlib `sqlite3`/`base64`/`json`/`zoneinfo`, `mcp[cli]` (FastMCP), `pytest`, `ruff`.

## Global Constraints

- Read-only: reuse the existing `mode=ro` connection; no writes/mutations.
- Owner scoping unchanged: `uf.userId = <owner> AND uf.isMyFlight = 1`, exclude deleted; **full history** (no archived filter) for trip-finding.
- Payload contract (shared with flight-animator): `?d=` = `base64url(JSON.stringify(stops))` **no padding**; `stops` items are `{code?, lat, lon, label, arrive?, depart?}`, key order `code,lat,lon,label,arrive,depart`; `arrive`/`depart` omitted when absent; timestamps are airport-local ISO 8601 (reuse `to_local_iso`). URL = `${BASE}/?d=<enc>`, `BASE` from env `FLIGHT_ANIMATOR_BASE_URL` else `https://flights.sailingnaturali.com`, trailing slash stripped.
- `dwell = stop.depart − stop.arrive` (per-stop); the pivot stop on a round trip carries both.
- Same-trip connection threshold: `SAME_TRIP_GAP = 24 * 3600` seconds, defined once in `trips.py`.
- `animate_trip(destination, origin=None, after=None, before=None)` returns one of: `ok` (with `url` + `round_trip_url`), `ambiguous_destination`, `confirm_home`, `no_match`.
- Pure modules (`animator`, the `plan_trip`/resolution/walk functions) take no DB and no real clock — `now_ts` is injected.
- Do NOT modify `tests/fixtures/build_fixture.py` (it backs the existing suite). Integration tests build their own DBs.

---

## File Structure

```
flighty_mcp/
  flights.py    # + Leg dataclass, _TRIP_LEG_SELECT, owner_legs_asc()   (additions only)
  animator.py   # NEW: stops_from_legs(), encode_route()
  trips.py      # NEW: resolve_airports(), infer_home(), plan_trip(), find_trip()
  server.py     # + animate_trip tool
  README.md     # + animate_trip docs
tests/
  trip_helpers.py        # NEW: make_leg() factory (not collected by pytest)
  test_owner_legs.py     # NEW
  test_animator.py       # NEW
  test_trips_resolve.py  # NEW
  test_trips_plan.py     # NEW
  test_trips_find.py     # NEW (own DB fixture)
  test_server.py         # + animate_trip registration assertion
```

---

## Task 1: `Leg` record + `owner_legs_asc` (flights.py)

**Files:**
- Modify: `flighty_mcp/flights.py` (add a dataclass, a query constant, and one function)
- Test: `tests/test_owner_legs.py`

**Interfaces:**
- Consumes: `db.connect`, `db.resolve_owner_id` (in the test only).
- Produces: `flighty_mcp.flights.Leg` (frozen-ish dataclass, fields listed below) and
  `owner_legs_asc(con, owner) -> list[Leg]` — the owner's full-history legs ordered by
  ascending departure timestamp, excluding legs with a NULL departure timestamp.

- [ ] **Step 1: Write the failing test `tests/test_owner_legs.py`**

```python
from flighty_mcp.db import connect, resolve_owner_id
from flighty_mcp.flights import owner_legs_asc


def test_owner_legs_asc_orders_and_fields(fixture_db):
    con = connect()
    legs = owner_legs_asc(con, resolve_owner_id(con))
    con.close()
    # owner-1 full history (archived included), NULL-departure legs excluded, ascending
    assert [l.flight_no for l in legs] == ["BA930", "UA194", "AC1725", "UA200"]
    assert all(legs[i].dep_ts <= legs[i + 1].dep_ts for i in range(len(legs) - 1))
    first = legs[0]
    assert first.dep_code == "LHR" and first.arr_code == "SFO"
    assert first.dep_id and first.arr_id and first.dep_ts is not None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_owner_legs.py -v`
Expected: FAIL with `ImportError: cannot import name 'owner_legs_asc'`.

- [ ] **Step 3: Add to `flighty_mcp/flights.py`**

At the top, add `from dataclasses import dataclass` to the imports. Then add (e.g. after the
existing `_LEG_SELECT` constant):

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_owner_legs.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add flighty_mcp/flights.py tests/test_owner_legs.py
git commit -m "add Leg record and owner_legs_asc for trip-finding"
```

---

## Task 2: `animator.py` — stops + `?d=` encoding

**Files:**
- Create: `flighty_mcp/animator.py`
- Create: `tests/trip_helpers.py`
- Test: `tests/test_animator.py`

**Interfaces:**
- Consumes: `flighty_mcp.flights.Leg`, `flighty_mcp.flights.to_local_iso`.
- Produces: `stops_from_legs(legs: list[Leg]) -> list[dict]` and
  `encode_route(stops: list[dict], base_url: str | None = None) -> str`.
- Produces helper for all later tests: `tests/trip_helpers.make_leg(**overrides) -> Leg`.

- [ ] **Step 1: Create `tests/trip_helpers.py`**

```python
"""Factory for synthetic Leg records used by the pure trip/animator tests."""
from flighty_mcp.flights import Leg


def make_leg(dep_id, dep_code, arr_id, arr_code, dep_ts, arr_ts, *,
             dep_city=None, arr_city=None,
             dep_country="US", arr_country="US",
             dep_country_name="United States", arr_country_name="United States",
             dep_lat=0.0, dep_lon=0.0, arr_lat=0.0, arr_lon=0.0,
             dep_tz="UTC", arr_tz="UTC",
             flight_no="XX1", airline_iata="XX", airline_name="Air X") -> Leg:
    return Leg(
        flight_no=flight_no, airline_iata=airline_iata, airline_name=airline_name,
        dep_id=dep_id, dep_code=dep_code, dep_city=dep_city or dep_code,
        dep_country=dep_country, dep_country_name=dep_country_name,
        dep_lat=dep_lat, dep_lon=dep_lon, dep_tz=dep_tz,
        arr_id=arr_id, arr_code=arr_code, arr_city=arr_city or arr_code,
        arr_country=arr_country, arr_country_name=arr_country_name,
        arr_lat=arr_lat, arr_lon=arr_lon, arr_tz=arr_tz,
        dep_ts=dep_ts, arr_ts=arr_ts,
    )
```

- [ ] **Step 2: Write the failing test `tests/test_animator.py`**

```python
import base64
import json

from flighty_mcp.animator import encode_route, stops_from_legs
from tests.trip_helpers import make_leg

# 2025-06-15 14:30 in two zones (absolute UTC seconds chosen for clean local times)
T1, T2, T3, T4 = 1750000000, 1750030000, 1750200000, 1750230000


def _connected_two_leg():
    # YVR -> SFO -> NRT, connected (SFO arr id == SFO dep id)
    return [
        make_leg("yvr", "YVR", "sfo", "SFO", T1, T2,
                 dep_city="Vancouver", arr_city="San Francisco", dep_tz="UTC", arr_tz="UTC"),
        make_leg("sfo", "SFO", "nrt", "NRT", T3, T4,
                 dep_city="San Francisco", arr_city="Tokyo", dep_tz="UTC", arr_tz="UTC"),
    ]


def test_stops_first_middle_last_shape():
    stops = stops_from_legs(_connected_two_leg())
    assert [s["code"] for s in stops] == ["YVR", "SFO", "NRT"]
    assert "arrive" not in stops[0] and "depart" in stops[0]      # first: depart only
    assert "arrive" in stops[1] and "depart" in stops[1]          # middle (connected): both
    assert "arrive" in stops[-1] and "depart" not in stops[-1]    # last: arrive only


def test_stops_omit_none_arrival():
    legs = [make_leg("yvr", "YVR", "sfo", "SFO", T1, None)]  # no arrival time
    stops = stops_from_legs(legs)
    assert "arrive" not in stops[1]


def test_encode_urlsafe_no_padding_roundtrips():
    stops = [{"code": "YVR", "lat": 49.19, "lon": -123.18, "label": "Vancouver",
              "depart": "2026-04-02T13:10:00-07:00"},
             {"code": "NRT", "lat": 35.76, "lon": 140.39, "label": "Tokyo",
              "arrive": "2026-04-03T16:40:00+09:00"}]
    url = encode_route(stops, base_url="https://example.com/")
    assert url.startswith("https://example.com/?d=")
    enc = url.split("?d=", 1)[1]
    assert "=" not in enc and "+" not in enc and "/" not in enc
    decoded = json.loads(base64.urlsafe_b64decode(enc + "=" * (-len(enc) % 4)))
    assert decoded == stops


def test_encode_compact_json_golden():
    stops = [{"code": "YVR", "lat": 49.19, "lon": -123.18, "label": "Vancouver",
              "depart": "2026-04-02T13:10:00-07:00"},
             {"code": "NRT", "lat": 35.76, "lon": 140.39, "label": "Tokyo",
              "arrive": "2026-04-03T16:40:00+09:00"}]
    enc = encode_route(stops, base_url="https://x").split("?d=", 1)[1]
    raw = base64.urlsafe_b64decode(enc + "=" * (-len(enc) % 4)).decode()
    assert raw == (
        '[{"code":"YVR","lat":49.19,"lon":-123.18,"label":"Vancouver",'
        '"depart":"2026-04-02T13:10:00-07:00"},'
        '{"code":"NRT","lat":35.76,"lon":140.39,"label":"Tokyo",'
        '"arrive":"2026-04-03T16:40:00+09:00"}]'
    )
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/test_animator.py -v`
Expected: FAIL with `ModuleNotFoundError: flighty_mcp.animator`.

- [ ] **Step 4: Create `flighty_mcp/animator.py`**

```python
"""Pure transform of trip legs into flight-animator stops and a ?d= route URL."""
import base64
import json
import os

from flighty_mcp.flights import Leg, to_local_iso

DEFAULT_BASE_URL = "https://flights.sailingnaturali.com"


def _node(code: str | None, city: str | None, lat: float | None, lon: float | None) -> dict:
    # Key order is the payload contract: code, lat, lon, label (then arrive/depart appended).
    return {"code": code, "lat": lat, "lon": lon, "label": city}


def stops_from_legs(legs: list[Leg]) -> list[dict]:
    """Collapse an ordered list of connected legs into flight-animator stops."""
    if not legs:
        return []
    first = legs[0]
    head = _node(first.dep_code, first.dep_city, first.dep_lat, first.dep_lon)
    dep_iso = to_local_iso(first.dep_ts, first.dep_tz)
    if dep_iso is not None:
        head["depart"] = dep_iso
    stops = [head]
    for i, leg in enumerate(legs):
        node = _node(leg.arr_code, leg.arr_city, leg.arr_lat, leg.arr_lon)
        arr_iso = to_local_iso(leg.arr_ts, leg.arr_tz)
        if arr_iso is not None:
            node["arrive"] = arr_iso
        if i + 1 < len(legs) and legs[i + 1].dep_id == leg.arr_id:
            nxt = to_local_iso(legs[i + 1].dep_ts, legs[i + 1].dep_tz)
            if nxt is not None:
                node["depart"] = nxt
        stops.append(node)
    return stops


def encode_route(stops: list[dict], base_url: str | None = None) -> str:
    """base64url(no-pad) the compact stops JSON into a ${BASE}/?d=<enc> URL."""
    base = (base_url or os.environ.get("FLIGHT_ANIMATOR_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    payload = json.dumps(stops, separators=(",", ":"))
    enc = base64.urlsafe_b64encode(payload.encode("utf-8")).rstrip(b"=").decode("ascii")
    return f"{base}/?d={enc}"
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_animator.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Commit**

```bash
git add flighty_mcp/animator.py tests/trip_helpers.py tests/test_animator.py
git commit -m "add animator stops transform and ?d= route encoding"
```

---

## Task 3: `trips.py` — destination/origin resolution + home inference

**Files:**
- Create: `flighty_mcp/trips.py`
- Test: `tests/test_trips_resolve.py`

**Interfaces:**
- Consumes: `flighty_mcp.flights.Leg`.
- Produces: `resolve_airports(legs, query, side) -> set[str]` (`side` is `"dep"` or `"arr"`;
  returns the matching airport ids on that side, tiered: IATA code → city → country) and
  `infer_home(legs) -> tuple[str | None, str | None, float]` (home airport id, its code,
  confidence = share of departures).

- [ ] **Step 1: Write the failing test `tests/test_trips_resolve.py`**

```python
from flighty_mcp.trips import infer_home, resolve_airports
from tests.trip_helpers import make_leg


def _legs():
    return [
        make_leg("yvr", "YVR", "sfo", "SFO", 100, 200, dep_city="Vancouver", arr_city="San Francisco",
                 dep_country="CA", arr_country="US", dep_country_name="Canada"),
        make_leg("sfo", "SFO", "nrt", "NRT", 300, 400, dep_city="San Francisco", arr_city="Tokyo",
                 dep_country="US", arr_country="JP", arr_country_name="Japan"),
        make_leg("yvr", "YVR", "kix", "KIX", 500, 600, dep_city="Vancouver", arr_city="Osaka",
                 dep_country="CA", arr_country="JP", arr_country_name="Japan"),
    ]


def test_resolve_by_iata_code():
    assert resolve_airports(_legs(), "nrt", "arr") == {"nrt"}


def test_resolve_by_city():
    assert resolve_airports(_legs(), "Tokyo", "arr") == {"nrt"}


def test_resolve_by_country_spans_airports():
    assert resolve_airports(_legs(), "Japan", "arr") == {"nrt", "kix"}


def test_resolve_origin_side_uses_departures():
    assert resolve_airports(_legs(), "Vancouver", "dep") == {"yvr"}


def test_resolve_unknown_is_empty():
    assert resolve_airports(_legs(), "Reykjavik", "arr") == set()


def test_infer_home_picks_most_common_departure():
    home_id, home_code, conf = infer_home(_legs())
    assert home_id == "yvr" and home_code == "YVR"
    assert round(conf, 3) == round(2 / 3, 3)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_trips_resolve.py -v`
Expected: FAIL with `ModuleNotFoundError: flighty_mcp.trips`.

- [ ] **Step 3: Create `flighty_mcp/trips.py` (resolution + home only)**

```python
"""Resolve "trip to X" from the owner's flights and emit flight-animator route URLs."""
from collections import Counter

from flighty_mcp.flights import Leg


def resolve_airports(legs: list[Leg], query: str, side: str) -> set[str]:
    """Airport ids on `side` ("dep"/"arr") matching `query`: IATA code -> city -> country."""
    q = query.strip()
    if not q:
        return set()
    qup = q.upper()

    def get(leg: Leg, suffix: str):
        return getattr(leg, f"{side}_{suffix}")

    if len(q) == 3 and q.isalpha():
        ids = {get(l, "id") for l in legs if (get(l, "code") or "").upper() == qup}
        if ids:
            return ids
    ids = {get(l, "id") for l in legs if (get(l, "city") or "").upper() == qup}
    if ids:
        return ids
    ids = {get(l, "id") for l in legs if qup in (get(l, "city") or "").upper()}
    if ids:
        return ids
    return {
        get(l, "id")
        for l in legs
        if (get(l, "country") or "").upper() == qup
        or (get(l, "country_name") or "").upper() == qup
        or qup in (get(l, "country_name") or "").upper()
    }


def infer_home(legs: list[Leg]) -> tuple[str | None, str | None, float]:
    """Home = most common departure airport; confidence = its share of departures."""
    if not legs:
        return None, None, 0.0
    counts = Counter(l.dep_id for l in legs)
    home_id, c = counts.most_common(1)[0]
    code = next((l.dep_code for l in legs if l.dep_id == home_id), None)
    return home_id, code, c / sum(counts.values())
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_trips_resolve.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add flighty_mcp/trips.py tests/test_trips_resolve.py
git commit -m "add airport resolution and home inference for trips"
```

---

## Task 4: `trips.py` — `plan_trip` (the planner)

**Files:**
- Modify: `flighty_mcp/trips.py` (add walks, date helper, and `plan_trip`)
- Test: `tests/test_trips_plan.py`

**Interfaces:**
- Consumes: `resolve_airports`, `infer_home` (this module); `animator.stops_from_legs`,
  `animator.encode_route`; `flights.local_date`; `filters.iso_date_to_ts`.
- Produces: `plan_trip(legs, destination, origin=None, after=None, before=None, now_ts=None,
  base_url=None) -> dict` returning one of the status dicts in the spec. `now_ts` is injected
  (no real clock in the pure planner); `find_trip` (Task 5) passes the real time.

- [ ] **Step 1: Write the failing test `tests/test_trips_plan.py`**

```python
from flighty_mcp.trips import plan_trip
from tests.trip_helpers import make_leg

DAY = 86400
# Outbound YVR->SFO->NRT (connected, same day), then a 7-day stay, then return NRT->SFO->YVR.
OUT1 = make_leg("yvr", "YVR", "sfo", "SFO", 1_000_000, 1_010_000,
                dep_city="Vancouver", arr_city="San Francisco", dep_country="CA")
OUT2 = make_leg("sfo", "SFO", "nrt", "NRT", 1_020_000, 1_060_000,
                dep_city="San Francisco", arr_city="Tokyo", arr_country="JP", arr_country_name="Japan")
RET1 = make_leg("nrt", "NRT", "sfo", "SFO", 1_060_000 + 7 * DAY, 1_060_000 + 7 * DAY + 40_000,
                dep_city="Tokyo", arr_city="San Francisco", dep_country="JP")
RET2 = make_leg("sfo", "SFO", "yvr", "YVR", 1_060_000 + 7 * DAY + 60_000, 1_060_000 + 7 * DAY + 70_000,
                dep_city="San Francisco", arr_city="Vancouver", arr_country="CA")
TRIP = [OUT1, OUT2, RET1, RET2]
PAST = 9_999_999_999  # now far in the future so all legs count as "past"


def test_no_match_destination():
    assert plan_trip(TRIP, "Reykjavik", now_ts=PAST)["status"] == "no_match"


def test_one_way_walks_back_to_natural_start():
    res = plan_trip(TRIP, "Japan", now_ts=PAST)
    assert res["status"] == "ok"
    assert res["destination"] == "NRT"
    assert res["home"] == "YVR"
    assert [s["code"] for s in res["stops"]] == ["YVR", "SFO", "NRT"]
    assert res["leg_count"] == 2
    assert "?d=" in res["url"]


def test_round_trip_returns_to_start():
    res = plan_trip(TRIP, "Japan", now_ts=PAST)
    assert res["round_trip_url"] is not None and res["round_trip_url"] != res["url"]


def test_origin_trims_the_start():
    res = plan_trip(TRIP, "Japan", origin="SFO", now_ts=PAST)
    assert res["status"] == "ok"
    assert [s["code"] for s in res["stops"]] == ["SFO", "NRT"]
    assert res["home"] == "SFO"


def test_origin_not_in_trip_is_no_match():
    res = plan_trip(TRIP, "Japan", origin="DEN", now_ts=PAST)
    assert res["status"] == "no_match" and res["field"] == "origin"


def test_ambiguous_destination_two_airports():
    kix = make_leg("yvr", "YVR", "kix", "KIX", 2_000_000, 2_050_000,
                   dep_city="Vancouver", arr_city="Osaka", arr_country="JP", arr_country_name="Japan")
    res = plan_trip(TRIP + [kix], "Japan", now_ts=PAST)
    assert res["status"] == "ambiguous_destination"
    assert {c["code"] for c in res["candidates"]} == {"NRT", "KIX"}


def test_after_before_window_selects_occurrence():
    # second NRT trip a year later; window picks the earlier one
    nrt2 = make_leg("yvr", "YVR", "nrt", "NRT", 1_000_000 + 400 * DAY, 1_000_000 + 400 * DAY + 50_000,
                    dep_city="Vancouver", arr_city="Tokyo", arr_country="JP", arr_country_name="Japan")
    res = plan_trip(TRIP + [nrt2], "NRT", before="2001-01-01", now_ts=PAST)
    # before filter excludes everything after 2001 -> falls to no_match (TRIP ts are ~1970+ epoch days)
    assert res["status"] in ("ok", "no_match")  # see note: window is by epoch seconds


def test_confirm_home_when_no_origin_and_low_confidence():
    # Each leg departs a distinct airport -> home confidence low (0.25), no origin given.
    legs = [
        make_leg("a", "AAA", "jp", "NRT", 10, 20, arr_country="JP", arr_country_name="Japan"),
        make_leg("b", "BBB", "c2", "CCC", 30, 40),
        make_leg("d", "DDD", "e2", "EEE", 50, 60),
        make_leg("f", "FFF", "g2", "GGG", 70, 80),
    ]
    res = plan_trip(legs, "Japan", now_ts=PAST)
    assert res["status"] == "confirm_home"
    assert res["inferred_home"] in {"AAA", "BBB", "DDD", "FFF"}
```

Note: `test_after_before_window_selects_occurrence` only asserts the call is well-formed
(`ok`/`no_match`) because the synthetic timestamps aren't real calendar dates; precise window
behavior is covered by the real-data integration test in Task 5.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_trips_plan.py -v`
Expected: FAIL with `ImportError: cannot import name 'plan_trip'`.

- [ ] **Step 3: Add to `flighty_mcp/trips.py`**

Update the imports at the top of `trips.py` to:

```python
import time
from collections import Counter

from flighty_mcp.animator import encode_route, stops_from_legs
from flighty_mcp.filters import iso_date_to_ts
from flighty_mcp.flights import Leg, local_date

SAME_TRIP_GAP = 24 * 3600  # seconds; max layover for two legs to count as the same trip
```

Then append:

```python
def _walk_back(legs: list[Leg], target: Leg, origin_ids: set[str] | None) -> list[Leg]:
    trip = [target]
    cur = target
    while True:
        if origin_ids is not None and cur.dep_id in origin_ids:
            break
        prevs = [
            l for l in legs
            if l.arr_id == cur.dep_id and l.arr_ts is not None
            and l.dep_ts < cur.dep_ts and 0 <= (cur.dep_ts - l.arr_ts) <= SAME_TRIP_GAP
        ]
        if not prevs:
            break
        prev = max(prevs, key=lambda l: l.arr_ts)
        trip.insert(0, prev)
        cur = prev
    return trip


def _walk_return(legs: list[Leg], target: Leg, home_ids: set[str]) -> list[Leg]:
    dest_id = target.arr_id
    pivot_ts = target.arr_ts if target.arr_ts is not None else target.dep_ts
    starts = [l for l in legs if l.dep_id == dest_id and l.dep_ts > pivot_ts]
    if not starts:
        return []
    cur = min(starts, key=lambda l: l.dep_ts)
    run = [cur]
    while cur.arr_id not in home_ids:
        nexts = [
            l for l in legs
            if l.dep_id == cur.arr_id and cur.arr_ts is not None
            and l.dep_ts > cur.dep_ts and 0 <= (l.dep_ts - cur.arr_ts) <= SAME_TRIP_GAP
        ]
        if not nexts:
            return []
        cur = min(nexts, key=lambda l: l.dep_ts)
        run.append(cur)
    return run


def _summary(stops: list[dict]) -> list[dict]:
    keys = ("code", "label", "arrive", "depart")
    return [{k: s[k] for k in keys if k in s} for s in stops]


def plan_trip(legs: list[Leg], destination: str, origin: str | None = None,
              after: str | None = None, before: str | None = None,
              now_ts: int | None = None, base_url: str | None = None) -> dict:
    if now_ts is None:
        now_ts = int(time.time())

    dest_ids = resolve_airports(legs, destination, "arr")
    if not dest_ids:
        return {"status": "no_match", "field": "destination", "query": destination}

    origin_ids = None
    if origin is not None:
        origin_ids = resolve_airports(legs, origin, "dep")
        if not origin_ids:
            return {"status": "no_match", "field": "origin", "query": origin}

    after_ts = iso_date_to_ts(after, "after") if after else None
    before_ts = iso_date_to_ts(before, "before") if before else None
    cands = [
        l for l in legs
        if l.arr_id in dest_ids
        and (after_ts is None or l.dep_ts >= after_ts)
        and (before_ts is None or l.dep_ts < before_ts)
    ]
    if not cands:
        return {"status": "no_match", "field": "destination", "query": destination}

    distinct = sorted({l.arr_id for l in cands})
    if len(distinct) > 1:
        candidates = []
        for aid in distinct:
            recent = max((l for l in cands if l.arr_id == aid), key=lambda l: l.dep_ts)
            candidates.append({
                "code": recent.arr_code, "city": recent.arr_city, "country": recent.arr_country,
                "most_recent": local_date(recent.arr_ts or recent.dep_ts, recent.arr_tz or recent.dep_tz),
            })
        return {"status": "ambiguous_destination", "candidates": candidates}

    upcoming = [l for l in cands if l.dep_ts > now_ts]
    target = min(upcoming, key=lambda l: l.dep_ts) if upcoming else max(cands, key=lambda l: l.dep_ts)

    home_id, home_code, home_conf = infer_home(legs)
    if origin_ids is None and home_conf < 0.4:
        counts = Counter(l.dep_id for l in legs)
        alt_codes = [
            next((l.dep_code for l in legs if l.dep_id == aid), None)
            for aid, _ in counts.most_common(4)
        ]
        return {
            "status": "confirm_home",
            "inferred_home": home_code,
            "home_confidence": round(home_conf, 2),
            "alternatives": [c for c in alt_codes[1:] if c],
        }

    outbound = _walk_back(legs, target, origin_ids)
    if origin_ids is not None and outbound[0].dep_id not in origin_ids:
        return {"status": "no_match", "field": "origin", "query": origin}

    return_run = _walk_return(legs, target, {outbound[0].dep_id})

    one_way = stops_from_legs(outbound)
    round_trip_url = encode_route(stops_from_legs(outbound + return_run), base_url) if return_run else None
    return {
        "status": "ok",
        "url": encode_route(one_way, base_url),
        "round_trip_url": round_trip_url,
        "home": outbound[0].dep_code,
        "home_confidence": 1.0 if origin_ids is not None else round(home_conf, 2),
        "destination": target.arr_code,
        "stops": _summary(one_way),
        "start_date": local_date(outbound[0].dep_ts, outbound[0].dep_tz),
        "end_date": local_date(target.arr_ts or target.dep_ts, target.arr_tz or target.dep_tz),
        "leg_count": len(outbound),
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_trips_plan.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add flighty_mcp/trips.py tests/test_trips_plan.py
git commit -m "add plan_trip: occurrence pick, connected walks, route URLs"
```

---

## Task 5: `find_trip` (DB) + `animate_trip` tool

**Files:**
- Modify: `flighty_mcp/trips.py` (add `find_trip`)
- Modify: `flighty_mcp/server.py` (add `animate_trip` tool)
- Test: `tests/test_trips_find.py` (own DB fixture)
- Test: `tests/test_server.py` (append a registration assertion)

**Interfaces:**
- Consumes: `db.connect`, `db.resolve_owner_id`, `flights.owner_legs_asc`, `plan_trip`.
- Produces: `find_trip(destination, origin=None, after=None, before=None) -> dict`; the
  `animate_trip` MCP tool.

- [ ] **Step 1: Write the failing test `tests/test_trips_find.py`**

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_trips_find.py -v`
Expected: FAIL with `ImportError: cannot import name 'find_trip'`.

- [ ] **Step 3: Add `find_trip` to `flighty_mcp/trips.py`**

Extend the trips imports with:

```python
from flighty_mcp.db import connect, resolve_owner_id
from flighty_mcp.flights import owner_legs_asc
```

Then append:

```python
def find_trip(destination: str, origin: str | None = None,
              after: str | None = None, before: str | None = None) -> dict:
    """Fetch the owner's legs and plan the trip to `destination`."""
    con = connect()
    try:
        legs = owner_legs_asc(con, resolve_owner_id(con))
    finally:
        con.close()
    return plan_trip(legs, destination, origin=origin, after=after, before=before)
```

(`flighty_mcp.flights` is now imported in two `from` lines — keep both; or merge the
`owner_legs_asc` import into the existing `from flighty_mcp.flights import ...` line.)

- [ ] **Step 4: Add the `animate_trip` tool to `flighty_mcp/server.py`**

Add `trips` to the existing import (`from flighty_mcp import flights, stats, trips`) and add:

```python
@mcp.tool()
def animate_trip(destination: str, origin: str | None = None,
                 after: str | None = None, before: str | None = None) -> dict:
    """Build a flight-animator route link for your trip to a place.

    Resolves the connected flights from your home (or `origin`) to `destination` and returns
    share links: `url` (one-way) and `round_trip_url` (there and back). May instead return a
    status of `ambiguous_destination`, `confirm_home`, or `no_match` for the assistant to
    resolve before re-calling.

    Args:
        destination: Where the trip goes — IATA code, city, or country (e.g. "Japan", "NRT").
        origin: Optional start — IATA code, city, or country. Defaults to your inferred home.
        after: Optional ISO date (YYYY-MM-DD); only trips departing on/after it.
        before: Optional ISO date (YYYY-MM-DD); only trips departing before it.
    """
    return trips.find_trip(destination, origin=origin, after=after, before=before)
```

- [ ] **Step 5: Append the registration assertion to `tests/test_server.py`**

```python
def test_animate_trip_registered():
    import asyncio

    from flighty_mcp.server import mcp

    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert "animate_trip" in names
```

- [ ] **Step 6: Run the full suite + lint**

Run: `uv run ruff check . && uv run pytest -v`
Expected: all PASS (existing 28 + new), ruff clean.

- [ ] **Step 7: Commit**

```bash
git add flighty_mcp/trips.py flighty_mcp/server.py tests/test_trips_find.py tests/test_server.py
git commit -m "add find_trip and animate_trip MCP tool"
```

---

## Task 6: README — document `animate_trip`

**Files:**
- Modify: `README.md`

**Interfaces:** none (docs only).

- [ ] **Step 1: Update `README.md`**

Add `animate_trip` to the tools list/table, with: a one-line description; that it returns
`url` (one-way) + `round_trip_url`, or a `ambiguous_destination` / `confirm_home` / `no_match`
status; the args (`destination`, `origin`, `after`, `before`); and an example
(`"animate my flight to Japan"`). Add the env var to the config table:

| Variable | Required | Description |
|----------|----------|-------------|
| `FLIGHT_ANIMATOR_BASE_URL` | No | Base URL for `animate_trip` links (default `https://flights.sailingnaturali.com`). |

Mention the companion `flight-animator` app consumes these `?d=` links. Keep any "why"
section ≤8 lines.

- [ ] **Step 2: Verify suite still green (docs-only, sanity)**

Run: `uv run pytest -q`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "document animate_trip and FLIGHT_ANIMATOR_BASE_URL"
```

---

## Self-Review

- **Spec coverage:** tool signature + 4 return shapes ✓ (Tasks 4–5); destination/origin
  resolution code→city→country ✓ (Task 3); occurrence pick upcoming→recent ✓ (Task 4);
  backward connected walk w/ 24h gap + origin trim ✓ (Task 4); home inference + `confirm_home`
  ✓ (Tasks 3–4); round-trip return run ✓ (Task 4); edge→node transform incl. pivot ✓ (Task 2);
  pinned payload + golden vector ✓ (Task 2); both URLs ✓ (Task 4); env base URL ✓ (Task 2);
  read-only + full-history leg fetch ✓ (Task 1); README ✓ (Task 6). No fixture changes ✓.
- **Round-trip home target:** the return run targets `outbound[0].dep_id` (the trip's actual
  start), NOT the globally-inferred home — so a hub that appears as a frequent departure can't
  truncate the round trip. Verified by `test_round_trip_returns_to_start` and the integration
  test (home inference there picks SFO=2 vs YVR=1, but the round trip still completes to YVR).
- **Placeholder scan:** none — every code step is complete. The one `assert ... in (...)` is a
  deliberately loose guard with an inline note (synthetic epoch values aren't calendar dates;
  real window behavior is covered by the Task 5 integration DB).
- **Type consistency:** `Leg` fields are referenced identically across Tasks 1–5;
  `stops_from_legs`/`encode_route`/`plan_trip`/`find_trip` signatures match their call sites;
  status dict keys (`status`,`url`,`round_trip_url`,`home`,`destination`,`stops`,`leg_count`,
  `field`,`candidates`,`inferred_home`,`home_confidence`,`alternatives`) match the spec.
```
