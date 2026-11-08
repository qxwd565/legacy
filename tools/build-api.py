#!/usr/bin/env python3
"""Publish HScard API indexes from canonical per-card JSON.

Source of current card data: cards.json (approved card catalogue).
Source of historical deltas: data/<cardId>.json (card.history).
Never overwrite curated current data with raw client snapshots.
Card release dates are loaded from release-policy.json (Asia/Seoul).


Generated endpoints:
  cards.json   - current cards for WP JSON imports
  render.json  - current cards + sparse history for WebGL and WordPress
  history.json - temporary compatibility endpoint for installed 7.12.10 sites

Do not hand-edit the generated indexes. Do not change cardId/dbfId mappings.
The separate history endpoint is retained only until old WordPress plugins are upgraded.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDER_FIELDS = (
    "id", "dbfId", "name", "type", "cardClass", "rarity", "collectible",
    "cost", "text", "attack", "health", "durability", "armor", "art",
    "races", "race", "spellSchool", "set", "nativeTags", "mechanics",
    "watermark", "classes",
)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def publish(path: Path, value):
    # Runtime catalogues are compact; the editor-facing catalog stays readable.
    if path.name in ("render.json", "history.json"):
        rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
    else:
        rendered = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == rendered:
        return False
    path.write_text(rendered, encoding="utf-8", newline="\n")
    return True


def read_history(card: dict, name: str):
    versions = card.get("history", [])
    if versions is None:
        return []
    if not isinstance(versions, list):
        raise ValueError(f"{name}: history must be an array")
    for rev in versions:
        if not isinstance(rev, dict) or not isinstance(rev.get("changes"), dict):
            raise ValueError(f"{name}: invalid history entry")
        if not rev["changes"] or not any(x in rev for x in ("from", "before")):
            raise ValueError(f"{name}: history has no changes or date boundary")
        if any(k in rev and (not isinstance(rev[k], str) or not DATE_RE.fullmatch(rev[k])) for k in ("from", "before")):
            raise ValueError(f"{name}: invalid history date")
        if all(k in rev for k in ("from", "before")) and rev["from"] >= rev["before"]:
            raise ValueError(f"{name}: invalid history interval")
    return versions


def read_catalog_source(path: Path, record: dict):
    if not path.is_file():
        return None
    data = load(path)
    card = data.get("card") if isinstance(data, dict) else None
    cid = record["id"]
    if not isinstance(card, dict) or card.get("id") != cid:
        raise ValueError(f"{cid}: source card ID mismatch")
    # A separately archived native token is not an asserted DBF mapping. Keep
    # the approved current catalog, but never attach its archived history to
    # a numeric ID or manufacture a DBF ID in the source document.
    if card.get("dbfId") is None and data.get("apiAvailability", "").startswith("standalone historical source;"):
        return None
    if card.get("dbfId") != record.get("dbfId"):
        raise ValueError(f"{cid}: source card ID mismatch")
    return data



def release_for_card(record: dict, policy: dict):
    """Korean-local first playable date; unknown dates are never invented."""
    cid = record["id"]
    rule = policy.get("default", {"date": None, "status": "pending"})
    for prefix in sorted(policy.get("prefixes", {}), key=len, reverse=True):
        if cid.startswith(prefix):
            rule = policy["prefixes"][prefix]
            break
    rule = policy.get("cards", {}).get(cid, rule)
    if not isinstance(rule, dict):
        raise ValueError(f"Invalid release policy for {cid}")
    day = rule.get("date")
    status = rule.get("status", "pending" if day is None else "verified")
    if day is not None:
        if not isinstance(day, str) or not DATE_RE.fullmatch(day):
            raise ValueError(f"{cid}: invalid Korean release date")
        from datetime import date
        date.fromisoformat(day)
    if status not in ("verified", "estimated", "pending"):
        raise ValueError(f"{cid}: invalid release confidence")
    if status == "verified" and not day:
        raise ValueError(f"{cid}: verified date cannot be null")
    return day, status


def main():
    source_path = ROOT / "cards.json"
    catalog = load(source_path)
    if catalog.get("schema") != 1 or not isinstance(catalog.get("cards"), list):
        raise ValueError("Unexpected cards.json schema")
    detailed = ROOT / "data"
    release_policy_path = ROOT / "release-policy.json"
    release_policy = load(release_policy_path) if release_policy_path.exists() else None
    if release_policy is not None and release_policy.get("timezone") != "Asia/Seoul":
        raise ValueError("Release dates must use Korea (Asia/Seoul)")
    release_counts = {"verified": 0, "estimated": 0, "pending": 0}
    changed_individual = 0
    history = {}
    renderer = []
    seen = set()
    for record in catalog["cards"]:
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            raise ValueError("Invalid card in cards.json")
        cid = record["id"]
        if cid in seen:
            raise ValueError(f"Duplicate card ID {cid}")
        seen.add(cid)
        path = detailed / (cid + ".json")
        data = read_catalog_source(path, record)
        revisions = []
        if data is None:
            if record.get("history"):
                raise ValueError(f"{cid}: historical data requires {path.name}")
            # Preserve cards that have no detailed source yet.
            record.pop("history", None)
        else:
            card = data["card"]
            # Preserve the approved current card catalogue exactly. Individual
            # JSON owns historical changes only until current data is reconciled.
            revisions = read_history(card, cid)
            if revisions:
                history[str(record["dbfId"])] = {"id": cid, "history": revisions}
            elif record.get("history"):
                # Avoid silently discarding previously migrated patches.
                raise ValueError(f"{cid}: history exists in cards.json but not data/{cid}.json")
            record.pop("history", None)
        render_card = {field: record[field] for field in RENDER_FIELDS if field in record}
        # A single runtime endpoint: the current card and its sparse dated
        # differences are delivered together. Absence of history means current.
        if data is not None and revisions:
            render_card["history"] = revisions
        if release_policy is not None:
            release_date, release_status = release_for_card(record, release_policy)
            record["releasedAt"] = release_date
            record["releaseStatus"] = release_status
            render_card["releasedAt"] = release_date
            # Consumers must not hide cards based on an estimated release date.
            render_card["releaseStatus"] = release_status
            release_counts[release_status] += 1
            if data is not None:
                card["releasedAt"] = release_date
                card["releaseStatus"] = release_status
                if publish(path, data):
                    changed_individual += 1
        renderer.append(render_card)

    files = {
        "cards.json": catalog,
        "render.json": {"schema": 1, "set": catalog["set"], "cards": renderer},
        "history.json": {"schema": 1, "set": catalog["set"], "cards": history},
    }
    changed = [name for name, value in files.items() if publish(ROOT / name, value)]
    print(json.dumps({
        "set": catalog["set"], "cards": len(renderer),
        "datedCards": len(history),
        "published": changed, "releaseDates": release_counts,
        "individualCardsUpdated": changed_individual,
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
