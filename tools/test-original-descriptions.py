"""Check native observations, history boundaries and untouched current data.

Run after import-original-descriptions.py and build-api.py. The temporary audit
is intentionally external to the repository and can be deleted after this test.
"""
import argparse
import copy
from datetime import date, timedelta
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def git_json(ref, path):
    return json.loads(subprocess.check_output(["git", "show", f"{ref}:{path}"], cwd=ROOT))


def value_at(card, field, day):
    value = card.get(field, "")
    for revision in card.get("history", []):
        if revision.get("from", "0001-01-01") <= day < revision.get("before", "9999-12-31"):
            value = revision["changes"].get(field, value)
    return value


def rendered(text):
    return text.replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")


def main(args):
    audit = read(args.audit)
    policy = read(ROOT / "tools/original-text-patches.json")
    before_catalog = git_json(args.baseline, "cards.json")
    assert read(ROOT / "cards.json") == before_catalog, "Current catalog changed"
    archive = subprocess.check_output(["git", "archive", args.baseline, "data"], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        originals = {Path(m.name).stem: json.load(tar.extractfile(m)) for m in tar if m.isfile() and m.name.endswith(".json")}
    rendered_cards = {c["id"]: c for c in read(ROOT / "render.json")["cards"]}
    old_rendered = {c["id"]: c for c in git_json(args.baseline, "render.json")["cards"]}
    assert set(rendered_cards) == set(old_rendered)
    compatibility = read(ROOT / "history.json")["cards"]
    checks = observations = 0
    for cid, old in originals.items():
        new = read(ROOT / "data" / (cid + ".json"))
        # This task owns only dated visible text, its observations and explicit
        # uncertainty. Current stats, tags, artwork and archived assets are exact.
        left, right = copy.deepcopy(old), copy.deepcopy(new)
        for d in (left, right):
            d["card"].pop("history", None)
            d.pop("historicalTextObservations", None)
            d.pop("unresolvedHistoricalTextDates", None)
        assert left == right, (cid, "non-history data changed")
        if cid not in audit["cards"]:
            assert old == new, (cid, "out-of-scope card changed")
        if cid in rendered_cards:
            a, b = copy.deepcopy(old_rendered[cid]), copy.deepcopy(rendered_cards[cid])
            a.pop("history", None)
            b.pop("history", None)
            assert a == b, (cid, "current renderer fields changed")
            if new["card"].get("dbfId") is not None:
                revisions = new["card"].get("history", [])
                assert rendered_cards[cid].get("history", []) == revisions
                if revisions:
                    compat = compatibility[str(new["card"]["dbfId"])]
                    assert compat["id"] == cid and compat["history"] == revisions
        fields = {k for c in (old["card"], new["card"]) for rev in c.get("history", []) for k in rev["changes"]}
        days = {"2013-01-01", "2021-03-25", "2021-03-26", "2026-11-08"}
        for c in (old["card"], new["card"]):
            for rev in c.get("history", []):
                for k in ("from", "before"):
                    if k in rev:
                        days.add(rev[k])
                        days.add((date.fromisoformat(rev[k]) - timedelta(days=1)).isoformat())
        for day in days:
            for field in fields:
                if field not in ("name", "text") or day >= policy["before"]:
                    assert value_at(old["card"], field, day) == value_at(new["card"], field, day), (cid, field, day)
                    checks += 1
        by_field = {field: [] for field in ("name", "text")}
        for rev in new["card"].get("history", []):
            for field in by_field:
                if field in rev["changes"]:
                    by_field[field].append((rev.get("from", "0001-01-01"), rev.get("before", "9999-12-31")))
        for field, intervals in by_field.items():
            intervals.sort()
            for a, b in zip(intervals, intervals[1:]):
                assert a[1] <= b[0], (cid, field, "overlapping intervals", a, b)
        seq = audit["cards"].get(cid, [])
        stored = {(o["build"], o["platform"]): o for o in new.get("historicalTextObservations", [])}
        for i, observation in enumerate(seq):
            assert stored[observation["build"], observation["platform"]]["rawText"] == observation["rawText"]
            start = policy["patchDates"][observation["build"]]
            end = policy["patchDates"][seq[i + 1]["build"]] if i + 1 < len(seq) else policy["before"]
            sample_days = {start, (date.fromisoformat(end) - timedelta(days=1)).isoformat()}
            for day in sample_days:
                expected = {"name": observation["name"], "text": rendered(observation["rawText"])}
                for override in policy["displayOverrides"].get(cid, []):
                    if override["from"] <= day < override["before"]:
                        expected.update(override["changes"])
                for gap in policy["uncertainIntervals"].get(cid, []):
                    if gap["from"] <= day < gap["before"]:
                        for field in gap["fields"]:
                            expected.pop(field, None)
                for field, value in expected.items():
                    assert value_at(new["card"], field, day) == value, (cid, observation["build"], day, field)
                    observations += 1
    # Human-reviewed regressions: no fallback to today's text during 2014-2021.
    backstab = rendered_cards["CS2_072"]
    assert value_at(backstab, "text", "2016-01-01") == "피해를 입지 않은 하수인 하나에게 피해를 $2 줍니다."
    assert value_at(backstab, "text", "2017-08-09") == "피해를 받지 않은 하수인 하나에게 피해를 $2 줍니다."
    assert value_at(backstab, "text", "2018-10-03") == "피해를 받지 않은 하수인에게 피해를 $2 줍니다."
    engineer = rendered_cards["EX1_015"]
    assert value_at(engineer, "text", "2016-08-09") == "<b>전투의 함성:</b> 카드를 1장 뽑습니다."
    assert value_at(engineer, "text", "2016-08-10") == "<b>전투의 함성:</b><br>카드를 1장 뽑습니다."
    spec = importlib.util.spec_from_file_location("builder", ROOT / "tools/build-api.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    with tempfile.TemporaryDirectory(prefix="hsplus-history-test-") as folder:
        path = Path(folder) / "token.json"
        path.write_text(json.dumps({"card": {"id": "token", "dbfId": None}, "apiAvailability": "standalone historical source; no mapping"}), encoding="utf-8")
        assert builder.read_catalog_source(path, {"id": "token", "dbfId": 4}) is None
        path.write_text(json.dumps({"card": {"id": "token", "dbfId": 3}}), encoding="utf-8")
        try:
            builder.read_catalog_source(path, {"id": "token", "dbfId": 4})
        except ValueError:
            pass
        else:
            raise AssertionError("Genuine DBF collision was accepted")
    print(json.dumps({"catalogCardsUnchanged": len(before_catalog["cards"]), "scannedCards": len(audit["cards"]),
                      "datedSourceChecks": observations, "unchangedFieldChecks": checks, "result": "passed"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--baseline", required=True)
    main(parser.parse_args())
