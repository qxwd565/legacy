#!/usr/bin/env python3
"""Verify Legacy's release-baseline + forward-patch model and current catalog."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS = (
    "name", "type", "cardClass", "classes", "rarity", "collectible",
    "cost", "attack", "health", "durability", "armor", "text",
    "races", "race", "spellSchool", "mechanics",
)


def main():
    catalog = json.loads((ROOT / "cards.json").read_text(encoding="utf-8"))
    render = json.loads((ROOT / "render.json").read_text(encoding="utf-8"))
    backward = json.loads((ROOT / "history.json").read_text(encoding="utf-8"))["cards"]
    render_by_id = {c["id"]: c for c in render["cards"]}
    if catalog.get("set") != "legacy" or render.get("set") != "legacy":
        raise AssertionError("Wrong card set")
    migrated = 0
    for modern in catalog["cards"]:
        cid = modern["id"]
        path = ROOT / "data" / (cid + ".json")
        if not path.is_file():
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        card = document["card"]
        if (card.get("dbfId") is None and
                document.get("apiAvailability", "").startswith("standalone historical source;")):
            continue
        if "history" in card or "patches" not in card:
            raise AssertionError(f"{cid}: not migrated to forward patches")
        if card.get("id") != cid or card.get("dbfId") != modern.get("dbfId"):
            raise AssertionError(f"{cid}: identity mismatch")
        baseline = {field: card[field] for field in SPECS if field in card}
        dates = []
        for ev in card["patches"]:
            d = ev["date"]
            if not isinstance(d, str) or (dates and d <= dates[-1]):
                raise AssertionError(f"{cid}: non-increasing patch dates")
            if card.get("releasedAt") and d <= card["releasedAt"]:
                raise AssertionError(f"{cid}: patch before release")
            if not ev["changes"]:
                raise AssertionError(f"{cid}: empty patch")
            for key, value in ev["changes"].items():
                if key in baseline:
                    if value == baseline[key]:
                        raise AssertionError(f"{cid}: redundant patch on {d} for {key}")
                    baseline[key] = value
                elif key == "legacyArt" and "legacyArt" in card:
                    baseline[key] = value
                else:
                    raise AssertionError(f"{cid}: no baseline for {key}")
            dates.append(d)
        for field in SPECS:
            if field in baseline or field in modern:
                if baseline.get(field) != modern.get(field):
                    raise AssertionError(f"{cid}: differs from current catalog ({field})")
        expected = render_by_id[cid]
        for field in SPECS:
            if field in modern and expected.get(field) != modern[field]:
                raise AssertionError(f"{cid}: renderer mismatch ({field})")
        derived = expected.get("history", [])
        compat = backward.get(str(modern["dbfId"]), {})
        if derived != compat.get("history", []) and (derived or compat):
            raise AssertionError(f"{cid}: backward compatibility mismatch")
        migrated += 1
    def get(cid):
        return json.loads((ROOT / "data" / (cid + ".json")).read_text(encoding="utf-8"))["card"]
    if get("EX1_016")["cost"] != 5:
        raise AssertionError("Sylvanas must debut at 5 mana")
    if not any(x["date"] == "2014-01-17" and x["changes"].get("cost") == 6
               for x in get("EX1_016")["patches"]):
        raise AssertionError("Sylvanas mana change missing")
    if get("EX1_350")["races"] != []:
        raise AssertionError("Velen incorrectly classified as Draenei at debut")
    if not any(x["date"] == "2024-10-30" and x["changes"].get("races") == ["DRAENEI"]
               for x in get("EX1_350")["patches"]):
        raise AssertionError("Velen Draenei introduction missing")
    if get("CS2_029")["spellSchool"] != "":
        raise AssertionError("Fireball incorrectly has a debut spell school")
    if not any(x["date"] == "2021-03-26" and x["changes"].get("spellSchool") == "FIRE"
               for x in get("CS2_029")["patches"]):
        raise AssertionError("Fireball spell school introduction missing")
    def value_at(cid, field, day):
        card = get(cid)
        value = card[field]
        for revision in card["patches"]:
            if revision["date"] <= day and field in revision["changes"]:
                value = revision["changes"][field]
        return value
    assert value_at("NEW1_019", "attack", "2015-01-01") == 3
    assert value_at("NEW1_019", "attack", "2017-01-01") == 2
    assert value_at("NEW1_019", "attack", "2022-01-01") == 3
    assert value_at("EX1_029", "attack", "2017-01-01") == 1
    assert value_at("EX1_029", "attack", "2022-01-01") == 2
    assert value_at("EX1_166", "health", "2017-01-01") == 2
    assert value_at("EX1_166", "health", "2022-01-01") == 4
    assert value_at("EX1_089", "health", "2017-01-01") == 4
    assert value_at("EX1_089", "health", "2022-01-01") == 2
    assert value_at("CS2_188", "attack", "2015-01-01") == 2
    assert value_at("CS2_188", "attack", "2017-01-01") == 1
    assert value_at("EX1_620", "cost", "2017-01-01") == 25
    assert value_at("EX1_620", "cost", "2019-01-01") == 20
    assert value_at("EX1_565", "cost", "2020-01-01") == 3
    assert value_at("EX1_565", "health", "2022-01-01") == 2
    assert value_at("EX1_565", "health", "2025-01-01") == 3
    # Core 2024 effects must not leak into the initial release or 2021 state.
    assert "TRADEABLE" not in value_at("EX1_005", "mechanics", "2024-03-11")
    assert "TRADEABLE" in value_at("EX1_005", "mechanics", "2024-03-12")
    assert "교환성" not in value_at("EX1_005", "text", "2024-03-11")
    assert "교환성" in value_at("EX1_005", "text", "2024-03-12")
    assert "무작위" in value_at("EX1_085", "text", "2024-03-11")
    assert "무작위" not in value_at("EX1_085", "text", "2024-03-12")
    assert "장소" not in value_at("EX1_312", "text", "2024-03-11")
    assert "장소" in value_at("EX1_312", "text", "2024-03-12")
    assert "둘" not in value_at("EX1_572", "text", "2024-03-11")
    assert "둘" in value_at("EX1_572", "text", "2024-03-12")
    # Verified effect changes must not be backdated to the 2021 Core revamp.
    holy = get("EX1_365")["patches"]
    assert not any(e["date"] == "2021-03-26" and "text" in e["changes"] for e in holy)
    assert any(e["date"] == "2025-11-14" and "하수인에게" in e["changes"].get("text","") for e in holy)
    sorc = get("EX1_608")["patches"]
    assert next(e for e in sorc if e["date"] == "2021-03-26")["changes"]["text"] == "내 주문들의 비용이 (1) 감소합니다."
    assert any(e["date"] == "2024-08-30" and "1보다 낮아지진" in e["changes"].get("text","") for e in sorc)
    # Core 2025 gameplay changes are distinct from the 2021 stat refresh.
    assert "TRADEABLE" not in value_at("EX1_002", "mechanics", "2025-03-18")
    assert "TRADEABLE" in value_at("EX1_002", "mechanics", "2025-03-19")
    assert "TAUNT" not in value_at("EX1_110", "mechanics", "2025-03-18")
    assert "TAUNT" in value_at("EX1_110", "mechanics", "2025-03-19")
    assert "도발" not in value_at("EX1_110", "text", "2025-03-18")
    assert "5/5" in value_at("EX1_110", "text", "2021-03-26")
    assert "피해를 2" in value_at("EX1_134", "text", "2025-03-18")
    assert "피해를 3" in value_at("EX1_134", "text", "2025-03-19")
    # Later effect changes must not replace the 2021 snapshot.
    assert "속공" in value_at("EX1_084", "text", "2023-04-04")
    assert "돌진" in value_at("EX1_084", "text", "2023-04-05")
    assert "5/4" in value_at("EX1_165", "text", "2023-04-04")
    assert "7/6" in value_at("EX1_165", "text", "2023-04-05")
    assert value_at("EX1_165t1", "mechanics", "2021-03-25") == ["CHARGE"]
    assert value_at("EX1_165t1", "mechanics", "2021-03-26") == ["RUSH"]
    assert "#2" in value_at("CS2_097", "text", "2023-04-04")
    assert "#3" in value_at("CS2_097", "text", "2023-04-05")
    assert "공격력을 +1" in value_at("CS3_014", "text", "2022-04-06")
    assert "초과 치유" in value_at("CS3_014", "text", "2023-04-05")
    assert "5 회복" in value_at("NEW1_008b", "text", "2023-04-04")
    assert "7 회복" in value_at("NEW1_008b", "text", "2023-04-05")
    assert "(2)" in value_at("EX1_259", "text", "2023-04-27")
    assert "(1)" in value_at("EX1_259", "text", "2023-04-28")
    assert "모든 적 하수인에게" in value_at("CS1_112", "text", "2023-04-04")
    assert "모든 적에게" in value_at("CS1_112", "text", "2023-04-05")
    assert "모든 적 하수인에게" in value_at("CS1_112", "text", "2023-04-28")
    assert "$4" in value_at("EX1_609", "text", "2023-08-22")
    assert "$6" in value_at("EX1_609", "text", "2023-08-23")
    assert "$2" in value_at("EX1_320", "text", "2023-08-22")
    assert "$3" in value_at("EX1_320", "text", "2023-08-23")
    # Dream-card and Molten Giant functionality must follow actual patch dates.
    assert "하수인" in value_at("DREAM_02", "text", "2023-01-01")
    assert "캐릭터" in value_at("DREAM_02", "text", "2024-03-29")
    assert value_at("DREAM_04", "cost", "2022-01-01") == 1
    assert value_at("DREAM_04", "cost", "2024-03-29") == 0
    assert "적 하수인" in value_at("DREAM_04", "text", "2022-01-01")
    assert "주인의 손" in value_at("DREAM_04", "text", "2024-03-29")
    assert "+4/+4" in value_at("DREAM_05", "text", "2022-01-01")
    assert "+5/+5" in value_at("DREAM_05", "text", "2024-03-29")
    assert "받은 피해" in value_at("EX1_620", "text", "2024-07-16")
    assert "잃은 생명력" in value_at("EX1_620", "text", "2024-07-17")
    assert get("CS3_014")["releasedAt"] == "2022-04-06"
    assert value_at("EX1_165a", "mechanics", "2021-03-25") == ["CHARGE"]
    assert value_at("EX1_165a", "mechanics", "2021-03-26") == ["RUSH"]
    for cid in ("NEW1_023", "DREAM_01"):
        assert "ELUSIVE" not in value_at(cid, "mechanics", "2024-03-11")
        assert "CANT_BE_TARGETED_BY_SPELLS" in value_at(cid, "mechanics", "2024-03-11")
        assert "모면" not in value_at(cid, "text", "2024-03-11")
        assert value_at(cid, "mechanics", "2024-03-12") == ["ELUSIVE"]
        assert value_at(cid, "text", "2024-03-12") == "<b>모면</b>"
    assert value_at("DREAM_02", "cost", "2024-03-28") == 3
    assert value_at("DREAM_02", "cost", "2024-03-29") == 2
    assert value_at("DREAM_04", "cost", "2024-03-28") == 1
    assert "+4/+4" in value_at("DREAM_05", "text", "2024-03-28")
    for number in range(1, 13):
        cid = f"GIFT_{number:02d}"
        assert get(cid)["releasedAt"] == "2024-02-14"
        assert get(cid)["releaseStatus"] == "verified"
    assert "번개 화살" in value_at("GIFT_06", "text", "2024-03-28")
    assert "번개 폭풍" in value_at("GIFT_06", "text", "2024-03-29")
    for cid in ("PRO_001", "PRO_001a", "PRO_001at", "PRO_001b", "PRO_001c"):
        assert get(cid)["releasedAt"] == "2013-12-12"
        assert not any(e["date"] <= "2013-12-12" for e in get(cid)["patches"])
    assert "디버그" not in get("PRO_001")["text"]
    for cid in ("BG31_BOB", "BG31_BOBt", "BG31_BOBt2", "BG31_BOBt3", "BG31_BOBt4"):
        assert get(cid)["releasedAt"] == "2024-12-11"
    assert "복사" not in value_at("BG31_BOBt2", "text", "2025-03-18")
    assert "복사" in value_at("BG31_BOBt2", "text", "2025-03-19")
    assert value_at("EX1_538", "cost", "2013-12-11") == 1
    assert value_at("EX1_538", "cost", "2013-12-12") == 4
    assert value_at("EX1_019", "health", "2013-12-11") == 3
    assert value_at("EX1_019", "health", "2013-12-12") == 2
    assert "낼 때마다" in value_at("EX1_258", "text", "2021-06-03")
    assert "낸 후에" in value_at("EX1_258", "text", "2021-06-04")
    assert "핑클 아인혼" in value_at("EX1_577", "text", "2021-10-12")
    assert "핍 퀵위트" in value_at("EX1_577", "text", "2021-10-13")
    assert value_at("EX1_finkle", "name", "2021-10-12") == "핑클 아인혼"
    assert value_at("EX1_finkle", "name", "2021-10-13") == "핍 퀵위트"
    for cid in ("EX1_302", "EX1_320"):
        assert "이 피해로" in value_at(cid, "text", "2026-03-10")
        assert "이 피해로" not in value_at(cid, "text", "2026-03-11")
    assert "$3" in value_at("EX1_320", "text", "2023-08-23")
    print(json.dumps({"set":"legacy","validatedCards":migrated,"result":"pass"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
