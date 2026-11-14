#!/usr/bin/env python3
"""Import only the two BASIC Death Knight cards' art and golden dependencies.

Source is pinned to the archived source repository commit; SHA-1 Git blob hashes
protect original bytes. Re-running is idempotent and never overwrites mismatches.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "qxwd565/The-League-of-Explorers"
PIN = "6fd5dd7967123cae83cdeffb714814b5a557744d"
ASSETS = {
    "art/HERO_11bp.png": "eb606b87a33b8ca2dad084750960ed2972396498",
    "art/HERO_11bpt.png": "cb7f1dd3edc2e64b064998845257454e1be40dba",
    "golden/textures/101aded79d6593b41cb251f76b82db61019dd6b8869e3849329a170e2c4da347.bin": "4c26ed157c876d20575b35425c59ce739fd7ee16",
    "golden/textures/2902d7c2013939f89399132b2e642a59dbedc08650bf6071ee75b3511ee4b653.bin": "54462972271d866eeaf16ce6c5ba6ef237f7848a",
    "golden/textures/36fca3de7ee36b6c2840072708a6e9d5a637b75e4a93ddb80776c3b653a84144.bin": "3038c0219482b9ba7cfd2d0302f5292e71e14baf",
    "golden/textures/384674bf00667d759282b8d87b6dee9e8f32ce23e00c9186f0ba647528867ae9.bin": "729c02d970c470f9bb640e8bbd8101a7e8b7afcc",
    "golden/textures/3946f6082fb8971ccb1a45c21093eb9491e1cd4128c182decd1329f5c48b61ae.bin": "660025e9850e4010b37d7ed22c066df62927158d",
    "golden/textures/3f00389dacb85f195b5e851ccee99d91dd01ff39516f517781315c164599aa37.bin": "8fdbc9ccb7f195b6d6d8cc6d7725b0b082484a6e",
    "golden/textures/610359b6a61e657fe17e11641f7afc8d1db5cc3095a2649ee9de230df7feb191.bin": "0f072d92819762ac397bc13e3fecec7213b19193",
    "golden/textures/66d35ece700887ddd813ba5e9ae35673c9697b3eb04f73d416d61b72212078a4.bin": "80640672f0f0f379c9ca30a95dcebf408f9a2174",
    "golden/textures/840e30c9777b64a4f15d252dc6e67f8ba4b5757fbf3991d3058ef8574b95590a.bin": "eaa6684ad4247be2248e87846c016cc83bb3ce68",
    "golden/textures/8aa8c2765b66614443705d373d3ed2a75e47dde368ec9efff6fdd01a86829ba1.bin": "1ca7ef5e8b04d443c4055da575ac9b328abe7b91",
    "golden/textures/95d8420910e37e829a5b714d874a9bd728f8eed2d42a393ca618ff6022e852ca.bin": "62b5292dd560b38d70d9ab91ede031e496bd61bd",
    "golden/textures/d62aa762642ef6b5cc91a60a774922191854a6da5bbd2dc35464e3b5386c8bd5.bin": "2e8d3c6a65c46bdd66553fa6ce484a2aad7527b2",
    "golden/textures/e4e4fb472c86f7d539a5f933d59df17b379e344f30822d6c6bcc76de5f96da7c.bin": "2d470d80b82dbc087fbf75fa156df00aca860e51",
    "golden/textures/ee6f48c839914d13cc1cad3079a67082f2b8960f4355ee1f5fd0b420a8caf399.bin": "47d072809a07969006b832c135aba96651979c2f",
    "golden/textures/f48126fb107fd5a22367ef45e7ae014ed7d8f9e91b9321db0d3c41096b98859b.bin": "7f1199a27838a09ab5207d709e2956a119fb498b",
}
CARDS = ("HERO_11bp", "HERO_11bpt")


def git_blob_sha(content: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()


def import_assets():
    for name, expected in ASSETS.items():
        target = ROOT / name
        if target.is_file():
            actual = target.read_bytes()
        else:
            url = f"https://raw.githubusercontent.com/{SOURCE}/{PIN}/{name}"
            with urlopen(url, timeout=50) as r:
                actual = r.read()
        digest = git_blob_sha(actual)
        if digest != expected:
            raise ValueError(f"{name}: source Git blob mismatch, {digest} != {expected}")
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(actual)
    print(json.dumps({"source": SOURCE, "pinnedCommit": PIN, "assets": len(ASSETS)}))


def import_catalog():
    target = ROOT / "cards.json"
    catalog = json.loads(target.read_text(encoding="utf-8"))
    rows = {row["id"]: row for row in catalog["cards"]}
    for cid in CARDS:
        meta = json.loads((ROOT / "metadata" / (cid + ".json")).read_text(encoding="utf-8"))
        row = meta["currentCatalog"]
        if cid in rows:
            if rows[cid]["dbfId"] != row["dbfId"]:
                raise ValueError("Existing card has a conflicting DBF ID: " + cid)
        else:
            catalog["cards"].append(row)
            rows[cid] = row
    if len(rows) != len(catalog["cards"]) or len({r["dbfId"] for r in catalog["cards"]}) != len(rows):
        raise ValueError("Duplicate card or DBF ID in Legacy catalog")
    target.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"legacyCurrentCards": len(rows)}))


if __name__ == "__main__":
    import_assets()
    import_catalog()
