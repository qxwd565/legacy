#!/usr/bin/env python3
"""Audit old/new English card text for Legacy cards between 2021 and 2026.

Read-only: changed text is not necessarily changed functionality. All output
is candidate evidence for checking Korean official balance notes; do not
automatically convert it into Korean card patches.
"""
from __future__ import annotations
import html
import json
import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REV_2021="9e10b526eed8a9c5ece2f73f0c2a6a3b60109d62"
REV_2026="31b034c26f24b8a66ece845ffd03c1ca397b9a02"


def run(repo,*args):
    return subprocess.run(["git","-C",str(repo),*args],
                          capture_output=True,check=True).stdout


def read_texts(xml, wanted):
    result={}
    for entity in ET.fromstring(xml).iter("Entity"):
        cid=entity.get("CardID")
        if cid not in wanted:
            continue
        for tag in entity.findall("Tag"):
            if tag.get("name") == "CARDTEXT_INHAND" or tag.get("enumID") == "184":
                english=tag.find("enUS")
                if english is not None:
                    result[cid]="".join(english.itertext())
                break
    return result


def norm(value):
    value=html.unescape(value or "")
    value=re.sub(r"<[^>]+>", "", value)
    return " ".join(value.replace("\\n"," ").split()).lower()


def main():
    cat=json.loads((ROOT/"cards.json").read_text(encoding="utf-8"))
    wanted={c["id"]:c for c in cat["cards"]}
    with tempfile.TemporaryDirectory(prefix="hsdata-effect-audit-") as folder:
        repo=Path(folder)/"hsdata"
        subprocess.run(["git","clone","--quiet","--filter=blob:none","--no-checkout",
                        "https://github.com/HearthSim/hsdata.git",str(repo)],check=True)
        early=read_texts(run(repo,"show",f"{REV_2021}:CardDefs.xml"),wanted)
        late=read_texts(run(repo,"show",f"{REV_2026}:CardDefs.xml"),wanted)
    out=[]
    for cid in sorted(wanted):
        a,b=early.get(cid),late.get(cid)
        if not a or not b or norm(a)==norm(b):
            continue
        modern=wanted[cid]
        path=ROOT/"data"/f"{cid}.json"
        from date_schema import compatibility_card
        card=compatibility_card(ROOT,cid) if path.exists() else {}
        recent=[{"date":p["date"],"text":p["changes"]["text"]}
                for p in card.get("patches",[])
                if p["date"]>"2021-03-26" and "text" in p["changes"]]
        out.append({"id":cid,"nameKo":modern.get("name"),"release":modern.get("releasedAt"),
                    "text2021En":a,"text2026En":b,
                    "currentKo":modern.get("text"),"recordedPost2021Changes":recent,
                    "reviewStatus":"needs gameplay-vs-wording classification"})
    result={"schema":1,"set":"legacy","2021source":
            f"https://github.com/HearthSim/hsdata/commit/{REV_2021}",
            "2026source":f"https://github.com/HearthSim/hsdata/commit/{REV_2026}",
            "description":"Lexical text differences, not verified balance changes. Never auto-publish.",
            "candidates":out,"changedCards":len(out)}
    p=ROOT/"tools"/"legacy-effect-diff-review.json"
    p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"early":len(early),"late":len(late),
                      "changedLegacyTexts":len(out),
                      "withRecordedPost2021":sum(bool(x["recordedPost2021Changes"]) for x in out)},ensure_ascii=False))


if __name__=="__main__":
    main()
