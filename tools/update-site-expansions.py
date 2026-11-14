#!/usr/bin/env python3
"""Merge public API repositories' site-set.json into the site release index."""
import datetime
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OWNER = "qxwd565"
REGISTRY = Path(__file__).resolve().parents[1] / "site-expansions.json"
SLUG = re.compile(r"^[a-z][a-z0-9-]{0,78}$")


def download(url, token=""):
    headers = {"User-Agent": "hsdeck-set-index/1.0"}
    if token and "api.github.com" in url:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read())


def valid(record):
    if not isinstance(record, dict):
        return None
    if record.get("schema") != 1 or record.get("timezone") != "Asia/Seoul":
        return None
    name = record.get("name")
    slug = record.get("slug")
    icon = record.get("assetKey", slug)
    date = record.get("releasedAt")
    year = record.get("rotation", "")
    year_slug = record.get("rotationSlug", "")
    if not (isinstance(name, str) and 0 < len(name) <= 80 and
            isinstance(slug, str) and SLUG.fullmatch(slug) and
            isinstance(icon, str) and SLUG.fullmatch(icon) and
            isinstance(date, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) and
            isinstance(year, str) and len(year) <= 70 and
            isinstance(year_slug, str) and (not year_slug or SLUG.fullmatch(year_slug))):
        return None
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        return None
    return {"name": name, "slug": slug, "assetKey": icon,
            "releasedAt": date, "rotation": year, "rotationSlug": year_slug}


def main():
    old = json.loads(REGISTRY.read_text(encoding="utf-8"))
    if old.get("schema") != 1 or old.get("timezone") != "Asia/Seoul":
        raise ValueError("Invalid existing registry")
    sets = {entry["slug"]: entry for entry in old["sets"]}
    updates = 0
    token = os.environ.get("GITHUB_TOKEN", "")
    for page in range(1, 6):
        url = f"https://api.github.com/users/{OWNER}/repos?per_page=100&page={page}"
        repos = download(url, token)
        if not isinstance(repos, list):
            raise ValueError("Invalid repository listing")
        for repo in repos:
            if repo.get("private") or repo.get("archived"):
                continue
            name = urllib.parse.quote(repo["name"], safe="")
            branch = urllib.parse.quote(repo["default_branch"], safe="")
            source = f"https://raw.githubusercontent.com/{OWNER}/{name}/{branch}/site-set.json"
            try:
                data = download(source)
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    print(f"WARNING: {repo['name']}: HTTP {e.code}", file=sys.stderr)
                continue
            except (ValueError, urllib.error.URLError, TimeoutError) as e:
                print(f"WARNING: {repo['name']}: {e}", file=sys.stderr)
                continue
            entry = valid(data)
            if entry is None:
                print(f"WARNING: invalid site-set.json: {repo['name']}", file=sys.stderr)
                continue
            if sets.get(entry["slug"]) != entry:
                sets[entry["slug"]] = entry
                updates += 1
        if len(repos) < 100:
            break

    rows = sorted(sets.values(), key=lambda item: (item["releasedAt"], item["slug"]))
    if len({item["name"] for item in rows}) != len(rows):
        raise ValueError("Duplicate expansion name; not publishing")
    out = json.dumps({"schema": 1, "timezone": "Asia/Seoul", "sets": rows}, ensure_ascii=False, indent=2) + "\n"
    if out != REGISTRY.read_text(encoding="utf-8"):
        REGISTRY.write_text(out, encoding="utf-8")
    print(f"Index valid: {len(rows)}; changed API entries: {updates}")


if __name__ == "__main__":
    main()
