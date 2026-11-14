#!/usr/bin/env python3
"""Convert proven per-card legacy wrappers to the HSdeck dates-v1 transport.

Only existing, valid Korean first-playable dates are accepted. Never invent
launch dates, and never replace an evidence-backed dates-v1 document.
Designed to be pinned to an immutable commit by expansion build workflows.
"""
from __future__ import annotations
import argparse
import copy
import datetime
import json
import pathlib
import re
import sys

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CARD_RE = re.compile(r"^[A-Za-z0-9_]{1,96}$")
REMOVE_KEYS = {"releasedAt", "releaseStatus", "patches", "history",
               "initialSpec", "initialSpecStatus", "historicalNotes"}
UNSAFE = {"__proto__", "constructor", "prototype"}

def date_ok(value):
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        return False
    try:
        datetime.date.fromisoformat(value)
        return True
    except ValueError:
        return False

def read(path):
    with path.open(encoding="utf-8") as file:
        return json.load(file)

def dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"

def date_from_entry(entry):
    if isinstance(entry, str):
        return entry if date_ok(entry) else None
    if not isinstance(entry, dict):
        return None
    day = entry.get("date")
    if not date_ok(day):
        return None
    # Don't promote pending/estimated/unknown provenance to a first date.
    if entry.get("status", "verified") not in {"verified", "confirmed"}:
        return None
    return day

def source_date(card, doc, policy, override):
    # Explicit per-card source chronology wins over generic set dates.
    primary = [doc["card"].get("releasedAt"), card.get("releasedAt")]
    known = [v for v in primary if date_ok(v)]
    if len(set(known)) > 1:
        raise ValueError("Conflicting recorded first playable dates: " + str(known))
    if known:
        return known[0]
    cid = card["id"]
    prefix = cid.split("_", 1)[0]
    for table in (override, policy):
        if not isinstance(table, dict):
            continue
        cards = table.get("cards", {})
        if isinstance(cards, dict):
            candidate = date_from_entry(cards.get(cid))
            if candidate:
                return candidate
        prefixes = table.get("prefixes", {})
        if isinstance(prefixes, dict):
            candidate = date_from_entry(prefixes.get(prefix))
            if candidate:
                return candidate
        if table is policy:
            candidate = date_from_entry(table.get("default"))
            if candidate:
                return candidate
    return None

def display_text(value):
    # Only user-facing card descriptions receive the standard HTML line break.
    if isinstance(value, str):
        return value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br></br>")
    return value

def text_fields(value):
    if not isinstance(value, dict):
        raise ValueError("Card state must be a JSON object")
    clean = {}
    for key, item in value.items():
        if not isinstance(key, str) or key in UNSAFE:
            raise ValueError("Unsafe card state key")
        clean[key] = display_text(item) if key == "text" else copy.deepcopy(item)
    return clean

def clean_changes(event):
    if not isinstance(event, dict):
        raise ValueError("Invalid patch object")
    changes = event.get("changes")
    if changes is None:
        changes = {k: v for k, v in event.items()
                   if k not in {"date", "source", "confidence", "note",
                                "reason", "status", "sources", "patch"}}
    if not isinstance(changes, dict):
        raise ValueError("Patch changes must be a dict")
    changes = text_fields(changes)
    removed = changes.pop("__remove", [])
    if removed:
        if not isinstance(removed, list) or not all(isinstance(x, str) for x in removed):
            raise ValueError("Invalid patch field removals")
        for key in removed:
            if key in UNSAFE:
                raise ValueError("Unsafe field removal")
            if key in changes and changes[key] is not None:
                raise ValueError("Removal conflicts with patch replacement")
            changes[key] = None
    return changes

