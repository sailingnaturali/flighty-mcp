"""FastMCP server exposing read-only Flighty flight data."""
from mcp.server.fastmcp import FastMCP

from flighty_mcp import flights, stats

mcp = FastMCP("flighty")


@mcp.tool()
def list_my_flights(
    year: int | None = None,
    after: str | None = None,
    before: str | None = None,
    upcoming_only: bool = False,
    limit: int = 200,
) -> list[dict]:
    """List your own flights as geo-ready legs (departure/arrival airports with coordinates).

    Args:
        year: Filter to a calendar year (e.g. 2025).
        after: Only flights departing on/after this ISO date (YYYY-MM-DD).
        before: Only flights departing before this ISO date (YYYY-MM-DD).
        upcoming_only: If true, return only flights that haven't departed yet (exclude past/archived). Default false = full history.
        limit: Maximum number of legs to return (default 200, newest first).
    """
    return flights.list_my_flights(year=year, after=after, before=before, upcoming_only=upcoming_only, limit=limit)


@mcp.tool()
def get_flight(flight_no: str) -> dict | None:
    """Get your most recent flight leg matching a flight number (e.g. "UA194").

    Args:
        flight_no: The flight number (case- and space-insensitive).
    """
    return flights.get_flight(flight_no)


@mcp.tool()
def flight_stats(year: int | None = None, upcoming_only: bool = False) -> dict:
    """Aggregate stats over your flights: counts, distance, unique airports/airlines, top routes.

    Args:
        year: Filter stats to a calendar year. Omit for all-time.
        upcoming_only: If true, return only flights that haven't departed yet (exclude past/archived). Default false = full history.
    """
    return stats.flight_stats(year=year, upcoming_only=upcoming_only)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
