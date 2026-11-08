#!/usr/bin/env python3
"""Merge verified Legacy balance changes, preserving unrelated history.

The canonical per-card source is data/<CardID>.json. This importer refuses
conflicting entries and verifies the reconstructed latest specs against the
approved current cards.json. It is safe to rerun.
"""
from __future__ import annotations
import copy
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tools" / "verified-legacy-balances.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def put(path: Path, obj):
    content = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8", newline="\n")
        return True
    return False


def main():
    rules = load(MANIFEST)
    catalog = load(ROOT / "cards.json")
    if (rules.get("set") != "legacy" or catalog.get("set") != "legacy"
            or rules.get("timezone") != "Asia/Seoul"):
        raise ValueError("Legacy-only verification script")
    modern_cards = {card["id"]: card for card in catalog["cards"]}
    fields = ("cost", "attack", "health", "armor", "durability")
    changed = already = new_events = 0
    errors = []
    for cid, rule in rules["cards"].items():
        if cid not in modern_cards:
            raise ValueError(f"Unknown Legacy ID: {cid}")
        path = ROOT / "data" / (cid + ".json")
        source = load(path)
        card = source["card"]
        modern = modern_cards[cid]
        if (card.get("id") != cid or card.get("dbfId") != modern.get("dbfId")
                or "history" in card or not isinstance(card.get("patches"), list)):
            raise ValueError(f"{cid}: not a canonical forward-history card")
        correction = rules.get("releaseCorrections", {}).get(cid)
        if correction:
            day = correction["date"]
            # These old taxonomy events existed only because this 2019 card
            # was previously misidentified as an August 2013 release.
            old_events = []
            for item in card["patches"]:
                if item["date"] < day:
                    if (item["changes"].keys() <= set(correction["obsoletePreReleaseFields"])):
                        continue
                    raise ValueError(f"{cid}: unmatched pre-release patch {item}")
                old_events.append(item)
            card["patches"] = old_events
            for field in correction.get("baselineFromCurrent", []):
                card[field] = copy.deepcopy(modern[field])
            card["releasedAt"] = day
            card["releaseStatus"] = correction.get("status", "estimated")
        events = {event["date"]: copy.deepcopy(event) for event in card["patches"]}
        for field, original in rule.get("baseline", {}).items():
            if field not in fields:
                raise ValueError(f"{cid}: not a numeric stat field: {field}")
            if card[field] != original:
                card[field] = original
        for rule_event in rule["patches"]:
            day, diff = rule_event["date"], rule_event["changes"]
            date.fromisoformat(day)
            if card.get("releasedAt") and card["releasedAt"] >= day:
                raise ValueError(f"{cid}: patch on/before release date")
            if day not in rules["sources"]:
                raise ValueError(f"{cid}: missing source for date {day}")
            existing = events.get(day)
            if existing is None:
                existing = {"date": day, "changes": {}}
                events[day] = existing
                new_events += 1
            for field, value in diff.items():
                if field not in fields:
                    raise ValueError(f"{cid}: unsupported changed field {field}")
                if field in existing["changes"]:
                    if existing["changes"][field] != value:
                        raise ValueError(
                            f"{cid} {day}: source conflict in {field}, "
                            f"stored={existing['changes'][field]}, imported={value}")
                    already += 1
                else:
                    existing["changes"][field] = value
        card["patches"] = sorted(events.values(), key=lambda event: event["date"])
        # This validation includes the prior repo patches, not just new entries.
        current = {field: card[field] for field in fields if field in card}
        last = card.get("releasedAt")
        for event in card["patches"]:
            if last and event["date"] <= last:
                raise ValueError(f"{cid}: invalid chronological order")
            for field in fields:
                if field in event["changes"]:
                    if current[field] == event["changes"][field]:
                        raise ValueError(f"{cid}: redundant {field} on {event['date']}")
                    current[field] = event["changes"][field]
            last = event["date"]
        for field in current:
            if current[field] != modern[field]:
                errors.append((cid, field, current[field], modern[field]))
        if put(path, source):
            changed += 1
    if errors:
        raise ValueError(f"Latest stat reconciliation failed: {errors[:20]}")
    print(json.dumps({
        "set": "legacy", "reviewed": len(rules["cards"]),
        "filesUpdated": changed, "alreadyPresent": already, "newPatchDates": new_events,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
