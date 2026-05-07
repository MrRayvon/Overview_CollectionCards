"""Universele snapshot-scraper voor webshop pagina's.

In plaats van per-shop CSS selectors (breken bij elke site update) maken we
een fingerprint van de pagina: genormaliseerde tekst-hash, set van prijzen,
en lengte. Wijzigt iets, dan weet je dat je moet kijken.
"""
from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, asdict
from typing import Optional

import requests
from bs4 import BeautifulSoup

PRICE_RE = re.compile(r"€\s?(\d{1,4}(?:[.,]\d{2})?)")
WS_RE = re.compile(r"\s+")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 CardTracker/1.0"
)


@dataclass
class Snapshot:
    url: str
    ok: bool
    status: int
    title: str
    content_hash: str
    char_count: int
    price_count: int
    prices: list
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _normalize(html: str) -> tuple[str, str, list[str]]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe"]):
        tag.decompose()
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    text = soup.get_text(" ")
    text = WS_RE.sub(" ", text).strip()
    prices = sorted({p.replace(",", ".") for p in PRICE_RE.findall(text)})
    return title, text, prices


def snapshot(url: str, timeout: int = 25, retries: int = 2) -> Snapshot:
    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8"},
                timeout=timeout,
            )
            title, text, prices = _normalize(r.text)
            return Snapshot(
                url=url,
                ok=r.ok,
                status=r.status_code,
                title=title,
                content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
                char_count=len(text),
                price_count=len(prices),
                prices=prices,
            )
        except Exception as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(2 ** attempt)
    return Snapshot(
        url=url,
        ok=False,
        status=0,
        title="",
        content_hash="",
        char_count=0,
        price_count=0,
        prices=[],
        error=str(last_err) if last_err else "unknown",
    )
