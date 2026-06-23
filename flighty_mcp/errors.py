"""Actionable error types surfaced to MCP clients."""


class FlightyAccessError(RuntimeError):
    """The Flighty database is missing or cannot be read (often Full Disk Access)."""


class FlightyOwnerError(RuntimeError):
    """The owner user could not be determined; set FLIGHTY_USER_ID."""
