"""Read original Korean client descriptions, keeping whitespace and markup exact.

The input is pre-extracted client JSONL, not a current-card text service. Dates
must be supplied separately: App Store upload timestamps are not patch dates.
No assets or current card fields are changed by this tool.
"""
from __future__ import annotations

import argparse
import copy
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def mpq_bundle(archive_path, library_path):
    dll = ctypes.WinDLL(str(library_path), use_last_error=True)
    handle, dword = wintypes.HANDLE, wintypes.DWORD

    def api(name, params, result=ctypes.c_bool):
        fn = getattr(dll, name)
        fn.argtypes, fn.restype = params, result
        return fn

    op = api("SFileOpenArchive", [wintypes.LPCWSTR, dword, dword, ctypes.POINTER(handle)])
    of = api("SFileOpenFileEx", [handle, ctypes.c_char_p, dword, ctypes.POINTER(handle)])
    size = api("SFileGetFileSize", [handle, ctypes.POINTER(dword)], dword)
    read = api("SFileReadFile", [handle, ctypes.c_void_p, dword, ctypes.POINTER(dword), ctypes.c_void_p])
    cf = api("SFileCloseFile", [handle])
    ca = api("SFileCloseArchive", [handle])
    archive, file = handle(), handle()
    if not op(str(archive_path), 0, 0x100, ctypes.byref(archive)):
        raise OSError(ctypes.get_last_error(), "MPQ open")
    try:
        for name in (b"Data\\cardxml0.unity3d", b"Data\\Win\\cardxml0.unity3d"):
            if of(archive, name, 0, ctypes.byref(file)):
                break
        else:
            raise FileNotFoundError("3749 cardxml0")
        try:
            high = dword()
            length = size(file, ctypes.byref(high))
            if high.value or length > 20_000_000:
                raise ValueError("Unexpected cardxml0 size")
            buffer, received = ctypes.create_string_buffer(length), dword()
            if not read(file, buffer, length, ctypes.byref(received), None) or received.value != length:
                raise OSError("Incomplete MPQ read")
            return buffer.raw
        finally:
            cf(file)
    finally:
        ca(archive)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def version_key(version):
    return tuple(int(v) for v in version.split("."))


def rendered(text):
    # Only the game's explicit escape syntax is converted. Never strip, split,
    # collapse whitespace or normalize Unicode: these are observed changes.
    return text.replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def pc_snapshot(path, wanted, version, unitypy):
    result = {}
    env = unitypy.load(path if isinstance(path, bytes) else str(path))
    for obj in env.objects:
        if obj.type.name != "TextAsset":
            continue
        tree = obj.read_typetree()
        body = tree.get("m_Script", "")
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        if "<Entity" not in body:
            continue
        document = ET.fromstring(body)
        entities = [document] if document.tag == "Entity" else document.findall("Entity")
        for entity in entities:
            cid = entity.get("CardID")
            if cid not in wanted:
                continue
            tags = {tag.get("enumID"): tag for tag in entity.findall("Tag")}
            card_set = tags.get("183")
            name_tag = tags.get("185")
            text_tag = tags.get("184")
            ko_name = name_tag.find("koKR") if name_tag is not None else None
            ko_text = text_tag.find("koKR") if text_tag is not None else None
            if ko_name is None:
                continue  # No Korean locale is not an empty description.
            item = {"name": "".join(ko_name.itertext()),
                    "sets": [int(card_set.get("value"))] if card_set is not None else []}
            if text_tag is None:
                item["text"] = ""
            elif ko_text is not None:
                item["text"] = "".join(ko_text.itertext())
            if cid in result and result[cid] != item:
                raise ValueError(f"{version}: conflicting native records for {cid}")
            result[cid] = item
    return result


def ios_snapshot(path, wanted):
    cards = {}
    with path.open(encoding="utf-8-sig") as stream:
        for line in stream:
            # Every record is still visited. Avoid decoding huge multilingual
            # native XML for unrelated expansions while comparing Legacy IDs.
            match = re.search(r'"cardId"\s*:\s*"([^"]+)"', line[:2000])
            if match and match[1] not in wanted:
                continue
            record = json.loads(line)
            cid = record.get("cardId")
            if cid not in wanted:
                continue
            ko = record.get("localized", {}).get("koKR")
            if not ko:
                continue
            ko = {key.lower(): value for key, value in ko.items()}
            name = ko.get("cardname", ko.get("name"))
            if name is None:
                continue
            text = ko.get("cardtextinhand", ko.get("textinhand", ""))
            item = {"name": name, "text": text,
                    "sets": [value["id"] for value in record.get("setMembership", [])]}
            if cid in cards and cards[cid] != item:
                raise ValueError(f"{path.parent.name}: conflicting native records for {cid}")
            cards[cid] = item
    return cards


