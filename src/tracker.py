"""Hoofd-orchestrator.

Drie data-lagen:
  1. Webshop snapshot diffs (welke pagina veranderde?)
  2. Pokemon TCG losse kaarten via Cardmarket - top stijgers/dalers
  3. Sealed product prijzen (retail + Marktplaats secondhand)

Alles persistent in data/, rapport in docs/index.html.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import movers, products
from .report import render
from .scrapers import onepiece_api, pokemon_api, pokemon_prices, webshop

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "sources.yaml"
WATCHLIST = ROOT / "config" / "watchlist.yaml"
DATA_DIR = ROOT / "data"
HISTORY = DATA_DIR / "history.jsonl"
STATE = DATA_DIR / "state.json"
SETS_STATE = DATA_DIR / "sets.json"
SINGLES_STATE = DATA_DIR / "singles_state.json"
SINGLES_HIST = DATA_DIR / "singles_history.jsonl"
PRODUCTS_STATE = DATA_DIR / "products_state.json"
PRODUCTS_HIST = DATA_DIR / "products_history.jsonl"
DOCS = ROOT / "docs"
REPORT = DOCS / "index.html"

log = logging.getLogger("tracker")


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _append_jsonl(path: Path, entries) -> None:
    if not entries:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def _diff_pages(old: dict | None, new: dict) -> list[str]:
    if old is None:
        return ["nieuwe pagina toegevoegd"]
    changes = []
    if not new["ok"]:
        changes.append(f"fout bij ophalen ({new.get('error') or new.get('status')})")
        return changes
    if old.get("content_hash") != new.get("content_hash"):
        changes.append("inhoud gewijzigd")
    op, np = set(old.get("prices") or []), set(new.get("prices") or [])
    added = sorted(np - op)
    removed = sorted(op - np)
    if added:
        changes.append("nieuwe prijzen: €" + ", €".join(added[:8]) + (" ..." if len(added) > 8 else ""))
    if removed:
        changes.append("weggevallen prijzen: €" + ", €".join(removed[:8]) + (" ..." if len(removed) > 8 else ""))
    if old.get("price_count") != new.get("price_count"):
        changes.append(f"aantal items: {old.get('price_count')} -> {new.get('price_count')}")
    if not changes:
        changes.append("geen wijziging")
    return changes


def run_pages(cfg, now: str):
    state = _load_json(STATE, {})
    shop_results, quick_links, history_entries, new_state = [], [], [], {}
    for shop in cfg.get("shops", []):
        if not shop.get("monitor", True):
            quick_links.append({
                "shop": shop["name"], "region": shop.get("region"),
                "notes": shop.get("notes"), "games": shop.get("games", []),
                "urls": shop.get("urls", []),
            })
            continue
        for url in shop.get("urls", []):
            log.info("ophalen: %s", url)
            snap = webshop.snapshot(url)
            entry = {
                "ts": now, "shop": shop["name"], "region": shop.get("region"),
                "games": shop.get("games", []), **snap.to_dict(),
            }
            entry["changes"] = _diff_pages(state.get(url), entry)
            shop_results.append(entry)
            history_entries.append(entry)
            new_state[url] = entry
            time.sleep(1)
    _save_json(STATE, new_state)
    _append_jsonl(HISTORY, history_entries)
    return shop_results, quick_links


def run_set_releases(now: str):
    pkm_sets, op_sets, errors = [], [], []
    try:
        pkm_sets = pokemon_api.latest_sets()
    except Exception as exc:
        errors.append({"name": "Pokemon TCG API", "error": str(exc)})
    try:
        op_sets = onepiece_api.latest_sets()
    except Exception as exc:
        errors.append({"name": "One Piece TCG API", "error": str(exc)})

    sets_state_old = _load_json(SETS_STATE, {})
    new_pkm = {s["id"] for s in pkm_sets} - set(sets_state_old.get("pokemon_ids", []))
    new_op = {s["id"] for s in op_sets if s.get("id")} - set(sets_state_old.get("onepiece_ids", []))
    _save_json(SETS_STATE, {
        "checked_at": now,
        "pokemon_ids": sorted({s["id"] for s in pkm_sets}),
        "onepiece_ids": sorted({s["id"] for s in op_sets if s.get("id")}),
    })
    return pkm_sets, op_sets, sorted(new_pkm), sorted(new_op), errors


def run_singles_prices(watchlist: dict, now: str):
    pkm_cfg = watchlist.get("pokemon_sets") or {}
    cards = pokemon_prices.gather(pkm_cfg)
    if not cards:
        return [], [], []
    old_state = _load_json(SINGLES_STATE, {})
    diffed = movers.diff_singles(old_state, cards)
    gainers, losers = movers.top_movers(diffed, n=20, min_price=2.0)
    new_state = {c["id"]: {"price_eur": c["price_eur"], "ts": now} for c in cards}
    _save_json(SINGLES_STATE, new_state)
    _append_jsonl(SINGLES_HIST, [
        {"ts": now, "id": c["id"], "name": c["name"], "set_id": c["set_id"],
         "rarity": c.get("rarity"), "price_eur": c["price_eur"]}
        for c in cards
    ])
    return diffed, gainers, losers


def run_products(watchlist: dict, now: str):
    specs = watchlist.get("sealed_products") or []
    if not specs:
        return []
    old = _load_json(PRODUCTS_STATE, {})
    snaps = []
    for spec in specs:
        log.info("product: %s", spec["url"])
        snaps.append(products.snap(spec).to_dict())
        time.sleep(1)
    diffed = movers.diff_products(old, snaps)
    new_state = {
        s["url"]: {"price_eur": s["price_eur"], "ts": now}
        for s in snaps if s.get("price_eur") is not None
    }
    # Behoud ook URLs die deze run gefaald zijn maar wel een vorige prijs hadden
    for url, prev in old.items():
        if url not in new_state and prev:
            new_state[url] = prev
    _save_json(PRODUCTS_STATE, new_state)
    _append_jsonl(PRODUCTS_HIST, [
        {"ts": now, "url": s["url"], "name": s["name"], "type": s["type"],
         "shop": s.get("shop"), "price_eur": s.get("price_eur")}
        for s in snaps
    ])
    return diffed


def run() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    watchlist = yaml.safe_load(WATCHLIST.read_text(encoding="utf-8")) if WATCHLIST.exists() else {}
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    shop_results, quick_links = run_pages(cfg, now)
    pkm_sets, op_sets, new_pkm_ids, new_op_ids, api_errors = run_set_releases(now)

    singles, gainers, losers = [], [], []
    try:
        singles, gainers, losers = run_singles_prices(watchlist, now)
    except Exception as exc:
        log.warning("singles prices faalden: %s", exc)
        api_errors.append({"name": "Pokemon prices", "error": str(exc)})

    product_diffs = []
    try:
        product_diffs = run_products(watchlist, now)
    except Exception as exc:
        log.warning("products faalden: %s", exc)
        api_errors.append({"name": "Sealed products", "error": str(exc)})

    render(
        out=REPORT, generated_at=now,
        shop_results=shop_results, quick_links=quick_links,
        pkm_sets=pkm_sets, op_sets=op_sets,
        new_pkm_ids=new_pkm_ids, new_op_ids=new_op_ids,
        api_errors=api_errors,
        singles_total=len(singles), gainers=gainers, losers=losers,
        product_diffs=product_diffs,
    )
    log.info("rapport: %s", REPORT)
    return 0


if __name__ == "__main__":
    sys.exit(run())
