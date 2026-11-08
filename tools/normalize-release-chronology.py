#!/usr/bin/env python3
"""Normalize true first-release dates in Legacy card JSON.

For originally misdated later additions, replay source patches up through
their true first playable day into that day's baseline; no fictional changes
can appear before the card exists. Preserve all later dated deltas.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {"name","type","cardClass","classes","rarity","collectible",
          "cost","attack","health","durability","armor","text",
          "races","race","spellSchool","mechanics","legacyArt"}


def main():
    policy = json.loads((ROOT / "release-policy.json").read_text(encoding="utf-8"))
    changed = {}
    for cid, rule in policy.get("cards", {}).items():
        day = rule.get("date")
        if not day:
            continue
        path = ROOT / "data" / f"{cid}.json"
        if not path.exists():
            continue
        original = path.read_text(encoding="utf-8")
        doc = json.loads(original)
        card = doc.get("card", {})
        if not isinstance(card, dict) or card.get("id") != cid:
            raise ValueError(f"{cid}: identity mismatch")
        if not isinstance(card.get("patches"), list):
            continue
        original_release = card.get("releasedAt")
        if original_release and day < original_release:
            # This tool handles only moving a mistaken early release later.
            continue
        due, later = [], []
        for event in card["patches"]:
            (due if event["date"] <= day else later).append(event)
        for event in sorted(due,key=lambda x:x["date"]):
            for field,value in event["changes"].items():
                if field not in FIELDS:
                    raise ValueError(f"{cid}: unknown first release field {field}")
                card[field]=value
        card["patches"] = later
        card["releasedAt"] = day
        card["releaseStatus"] = rule.get("status","estimated")
        new = json.dumps(doc,ensure_ascii=False,indent=2)+"\n"
        if original != new:
            path.write_text(new,encoding="utf-8",newline="\n")
            changed[cid]={"date":day,"absorbedPatches":len(due)}
    print(json.dumps({"updatedCards":len(changed),"detail":changed},ensure_ascii=False))


if __name__=="__main__":
    main()
