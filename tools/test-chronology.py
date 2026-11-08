#!/usr/bin/env python3
"""Verify Legacy's release-baseline + forward-patch model and current catalog."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS = (
    "name", "type", "cardClass", "classes", "rarity", "collectible",
    "cost", "attack", "health", "durability", "armor", "text",
    "races", "race", "spellSchool", "mechanics",
)


def main():
    catalog = json.loads((ROOT / "cards.json").read_text(encoding="utf-8"))
    render = json.loads((ROOT / "render.json").read_text(encoding="utf-8"))
    backward = json.loads((ROOT / "history.json").read_text(encoding="utf-8"))["cards"]
    render_by_id = {c["id"]: c for c in render["cards"]}
    if catalog.get("set") != "legacy" or render.get("set") != "legacy":
        raise AssertionError("Wrong card set")
    migrated = 0
    for modern in catalog["cards"]:
        cid = modern["id"]
        path = ROOT / "data" / (cid + ".json")
        if not path.is_file():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        card = document["card"]
        if (card.get("dbfId") is None and
                document.get("apiAvailability", "").startswith("standalone historical source;")):
            continue
        if "history" in card or "patches" not in card:
            raise AssertionError(f"{cid}: not migrated to forward patches")
        if card.get("id") != cid or card.get("dbfId") != modern.get("dbfId"):
            raise AssertionError(f"{cid}: identity mismatch")
        baseline = {field: card[field] for field in SPECS if field in card}
        dates = []
        for ev in card["patches"]:
            d = ev["date"]
            if not isinstance(d, str) or (dates and d <= dates[-1]):
                raise AssertionError(f"{cid}: non-increasing patch dates")
            if card.get("releasedAt") and d <= card["releasedAt"]:
                raise AssertionError(f"{cid}: patch before release")
            if not ev["changes"]:
                raise AssertionError(f"{cid}: empty patch")
            for key, value in ev["changes"].items():
                if key in baseline:
                    if value == baseline[key]:
                        raise AssertionError(f"{cid}: redundant patch on {d} for {key}")
                    baseline[key] = value
                elif key == "legacyArt" and "legacyArt" in card:
                    baseline[key] = value
                else:
                    raise AssertionError(f"{cid}: no baseline for {key}")
            dates.append(d)
        for field in SPECS:
            if field in baseline or field in modern:
                if baseline.get(field) != modern.get(field):
                    raise AssertionError(f"{cid}: differs from current catalog ({field})")
        expected = render_by_id[cid]
        for field in SPECS:
            if field in modern and expected.get(field) != modern[field]:
                raise AssertionError(f"{cid}: renderer mismatch ({field})")
        derived = expected.get("history", [])
        compat = backward.get(str(modern["dbfId"]), {})
        if derived != compat.get("history", []) and (derived or compat):
            raise AssertionError(f"{cid}: backward compatibility mismatch")
        migrated += 1
    def get(cid):
        return json.loads((ROOT / "data" / (cid + ".json")).read_text(encoding="utf-8"))["card"]
    if get("EX1_016")["cost"] != 5:
        raise AssertionError("Sylvanas must debut at 5 mana")
    if not any(x["date"] == "2014-01-17" and x["changes"].get("cost") == 6
               for x in get("EX1_016")["patches"]):
        raise AssertionError("Sylvanas mana change missing")
    if get("EX1_350")["races"] != []:
        raise AssertionError("Velen incorrectly classified as Draenei at debut")
    if not any(x["date"] == "2024-10-30" and x["changes"].get("races") == ["DRAENEI"]
               for x in get("EX1_350")["patches"]):
        raise AssertionError("Velen Draenei introduction missing")
    if get("CS2_029")["spellSchool"] != "":
        raise AssertionError("Fireball incorrectly has a debut spell school")
    if not any(x["date"] == "2021-03-26" and x["changes"].get("spellSchool") == "FIRE"
               for x in get("CS2_029")["patches"]):
        raise AssertionError("Fireball spell school introduction missing")
    print(json.dumps({"set":"legacy","validatedCards":migrated,"result":"pass"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
