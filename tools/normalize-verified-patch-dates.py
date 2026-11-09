#!/usr/bin/env python3
"""Correct independently verified regional patch dates, preserving raw observations."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# 4217 reached Korea on December 12; December 11 KST was the NA deployment.
# Source: https://hearthstone.blizzard.com/ko-kr/news/11868609
CORRECTIONS = {"2013-12-11": "2013-12-12"}


def main():
    changed = []
    for path in sorted((ROOT / "data").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        card = doc.get("card", {})
        patches = card.get("patches")
        if not isinstance(patches, list):
            continue
        if not any(e["date"] in CORRECTIONS for e in patches):
            continue
        merged = {}
        for event in patches:
            day = CORRECTIONS.get(event["date"], event["date"])
            changes = merged.setdefault(day, {})
            for key, value in event["changes"].items():
                if key in changes and changes[key] != value:
                    raise ValueError(f"{path.stem}: conflicting {key} on {day}")
                changes[key] = value
        card["patches"] = [{"date": day, "changes": value}
                           for day, value in sorted(merged.items())]
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changed.append(path.stem)
    print(json.dumps({"correctedCards": len(changed), "cards": changed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
