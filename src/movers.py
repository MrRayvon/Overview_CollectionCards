"""Bereken prijs-veranderingen tussen vorige en huidige snapshot."""
from __future__ import annotations


def _pct(old: float | None, new: float | None) -> float | None:
    if old is None or new is None or old <= 0:
        return None
    return (new - old) / old * 100.0


def diff_singles(old: dict[str, dict], new: list[dict]) -> list[dict]:
    """Combineer per kaart-id de oude en nieuwe prijs en %verschil.

    `old` is dict van id -> vorige snapshot record.
    `new` is lijst van huidige snapshot records.
    """
    out = []
    for c in new:
        prev = old.get(c["id"])
        prev_price = (prev or {}).get("price_eur")
        pct = _pct(prev_price, c["price_eur"])
        out.append({
            **c,
            "prev_price_eur": prev_price,
            "pct_change": pct,
            "abs_change": (c["price_eur"] - prev_price) if prev_price is not None else None,
        })
    return out


def top_movers(items: list[dict], n: int = 20, *, min_price: float = 1.0,
               require_prev: bool = True) -> tuple[list[dict], list[dict]]:
    """Geef (top_gainers, top_losers) gesorteerd op pct_change."""
    eligible = [
        x for x in items
        if x.get("price_eur") is not None
        and x["price_eur"] >= min_price
        and x.get("pct_change") is not None
        and (not require_prev or x.get("prev_price_eur") is not None)
    ]
    gainers = sorted(eligible, key=lambda x: x["pct_change"], reverse=True)[:n]
    losers = sorted(eligible, key=lambda x: x["pct_change"])[:n]
    return gainers, losers


def diff_products(old: dict[str, dict], new: list[dict]) -> list[dict]:
    """Per product-URL: combineer oude met nieuwe prijs."""
    out = []
    for p in new:
        prev = old.get(p["url"])
        prev_price = (prev or {}).get("price_eur")
        pct = _pct(prev_price, p.get("price_eur"))
        out.append({
            **p,
            "prev_price_eur": prev_price,
            "pct_change": pct,
        })
    return out
