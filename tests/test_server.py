import asyncio


def test_tools_registered():
    from flighty_mcp.server import mcp

    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {"list_my_flights", "get_flight", "flight_stats"} <= names


def test_animate_trip_registered():
    import asyncio

    from flighty_mcp.server import mcp

    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert "animate_trip" in names
