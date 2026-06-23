"""Shared query-filter helpers with clear, user-facing error messages."""
from datetime import datetime, timezone


def year_bounds(year: int) -> tuple[int, int]:
    """Return (start_ts, end_ts) Unix-second bounds for a calendar year (UTC)."""
    if not (1 <= year <= 9999):
        raise ValueError("year must be a 4-digit calendar year between 1 and 9999")
    start = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp())
    if year == 9999:
        end = int(datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp()) + 1
    else:
        end = int(datetime(year + 1, 1, 1, tzinfo=timezone.utc).timestamp())
    return start, end


def iso_date_to_ts(value: str, field: str) -> int:
    """Parse an ISO date (YYYY-MM-DD) to a UTC Unix timestamp, with a clear error."""
    try:
        return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        raise ValueError(f"{field} must be an ISO date like 2025-01-31") from None
