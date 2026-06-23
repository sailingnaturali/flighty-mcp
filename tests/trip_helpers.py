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
