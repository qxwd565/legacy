#!/usr/bin/env python3
"""Publish HScard API indexes from canonical per-card JSON.

Source of current card data: cards.json (approved card catalogue).
Source of historical deltas: data/<cardId>.json (card.history).
Never overwrite curated current data with raw client snapshots.


Generated endpoints:
  cards.json   - current cards for WP JSON imports
  render.json  - current cards for the real-time WebGL renderer
  history.json - tiny dated changes index, only cards with history

Do not hand-edit the generated indexes. Do not change cardId/dbfId mappings.
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
    path.write_text(rendered, encoding="utf-8")
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


def main():
    source_path = ROOT / "cards.json"
    catalog = load(source_path)
    if catalog.get("schema") != 1 or not isinstance(catalog.get("cards"), list):
        raise ValueError("Unexpected cards.json schema")
    detailed = ROOT / "data"
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
        if not path.is_file():
            if record.get("history"):
                raise ValueError(f"{cid}: historical data requires {path.name}")
            # Preserve cards that have no detailed source yet.
            record.pop("history", None)
        else:
            data = load(path)
            card = data.get("card") if isinstance(data, dict) else None
            if not isinstance(card, dict) or card.get("id") != cid or card.get("dbfId") != record.get("dbfId"):
                raise ValueError(f"{cid}: source card ID mismatch")
            # Preserve the approved current card catalogue exactly. Individual
            # JSON owns historical changes only until current data is reconciled.
            revisions = read_history(card, cid)
            if revisions:
                history[str(record["dbfId"])] = {"id": cid, "history": revisions}
            elif record.get("history"):
                # Avoid silently discarding previously migrated patches.
                raise ValueError(f"{cid}: history exists in cards.json but not data/{cid}.json")
            record.pop("history", None)
        renderer.append({field: record[field] for field in RENDER_FIELDS if field in record})

    files = {
        "cards.json": catalog,
        "render.json": {"schema": 1, "set": catalog["set"], "cards": renderer},
        "history.json": {"schema": 1, "set": catalog["set"], "cards": history},
    }
    changed = [name for name, value in files.items() if publish(ROOT / name, value)]
    print(json.dumps({
        "set": catalog["set"], "cards": len(renderer),
        "datedCards": len(history),
        "published": changed,
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
