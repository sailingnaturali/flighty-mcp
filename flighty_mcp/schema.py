"""Detect which columns exist so queries survive Flighty schema drift."""
import sqlite3


def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    rows = con.execute("PRAGMA table_info(" + table + ")").fetchall()
    return {r[1] for r in rows}


def has_columns(con: sqlite3.Connection, table: str, *names: str) -> bool:
    present = table_columns(con, table)
    return all(n in present for n in names)
