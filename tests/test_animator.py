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
    # Versioned envelope shared with flight-animator's decodeRich.
    assert decoded == {"v": 1, "stops": stops}


def test_encode_compact_json_golden():
    stops = [{"code": "YVR", "lat": 49.19, "lon": -123.18, "label": "Vancouver",
              "depart": "2026-04-02T13:10:00-07:00"},
             {"code": "NRT", "lat": 35.76, "lon": 140.39, "label": "Tokyo",
              "arrive": "2026-04-03T16:40:00+09:00"}]
    enc = encode_route(stops, base_url="https://x").split("?d=", 1)[1]
    raw = base64.urlsafe_b64decode(enc + "=" * (-len(enc) % 4)).decode()
    assert raw == (
        '{"v":1,"stops":['
        '{"code":"YVR","lat":49.19,"lon":-123.18,"label":"Vancouver",'
        '"depart":"2026-04-02T13:10:00-07:00"},'
        '{"code":"NRT","lat":35.76,"lon":140.39,"label":"Tokyo",'
        '"arrive":"2026-04-03T16:40:00+09:00"}]}'
    )


def test_matches_flight_animator_golden_vector():
    # Cross-repo contract anchor: our encoder must byte-reproduce flight-animator's
    # canonical ?d= vector (src/route/__fixtures__/golden-d.json). If this breaks,
    # the two repos have diverged on the wire format.
    golden_stops = [
        {"code": "SFO", "label": "San Francisco", "depart": "2025-04-15T14:30:00Z"},
        {"code": "LHR", "label": "London", "arrive": "2025-04-15T22:15:00Z",
         "depart": "2025-04-18T09:00:00Z"},
        {"code": "CDG", "label": "Paris", "arrive": "2025-04-18T10:20:00Z"},
    ]
    golden_encoded = (
        "eyJ2IjoxLCJzdG9wcyI6W3siY29kZSI6IlNGTyIsImxhYmVsIjoiU2FuIEZyYW5jaXNjbyIsImRlcGFy"
        "dCI6IjIwMjUtMDQtMTVUMTQ6MzA6MDBaIn0seyJjb2RlIjoiTEhSIiwibGFiZWwiOiJMb25kb24iLCJh"
        "cnJpdmUiOiIyMDI1LTA0LTE1VDIyOjE1OjAwWiIsImRlcGFydCI6IjIwMjUtMDQtMThUMDk6MDA6MDBa"
        "In0seyJjb2RlIjoiQ0RHIiwibGFiZWwiOiJQYXJpcyIsImFycml2ZSI6IjIwMjUtMDQtMThUMTA6MjA6"
        "MDBaIn1dfQ"
    )
    enc = encode_route(golden_stops, base_url="https://x").split("?d=", 1)[1]
    assert enc == golden_encoded
