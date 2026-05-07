"""Hoofd-orchestrator.

Leest config, draait scrapers, vergelijkt met laatste snapshot per URL,
schrijft history (jsonl) en een laatste-state file (json), en genereert
het HTML rapport.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from .report import render
from .scrapers import onepiece_api, pokemon_api, webshop

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "sources.yaml"
DATA_DIR = ROOT / "data"
HISTORY = DATA_DIR / "history.jsonl"
STATE = DATA_DIR / "state.json"
SETS_STATE = DATA_DIR / "sets.json"
DOCS = ROOT / "docs"
REPORT = DOCS / "index.html"

log = logging.getLogger("tracker")


def _load_state() -> dict:
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_state(state: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _append_history(entries: list[dict]) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def _diff(old: dict | None, new: dict) -> list[str]:
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
        changes.append(f"nieuwe prijzen: €{', €'.join(added[:8])}" + (" ..." if len(added) > 8 else ""))
    if removed:
        changes.append(f"weggevallen prijzen: €{', €'.join(removed[:8])}" + (" ..." if len(removed) > 8 else ""))
    if old.get("price_count") != new.get("price_count"):
        changes.append(
            f"aantal items: {old.get('price_count')} -> {new.get('price_count')}"
        )
    if not changes:
        changes.append("geen wijziging")
    return changes


def run() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    state = _load_state()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    shop_results: list[dict] = []
    quick_links: list[dict] = []
    history_entries: list[dict] = []
    new_state: dict = {}

    for shop in cfg.get("shops", []):
        monitor = shop.get("monitor", True)
        if not monitor:
            quick_links.append({
                "shop": shop["name"],
                "region": shop.get("region"),
                "notes": shop.get("notes"),
                "games": shop.get("games", []),
                "urls": shop.get("urls", []),
            })
            continue
        for url in shop.get("urls", []):
            log.info("ophalen: %s", url)
            snap = webshop.snapshot(url)
            entry = {
                "ts": now,
                "shop": shop["name"],
                "region": shop.get("region"),
                "games": shop.get("games", []),
                **snap.to_dict(),
            }
            old = state.get(url)
            changes = _diff(old, entry)
            entry["changes"] = changes
            shop_results.append(entry)
            history_entries.append(entry)
            new_state[url] = entry
            time.sleep(1)

    # APIs
    pkm_sets: list[dict] = []
    op_sets: list[dict] = []
    api_errors: list[dict] = []
    try:
        pkm_sets = pokemon_api.latest_sets()
    except Exception as exc:
        log.warning("pokemon api faalde: %s", exc)
        api_errors.append({"name": "Pokemon TCG API", "error": str(exc)})
    try:
        op_sets = onepiece_api.latest_sets()
    except Exception as exc:
        log.warning("one piece api faalde: %s", exc)
        api_errors.append({"name": "One Piece TCG API", "error": str(exc)})

    sets_state_old = {}
    if SETS_STATE.exists():
        try:
            sets_state_old = json.loads(SETS_STATE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            sets_state_old = {}
    new_pkm_ids = {s["id"] for s in pkm_sets} - set(sets_state_old.get("pokemon_ids", []))
    new_op_ids = {s["id"] for s in op_sets if s.get("id")} - set(sets_state_old.get("onepiece_ids", []))
    sets_state_new = {
        "checked_at": now,
        "pokemon_ids": sorted({s["id"] for s in pkm_sets}),
        "onepiece_ids": sorted({s["id"] for s in op_sets if s.get("id")}),
    }
    SETS_STATE.parent.mkdir(parents=True, exist_ok=True)
    SETS_STATE.write_text(json.dumps(sets_state_new, indent=2, ensure_ascii=False), encoding="utf-8")

    _save_state(new_state)
    if history_entries:
        _append_history(history_entries)

    render(
        out=REPORT,
        generated_at=now,
        shop_results=shop_results,
        quick_links=quick_links,
        pkm_sets=pkm_sets,
        op_sets=op_sets,
        new_pkm_ids=sorted(new_pkm_ids),
        new_op_ids=sorted(new_op_ids),
        api_errors=api_errors,
    )
    log.info("rapport: %s", REPORT)
    return 0


if __name__ == "__main__":
    sys.exit(run())