def scan(args):
    wanted = {p.stem for p in (ROOT / "data").glob("*.json")}
    snapshots = []
    if args.beta:
        sys.path.insert(0, str(args.unitypy))
        import UnityPy
        originals = args.beta.parent / "beta-client-originals-20261101"
        for build in [3664, 3749, 3890, 3937, 4217, 4243, 4458, 4482, 4944]:
            version = f"1.0.0.{build}"
            folder = args.beta / version / "Data"
            if build == 3749:
                path = mpq_bundle(args.mpq or originals / "3749-input" / "base-Win.MPQ",
                                  args.stormlib or originals / "tools" / "stormlib" / "StormLib.dll")
            else:
                path = next((p for p in (folder / "cardxml0.unity3d", folder / "Win" / "cardxml0.unity3d", folder / "cards.unity3d") if p.is_file()), None)
            if path is None:
                raise FileNotFoundError(version)
            cards = pc_snapshot(path, wanted, version, UnityPy)
            snapshots.append({"build": version, "platform": "Windows", "cards": cards})
            print(f"Read {version}: {len(cards)} Korean API cards", flush=True)
    by_version = {}
    folders = sorted((p for p in args.snapshots.iterdir() if p.is_dir() and re.match(r"\d+\.", p.name) and int(p.name.split(".")[0]) < 20), key=lambda p: (version_key(p.name.split("__")[0]), p.name))
    for folder in folders:
        version = folder.name.split("__")[0]
        cards = ios_snapshot(folder / "카드 원본 정보.jsonl", wanted)
        previous = by_version.get(version)
        if previous is not None:
            if cards != previous["cards"]:
                diff = [cid for cid in cards.keys() | previous["cards"].keys() if cards.get(cid) != previous["cards"].get(cid)]
                raise ValueError(f"Conflicting archives for {version}: {diff}")
            previous["archives"].append(folder.name)
            continue
        snapshot = {"build": version, "platform": "iOS", "archives": [folder.name], "cards": cards}
        by_version[version] = snapshot
        snapshots.append(snapshot)
        print(f"Read {version}: {len(cards)} Korean API cards", flush=True)
    # Eligibility comes from native Basic/Expert1 set tags, not an ID prefix.
    eligible = {cid for s in snapshots for cid, c in s["cards"].items() if set(c["sets"]) & {2, 3}}
    transitions = {}
    for s in snapshots:
        changed = 0
        for cid in sorted(eligible):
            card = s["cards"].get(cid)
            if card is None or "text" not in card:
                continue
            items = transitions.setdefault(cid, [])
            value = {"name": card["name"], "rawText": card["text"]}
            if items and all(items[-1][k] == value[k] for k in value):
                items[-1]["lastObservedBuild"] = s["build"]
                continue
            items.append({"build": s["build"], "platform": s["platform"], **value,
                          "sets": card["sets"], "lastObservedBuild": s["build"]})
            changed += 1
        if changed:
            print(f"Transitions {s['build']}: {changed}", flush=True)
    output = {"locale": "koKR", "before": "2021-03-26", "eligibleCards": len(eligible),
              "snapshots": [{k: v for k, v in s.items() if k != "cards"} for s in snapshots],
              "cards": transitions}
    args.output.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"cards": len(eligible), "distinctSnapshots": len(snapshots), "archives": len(folders),
                      "transitionsIncludingInitial": sum(len(v) for v in transitions.values()), "output": str(args.output)}, ensure_ascii=False))


def active(revision, day):
    return revision.get("from", "0001-01-01") <= day < revision.get("before", "9999-12-31")


def expected_values(cid, observation, day, policy):
    values = {"name": observation["name"], "text": rendered(observation["rawText"])}
    for override in policy.get("displayOverrides", {}).get(cid, []):
        if active(override, day):
            values.update(override["changes"])
    for gap in policy.get("uncertainIntervals", {}).get(cid, []):
        if active(gap, day):
            for field in gap["fields"]:
                values.pop(field, None)
    return values


