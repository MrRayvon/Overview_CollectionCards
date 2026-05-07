"""One Piece TCG via apitcg.com.

Endpoint vorm (docs: https://docs.apitcg.com/): GET /v1/one-piece/sets
Werkt vandaag zonder key voor lage volumes; defensief geschreven zodat een
404 of layout-verandering geen runfout geeft.
"""
from __future__ import annotations

import requests

API = "https://apitcg.com/api"


def latest_sets(limit: int = 12) -> list[dict]:
    candidates = [
        f"{API}/one-piece/sets",
        f"{API}/v1/one-piece/sets",
    ]
    last_err: Exception | None = None
    for url in candidates:
        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            data = r.json()
            sets = data.get("data") if isinstance(data, dict) else data
            if not sets:
                continue
            out = []
            for s in sets[:limit]:
                if not isinstance(s, dict):
                    continue
                out.append({
                    "id": s.get("id") or s.get("code"),
                    "name": s.get("name") or s.get("title"),
                    "releaseDate": s.get("releaseDate") or s.get("release_date"),
                    "total": s.get("total") or s.get("cardCount"),
                    "logo": s.get("logo") or s.get("image"),
                })
            return out
        except Exception as exc:
            last_err = exc
            continue
    if last_err:
        raise last_err
    return []
