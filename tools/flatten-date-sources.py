#!/usr/bin/env python3
"""Flatten audited card history into the browser's dates-v1 card documents.

The pre-migration repository branch must be archived *before* this runs:
audit/source-before-dates-v1. No speculative launch dates or modern values
are copied into historical snapshots; only stable identity/art is inherited.
"""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import json
import pathlib
import re
import sys

DAY = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
ID = re.compile(r"^[A-Za-z0-9_]{1,96}$")
AUDIT = {
    "schemaVersion", "_meta", "_current", "source", "sources",
    "sourceCommit", "sourceBaseline", "dateMeaning", "mode", "history",
    "observations", "initialSpec", "initialSpecStatus", "patches",
    "artworkProvenance", "nativeTagEvidence", "tagSnapshotEvidence",
    "nativeTagOrigins", "nativeTagOriginsCurrent", "tagHistoryStatus",
    "nativeTagUpdates", "nativeTagChanges", "nativeTagDelta",
    "nativeTagsOwned", "nativeTagsReferenced", "nativeTagSnapshots",
    "ownedTags", "referencedTags", "eventTypes", "historicalTextObservations",
    "provenance", "tagHistory", "nativeTagOrigins",
    "currentOnlyFields", "knownEvents", "tagReferences",
    "historyIncompleteFields", "historyIncompleteReasons",
    "historyKnownFields", "historyCompatibilityLimits",
    "unresolvedSourceFields", "nativeTagsTimelineStatus",
    "confidence", "note", "evidence", "notes", "reason", "status",
    "tagSnapshot", "tagSnapshotEvidence", "referenceTags",
    "nativeReferences", "nativeTagOrigins",
}
DANGEROUS = {"__proto__", "constructor", "prototype"}
PROTECTED_FIELDS = {"name", "type", "id", "dbfId"}
TAG_CLEAN = {"id", "name", "value"}

def valid_day(key):
    if not isinstance(key, str) or not DAY.fullmatch(key):
        return False
    try:
        dt.date.fromisoformat(key)
        return True
    except ValueError:
        return False

def read(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)

