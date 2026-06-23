from flighty_mcp.db import connect, resolve_owner_id
from flighty_mcp.flights import owner_legs_asc


def test_owner_legs_asc_orders_and_fields(fixture_db):
    con = connect()
    legs = owner_legs_asc(con, resolve_owner_id(con))
    con.close()
    # owner-1 full history (archived included), NULL-departure legs excluded, ascending
    assert [leg.flight_no for leg in legs] == ["BA930", "UA194", "AC1725", "UA200"]
    assert all(legs[i].dep_ts <= legs[i + 1].dep_ts for i in range(len(legs) - 1))
    first = legs[0]
    assert first.dep_code == "LHR" and first.arr_code == "SFO"
    assert first.dep_id and first.arr_id and first.dep_ts is not None
