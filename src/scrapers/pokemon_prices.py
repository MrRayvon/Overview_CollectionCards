"""Pokemon TCG API: losse-kaart prijzen via Cardmarket.

Gratis, zonder key. Per set ~1 request van paginated /v2/cards.
Retourneert per kaart de laatste Cardmarket prijzen (EUR).
"""
from __future__ import annotations

import logging
import time

import requests

API = "https://api.pokemontcg.io/v2"
log = logging.getLogger(__name__)


def _get(path: str, params: dict | None = None) -> dict:
    r = requests.get(f"{API}/{path}", params=params or {}, timeout=30)
    r.raise_for_status()
    return r.json()


def latest_set_ids(n: int) -> list[str]:
    data = _get("sets", {"orderBy": "-releaseDate", "pageSize": n})
    return [s["id"] for s in data.get("data", [])]


def cards_with_prices(set_id: str, page_size: int = 250) -> list[dict]:
    """Geef alle kaarten in een set terug met Cardmarket-prijzen genormaliseerd."""
    out: list[dict] = []
    page = 1
    while True:
        data = _get("cards", {
            "q": f"set.id:{set_id}",
            "page": page,
            "pageSize": page_size,
        })
        items = data.get("data", [])
        if not items:
            break
        for c in items:
            cm = (c.get("cardmarket") or {})
            prices = cm.get("prices") or {}
            trend = prices.get("trendPrice")
            avg30 = prices.get("avg30")
            avg7 = prices.get("avg7")
            low = prices.get("lowPrice")
            avg_sell = prices.get("averageSellPrice")
            # Beste single-getal voor "huidige" marktprijs
            current = trend or avg_sell or avg7 or avg30 or low
            if current is None:
                continue
            out.append({
                "id": c["id"],
                "name": c.get("name"),
                "number": c.get("number"),
                "rarity": c.get("rarity"),
                "set_id": set_id,
                "set_name": (c.get("set") or {}).get("name"),
                "cm_url": cm.get("url"),
                "image": (c.get("images") or {}).get("small"),
                "price_eur": float(current),
                "trend": trend,
                "avg7": avg7,
                "avg30": avg30,
                "low": low,
                "avg_sell": avg_sell,
                "updated": cm.get("updatedAt"),
            })
        if len(items) < page_size:
            break
        page += 1
        time.sleep(0.5)  # vriendelijk
    return out


def gather(watchlist: dict) -> list[dict]:
    """Combineer expliciete IDs en latest_n uit de watchlist."""
    ids: set[str] = set(watchlist.get("ids") or [])
    n = int(watchlist.get("latest_n") or 0)
    if n > 0:
        try:
            for sid in latest_set_ids(n):
                ids.add(sid)
        except Exception as exc:
            log.warning("kon latest_set_ids niet ophalen: %s", exc)
    all_cards: list[dict] = []
    for sid in sorted(ids):
        try:
            cards = cards_with_prices(sid)
            log.info("set %s: %d kaarten met prijs", sid, len(cards))
            all_cards.extend(cards)
        except Exception as exc:
            log.warning("set %s prijzen falen: %s", sid, exc)
    return all_cards
