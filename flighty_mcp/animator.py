"""Pure transform of trip legs into flight-animator stops and a ?d= route URL."""
import base64
import json
import os
import urllib.request

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
    """base64url(no-pad) the compact route JSON into a ${BASE}/?d=<enc> URL.

    Payload is the versioned envelope shared with flight-animator's decodeRich:
    {"v": 1, "stops": [...]}.
    """
    base = (base_url or os.environ.get("FLIGHT_ANIMATOR_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    payload = json.dumps({"v": 1, "stops": stops}, separators=(",", ":"))
    enc = base64.urlsafe_b64encode(payload.encode("utf-8")).rstrip(b"=").decode("ascii")
    return f"{base}/?d={enc}"


def shorten_url(long_url: str, *, timeout: float = 3.0) -> str:
    """Trade a `{base}/?d=<payload>` URL for a short `{base}/t/<code>` link via the shortener.

    Returns the original URL unchanged on any failure, or when there's no `?d=` payload to
    shorten, so a shortener outage never blocks the animate_trip response.
    """
    marker = "/?d="
    if marker not in long_url:
        return long_url
    base, payload = long_url.split(marker, 1)
    try:
        req = urllib.request.Request(
            f"{base}/api/shorten",
            data=json.dumps({"d": payload}).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return long_url
            body = json.loads(resp.read())
        return body.get("url") or long_url
    except Exception:
        return long_url


def apply_shortening(result: dict, *, enabled: bool, shorten=shorten_url) -> dict:
    """Replace the long share URLs in an animate_trip result with short links, in place.

    No-op unless the result is a successful trip and shortening is enabled. `round_trip_url`
    may be None (one-way trip) and is left as-is in that case.
    """
    if result.get("status") != "ok" or not enabled:
        return result
    result["url"] = shorten(result["url"])
    if result.get("round_trip_url"):
        result["round_trip_url"] = shorten(result["round_trip_url"])
    return result
