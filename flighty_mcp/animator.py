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
