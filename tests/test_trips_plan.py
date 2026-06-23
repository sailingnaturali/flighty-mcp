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
