"""Resolve "trip to X" from the owner's flights and emit flight-animator route URLs."""
import time
from collections import Counter

from flighty_mcp.animator import encode_route, stops_from_legs
from flighty_mcp.db import connect, resolve_owner_id
from flighty_mcp.filters import iso_date_to_ts
from flighty_mcp.flights import Leg, local_date, owner_legs_asc

SAME_TRIP_GAP = 24 * 3600  # seconds; max layover for two legs to count as the same trip


def resolve_airports(legs: list[Leg], query: str, side: str) -> set[str]:
    """Airport ids on `side` ("dep"/"arr") matching `query`: IATA code -> city -> country."""
    q = query.strip()
    if not q:
        return set()
    qup = q.upper()

    def get(leg: Leg, suffix: str):
        return getattr(leg, f"{side}_{suffix}")

    if len(q) == 3 and q.isalpha():
        ids = {get(leg, "id") for leg in legs if (get(leg, "code") or "").upper() == qup}
        if ids:
            return ids
    ids = {get(leg, "id") for leg in legs if (get(leg, "city") or "").upper() == qup}
    if ids:
        return ids
    ids = {get(leg, "id") for leg in legs if qup in (get(leg, "city") or "").upper()}
    if ids:
        return ids
    return {
        get(leg, "id")
        for leg in legs
        if (get(leg, "country") or "").upper() == qup
        or (get(leg, "country_name") or "").upper() == qup
        or qup in (get(leg, "country_name") or "").upper()
    }


def infer_home(legs: list[Leg]) -> tuple[str | None, str | None, float]:
    """Home = most common departure airport; confidence = its share of departures."""
    if not legs:
        return None, None, 0.0
    counts = Counter(leg.dep_id for leg in legs)
    home_id, c = counts.most_common(1)[0]
    code = next((leg.dep_code for leg in legs if leg.dep_id == home_id), None)
    return home_id, code, c / sum(counts.values())


def _walk_back(legs: list[Leg], target: Leg, origin_ids: set[str] | None) -> list[Leg]:
    trip = [target]
    cur = target
    while True:
        if origin_ids is not None and cur.dep_id in origin_ids:
            break
        prevs = [
            leg for leg in legs
            if leg.arr_id == cur.dep_id and leg.arr_ts is not None
            and leg.dep_ts < cur.dep_ts and 0 <= (cur.dep_ts - leg.arr_ts) <= SAME_TRIP_GAP
        ]
        if not prevs:
            break
        prev = max(prevs, key=lambda leg: leg.arr_ts)
        trip.insert(0, prev)
        cur = prev
    return trip


def _walk_return(legs: list[Leg], target: Leg, home_ids: set[str]) -> list[Leg]:
    dest_id = target.arr_id
    pivot_ts = target.arr_ts if target.arr_ts is not None else target.dep_ts
    # The first return leg is intentionally NOT gap-bounded: the destination dwell (a
    # multi-day stay) is the point of a round trip. Only intra-run legs use SAME_TRIP_GAP.
    starts = [leg for leg in legs if leg.dep_id == dest_id and leg.dep_ts > pivot_ts]
    if not starts:
        return []
    cur = min(starts, key=lambda leg: leg.dep_ts)
    run = [cur]
    while cur.arr_id not in home_ids:
        nexts = [
            leg for leg in legs
            if leg.dep_id == cur.arr_id and cur.arr_ts is not None
            and leg.dep_ts > cur.dep_ts and 0 <= (leg.dep_ts - cur.arr_ts) <= SAME_TRIP_GAP
        ]
        if not nexts:
            return []
        cur = min(nexts, key=lambda leg: leg.dep_ts)
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
        leg for leg in legs
        if leg.arr_id in dest_ids
        and (after_ts is None or leg.dep_ts >= after_ts)
        and (before_ts is None or leg.dep_ts < before_ts)
    ]
    if not cands:
        return {"status": "no_match", "field": "destination", "query": destination}

    distinct = sorted({leg.arr_id for leg in cands})
    if len(distinct) > 1:
        candidates = []
        for aid in distinct:
            recent = max((leg for leg in cands if leg.arr_id == aid), key=lambda leg: leg.dep_ts)
            candidates.append({
                "code": recent.arr_code, "city": recent.arr_city, "country": recent.arr_country,
                "most_recent": local_date(recent.arr_ts or recent.dep_ts, recent.arr_tz or recent.dep_tz),
            })
        return {"status": "ambiguous_destination", "candidates": candidates}

    upcoming = [leg for leg in cands if leg.dep_ts > now_ts]
    target = min(upcoming, key=lambda leg: leg.dep_ts) if upcoming else max(cands, key=lambda leg: leg.dep_ts)

    home_id, home_code, home_conf = infer_home(legs)
    if origin_ids is None and home_conf < 0.4:
        counts = Counter(leg.dep_id for leg in legs)
        alt_codes = [
            next((leg.dep_code for leg in legs if leg.dep_id == aid), None)
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


def find_trip(destination: str, origin: str | None = None,
              after: str | None = None, before: str | None = None) -> dict:
    """Fetch the owner's legs and plan the trip to `destination`."""
    con = connect()
    try:
        legs = owner_legs_asc(con, resolve_owner_id(con))
    finally:
        con.close()
    return plan_trip(legs, destination, origin=origin, after=after, before=before)