def history_for(cid, card, sequence, policy):
    dates = policy["patchDates"]
    start, end = dates[sequence[0]["build"]], policy["before"]
    generated = []
    for index, observation in enumerate(sequence):
        left = dates[observation["build"]]
        right = dates[sequence[index + 1]["build"]] if index + 1 < len(sequence) else end
        if not start <= left < right <= end:
            raise ValueError(f"{cid}: unordered patch dates {left}, {right}")
        boundaries = {left, right}
        for rule in policy.get("displayOverrides", {}).get(cid, []) + policy.get("uncertainIntervals", {}).get(cid, []):
            boundaries.update(rule[k] for k in ("from", "before") if left < rule[k] < right)
        ordered = sorted(boundaries)
        for a, b in zip(ordered, ordered[1:]):
            values = expected_values(cid, observation, a, policy)
            changes = {key: value for key, value in values.items() if value != card.get(key, "")}
            if not changes:
                continue
            if generated and generated[-1]["before"] == a and generated[-1]["changes"] == changes:
                generated[-1]["before"] = b
            else:
                generated.append({"from": a, "before": b, "changes": changes})
    retained = []
    for revision in card.get("history", []):
        old_left, old_right = revision.get("from", "0001-01-01"), revision.get("before", "9999-12-31")
        if old_right <= start or old_left >= end:
            retained.append(copy.deepcopy(revision))
            continue
        other = {k: v for k, v in revision["changes"].items() if k not in ("name", "text")}
        if other:
            retained.append({**revision, "changes": other})
        names = {k: v for k, v in revision["changes"].items() if k in ("name", "text")}
        if names:
            if old_left < start:
                retained.append({**revision, "before": start, "changes": names})
            if old_right > end:
                retained.append({**revision, "from": end, "changes": names})
    return sorted(retained + generated, key=lambda r: (r.get("from", ""), r.get("before", "9999"), tuple(sorted(r["changes"]))))


def import_audit(args):
    audit, policy = read_json(args.audit), read_json(args.policy)
    if audit["locale"] != "koKR" or policy["timezone"] != "Asia/Seoul" or audit["before"] != policy["before"]:
        raise ValueError("Unexpected locale or historical boundary")
    updates, rule_count = [], 0
    for cid, sequence in sorted(audit["cards"].items()):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", cid) or not sequence:
            raise ValueError(f"Invalid card identity or observations: {cid}")
        path = ROOT / "data" / (cid + ".json")
        original = read_json(path)
        document = copy.deepcopy(original)
        if document["card"]["id"] != cid:
            raise ValueError(f"Card ID mismatch: {cid}")
        document["card"]["history"] = history_for(cid, document["card"], sequence, policy)
        previous = {(o["build"], o["platform"]): o for o in document.get("historicalTextObservations", [])}
        for observation in sequence:
            key = observation["build"], observation["platform"]
            existing = previous.get(key, {})
            if "rawText" in existing and existing["rawText"] != observation["rawText"]:
                raise ValueError(f"{cid}/{key}: existing source observation disagrees")
            # This is the display interval's start, not a claim about the exact
            # iOS rollout time (or the unresolved 3749 cutover).
            previous[key] = {**existing, **observation, "displayFromKst": policy["patchDates"][observation["build"]]}
            previous[key].pop("patchDateKst", None)
        document["historicalTextObservations"] = sorted(previous.values(), key=lambda o: (0 if o["platform"] == "Windows" else 1, version_key(o["build"])))
        for gap in policy.get("uncertainIntervals", {}).get(cid, []):
            unresolved = document.setdefault("unresolvedHistoricalTextDates", [])
            if not any(g.get("from") == gap["from"] and g.get("before") == gap["before"] for g in unresolved):
                unresolved.append({**gap, "reason": "The 3749 patch cutover in Korea is unresolved within these dates; no dated value is assigned for the affected field.",
                                   "olderBuild": "1.0.0.3664", "newerBuild": "1.0.0.3749"})
        rule_count += len(document["card"]["history"])
        text = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        if document != original:
            updates.append((path, text))
    # Reconciliation is complete before the first canonical file is touched.
    if args.apply:
        for path, text in updates:
            temporary = path.with_suffix(".json.tmp")
            try:
                with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                    stream.write(text)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
    print(json.dumps({"comparedCards": len(audit["cards"]), "changedFiles": len(updates),
                      "historyRules": rule_count, "applied": args.apply}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshots", type=Path)
    parser.add_argument("--beta", type=Path)
    parser.add_argument("--unitypy", type=Path)
    parser.add_argument("--mpq", type=Path)
    parser.add_argument("--stormlib", type=Path)
    parser.add_argument("--output", type=Path, help="Temporary compact audit; remove after import")
    parser.add_argument("--audit", type=Path, help="Import previously extracted transitions")
    parser.add_argument("--policy", type=Path, default=ROOT / "tools" / "original-text-patches.json")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.audit:
        import_audit(args)
    elif args.snapshots and args.output:
        scan(args)
    else:
        parser.error("Supply --audit, or --snapshots and --output")
