#!/usr/bin/env python3
"""Audit transient Hearthstone card ability changes in all archived client builds.

This is a read-only evidence audit. The fact that an English card text differs
between two client files does *not* prove a balance change or its Korean
server effective date. Changes are never written to card.patches automatically.

Input: HearthSim/hsdata historical CardDefs.xml builds.
Output: tools/legacy-effect-build-review.json
"""
from __future__ import annotations

import html
import json
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"tools"/"legacy-effect-build-review.json"


def git(repo,*args):
    return subprocess.run(["git","-C",str(repo),*args],check=True,
                          capture_output=True).stdout


def normalize(text):
    text=html.unescape(text or "")
    text=re.sub(r"<[^>]*>", "", text)
    text=text.replace("\\n"," ").replace("\n"," ")
    return re.sub(r"\s+"," ",text).strip().lower()


def read_build(xml,wanted):
    data={}
    root=ET.fromstring(xml)
    for ent in root.iter("Entity"):
        cid=ent.attrib.get("CardID")
        if cid not in wanted:
            continue
        val=None
        for tag in ent.findall("Tag"):
            if tag.get("enumID")=="184" or tag.get("name")=="CARDTEXT_INHAND":
                en=tag.find("enUS")
                if en is not None:
                    val="".join(en.itertext())
                break
        if val is not None:
            data[cid]=val
    return data


def main():
    cards=json.loads((ROOT/"cards.json").read_text(encoding="utf-8"))["cards"]
    byid={c["id"]:c for c in cards}
    rules=json.loads((ROOT/"tools"/"archived-build-dates.json").read_text(encoding="utf-8"))["builds"]
    with tempfile.TemporaryDirectory(prefix="legacy-effect-archive-") as tmp:
        repo=Path(tmp)/"hsdata"
        subprocess.run(["git","clone","--quiet","--filter=blob:none",
                        "--no-checkout","https://github.com/HearthSim/hsdata.git",str(repo)],check=True)
        lines=git(repo,"log","--reverse","--format=%H|%aI|%s","--","CardDefs.xml").decode("utf-8").splitlines()
        previous={}
        changes=[]
        coverage=[]
        for index,line in enumerate(lines):
            sha,observed,message=line.split("|",2)
            build=message.removeprefix("Update to patch ").strip()
            xml=git(repo,"show",f"{sha}:CardDefs.xml")
            current=read_build(xml,byid)
            if index%25==0:
                print(f"scanned {index+1}/{len(lines)}: {build}; matches={len(current)}",flush=True)
            date_rule=rules.get(build)
            mapped_date=date_rule["date"] if date_rule else None
            if previous:
                for cid,after in current.items():
                    before=previous.get(cid)
                    if before is None or normalize(before)==normalize(after):
                        continue
                    changes.append({
                        "id":cid,"nameKo":byid[cid].get("name"),
                        "build":build,"observedAtUtc":observed,
                        "dateCandidateKst":mapped_date,
                        "dateStatus":"mapped-needs-confirmation" if mapped_date else "unknown",
                        "beforeEnglish":before,
                        "afterEnglish":after,
                        "source":f"https://github.com/HearthSim/hsdata/commit/{sha}",
                    })
            coverage.append({"build":build,"observedAtUtc":observed,"cardsWithText":len(current)})
            previous=current
    changes.sort(key=lambda x:(x["observedAtUtc"],x["id"]))
    grouped=defaultdict(list)
    for row in changes:
        grouped[row["id"]].append(row)
    # Separate recurring/reverted entries from ordinary text diffs.
    transient=[]
    for cid,rows in grouped.items():
        seen=set()
        for row in rows:
            k=normalize(row["afterEnglish"])
            if k in seen:
                transient.append({"id":cid,"build":row["build"],"dateCandidateKst":row["dateCandidateKst"],
                                  "reason":"observed wording returned to an earlier state"})
            seen.add(normalize(row["beforeEnglish"]))
            seen.add(k)
    data={
      "schema":1,"set":"legacy",
      "scope":"All available HearthSim CardDefs.xml revisions; observed text changes, not certified balance patches",
      "warning":"Never derive Korean effective patch dates from commit timestamps. Do not automatically edit canonical cards.",
      "buildsScanned":len(coverage),
      "cardsWithEnglishTextChanges":len(grouped),
      "textTransitions":len(changes),
      "transientOrRevertedTransitions":len(transient),
      "transient":transient,
      "coverage":coverage,
      "changes":changes,
    }
    OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"builds":len(coverage),"cards":len(grouped),
                      "transitions":len(changes),"transient":len(transient),
                      "output":str(OUT)},ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
