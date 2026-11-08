#!/usr/bin/env python3
"""One-time migration: reverse historical overrides -> release baseline plus forward patches.

Legacy only. Old card.history described historical values in [from,before).
After migration card gameplay fields hold the earliest recoverable state,
while card.patches records changed values on subsequent dates.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS = (
    "name", "type", "cardClass", "classes", "rarity", "collectible",
    "cost", "attack", "health", "durability", "armor", "text",
    "races", "race", "spellSchool", "mechanics",
)
MIN_DAY = "0001-01-01"


def snapshot(modern: dict, histories: list[dict], day: str) -> dict:
    """Reproduce the prior renderer's inclusive-from/exclusive-before values."""
    result = copy.deepcopy(modern)
    for revision in histories:
        if (revision.get("from", MIN_DAY) <= day
                and day < revision.get("before", "9999-12-31")):
            for field, value in revision["changes"].items():
                if field not in modern and field != "legacyArt":
                    raise ValueError("History contains unknown modern field: " + field)
                result[field] = copy.deepcopy(value)
    return result


def migrate(card: dict, modern: dict) -> tuple[dict, int]:
    if "patches" in card:
        if "history" in card:
            raise ValueError("Mixed chronological and reverse history for " + card["id"])
        return card, 0
    history = card.get("history", []) or []
    if not isinstance(history, list):
        raise ValueError(f"{card['id']}: invalid reverse history")
    latest = {key: copy.deepcopy(modern[key]) for key in SPECS if key in modern}
    if any("legacyArt" in rev.get("changes", {}) for rev in history):
        latest["legacyArt"] = False
    first_day = modern.get("releasedAt")
    if first_day is not None and not isinstance(first_day, str):
        raise ValueError(f"{card['id']}: invalid release date")
    origin = first_day or MIN_DAY
    base = snapshot(latest, history, origin)
    points = sorted({day for revision in history
                     for day in (revision.get("from"), revision.get("before"))
                     if day and day > origin})
    last = base
    patches = []
    for day in points:
        state = snapshot(latest, history, day)
        delta = {key: copy.deepcopy(value) for key, value in state.items()
                 if last.get(key) != value}
        if delta:
            patches.append({"date": day, "changes": delta})
        last = state
    if last != latest:
        raise ValueError(f"{card['id']}: latest state differs after migration")
    for key in SPECS + ("legacyArt",):
        if key in base:
            card[key] = base[key]
        else:
            card.pop(key, None)
    card.pop("history", None)
    card["patches"] = patches
    card["releasedAt"] = first_day
    card["releaseStatus"] = modern.get("releaseStatus", "pending")
    return card, len(patches)


def main():
    catalog = json.loads((ROOT / "cards.json").read_text(encoding="utf-8"))
    if catalog.get("schema") != 1 or catalog.get("set") != "legacy":
        raise ValueError("This script only migrates the legacy card API")
    converted = skipped = missing = dated = 0
    for modern in catalog["cards"]:
        cid = modern["id"]
        path = ROOT / "data" / (cid + ".json")
        if not path.is_file():
            missing += 1
            continue
        source = path.read_text(encoding="utf-8")
        document = json.loads(source)
        card = document.get("card")
        if not isinstance(card, dict) or card.get("id") != cid:
            raise ValueError(f"{cid}: mismatched original ID")
        if card.get("dbfId") != modern.get("dbfId"):
            if (card.get("dbfId") is None and
                    document.get("apiAvailability", "").startswith("standalone historical source;")):
                # Native historical token has no proven modern DBF mapping;
                # do not assign one or alter the archived source.
                skipped += 1
                continue
            raise ValueError(f"{cid}: mismatched original dbfId")
        if "patches" in card:
            skipped += 1
            continue
        _, num = migrate(card, modern)
        document["schemaVersion"] = 2
        output = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        if source != output:
            path.write_text(output, encoding="utf-8", newline="\n")
        converted += 1
        dated += num
    print(json.dumps({"set": "legacy", "converted": converted,
                      "unchanged": skipped, "missing": missing,
                      "datedChanges": dated}, ensure_ascii=False))


if __name__ == "__main__":
    main()
