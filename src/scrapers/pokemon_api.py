"""Pokemon TCG API: officiele set-data, gratis, geen key nodig voor lichte queries."""
from __future__ import annotations

import requests

API = "https://api.pokemontcg.io/v2"


def latest_sets(limit: int = 12) -> list[dict]:
    r = requests.get(
        f"{API}/sets",
        params={"orderBy": "-releaseDate", "pageSize": limit},
        timeout=20,
    )
    r.raise_for_status()
    payload = r.json().get("data", [])
    out = []
    for s in payload:
        out.append({
            "id": s.get("id"),
            "name": s.get("name"),
            "series": s.get("series"),
            "releaseDate": s.get("releaseDate"),
            "total": s.get("total"),
            "ptcgoCode": s.get("ptcgoCode"),
            "logo": (s.get("images") or {}).get("logo"),
        })
    return out
