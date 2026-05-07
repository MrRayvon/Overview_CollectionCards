"""One Piece TCG set-data.

Probeert in volgorde meerdere openbare endpoints. Faalt zacht.
"""
from __future__ import annotations

import requests

CANDIDATES = [
    # OPTCG API (community)
    ("https://www.optcgapi.com/api/Sets/", "optcg_v1"),
    ("https://optcgapi.com/api/Sets/", "optcg_v1"),
    # apitcg.com
    ("https://apitcg.com/api/one-piece/sets", "apitcg"),
    ("https://www.apitcg.com/api/one-piece/sets", "apitcg"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 CardTracker/1.0",
    "Accept": "application/json",
}


def _normalize(payload, kind: str) -> list[dict]:
    if kind == "optcg_v1":
        # optcgapi.com geeft een lijst van sets terug
        items = payload if isinstance(payload, list) else payload.get("data", [])
        out = []
        for s in items:
            if not isinstance(s, dict):
                continue
            out.append({
                "id": s.get("set_id") or s.get("id") or s.get("code"),
                "name": s.get("set_name") or s.get("name"),
                "releaseDate": s.get("release_date") or s.get("releaseDate"),
                "total": s.get("total_cards") or s.get("total"),
            })
        return out
    if kind == "apitcg":
        items = payload.get("data") if isinstance(payload, dict) else payload
        out = []
        for s in (items or []):
            if not isinstance(s, dict):
                continue
            out.append({
                "id": s.get("id") or s.get("code"),
                "name": s.get("name") or s.get("title"),
                "releaseDate": s.get("releaseDate") or s.get("release_date"),
                "total": s.get("total") or s.get("cardCount"),
            })
        return out
    return []


def latest_sets(limit: int = 12) -> list[dict]:
    last_err: Exception | None = None
    for url, kind in CANDIDATES:
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code in (404, 403):
                continue
            r.raise_for_status()
            data = r.json()
            sets = _normalize(data, kind)
            if not sets:
                continue
            # Sorteer op releaseDate desc indien beschikbaar
            def _key(s):
                return s.get("releaseDate") or ""
            sets.sort(key=_key, reverse=True)
            return [s for s in sets if s.get("id")][:limit]
        except Exception as exc:
            last_err = exc
            continue
    if last_err:
        raise last_err
    return []
