import sqlite3


def test_fixture_builds_and_has_owner_flights(fixture_db):
    con = sqlite3.connect(fixture_db)
    n = con.execute(
        "SELECT COUNT(*) FROM UserFlight WHERE userId='owner-1' AND isMyFlight=1"
    ).fetchone()[0]
    con.close()
    assert n == 5  # f1,f2,f3,f6,f7 (f3 archived, f7 deleted-flight filtered later)
