#!/usr/bin/env python3
"""Audit last 38 first-day beta Legacy releases without modifying gameplay state.

Review is for Korean first playable availability, not current native tags, art,
balance patches or exact 2013 stats. Deck submissions are not match logs.
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
DAY="2013-08-17"

def read(path):
    return json.loads(path.read_text(encoding="utf-8"))

def write(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def main():
    manifest=read(ROOT/"tools/legacy-beta-final-20261113.json")
    assert manifest["schema"]==1 and manifest["timeZone"]=="Asia/Seoul"
    assert manifest["releaseDay"]==DAY and manifest["originalBuild"]=="1.0.0.3664"
    assert manifest["baselineCounts"]=={"total":615,"verified":574,"estimated":41}
    collectible=manifest["collectibleDebuts"]
    generated=manifest["generatedDebuts"]
    pending=manifest["excluded"]
    assert len(collectible)==21 and len(generated)==17
    assert pending==["EX1_538t","EX1_116t","EX1_317t"]
    ids=[x["id"] for x in collectible+generated]
    assert len(set(ids))==38 and not set(ids)&set(pending)
    cards={x["id"]:x for x in read(ROOT/"cards.json")["cards"]}
    assert len(cards)==615
    count={"verified":0,"estimated":0}
    for item in cards.values():count[item["releaseStatus"]]+=1
    archive=read(ROOT/"original/1.0.0.3664-descriptions.json")["cards"]
    policy_path=ROOT/"release-policy.json"
    policy=read(policy_path)
    readme_path=ROOT/"README.md"
    readme=readme_path.read_text(encoding="utf-8")
    test_path=ROOT/"tools/test-date-schema.py"
    test=test_path.read_text(encoding="utf-8")
    compat_path=ROOT/"tools/test-legacy-compatibility.py"
    compat=compat_path.read_text(encoding="utf-8")

    # Check generated outputs in code before any write to a tracked file.
    original="574건은 출시일 검증, 41건은 기존 추정값 보존"
    assert readme.count(original)==1
    native_marker="설치된 최신 "+chr(96)+"nativeTags"+chr(96)+"를 과거에 소급하지 않습니다."
    assert readme.count(native_marker)==1
    assert test.count("    assert statuses=={'estimated':41,'verified':574}")==1
    assert compat.count("VERIFIED_HERO_POWER_RELEASES = frozenset(")==1
    if count=={"verified":612,"estimated":3}:
        assert all(cards[cid]["releaseStatus"]=="verified" for cid in ids)
        assert all(cards[cid]["releaseStatus"]=="estimated" for cid in pending)
        print(json.dumps({"result":"no-op","alreadyVerified":len(ids)}))
        return
    assert count=={"verified":574,"estimated":41},count

    new_metadata=[]
    for x in collectible+generated:
        cid=x["id"]
        row=cards[cid]
        assert row["releaseStatus"]=="estimated" and row["releasedAt"]==DAY,cid
        assert row["collectible"]==("source" in x),cid
        meta_path=ROOT/"metadata"/(cid+".json")
        meta=read(meta_path)
        timelines=read(ROOT/"data"/(cid+".json"))
        assert list(timelines)[0]==DAY,cid
        assert timelines[DAY]["collectible"]==row["collectible"],cid
        assert timelines[DAY]["id"]==cid,cid
        assert meta["release"]=={"date":DAY,"status":"estimated"},cid
        assert meta["currentCatalog"]["releaseStatus"]=="estimated",cid
        assert meta["currentCatalog"]["releasedAt"]==DAY,cid
        assert meta["currentCatalog"]["id"]==cid,cid
        assert meta["currentCatalog"]["name"]==x["koreanName"]==row["name"],cid
        assert meta["originalSource"]["card"]["id"]==cid,cid
        assert meta["originalSource"].get("englishName"),cid
        assert meta.get("releaseEvidence") is None,cid
        assert policy["cards"].get(cid) is None,cid
        assert archive.get(cid,{}).get("status")==x["archiveStatus"],cid
        assert x["archiveStatus"] in ("available","no-description-tag"),cid
        if "source" in x:
            assert (x["source"].startswith("https://www.hearthpwn.com/")
                    or x["source"].startswith("https://linuxtest.hearthpwn.com/")),cid
            stamp=x["lastUpdatedUS"]
            assert stamp.endswith(" UTC-5"),cid
            us=datetime.fromisoformat(stamp.removesuffix(" UTC-5")).replace(
                tzinfo=timezone(timedelta(hours=-5)))
            assert us.astimezone(ZoneInfo("Asia/Seoul")).date().isoformat()==DAY,cid
            assert any(o.get("build")=="1.0.0.3664"
                       for o in meta["originalSource"].get("historicalTextObservations",[])),cid
            proof={
                "date":DAY,"timezone":"Asia/Seoul",
                "evidenceType":"Contemporaneous August 16 beta deck-builder card list plus independent Korean 3664 ID",
                "deckSource":x["source"],
                "deckLastUpdatedUS":stamp,"deckEffectiveDayKST":DAY,
                "historicalCardArchive":"original/1.0.0.3664-descriptions.json",
                "historicalCardArchiveStatus":x["archiveStatus"],
                "officialBetaStart":"https://hearthstone.blizzard.com/en-us/news/10639928/hearthstone-closed-beta-test-begins-8-16-2013",
                "basis":"Original beta-day deck-builder includes this specific collectible card; native 3664 definition independently confirms ID and Korean name.",
                "limitation":"Deck-builder list is not a recorded game match. Historical stats, later art, and balance patches are not certified by the listing."
            }
            basis="Beta-day selectable deck evidence "+x["source"]+" ("+stamp+"), original native 3664 ID; see metadata/"+cid+".json. Deck builder is not a match log."
            note="Playable first beta day supported by contemporaneous public deck-builder and native 3664 card ID. Launch-day stats only partially verified."
        else:
            parent=x["parentCardId"]
            assert parent in cards,cid
            assert cards[parent]["releaseStatus"]=="verified" or parent in ids,cid
            assert archive.get(parent,{}).get("status")=="available",cid
            assert archive[parent].get("text"),cid
            assert x["relationEvidence"],cid
            proof={
                "date":DAY,"timezone":"Asia/Seoul",
                "evidenceType":"Original 3664 beta child generated from a verified day-one playable parent",
                "parentCardId":parent,
                "parentName":x["parentKoreanName"],
                "criterion":"Earliest in-game generation, not client preload",
                "basis":x["relationEvidence"],
                "parentReleaseSource":"metadata/"+parent+".json",
                "historicalCardArchive":"original/1.0.0.3664-descriptions.json",
                "historicalCardArchiveStatus":x["archiveStatus"],
                "independentSource":x.get("additionalSource"),
                "officialBetaStart":"https://hearthstone.blizzard.com/en-us/news/10639928/hearthstone-closed-beta-test-begins-8-16-2013",
                "limitation":"Child ID/generation date corroborated by original client and parent. Exact original stats or modern display name may not be the original version."
            }
            basis="First generatable by verified 2013 beta parent "+parent+"; original 3664 parent text and native child ID checked. See metadata/"+cid+".json."
            note="Playable beta-day parent generated this original 3664 child. The ID/date but not the full historical baseline is verified."
        meta["release"]["status"]="verified"
        meta["currentCatalog"]["releaseStatus"]="verified"
        meta["confidenceNote"]=note
        meta["releaseEvidence"]=proof
        policy["cards"][cid]={"date":DAY,"status":"verified","basis":basis}
        new_metadata.append((meta_path,meta))
    assert len(new_metadata)==38
    assert all(cards[cid]["releaseStatus"]=="estimated" for cid in pending)

    readme=readme.replace(original,"612건은 출시일 검증, 3건은 기존 추정값 보존")
    readme=readme.replace(native_marker,(
        "2013년 북미 베타 당일 덱 빌더의 실제 목록과 당시 한국어 원본 카드 ID가 일치하는 "
        "수집 가능 카드 21장의 2013-08-17 최초 사용을 추가 검증했습니다. "
        "이미 검증된 첫날 부모 카드에서 실제 생성 가능한 자식 카드 17종도 초기 3664 ID와 "
        "효과를 대조하여 검증했습니다. 커뮤니티 덱 목록은 실전 대전 로그가 아니라는 한계를 "
        "개별 근거에 남겼습니다. EX1_538t는 당시 강화 효과와 후대 사냥개가 겹치고 "
        "EX1_116t는 3664에 같은 ID가 없으며 EX1_317t는 초기 실제 생성 증거가 부족하므로 "
        "셋 모두 검증 전 추정으로 남깁니다. "
    )+native_marker)

    original_test="    assert statuses=={'estimated':41,'verified':574}"
    quoted=",".join(repr(x["id"]) for x in collectible)
    paired=",".join("("+repr(x["id"])+","+repr(x["parentCardId"])+")" for x in generated)
    new_test=(
        "    # Additional original 3664 beta deck entries, with KST-local date evidence.\n"
        "    final_beta_collectible_ids=("+quoted+")\n"
        "    for cid in final_beta_collectible_ids:\n"
        "        state, meta=read_card(ROOT,cid)\n"
        "        assert list(state)[0]=='2013-08-17' and state['2013-08-17']['collectible'],cid\n"
        "        assert meta['release']=={'date':'2013-08-17','status':'verified'},cid\n"
        "        assert meta['currentCatalog']['releaseStatus']=='verified',cid\n"
        "        assert archived_3664[cid]['status'] in ('available','no-description-tag'),cid\n"
        "        assert meta['releaseEvidence']['deckEffectiveDayKST']=='2013-08-17',cid\n"
        "        assert resolve(state,meta,'2013-08-16') is None,cid\n"
        "    # Child forms actually generated from beta-day parents, including recent cohort.\n"
        "    final_beta_child_pairs=("+paired+")\n"
        "    for cid,pid in final_beta_child_pairs:\n"
        "        state, meta=read_card(ROOT,cid)\n"
        "        parent_state,parent_meta=read_card(ROOT,pid)\n"
        "        assert list(state)[0]=='2013-08-17' and not state['2013-08-17']['collectible'],cid\n"
        "        assert parent_meta['release']=={'date':'2013-08-17','status':'verified'},pid\n"
        "        assert meta['release']=={'date':'2013-08-17','status':'verified'},cid\n"
        "        assert meta['currentCatalog']['releaseStatus']=='verified',cid\n"
        "        assert meta['releaseEvidence']['parentCardId']==pid,cid\n"
        "        assert archived_3664[cid]['status'] in ('available','no-description-tag'),cid\n"
        "        assert resolve(state,meta,'2013-08-16') is None,cid\n"
        "    for cid in ('EX1_538t','EX1_116t','EX1_317t'):\n"
        "        state,meta=read_card(ROOT,cid)\n"
        "        assert meta['release']['status']=='estimated',cid\n"
        "    assert statuses=={'estimated':3,'verified':612}"
    )
    test=test.replace(original_test,new_test)
    anchor="VERIFIED_HERO_POWER_RELEASES = frozenset("
    compat=compat.replace(anchor,
        "# Original beta-day available card IDs verified against contemporaneous deck sources and native 3664.\n"
        "VERIFIED_BETA_DEBUT_IDS = VERIFIED_BETA_DEBUT_IDS | frozenset(("+",".join(repr(cid) for cid in ids)+"))\n"+anchor)
    for path,meta in new_metadata:write(path,meta)
    write(policy_path,policy)
    readme_path.write_text(readme,encoding="utf-8")
    test_path.write_text(test,encoding="utf-8")
    compat_path.write_text(compat,encoding="utf-8")
    write(ROOT/"tools/legacy-beta-final-validation-20261113.json",{
        "schema":1,"date":DAY,"timezone":"Asia/Seoul","result":"preflight passed",
        "verifiedCollectible":len(collectible),"verifiedGenerated":len(generated),
        "beforeCounts":{"verified":574,"estimated":41},
        "expectedCounts":{"verified":612,"estimated":3},
        "unverifiedExceptions":pending,
        "sourcesAreNotGameLogs":True,
        "noGameplayPatchChanges":True,
        "cards":[{"id":x["id"],"name":x["koreanName"],"source":x.get("source"),
                  "parentId":x.get("parentCardId")} for x in collectible+generated]
    })
    print(json.dumps({"result":"pass","newVerified":len(ids),"collectible":len(collectible),
                      "generated":len(generated),"expectedVerified":612,"remaining":pending}))

if __name__=="__main__":
    main()
