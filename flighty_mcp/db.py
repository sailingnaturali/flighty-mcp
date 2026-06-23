"""Read-only access to the local Flighty SQLite database."""
import os
import sqlite3
import threading

from flighty_mcp.errors import FlightyAccessError, FlightyOwnerError

_DEFAULT = (
    "~/Library/Containers/com.flightyapp.flighty/Data/Documents/MainFlightyDatabase.db"
)


def default_db_path() -> str:
    return os.path.expanduser(os.environ.get("FLIGHTY_DB_PATH", _DEFAULT))


def _readable_or_raise(path: str, timeout: float = 5.0) -> None:
    """Fail fast if the DB is missing or a read stalls (e.g. missing Full Disk Access).

    macOS TCC can *hang* reads into an app container rather than erroring, so we
    probe in a worker thread and abandon it on timeout instead of blocking.
    """
    if not os.path.exists(path):
        raise FlightyAccessError(
            f"Flighty database not found at {path}. Is the Flighty app installed? "
            "Set FLIGHTY_DB_PATH to override the location."
        )
    result: dict = {}

    def probe() -> None:
        try:
            with open(path, "rb") as fh:
                fh.read(16)
            result["ok"] = True
        except Exception as exc:  # noqa: BLE001
            result["err"] = exc

    t = threading.Thread(target=probe, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise FlightyAccessError(
            f"Reading the Flighty database at {path} timed out. Grant Full Disk Access "
            "to the app launching this server (System Settings -> Privacy & Security -> "
            "Full Disk Access), then restart it."
        )
    if "err" in result:
        raise FlightyAccessError(
            f"Cannot read the Flighty database at {path}: {result['err']}. If this is a "
            "permissions error, grant Full Disk Access to the launching app."
        )


def connect() -> sqlite3.Connection:
    path = default_db_path()
    _readable_or_raise(path)
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=3)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout = 3000")
    return con


def resolve_owner_id(con: sqlite3.Connection) -> str:
    override = os.environ.get("FLIGHTY_USER_ID")
    if override:
        return override
    row = con.execute(
        "SELECT userId FROM UserFlight WHERE deleted IS NULL AND isMyFlight = 1 "
        "GROUP BY userId ORDER BY COUNT(*) DESC LIMIT 1"
    ).fetchone()
    if row and row[0]:
        return row[0]
    row = con.execute(
        "SELECT userId FROM UserFlight WHERE deleted IS NULL "
        "GROUP BY userId ORDER BY COUNT(*) DESC LIMIT 1"
    ).fetchone()
    if row and row[0]:
        return row[0]
    raise FlightyOwnerError(
        "Could not determine the Flighty owner. Set FLIGHTY_USER_ID to your user id."
    )
