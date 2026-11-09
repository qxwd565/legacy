#!/usr/bin/env python3
"""Conservatively integrate archived numeric Legacy changes into chronological JSON.

Uses per-build numeric before/after differences recorded from HearthSim.
Only explicit KST date mappings may be applied; these are not inferred from
commit timestamps. Preserves all existing patch fields and refuses conflicts.
If evidence or reconciliation is inconsistent, leaves the field untouched
and records it in a separate review report. Safe to rerun.
"""
from __future__ import annotations
import copy
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Superseded mutators cannot rewrite the canonical date-map format.
if __name__ == "__main__" and (ROOT / "metadata").is_dir():
    raise SystemExit("Date-map source detected. Edit data/<ID>.json and its evidence metadata; this legacy wrapper importer is disabled. See docs/date-schema.md.")

CANDIDATES = ROOT / "tools/legacy-balance-candidates.json"
DATES = ROOT / "tools/archived-build-dates.json"
REPORT = ROOT / "tools/legacy-stat-reconstruction-report.json"
FIELDS = {"cost", "attack", "health", "durability", "armor"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def put(path, value):
    output = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if not path.exists() or path.read_text(encoding="utf-8") != output:
        path.write_text(output, encoding="utf-8", newline="\n")
        return True
    return False


def state(baseline, events, field, day):
    result = baseline
    for event in events:
        if event["date"] <= day and field in event["changes"]:
            result = event["changes"][field]
    return result


def previous(day):
    return (date.fromisoformat(day) - timedelta(days=1)).isoformat()


def reconcile_field(original, field, observations, first_baseline, release, expected_latest):
    baseline = copy.deepcopy(original[field])
    events = copy.deepcopy(original["patches"])
    confirmed = 0
    added = 0
    baseline_fixed = 0
    if first_baseline is not None and release == "2013-08-17":
        if any(e["date"] <= release and field in e["changes"] for e in events):
            return None, f"existing patch before release {release}"
        if baseline != first_baseline:
            baseline = first_baseline
            baseline_fixed += 1
    for item in observations:
        day = item["date"]
        old, new = item["before"], item["after"]
        if not release or release >= day:
            return None, f"patch date on/before release: {day}"
        actual_before = state(baseline, events, field, previous(day))
        if actual_before != old:
            anchors = [x for x in events if x["date"] < day and field in x["changes"]]
            if anchors:
                return None, f"prior patch conflict at {day}: expected {old}, stored {actual_before}, last {anchors[-1]['date']}"
            # Earliest observed post-release change: correct the release stat.
            baseline = copy.deepcopy(old)
            baseline_fixed += 1
            actual_before = state(baseline, events, field, previous(day))
            if actual_before != old:
                return None, f"unable to reconcile before-state on {day}"
        at_day = next((ev for ev in events if ev["date"] == day), None)
        if at_day is not None and field in at_day["changes"]:
            if at_day["changes"][field] != new:
                return None, f"explicit patch conflict {day}: {at_day['changes'][field]} vs {new}"
            confirmed += 1
        else:
            if at_day is None:
                at_day = {"date": day, "changes": {}}
                events.append(at_day)
            at_day["changes"][field] = copy.deepcopy(new)
            added += 1
        events.sort(key=lambda e:e["date"])
        if state(baseline, events, field, day) != new:
            return None, f"unable to reconstruct after-state at {day}"
    final = state(baseline, events, field, "9999-12-30")
    if final != expected_latest:
        return None, f"current mismatch: reconstructed {final}, approved {expected_latest}"
    return {"baseline":baseline,"events":events,"confirmed":confirmed,
            "added":added,"baselineFixed":baseline_fixed}, None


def main():
    audit = read(CANDIDATES)
    policy = read(DATES)
    catalog = read(ROOT / "cards.json")
    if audit.get("set") != "legacy" or catalog.get("set") != "legacy" or policy.get("timezone") != "Asia/Seoul":
        raise ValueError("This importer only supports the Legacy API, Korean-local dates")
    approved = {c["id"]: c for c in catalog["cards"]}
    grouped = defaultdict(lambda: defaultdict(list))
    baseline = defaultdict(dict)
    ignored = []
    used = []
    for item in audit["candidates"]:
        cid = item["id"]
        if cid not in approved:
            ignored.append({"id":cid,"build":item["build"],"why":"not in Legacy catalogue"})
            continue
        build = item["build"]
        if build == policy["baselineObservationBuild"]:
            # This is a snapshot immediately before closed beta, not a patch.
            for field, diff in item["statChanges"].items():
                if field in FIELDS:
                    baseline[cid][field] = diff["after"]
            continue
        rule = policy["builds"].get(build)
        if not rule:
            ignored.append({"id":cid,"build":build,"why":"before release or unverified build date"})
            continue
        for field, diff in item["statChanges"].items():
            if field not in FIELDS:
                continue
            grouped[cid][field].append({
                "date":rule["date"],"before":diff["before"],"after":diff["after"],
                "build":build,"source":item["source"]
            })
    review = []
    saved_cards = 0
    imported_fields = 0
    baselines_fixed = 0
    duplicate_fields = 0
    for cid in sorted(set(grouped) | set(baseline)):
        modern = approved[cid]
        path = ROOT / "data" / f"{cid}.json"
        doc = read(path)
        card = doc.get("card", {})
        if card.get("id") != cid or card.get("dbfId") != modern.get("dbfId"):
            review.append({"id":cid,"reason":"canonical ID/dbf mapping mismatch"})
            continue
        if not isinstance(card.get("patches"), list):
            review.append({"id":cid,"reason":"no forward patches"})
            continue
        release = card.get("releasedAt")
        updated = copy.deepcopy(card)
        successes = []
        for field in sorted(set(grouped[cid]) | set(baseline[cid])):
            if field not in card or field not in modern:
                review.append({"id":cid,"field":field,"reason":"field missing in source"})
                continue
            evidence = sorted(grouped[cid][field],key=lambda r:r["date"])
            observed_base = baseline[cid].get(field)
            result, reason = reconcile_field(updated,field,evidence,observed_base,release,modern[field])
            if reason:
                review.append({"id":cid,"field":field,
                               "reason":reason,
                               "evidence":[{"date":e["date"],"old":e["before"],"new":e["after"],"build":e["build"]} for e in evidence]})
                continue
            updated[field] = result["baseline"]
            # Merge only this numeric field back into the canonical timeline.
            by_date = {event["date"]:copy.deepcopy(event) for event in updated["patches"]}
            for event in result["events"]:
                if field in event["changes"]:
                    dest = by_date.setdefault(event["date"], {"date":event["date"],"changes":{}})
                    dest["changes"][field] = event["changes"][field]
            updated["patches"] = sorted(by_date.values(), key=lambda e:e["date"])
            # Proven numeric results only. No flavor/text/mechanics/IDs are altered.
            successes.extend(evidence)
            imported_fields += result["added"]
            baselines_fixed += result["baselineFixed"]
            duplicate_fields += result["confirmed"]
        if updated != card:
            doc["card"] = updated
            if put(path,doc):
                saved_cards += 1
        for e in successes:
            used.append({"id":cid,"field":next((field for field,rows in grouped[cid].items() if e in rows),None),
                         "date":e["date"],"build":e["build"],"source":e["source"]})
    out={"schema":1,"set":"legacy","sourceBuilds":audit.get("buildsRead"),
         "totalSourceCandidates":len(audit.get("candidates",[])),
         "calendarDateSource":"tools/archived-build-dates.json",
         "merged":len(used),"reviewRequired":len(review),
         "unmappedOrPreRelease":len(ignored),
         "appliedCards":saved_cards,"newNumericChanges":imported_fields,
         "originalStatsReconstructed":baselines_fixed,
         "alreadyMatched":duplicate_fields,
         "review":review,"ignored":ignored}
    put(REPORT,out)
    print(json.dumps({
        "sourceBuilds":out["sourceBuilds"],"merged":len(used),"appliedCards":saved_cards,
        "newNumericChanges":imported_fields,"originalStatsReconstructed":baselines_fixed,
        "alreadyMatched":duplicate_fields,
        "reviewRequired":len(review),"excluded":len(ignored)
    },ensure_ascii=False))


if __name__=="__main__":
    main()
