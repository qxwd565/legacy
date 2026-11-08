#!/usr/bin/env python3
"""Read-only candidate audit of Legacy card stat changes across real HearthSim client builds.

Not a patch applier. The UTC HearthSim commit date is an observation timestamp,
NOT a verified Korean patch activation date. This tool deliberately never
modifies data/*.json, cards.json, or published runtime indexes.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
FIELD_BY_TAG = {"48": "cost", "47": "attack", "45": "health", "187": "durability", "292": "armor"}


def git(folder, *args):
    result = subprocess.run(["git", "-C", str(folder), *args],
                            capture_output=True, check=True)
    return result.stdout


def read_carddefs(xml, target_ids):
    result = {}
    root = ET.fromstring(xml)
    for entity in root.iter("Entity"):
        cid = entity.get("CardID")
        if cid not in target_ids:
            continue
        spec = {}
        for tag in entity.iter("Tag"):
            field = FIELD_BY_TAG.get(tag.get("enumID"))
            val = tag.get("value")
            if field and val is not None:
                try:
                    spec[field] = int(val)
                except ValueError:
                    pass
        result[cid] = spec
    return result


def audit(hsdata: Path, target_ids):
    log = git(hsdata, "log", "--reverse", "--format=%H|%aI|%s", "--", "CardDefs.xml")
    records = []
    for line in log.decode().splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            records.append(parts)
    candidates = []
    coverage = []
    prev = {}
    last_meta = None
    for idx, (commit, timestamp, message) in enumerate(records):
        try:
            xml = git(hsdata, "show", f"{commit}:CardDefs.xml")
        except subprocess.CalledProcessError:
            print(f"SKIP: unreadable CardDefs.xml at {commit}", flush=True)
            continue
        parsed = read_carddefs(xml, target_ids)
        meta = {"commit": commit, "observedAtUtc": timestamp, "build": message.replace("Update to patch ", "")}
        if idx == 0 or idx % 25 == 0:
            print(f"scanned {idx + 1}/{len(records)}: {message} ({len(parsed)} Legacy IDs)", flush=True)
        coverage.append({"build":meta["build"], "observedAtUtc":timestamp, "cards":len(parsed)})
        if last_meta:
            for cid in target_ids:
                old, new = prev.get(cid), parsed.get(cid)
                if not old or not new:
                    continue
                changes = {field: {"before": old[field], "after": new[field]}
                           for field in FIELD_BY_TAG.values()
                           if field in old and field in new and old[field] != new[field]}
                if changes:
                    candidates.append({"id":cid, "build": meta["build"],
                                       "observedAtUtc":timestamp,
                                       "previousBuild":last_meta["build"],
                                       "statChanges":changes,
                                       "dateStatus":"needs-KST-patch-verification",
                                       "source":f"https://github.com/HearthSim/hsdata/commit/{commit}"})
        prev, last_meta = parsed, meta
    candidates.sort(key=lambda c:(c["observedAtUtc"],c["id"]))
    return {"schema":1,"set":"legacy","method":"HearthSim/hsdata CardDefs.xml build-to-build stat diff",
            "notice":"Candidates only. Observed timestamp is not exact Korean patch date; do not auto-publish.",
            "buildsRead":len(coverage),"coverage":coverage,
            "candidates":candidates}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="tools/legacy-balance-candidates.json")
    args = parser.parse_args()
    catalog = json.loads((ROOT / "cards.json").read_text(encoding="utf-8"))
    if catalog.get("set") != "legacy":
        raise ValueError("Legacy-only audit")
    target_ids = {card["id"] for card in catalog["cards"]}
    with tempfile.TemporaryDirectory(prefix="hsdata-stat-audit-") as temp:
        repo = Path(temp) / "hsdata"
        subprocess.run(["git", "clone", "--quiet", "--filter=blob:none", "--no-checkout",
                        "https://github.com/HearthSim/hsdata.git", str(repo)],
                       check=True)
        result = audit(repo, target_ids)
    output = ROOT / args.out
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"builds":result["buildsRead"],
                      "statChanges":len(result["candidates"]),
                      "cards":len({c["id"] for c in result["candidates"]}),
                      "report":str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
