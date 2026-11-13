#!/usr/bin/env python3
"""One-time first-day Legacy availability review (Korean dates; release only).

Inputs: an immutable list of 2013-08-16 US beta deck-builder inclusions
paired with native 1.0.0.3664 Korean card IDs. Never change gameplay baselines,
later patches, or source observations. Community deck lists are not match logs.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tools/legacy-beta-first-day-20261113.json"
ARCHIVE = ROOT / "original/1.0.0.3664-descriptions.json"
DAY = "2013-08-17"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    manifest = read(MANIFEST)
    candidates = manifest["candidates"]
    assert manifest["schema"] == 1 and manifest["dateKST"] == DAY
    archive = read(ARCHIVE)["cards"]
    catalog = {x["id"]: x for x in read(ROOT / "cards.json")["cards"]}
    policy_path = ROOT / "release-policy.json"
    policy = read(policy_path)
    assert len(candidates) == 176 and len({x["id"] for x in candidates}) == 176
    assert len(catalog) == 615 and policy["timezone"] == "Asia/Seoul"

    validated = []
    errors = []
    new_updates = 0

    # Validate all candidates before any write. A failure makes zero partial edits.
    for x in candidates:
        cid = x["id"]
        try:
            assert x["source"].startswith("https://www.hearthpwn.com/decks/")
            assert x["lastUpdatedUS"].endswith(" UTC-5")
            local_stamp = datetime.fromisoformat(x["lastUpdatedUS"].removesuffix(" UTC-5"))
            utc_offset = timezone(timedelta(hours=-5))
            kst = local_stamp.replace(tzinfo=utc_offset).astimezone(ZoneInfo("Asia/Seoul"))
            assert kst.date().isoformat() == DAY == x["dateKST"], (cid, kst)

            assert cid in catalog and catalog[cid]["collectible"] is True, cid
            assert catalog[cid]["name"] == x["nameKo"], cid
            assert catalog[cid]["releasedAt"] == DAY, cid
            meta_path = ROOT / "metadata" / f"{cid}.json"
            meta = read(meta_path)
            timeline = read(ROOT / "data" / f"{cid}.json")
            assert list(timeline)[0] == DAY and timeline[DAY]["collectible"] is True, cid
            assert timeline[DAY]["id"] == cid, cid
            assert meta["originalSource"]["card"]["id"] == cid, cid
            assert meta["currentCatalog"]["id"] == cid, cid
            assert meta["currentCatalog"]["name"] == x["nameKo"], cid
            assert meta["originalSource"].get("englishName"), cid
            assert any(o.get("build") == "1.0.0.3664"
                       for o in meta["originalSource"].get("historicalTextObservations", [])), cid
            original_status = archive.get(cid, {}).get("status")
            assert original_status == x["archivedStatus"], (cid, original_status)
            assert original_status in {"available", "no-description-tag"}, cid
            assert meta["release"]["date"] == DAY, cid
            assert meta["currentCatalog"]["releasedAt"] == DAY, cid

            status = meta["release"]["status"]
            assert status in {"estimated", "verified"} and meta["currentCatalog"]["releaseStatus"] == status
            assert catalog[cid]["releaseStatus"] == status, cid

            existing_rule = policy["cards"].get(cid)
            if status == "estimated":
                assert existing_rule is None, (cid, existing_rule)
                assert "releaseEvidence" not in meta, cid
                new_updates += 1
            else:
                assert existing_rule is not None and existing_rule["date"] == DAY
                assert existing_rule["status"] == "verified"
                assert meta["releaseEvidence"]["deckSource"] == x["source"], cid

            validated.append((x, meta_path, meta, status))
        except (AssertionError, ValueError, KeyError, IndexError) as exc:
            errors.append({"id": cid, "error": str(exc) or "preflight assertion failed"})

    if errors:
        raise RuntimeError("No changes written; preflight failed: " + json.dumps(errors, ensure_ascii=False))
    if new_updates == 0:
        print(json.dumps({"result": "no-op", "verifiedCandidates": len(validated)}))
        return
    assert new_updates == len(validated), "Partial previous run: reconcile before retry"
    assert sum(c["releaseStatus"] == "verified" for c in catalog.values()) == 398

    by_en = []
    for x, path, meta, status in validated:
        cid = x["id"]
        meta["release"]["status"] = "verified"
        meta["currentCatalog"]["releaseStatus"] = "verified"
        meta["confidenceNote"] = (
            "Earliest available beta day corroborated by the contemporaneous "
            "community deck-builder listing and original 3664 Korean card ID. "
            "This is NOT an actual match log; precise launch stats remain partially verified."
        )
        meta["releaseEvidence"] = {
            "date": DAY,
            "timezone": "Asia/Seoul",
            "evidenceType": "2013-08-16 original beta deckbuilder listing plus Korean 3664 card definition",
            "deckSource": x["source"],
            "deckLastUpdatedUS": x["lastUpdatedUS"],
            "deckEffectiveDayKST": DAY,
            "historicalCardArchive": "original/1.0.0.3664-descriptions.json",
            "historicalCardArchiveStatus": x["archivedStatus"],
            "officialBetaOpening": "https://hearthstone.blizzard.com/en-us/news/10639928/hearthstone-closed-beta-test-begins-8-16-2013",
            "basis": ("Card is listed in an archived public beta-day deck construction record "
                      "while the North American beta was open; the same card ID is present "
                      "in the original playable beta build's Korean card archive."),
            "limitation": ("Community deck-builder inclusion is evidence of selectable availability, "
                           "not direct evidence that the author entered a match. "
                           "Card content and historical stats have not been promoted.")
        }
        by_en.append({"id": cid, "historicalEnglishName": meta["originalSource"]["englishName"],
                      "currentKoreanName": x["nameKo"], "deck": x["source"]})
        policy["cards"][cid] = {
            "date": DAY,
            "status": "verified",
            "basis": ("Beta day-one first selectable availability: public deckbuilder "
                      + x["source"] + " (last updated " + x["lastUpdatedUS"]
                      + "), together with original Korean 3664 card ID; "
                      + "see metadata/" + cid + ".json releaseEvidence. "
                      + "Community deck inclusion is not a direct gameplay match log.")
        }
        write(path, meta)
    write(policy_path, policy)

    readme_path = ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    old_total = "398건은 출시일 검증, 217건은 기존 추정값 보존"
    assert readme.count(old_total) == 1
    readme = readme.replace(old_total, "574건은 출시일 검증, 41건은 기존 추정값 보존")
    note = (
        "2013년 8월 16일(북미) 베타 중 작성된 커뮤니티 덱 빌더 기록과 3664 한국어 "
        "원본 카드 정의를 함께 확인하여 수집 가능 카드 176개의 최초 사용 가능일을 "
        "한국 시간 2013-08-17로 추가 검증했습니다. 커뮤니티 덱 작성은 실제 대전 로그와 "
        "다르므로 해당 증거 한계를 개별 메타데이터에 기록했으며 당시 기본 스탯이나 "
        "이후 밸런스 패치는 변경하지 않았습니다. "
    )
    assert readme.count("설치된 최신 \u0060nativeTags\u0060를 과거에 소급하지 않습니다.") == 1
    readme = readme.replace("설치된 최신 \u0060nativeTags\u0060를 과거에 소급하지 않습니다.",
                            note + "설치된 최신 \u0060nativeTags\u0060를 과거에 소급하지 않습니다.")
    readme_path.write_text(readme, encoding="utf-8")

    test_path = ROOT / "tools/test-date-schema.py"
    source = test_path.read_text(encoding="utf-8")
    previous = "    assert statuses=={'estimated':217,'verified':398}"
    assert source.count(previous) == 1
    id_tuple = ",".join(repr(x["id"]) for x in candidates)
    check = (
        "    # First-day community beta deck builder + independent native 3664 cards.\\n"
        "    additional_beta_day_deck_ids = (" + id_tuple + ")\\n"
        "    for cid in additional_beta_day_deck_ids:\\n"
        "        history, meta = read_card(ROOT, cid)\\n"
        "        assert list(history)[0]=='2013-08-17' and history['2013-08-17']['collectible'], cid\\n"
        "        assert meta['release']=={'date':'2013-08-17','status':'verified'}, cid\\n"
        "        assert meta['currentCatalog']['releaseStatus']=='verified', cid\\n"
        "        assert archived_3664[cid]['status'] in ('available','no-description-tag'), cid\\n"
        "        assert meta['releaseEvidence']['deckEffectiveDayKST']=='2013-08-17', cid\\n"
        "        assert resolve(history,meta,'2013-08-16') is None, cid\\n"
        "    assert statuses=={'estimated':41,'verified':574}"
    ).replace("\\n", "\n")
    source = source.replace(previous, check)
    test_path.write_text(source, encoding="utf-8")

    compat_path = ROOT / "tools/test-legacy-compatibility.py"
    compat = compat_path.read_text(encoding="utf-8")
    marker = "VERIFIED_HERO_POWER_RELEASES = frozenset("
    assert compat.count(marker) == 1
    compat_update = (
        "# Verified initial beta day by public deck-builder inclusions and the original 3664 card archive.\\n"
        "VERIFIED_BETA_DEBUT_IDS = VERIFIED_BETA_DEBUT_IDS | frozenset(("
        + id_tuple + "))\\n"
    ).replace("\\n", "\n")
    compat_path.write_text(compat.replace(marker, compat_update + marker), encoding="utf-8")

    write(ROOT / "tools/legacy-beta-first-day-validation-20261113.json", {
        "schema": 1,
        "timezone": "Asia/Seoul",
        "date": DAY,
        "result": "passed preflight",
        "previousStatuses": {"verified": 398, "estimated": 217},
        "newStatuses": {"verified": 574, "estimated": 41},
        "reviewedNewCollectibleCardIDs": len(validated),
        "sourceLimits": ["Deck-builder listings are not match logs",
                         "Only release dates/confidence, not original statistics, are verified"],
        "cards": by_en,
    })
    print(json.dumps({"result": "pass", "newReleaseVerified": len(validated),
                      "expectedStatuses": {"verified": 574, "estimated": 41}}))


if __name__ == "__main__":
    main()
