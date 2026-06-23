"""Resolve "trip to X" from the owner's flights and emit flight-animator route URLs."""
from collections import Counter

from flighty_mcp.flights import Leg


def resolve_airports(legs: list[Leg], query: str, side: str) -> set[str]:
    """Airport ids on `side` ("dep"/"arr") matching `query`: IATA code -> city -> country."""
    q = query.strip()
    if not q:
        return set()
    qup = q.upper()

    def get(leg: Leg, suffix: str):
        return getattr(leg, f"{side}_{suffix}")

    if len(q) == 3 and q.isalpha():
        ids = {get(l, "id") for l in legs if (get(l, "code") or "").upper() == qup}
        if ids:
            return ids
    ids = {get(l, "id") for l in legs if (get(l, "city") or "").upper() == qup}
    if ids:
        return ids
    ids = {get(l, "id") for l in legs if qup in (get(l, "city") or "").upper()}
    if ids:
        return ids
    return {
        get(l, "id")
        for l in legs
        if (get(l, "country") or "").upper() == qup
        or (get(l, "country_name") or "").upper() == qup
        or qup in (get(l, "country_name") or "").upper()
    }


def infer_home(legs: list[Leg]) -> tuple[str | None, str | None, float]:
    """Home = most common departure airport; confidence = its share of departures."""
    if not legs:
        return None, None, 0.0
    counts = Counter(l.dep_id for l in legs)
    home_id, c = counts.most_common(1)[0]
    code = next((l.dep_code for l in legs if l.dep_id == home_id), None)
    return home_id, code, c / sum(counts.values())
