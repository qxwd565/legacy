#!/usr/bin/env python3
"""One-time lossless Legacy wrapper -> date-map migration, safe to rerun."""
from pathlib import Path
import json
import subprocess
from date_schema import load, put, migrate_document, validate_timeline
ROOT = Path(__file__).resolve().parents[1]


def main():
    catalog = load(ROOT/"cards.json")
    if catalog.get("set") != "legacy":
        raise ValueError("Legacy only")
    current = {c["id"]:c for c in catalog["cards"]}
    commit = subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    changed = 0
    for path in sorted((ROOT/"data").glob("*.json")):
        document = load(path)
        if "card" not in document:
            validate_timeline(document)
            if not (ROOT/"metadata"/path.name).exists():
                raise ValueError(f"Missing metadata for {path.name}")
            continue
        sidecar = ROOT/"metadata"/path.name
        if sidecar.exists():
            raise ValueError(f"Refusing to overwrite migration evidence: {sidecar}")
        timeline, meta = migrate_document(document, current.get(path.stem), commit)
        put(sidecar,meta)
        put(path,timeline)
        changed += 1
    print(json.dumps({"migrated":changed,"format":"date-map-1"}))


if __name__ == "__main__":
    main()
