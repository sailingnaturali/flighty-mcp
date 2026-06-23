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
