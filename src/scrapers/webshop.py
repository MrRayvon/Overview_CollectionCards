"""Universele snapshot-scraper voor webshop pagina's.

Strategie: complete browser-achtige headers, optioneel cloudscraper-fallback
bij 403. Voor pagina's die we niet kunnen ophalen vanuit GitHub Actions IPs
(zware Cloudflare bot management bij Bol/MediaMarkt) gebruiken we in plaats
daarvan de "quick link" mode (zie tracker + config: monitor: false).
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

# Volledige set Chrome-achtige headers. Helpt bij eenvoudige bot-checks.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Ch-Ua": '"Chromium";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}


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


def _try_cloudscraper(url: str, timeout: int):
    """Optionele Cloudflare-bypass; alleen geprobeerd bij 403."""
    try:
        import cloudscraper  # type: ignore
    except ImportError:
        return None
    try:
        scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
        return scraper.get(url, timeout=timeout)
    except Exception:
        return None


def _shorten(err: str, n: int = 160) -> str:
    err = err.replace("\n", " ").strip()
    return err if len(err) <= n else err[: n - 1] + "..."


def snapshot(url: str, timeout: int = 25, retries: int = 1) -> Snapshot:
    last_err: Optional[Exception] = None
    last_status: int = 0
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout, allow_redirects=True)
            last_status = r.status_code
            if r.status_code == 403:
                cs = _try_cloudscraper(url, timeout)
                if cs is not None and cs.ok:
                    r = cs
                    last_status = r.status_code
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
                error=None if r.ok else f"HTTP {r.status_code}",
            )
        except Exception as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(2 ** attempt)
    return Snapshot(
        url=url,
        ok=False,
        status=last_status,
        title="",
        content_hash="",
        char_count=0,
        price_count=0,
        prices=[],
        error=_shorten(str(last_err)) if last_err else "unknown",
    )