def render(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"

def clean_values(data):
    if not isinstance(data, dict):
        raise ValueError("Card history state or delta must be an object")
    result = {}
    for key,value in data.items():
        if key in DANGEROUS:
            raise ValueError("Unsafe key " + key)
        if key in AUDIT or key.startswith("_"):
            continue
        result[key] = copy.deepcopy(value)
        if key == "text" and isinstance(value, str):
            result[key] = value.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br></br>")
    removed = data.get("__remove", [])
    if removed:
        if not isinstance(removed, list):
            raise ValueError("__remove is not a list")
        for key in removed:
            if not isinstance(key, str) or key in DANGEROUS or key in PROTECTED_FIELDS:
                raise ValueError("Unsafe field removal")
            if key in result and result[key] is not None:
                raise ValueError("Conflicting explicit field removal")
            result[key] = None
    return result

def tag_map(tags):
    result = {}
    if tags is None:
        return result
    if not isinstance(tags, list):
        raise ValueError("Expected an array of native tags")
    for tag in tags:
        if not isinstance(tag, dict) or not isinstance(tag.get("id"), int):
            raise ValueError("Invalid native tag")
        result[tag["id"]] = copy.deepcopy(tag)
    return result

def update_tags(previous, entry):
    if "nativeTags" in entry:
        return copy.deepcopy(entry["nativeTags"])
    tag_events = entry.get("nativeTagUpdates", [])
    other = entry.get("nativeTagChanges", {})
    if not tag_events and not other:
        return None
    tags = tag_map(previous)
    if tag_events:
        if not isinstance(tag_events, list):
            raise ValueError("nativeTagUpdates must be an array")
        for item in tag_events:
            if not isinstance(item, dict) or not isinstance(item.get("id"), int):
                raise ValueError("Invalid dated native tag update")
            tid = item["id"]
            if item.get("removed") is True or item.get("value") is None:
                tags.pop(tid, None)
            else:
                tags[tid] = {"id": tid, "value":copy.deepcopy(item["value"])}
    if other:
        if not isinstance(other, dict):
            raise ValueError("nativeTagChanges must be a map")
        for key, entry_value in other.items():
            if not str(key).isdigit() or not isinstance(entry_value, dict):
                raise ValueError("Invalid native tag transition")
            tid = int(key)
            after = entry_value.get("after", {})
            if not isinstance(after, dict):
                raise ValueError("Invalid after tag state")
            if after.get("present") is False:
                tags.pop(tid, None)
            elif after.get("present") is True:
                tags[tid] = {"id":tid, "value":copy.deepcopy(after.get("value"))}
    return list(tags.values())

def flatten_doc(doc, row):
    if not isinstance(doc, dict):
        raise ValueError("Invalid source document")
    days = sorted([key for key in doc if valid_day(key)])
    if not days:
        raise ValueError("No verified date-keyed card state")
    first, previous, output = True, {}, {}
    for day in days:
        value = doc[day]
        if not isinstance(value, dict):
            raise ValueError(day + ": date entry must be an object")
        if isinstance(value.get("state"), dict):
            state = clean_values(value["state"])
            # A wrapped full state is an authenticated snapshot; subsequent
            # complete states are diffed against the previously resolved state.
            if "nativeTags" not in state and isinstance(value.get("ownedTags"), list):
                state["nativeTags"] = copy.deepcopy(value["ownedTags"])
            if "referencedTags" not in state and isinstance(value.get("referencedTags"), list):
                state["referencedTags"] = copy.deepcopy(value["referencedTags"])
            delta = {key:copy.deepcopy(v) for key,v in state.items() if key not in previous or previous[key]!=v}
            if not first:
                for key in set(previous) - set(state):
                    if key not in PROTECTED_FIELDS:
                        delta[key] = None
        elif isinstance(value.get("changes"), dict):
            delta = clean_values(value["changes"])
            # Preserve occasional actual direct gameplay fields alongside
            # changes, but never import audit notes into the card timeline.
            rest = {k:v for k,v in value.items() if k not in {"changes"}}
            for key,v in clean_values(rest).items():
                if key in {"name","text","type","cost","attack","health","durability","armor","race","races",
                            "rarity","collectible","mechanics","spellSchool","cardClass","runes",
                            "classes","watermark","art","relatedIds","parentId","nativeTags","nativeRawText",
                            "nativeTextBuilder","referenceTags","nativeSetId","heroPowerDbfId"}:
                    delta[key] = v
        else:
            delta = clean_values(value)
        # Dated owned-tag mutations affect frame selection at a known patch.
        before_tags = previous.get("nativeTags", [])
        tags = update_tags(before_tags, value)
        if tags is not None and "nativeTags" not in delta and tags != before_tags:
            delta["nativeTags"] = tags
        if first:
            if not isinstance(delta.get("name"),str) or not isinstance(delta.get("type"),str):
                raise ValueError(day+": first date does not include name and type")
            if delta.get("id") not in (None,row["id"]):
                raise ValueError(day+": incorrect card ID")
            if delta.get("dbfId") not in (None,row["dbfId"]):
                raise ValueError(day+": incorrect DBF ID")
            delta["id"] = row["id"]
            delta["dbfId"] = row["dbfId"]
            # Art/base set is a visual source link, not an extrapolated stat.
            for key in ["set","art"]:
                if key not in delta and isinstance(row.get(key),str):
                    delta[key] = row[key]
            first = False
        else:
            if not delta:
                continue   # Provenance-only event, not a card stat change.
            for key in PROTECTED_FIELDS:
                if delta.get(key) is None and key in delta:
                    raise ValueError(day+": deleted required card field "+key)
        for key,value in delta.items():
            if value is None:
                previous.pop(key,None)
            elif key in {"cost","mana"}:
                previous["cost"]=copy.deepcopy(value)
                previous["mana"]=copy.deepcopy(value)
            else:
                previous[key]=copy.deepcopy(value)
        if not isinstance(previous.get("name"),str) or not isinstance(previous.get("type"),str):
            raise ValueError(day+": snapshot cannot render")
        output[day]=delta
    return output

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--root",type=pathlib.Path,default=pathlib.Path("."))
    ap.add_argument("--check",action="store_true")
    ap.add_argument("--strict",action="store_true")
    args=ap.parse_args()
    root=args.root.resolve()
    index=read(root/"cards.json")
    rows=index.get("cards", [])
    if not isinstance(rows,list) or not rows:
        raise ValueError("Expected cards.json cards array")
    changes, skipped = {},[]
    seen=set()
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get("id"),str) or not ID.fullmatch(row["id"]) or not isinstance(row.get("dbfId"),int):
            raise ValueError("Invalid catalogue identity")
        cid=row["id"]
        if cid in seen:
            raise ValueError("Duplicate "+cid)
        seen.add(cid)
        path=root/"data"/(cid+".json")
        if not path.is_file():
            raise ValueError("Missing source "+str(path))
        doc=read(path)
        try:
            output=flatten_doc(doc,row)
        except ValueError as exc:
            if args.strict:
                raise ValueError(f"{cid}: {exc}") from exc
            skipped.append({"id":cid,"reason":str(exc)})
            continue
        content=render(output)
        if path.read_text(encoding="utf-8")!=content:
            changes[path]=content
    print(json.dumps({"set":index.get("set"),"catalog":len(rows),"convertible":len(changes),
                      "skipped":len(skipped),"reasons":skipped[:12]},ensure_ascii=False),flush=True)
    if args.check:
        if changes or (skipped and args.strict):
            raise ValueError("Unconverted card documents remain")
        return
    for path,data in changes.items():
        path.write_text(data,encoding="utf-8",newline="\n")

if __name__=="__main__":
    try:
        main()
    except (OSError,ValueError,TypeError,json.JSONDecodeError) as exc:
        print("HSdeck flatten dates-v1 error:",exc,file=sys.stderr)
        sys.exit(1)
