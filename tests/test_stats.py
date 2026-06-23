from flighty_mcp.stats import flight_stats


def test_stats_counts_owner_active_flights(fixture_db):
    s = flight_stats()
    assert s["flights"] == 3  # UA194, BA930, UA200
    assert s["unique_airlines"] == 2  # UA, BA
    assert s["year"] == "all_time"


def test_stats_sums_distance_ignoring_nulls(fixture_db):
    s = flight_stats()
    assert s["distance_km"] == 8616.0 + 8616.0  # UA200 distance is NULL


def test_stats_top_routes_present(fixture_db):
    routes = {r["route"] for r in flight_stats()["top_routes"]}
    assert "SFO -> LHR" in routes


def test_stats_year_filter(fixture_db):
    s = flight_stats(year=2024)
    assert s["flights"] == 1 and s["year"] == 2024
