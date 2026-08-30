"""Voorraad-detectie uit HTML.

Signaal-bronnen in volgorde van betrouwbaarheid:
  1. JSON-LD product schema met availability
  2. schema.org microdata itemprop=availability
  3. og:availability / product:availability meta tag
  4. NL/EN tekstuele signalen ('op voorraad', 'uitverkocht', ...)
"""
from __future__ import annotations

import json
import re
from typing import Optional

from bs4 import BeautifulSoup

# Volgorde: 'in_stock' wint als er zowel positief als negatief signaal is
# op een productpagina, want winkels laten "uitverkocht" gerelateerde
# producten vaak in de rechterkolom zien.
STATUSES = ("in_stock", "preorder", "backorder", "out_of_stock", "unknown")

SCHEMA_MAP = {
    "instock": "in_stock",
    "in_stock": "in_stock",
    "onlineonly": "in_stock",
    "limitedavailability": "in_stock",
    "preorder": "preorder",
    "presale": "preorder",
    "backorder": "backorder",
    "outofstock": "out_of_stock",
    "out_of_stock": "out_of_stock",
    "soldout": "out_of_stock",
    "discontinued": "out_of_stock",
}

# Nederlandse en Engelse textuele patronen. Woordgrenzen om false positives
# te voorkomen (bijv. "leverbaar in 3 dagen" hoort bij op voorraad).
POSITIVE_TEXT = [
    r"\bop\s*voorraad\b",
    r"\bin\s*voorraad\b",
    r"\bdirect\s*leverbaar\b",
    r"\bvandaag\s*verzonden\b",
    r"\bin\s*winkelmand(je)?\b",
    r"\btoevoegen\s*aan\s*winkelmand(je)?\b",
    r"\bbestellen\b",
    r"\bkoop\s*nu\b",
    r"\bnu\s*kopen\b",
    r"\bin\s*stock\b",
    r"\badd\s*to\s*cart\b",
]

NEGATIVE_TEXT = [
    r"\buitverkocht\b",
    r"\bniet\s*(meer\s*)?leverbaar\b",
    r"\bniet\s*(op\s*)?voorraad\b",
    r"\btijdelijk\s*niet\s*beschikbaar\b",
    r"\bniet\s*beschikbaar\b",
    r"\bout\s*of\s*stock\b",
    r"\bsold\s*out\b",
    r"\bmeld\s*je\s*aan\b.{0,40}\bvoorraad\b",  # "meld me als weer op voorraad"
    r"\bbericht\s*bij\s*binnenkomst\b",
]

PREORDER_TEXT = [
    r"\bpre[-\s]?order\b",
    r"\bvoor(uit)?bestell(en|ing)\b",
    r"\bverwacht\b",
]

BACKORDER_TEXT = [
    r"\bnalevering\b",
    r"\bop\s*bestelling\b",
]

_re_pos = [re.compile(p, re.IGNORECASE) for p in POSITIVE_TEXT]
_re_neg = [re.compile(p, re.IGNORECASE) for p in NEGATIVE_TEXT]
_re_pre = [re.compile(p, re.IGNORECASE) for p in PREORDER_TEXT]
_re_bo = [re.compile(p, re.IGNORECASE) for p in BACKORDER_TEXT]


def _normalize_schema(value: str) -> Optional[str]:
    if not value:
        return None
    v = value.lower().rsplit("/", 1)[-1].strip()
    return SCHEMA_MAP.get(v)


def _from_jsonld(soup: BeautifulSoup) -> Optional[str]:
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = (tag.string or tag.text or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        # data kan lijst zijn, of dict, of dict met @graph
        candidates = []
        if isinstance(data, list):
            candidates.extend(data)
        elif isinstance(data, dict):
            candidates.append(data)
            if isinstance(data.get("@graph"), list):
                candidates.extend(data["@graph"])
        for c in candidates:
            if not isinstance(c, dict):
                continue
            t = c.get("@type")
            types = t if isinstance(t, list) else [t] if t else []
            if not any(str(x).lower() in ("product", "offer", "aggregateoffer") for x in types):
                offers = c.get("offers")
            else:
                offers = c.get("offers") or c
            offer_list = []
            if isinstance(offers, list):
                offer_list = offers
            elif isinstance(offers, dict):
                offer_list = [offers]
            for o in offer_list:
                if not isinstance(o, dict):
                    continue
                a = o.get("availability")
                s = _normalize_schema(a) if isinstance(a, str) else None
                if s:
                    return s
    return None


def _from_microdata(soup: BeautifulSoup) -> Optional[str]:
    for el in soup.find_all(attrs={"itemprop": "availability"}):
        val = el.get("href") or el.get("content") or el.get_text()
        s = _normalize_schema(str(val))
        if s:
            return s
    return None


def _from_meta(soup: BeautifulSoup) -> Optional[str]:
    for prop in ("product:availability", "og:availability", "availability"):
        el = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
        if el and el.get("content"):
            s = _normalize_schema(el["content"])
            if s:
                return s
    return None


def _from_text(text: str) -> tuple[Optional[str], Optional[str]]:
    """Retourneer (status, matching_pattern) uit vrije tekst."""
    for r in _re_pre:
        m = r.search(text)
        if m:
            return "preorder", m.group(0)
    for r in _re_bo:
        m = r.search(text)
        if m:
            return "backorder", m.group(0)
    neg_match = None
    for r in _re_neg:
        m = r.search(text)
        if m:
            neg_match = m.group(0)
            break
    pos_match = None
    for r in _re_pos:
        m = r.search(text)
        if m:
            pos_match = m.group(0)
            break
    if pos_match and not neg_match:
        return "in_stock", pos_match
    if neg_match and not pos_match:
        return "out_of_stock", neg_match
    if pos_match and neg_match:
        # Beide aanwezig: op productpagina is negatief meestal het echte signaal
        # (de "toevoegen aan winkelmand" knop kan bestaan maar disabled zijn).
        # We bevoordelen 'out_of_stock' als de negatieve match dichter bij de
        # productnaam / titel staat, maar dat vereist te veel context - kies
        # veilig: markeer als 'unknown' zodat we niet verkeerd rapporteren.
        return "unknown", f"{pos_match} + {neg_match}"
    return None, None


def detect(html: str) -> dict:
    """Detecteer voorraadstatus. Retourneert:
        {"status": "in_stock" | ... | "unknown",
         "source": "jsonld" | "microdata" | "meta" | "text" | "none",
         "signal": "<matched string or schema value>"}
    """
    if not html:
        return {"status": "unknown", "source": "none", "signal": None}
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["style", "svg", "iframe"]):
        tag.decompose()

    s = _from_jsonld(soup)
    if s:
        return {"status": s, "source": "jsonld", "signal": s}
    s = _from_microdata(soup)
    if s:
        return {"status": s, "source": "microdata", "signal": s}
    s = _from_meta(soup)
    if s:
        return {"status": s, "source": "meta", "signal": s}

    # Alleen zichtbare tekst
    for tag in soup(["script", "noscript", "footer", "nav", "header"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    status, sig = _from_text(text)
    if status:
        return {"status": status, "source": "text", "signal": sig}
    return {"status": "unknown", "source": "none", "signal": None}
