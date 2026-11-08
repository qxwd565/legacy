#!/usr/bin/env python3
"""One-time idempotent import of legacy HSdeck history into individual API cards.
The catalog remains backwards compatible. Every render index is derived
from the per-card JSON files, never vice versa.
"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULE_URL = "https://raw.githubusercontent.com/qxwd565/legacy/main/history-rules.json"
RENDER_FIELDS = (
    "id", "dbfId", "name", "type", "cardClass", "rarity", "collectible",
    "cost", "text", "attack", "health", "durability", "armor", "art",
    "races", "race", "spellSchool", "set", "nativeTags", "mechanics",
    "watermark", "classes", "history",
)

def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def store_if_changed(path: Path, data):
    new = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == new:
        return False
    path.write_text(new, encoding="utf-8")
    return True

def key(name):
    return re.sub(r"\s+", " ", str(name or "").strip())

def convert_rules(revisions):
    result = []
    for entry in revisions:
        changes = {}
        for source, dest in (("mana", "cost"), ("name", "name"), ("legacy_art", "legacyArt")):
            if source in entry:
                changes[dest] = entry[source]
        if not changes:
            continue
        item = {}
        for field in ("from", "before"):
            if entry.get(field):
                item[field] = entry[field]
        item["changes"] = changes
        result.append(item)
    return result

def clean_ios_versions(card):
    versions = card.get("versions")
    if not isinstance(versions, list):
        return 0
    retained = []
    for item in versions:
        if not isinstance(item, dict):
            retained.append(item)
            continue
        platform = str((item.get("source") or {}).get("platform") or "").casefold()
        variant = str(item.get("id") or "").casefold()
        if platform == "ios" or variant.startswith("ios-"):
            continue
        retained.append(item)
    removed = len(versions) - len(retained)
    if removed:
        if retained:
            card["versions"] = retained
        else:
            card.pop("versions", None)
    return removed

def main():
    with urllib.request.urlopen(RULE_URL, timeout=25) as response:
        rules = json.load(response)
    rules = {key(name): convert_rules(revisions) for name, revisions in rules.items()}

    catalog_path = ROOT / "cards.json"
    catalog = load(catalog_path)
    assert catalog.get("schema") == 1 and isinstance(catalog.get("cards"), list)
    data_dir = ROOT / "data"
    cards_by_id = {c["id"]: c for c in catalog["cards"] if isinstance(c, dict) and isinstance(c.get("id"), str)}
    history_by_id = {}
    updated_files = 0
    rule_matches = set()
    removed_ios = 0
    art_flags = 0

    for path in sorted(data_dir.glob("*.json")):
        data = load(path)
        if not isinstance(data, dict):
            continue
        card = data.get("card")
        if not isinstance(card, dict) or card.get("id") != path.stem:
            continue
        removed_ios += clean_ios_versions(card)
        normalized_name = key(card.get("name"))
        revisions = rules.get(normalized_name, [])
        if revisions:
            rule_matches.add(normalized_name)
            current = card.get("history")
            current = list(current) if isinstance(current, list) else []
            for entry in revisions:
                if entry not in current:
                    current.append(entry)
                if entry["changes"].get("legacyArt") is True:
                    art_flags += 1
            card["history"] = current
        if isinstance(card.get("history"), list) and card["history"]:
            history_by_id[path.stem] = card["history"]
        if store_if_changed(path, data):
            updated_files += 1

    for item in catalog["cards"]:
        cid = item.get("id")
        if cid in history_by_id:
            item["history"] = history_by_id[cid]
    catalog_changed = store_if_changed(catalog_path, catalog)
    slim = {
        "schema": catalog["schema"],
        "set": catalog["set"],
        "cards": [
            {key: card[key] for key in RENDER_FIELDS if key in card}
            for card in catalog["cards"]
        ],
    }
    render_changed = store_if_changed(ROOT / "render.json", slim)
    print(json.dumps({
        "repository": ROOT.name,
        "cards": len(catalog["cards"]),
        "updatedIndividualFiles": updated_files,
        "removedIosSnapshots": removed_ios,
        "matchedHistoricalNames": len(rule_matches),
        "artHistoryFlags": art_flags,
        "catalogChanged": catalog_changed,
        "renderIndexChanged": render_changed,
        "matchedNames": sorted(rule_matches),
    }, ensure_ascii=False))
    if not (ROOT / "render.json").exists():
        raise RuntimeError("Missing render index")

if __name__ == "__main__":
    main()
