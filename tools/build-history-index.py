#!/usr/bin/env python3
"""Build a small, server-side card-history index from API cards.json.

Source of truth: data/<card id>.json -> cards.json -> history.json.
No card corrections are authored in the WordPress plugin.
"""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
catalog = json.loads((root / "cards.json").read_text(encoding="utf-8"))
if catalog.get("schema") != 1 or not isinstance(catalog.get("cards"), list):
    raise ValueError("Unexpected cards.json shape")
history = {}
for card in catalog["cards"]:
    if not isinstance(card, dict):
        continue
    versions = card.get("history")
    if not isinstance(versions, list) or not versions:
        continue
    if not isinstance(card.get("dbfId"), int) or card["dbfId"] < 1:
        continue
    if not isinstance(card.get("id"), str):
        continue
    history[str(card["dbfId"])] = {
        "id": card["id"],
        "history": versions,
    }
result = {"schema": 1, "set": catalog["set"], "cards": history}
target = root / "history.json"
content = json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n"
if not target.exists() or target.read_text(encoding="utf-8") != content:
    target.write_text(content, encoding="utf-8")
print(json.dumps({"set": catalog["set"], "historyCards": len(history), "bytes": len(content.encode("utf-8"))}))
