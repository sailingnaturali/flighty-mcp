from flighty_mcp.flights import get_flight, list_my_flights, to_local_iso


def _by_no(legs):
    return {leg["flight_no"]: leg for leg in legs}


def test_lists_only_owner_active_flights(fixture_db):
    legs = list_my_flights()
    nos = {leg["flight_no"] for leg in legs}
    # f1,f2,f6 are owner, not archived, not deleted; f3 archived, f4 friend,
    # f5 family, f7 deleted-flight all excluded.
    assert nos == {"UA194", "BA930", "UA200"}


def test_legs_carry_coordinates_and_country_code(fixture_db):
    leg = _by_no(list_my_flights())["UA194"]
    assert leg["from"]["iata"] == "SFO"
    assert leg["to"]["iata"] == "LHR"
    assert leg["from"]["country"] == "US"
    assert leg["to"]["country"] == "GB"
    assert round(leg["from"]["lat"], 2) == 37.62
    assert round(leg["to"]["lon"], 2) == -0.45


def test_departure_is_airport_local_time(fixture_db):
    leg = _by_no(list_my_flights())["UA194"]
    # 1750023000 in America/Los_Angeles is 2025-06-15 (PDT, -07:00)
    assert leg["departure"].startswith("2025-06-15T")
    assert leg["departure"].endswith("-07:00")
    assert leg["date"] == "2025-06-15"


def test_null_arrival_and_distance_degrade_to_none(fixture_db):
    leg = _by_no(list_my_flights())["UA200"]
    assert leg["arrival"] is None


def test_year_filter(fixture_db):
    nos = {leg["flight_no"] for leg in list_my_flights(year=2024)}
    assert nos == {"BA930"}


def test_after_before_filter(fixture_db):
    nos = {leg["flight_no"] for leg in list_my_flights(after="2025-01-01", before="2025-07-01")}
    assert nos == {"UA194"}


def test_to_local_iso_falls_back_to_utc_z():
    assert to_local_iso(1750023000, None).endswith("Z")


def test_get_flight_matches_case_and_space_insensitive(fixture_db):
    leg = get_flight("ua 194")
    assert leg is not None and leg["flight_no"] == "UA194"


def test_get_flight_unknown_returns_none(fixture_db):
    assert get_flight("ZZ000") is None


def test_get_flight_excludes_friend_flights(fixture_db):
    # UA100 belongs to the friend, not the owner
    assert get_flight("UA100") is None
