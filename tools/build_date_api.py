"""Compile date maps to stable aggregate transports (schema 1, historySchema 2)."""
from __future__ import annotations
import copy
import json
from collections import Counter
from pathlib import Path
from date_schema import (SPECS, CURRENT_ONLY, load, put, read_card, resolve,
                         project, apply, delta, validate_timeline)
from legacy_projection import compile_legacy, RENDER_FIELDS, loss_report


def compile_history(timeline, meta):
    if timeline:
        items = list(timeline.items())
        baseline_day, baseline = items[0]
        events = [{"date": d, "changes": c} for d,c in items[1:]]
    else:
        baseline_day = None
        baseline = meta["undated"]["baseline"]
        events = meta["undated"]["patches"]
    latest = resolve(timeline,meta)
    state = copy.deepcopy(baseline)
    revisions = []
    for index, event in enumerate(events):
        changes = delta(latest,state)
        if changes:
            rev = {"before": event["date"], "changes": changes}
            # Keep estimated baseline visible before its estimate, matching
            # the compatibility resolver rather than implying verified release.
            if baseline_day and (index > 0 or meta["release"]["status"] == "verified"):
                rev["from"] = baseline_day
            revisions.append(rev)
        state = apply(state,event["changes"])
        baseline_day = event["date"]
    return revisions


def build(root):
    root = Path(root)
    old_catalog = load(root/"cards.json")
    catalog = {k:copy.deepcopy(v) for k,v in old_catalog.items() if k != "cards"}
    catalog["cards"] = []
    renderer = []
    backward = {}
    legacy_catalog = {k:copy.deepcopy(v) for k,v in catalog.items() if k != 'cards'}
    legacy_catalog['cards'] = []
    legacy_renderer = []
    legacy_history = {}
    release_counts = Counter()
    for old in old_catalog["cards"]:
        cid = old["id"]
        timeline,meta = read_card(root,cid)
        validate_timeline(timeline)
        # Current snapshot metadata is not a historically dated card state.
        record = copy.deepcopy(meta["currentCatalog"] or old)
        state = resolve(timeline,meta)
        unmapped = meta["originalSource"].get("apiAvailability","").startswith("standalone historical source;")
        if unmapped:
            # Preserve approved numeric catalogue row, but NEVER attach the
            # standalone native source to its unverified numeric mapping.
            state = project(record)
            revisions = []
            release = {"date":record.get("releasedAt"),"status":record.get("releaseStatus","pending")}
            # Normalize this approved catalogue row on its own evidence only.
            # Do not attach the unmapped native source's baseline/history.
            for key in set(SPECS) | set(meta.get("canonicalFields", [])):
                record.pop(key,None)
            record.update(copy.deepcopy(state))
        else:
            for key in set(SPECS) | set(meta.get("canonicalFields", [])):
                record.pop(key,None)
            record.update(copy.deepcopy(state))
            revisions = compile_history(timeline,meta)
            release = meta["release"]
        record["releasedAt"] = release["date"]
        record["releaseStatus"] = release["status"]
        record.pop("history",None)
        catalog["cards"].append(record)
        render = copy.deepcopy(record)
        # Raw native tags remain explicitly current-only metadata, never used
        # as historical truth. Consumers strip these whenever a day is chosen.
        render["currentOnlyFields"] = [k for k in CURRENT_ONLY if k in render]
        render["history"] = revisions
        render["historySchema"] = 2
        render["baselineStatus"] = meta["baselineStatus"]
        renderer.append(render)
        compiled = copy.deepcopy(state)
        # Existing artwork remains a current link, not a claim about old art.
        if "art" in record:
            compiled["art"] = record["art"]
        backward[str(record["dbfId"])] = {
            "id":cid,"current":compiled,"history":revisions,
            "releasedAt":release["date"],"releaseStatus":release["status"],
            "baselineStatus":meta["baselineStatus"],
            "currentOnlyFields":render["currentOnlyFields"],
        }
        release_counts[release["status"]] += 1
        legacy_card,legacy_revisions = compile_legacy(timeline,meta,record)
        legacy_catalog['cards'].append(legacy_card)
        legacy_render={k:copy.deepcopy(v) for k,v in legacy_card.items() if k in RENDER_FIELDS}
        if legacy_revisions:
            legacy_render['history']=legacy_revisions
            legacy_history[str(legacy_card['dbfId'])]={'id':cid,'history':legacy_revisions}
        legacy_renderer.append(legacy_render)
    changed = []
    values = {"cards-date.json":catalog,
              "render-date.json":{"schema":1,"historySchema":2,"set":"legacy","cards":renderer},
              "history-date.json":{"schema":1,"historySchema":2,"set":"legacy","cards":backward},
              "cards.json":legacy_catalog,
              "render.json":{"schema":1,"set":"legacy","cards":legacy_renderer},
              "history.json":{"schema":1,"set":"legacy","cards":legacy_history}}
    for name,value in values.items():
        if name in ("cards.json","cards-date.json"):
            if put(root/name,value): changed.append(name)
        else:
            text = json.dumps(value,ensure_ascii=False,separators=(",",":"))+"\n"
            path=root/name
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                path.write_text(text,encoding="utf-8",newline="\n")
                changed.append(name)
    print(json.dumps({"cards":len(renderer),"historyRecords":len(backward),
                      "releaseDates":dict(release_counts),"published":changed,
                      "historyBytes":(root/"history.json").stat().st_size,
                      "preciseHistoryBytes":(root/"history-date.json").stat().st_size}))
    put(root/'tools/legacy-compatibility-losses.json',loss_report())