def migrate(doc, index_card, policy, override):
    cid = index_card["id"]
    if not isinstance(doc, dict) or not isinstance(doc.get("card"), dict):
        raise ValueError("Unsupported undated source shape")
    source = doc["card"]
    if source.get("id") != cid or source.get("dbfId") != index_card.get("dbfId"):
        raise ValueError("CardID/DBF ID mismatch between source and cards.json")
    first = source_date(index_card, doc, policy, override)
    if not first:
        return None
    if any(date_ok(k) for k in doc):
        raise ValueError("Mixed wrapper and dated keys must be audited separately")

    # Do not discard card drawing properties or references, including native tags.
    initial = doc.get("initialSpec") if isinstance(doc.get("initialSpec"), dict) else source.get("initialSpec")
    if isinstance(initial, dict) and isinstance(initial.get("name"), str) and isinstance(initial.get("type"), str):
        base = text_fields(initial)
        for key in ("id", "dbfId", "art", "set", "watermark", "portrait",
                    "nativeTags", "nativeRawText", "nativeTextBuilder", "relatedIds"):
            if key not in base and key in source:
                base[key] = copy.deepcopy(source[key])
    else:
        base = text_fields({k:v for k,v in source.items() if k not in REMOVE_KEYS})
    for key in ("englishName", "root", "relatedIds"):
        if key in doc and key not in base:
            base[key] = copy.deepcopy(doc[key])
    if not isinstance(base.get("name"), str) or not isinstance(base.get("type"), str):
        raise ValueError("Initial state lacks name/type")
    if base.get("id") != cid or base.get("dbfId") != source.get("dbfId"):
        raise ValueError("Initial state card ID invalid")
    if not isinstance(base.get("set"), str) and isinstance(index_card.get("set"), str):
        base["set"] = index_card["set"]
    if not base.get("art") and index_card.get("art"):
        base["art"] = index_card["art"]

    patches = []
    for group in (source.get("patches", []), doc.get("patches", [])):
        if group is None:
            continue
        if not isinstance(group, list):
            raise ValueError("Patches must be list")
        patches.extend(group)
    state = {first: base}
    for event in patches:
        day = event.get("date") if isinstance(event, dict) else None
        if not date_ok(day):
            raise ValueError("Undated patch event must be resolved before migration")
        if day < first:
            raise ValueError("Patch precedes first playable date")
        changes = clean_changes(event)
        if not changes:
            continue
        current = state.setdefault(day, {})
        for key, value in changes.items():
            if key in current and current[key] != value and day != first:
                raise ValueError(f"Conflicting patch field {key} on {day}")
            current[key] = value

    timeline = {k: state[k] for k in sorted(state)}
    if not timeline[first].get("name") or not timeline[first].get("type"):
        raise ValueError("First date cannot render")
    return timeline

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path("."))
    parser.add_argument("--strict", action="store_true",
                        help="Fail rather than allow cards without established dates")
    parser.add_argument("--check", action="store_true",
                        help="Validate without writing any outputs")
    args = parser.parse_args()
    root = args.root.resolve()
    index_path = root / "cards.json"
    index = read(index_path)
    if not isinstance(index, dict) or not isinstance(index.get("cards"), list) or not isinstance(index.get("set"), str):
        raise ValueError("cards.json must contain set and cards")
    cards = index["cards"]
    policy = read(root / "release-policy.json") if (root / "release-policy.json").exists() else {}
    override = read(root / "tools" / "dated-migration-dates.json") if (root / "tools" / "dated-migration-dates.json").exists() else {}
    original_ids, changes, skipped, existing = set(), {}, [], 0
    for card in cards:
        if not isinstance(card, dict) or not CARD_RE.fullmatch(str(card.get("id", ""))) or not isinstance(card.get("dbfId"), int):
            raise ValueError("Invalid card index entry")
        cid = card["id"]
        if cid in original_ids:
            raise ValueError("Duplicate CardID in catalog")
        original_ids.add(cid)
        path = root / "data" / (cid + ".json")
        if not path.is_file():
            raise ValueError(f"Missing card file for {cid}")
        doc = read(path)
        if not isinstance(doc, dict):
            raise ValueError(f"Invalid card JSON for {cid}")
        dates = [k for k in doc if date_ok(k)]
        if dates:
            if "card" in doc:
                raise ValueError(f"{cid}: mixed date and obsolete card wrapper")
            first = doc[sorted(dates)[0]]
            # Protected v2 historical sources require a separate lossless migration.
            if not isinstance(first, dict) or not isinstance(first.get("name"), str) or not isinstance(first.get("type"), str):
                skipped.append((cid, "dated-v2 structural migration required"))
            else:
                existing += 1
            continue
        if "card" not in doc:
            skipped.append((cid, "no supported dated wrapper"))
            continue
        try:
            dated = migrate(doc, card, policy, override)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{cid}: {exc}") from exc
        if dated is None:
            skipped.append((cid, "first playable Korean date unresolved"))
            continue
        content = dump(dated)
        if path.read_text(encoding="utf-8") != content:
            changes[path] = content
    if len(original_ids) != len(cards):
        raise ValueError("Card inventory count changed")
    stats = {"set": index["set"], "cardCount": len(cards),
             "alreadyDated": existing, "convertible": len(changes),
             "unresolvedCount": len(skipped), "unresolved": skipped[:30]}
    print(json.dumps(stats, ensure_ascii=False), flush=True)
    if args.strict and skipped:
        raise ValueError(f"Cannot claim all cards date-keyed: {len(skipped)} unresolved; {skipped[:10]}")
    if args.check:
        if changes:
            raise ValueError(f"{len(changes)} source cards need conversion")
        return
    for path, content in changes.items():
        path.write_text(content, encoding="utf-8", newline="\n")

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"HSdeck date migration rejected: {exc}", file=sys.stderr)
        sys.exit(1)
