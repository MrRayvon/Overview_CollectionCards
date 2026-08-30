"""Sealed product prijs-extractie.

Voor retail: pakt de "hoofdprijs" van een productpagina (eerste plausibele
EUR-prijs > €5 die niet in een nav of footer staat).
Voor secondhand (Marktplaats): pakt de minimum prijs op de zoekresultatenpagina.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, asdict
from typing import Optional

from bs4 import BeautifulSoup
import requests

from . import stock as stock_mod
from .scrapers.webshop import BROWSER_HEADERS, _try_cloudscraper

PRICE_RE = re.compile(r"€\s?(\d{1,4})(?:[.,](\d{2}))?")
log = logging.getLogger(__name__)


@dataclass
class ProductSnap:
    name: str
    type: str          # "retail" | "secondhand"
    shop: str
    url: str
    ok: bool
    status: int
    price_eur: Optional[float]
    secondary_prices: list   # alle gevonden prijzen op de pagina (sorted)
    stock_status: str = "unknown"    # in_stock / preorder / backorder / out_of_stock / unknown
    stock_source: str = "none"       # jsonld / microdata / meta / text / none
    stock_signal: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _all_prices(html: str) -> list[float]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "footer", "nav"]):
        tag.decompose()
    text = soup.get_text(" ")
    out: list[float] = []
    for m in PRICE_RE.finditer(text):
        whole = m.group(1)
        cents = m.group(2) or "00"
        try:
            v = float(f"{whole}.{cents}")
        except ValueError:
            continue
        out.append(v)
    return out


def _structured_price(html: str) -> Optional[float]:
    """Probeer schema.org / og:price meta-tags voor een betrouwbare prijs."""
    soup = BeautifulSoup(html, "html.parser")
    selectors = [
        ("meta", {"property": "product:price:amount"}),
        ("meta", {"property": "og:price:amount"}),
        ("meta", {"itemprop": "price"}),
    ]
    for tag, attrs in selectors:
        el = soup.find(tag, attrs=attrs)
        if el and el.get("content"):
            try:
                return float(str(el["content"]).replace(",", "."))
            except ValueError:
                pass
    el = soup.find(attrs={"itemprop": "price"})
    if el:
        v = el.get("content") or el.get_text()
        try:
            return float(str(v).replace(",", "."))
        except (ValueError, TypeError):
            pass
    return None


def _fetch(url: str, timeout: int = 25) -> tuple[int, str, Optional[str]]:
    try:
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code == 403:
            cs = _try_cloudscraper(url, timeout)
            if cs is not None and cs.ok:
                return cs.status_code, cs.text, None
        return r.status_code, r.text, (None if r.ok else f"HTTP {r.status_code}")
    except Exception as exc:
        return 0, "", str(exc)[:160]


def snap_retail(name: str, shop: str, url: str) -> ProductSnap:
    status, html, err = _fetch(url)
    if not html:
        return ProductSnap(name, "retail", shop, url, False, status, None, [], error=err)
    structured = _structured_price(html)
    all_p = sorted(set(_all_prices(html)))
    if structured is not None:
        primary = structured
    else:
        plausible = [p for p in all_p if 5.0 <= p <= 2000.0]
        primary = plausible[0] if plausible else (all_p[0] if all_p else None)
    st = stock_mod.detect(html)
    return ProductSnap(name, "retail", shop, url, status == 200, status,
                       primary, all_p,
                       stock_status=st["status"], stock_source=st["source"],
                       stock_signal=st["signal"], error=err)


def snap_secondhand(name: str, shop: str, url: str) -> ProductSnap:
    status, html, err = _fetch(url)
    if not html:
        return ProductSnap(name, "secondhand", shop, url, False, status, None, [], error=err)
    all_p = sorted(set(_all_prices(html)))
    plausible = [p for p in all_p if 10.0 <= p <= 5000.0]  # filter losse kaartprijsjes
    primary = plausible[0] if plausible else None  # laagste = scalper-bodem
    # Voor Marktplaats-zoekpagina's is er altijd 'aanbod' als er hits zijn;
    # geef 'in_stock' terug als er plausibele prijzen zijn, anders 'out_of_stock'.
    st_status = "in_stock" if plausible else "out_of_stock"
    return ProductSnap(name, "secondhand", shop, url, status == 200, status,
                       primary, plausible,
                       stock_status=st_status, stock_source="text",
                       stock_signal=f"{len(plausible)} aanbiedingen",
                       error=err)


def snap(spec: dict) -> ProductSnap:
    if spec.get("type") == "secondhand":
        return snap_secondhand(spec["name"], spec.get("shop", ""), spec["url"])
    return snap_retail(spec["name"], spec.get("shop", ""), spec["url"])
