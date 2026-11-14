#!/usr/bin/env python3
"""Normalize HSdeck card APIs to Legacy's date-keyed gameplay format.

Keep historical evidence in metadata, never invent dates or original stats.
Preflight every card before writing any files.
"""
from __future__ import annotations
import argparse
import copy
from datetime import date
import json
from pathlib import Path
import re
import sys

ROOT = Path.cwd()
DATE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
GAMEPLAY = set('id dbfId name type cardClass classes rarity collectible cost attack health durability armor text races race spellSchool mechanics legacyArt heroPowerDbfId runes'.split())
STATS = {'cost', 'attack', 'health', 'durability', 'armor'}
BREAK = re.compile(r'<br\s*/?>\s*(?:</br>)?|\\r\\n|\\n|\\r|\r\n?|\n|/n', re.I)

def is_day(s):
    if not isinstance(s, str) or not DATE.fullmatch(s):
        return False
    date.fromisoformat(s)
    return True

def clone(v):
    return copy.deepcopy(v)

def equal(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    return type(a) is type(b) and a == b

def apply(state, changes):
    if not isinstance(changes, dict):
        raise ValueError('record must be an object')
    removals = changes.get('__remove', [])
    if (not isinstance(removals, list) or len(set(removals)) != len(removals)
            or any(not isinstance(k, str) or k in changes for k in removals)):
        raise ValueError('invalid __remove')
    out = clone(state)
    for k in removals:
        out.pop(k, None)
    out.update((k, clone(v)) for k, v in changes.items() if k != '__remove')
    return out

def delta(before, after):
    out = {k: clone(v) for k, v in after.items() if k not in before or not equal(before[k], v)}
    removed = sorted(before.keys() - after.keys())
    if removed:
        out['__remove'] = removed
    return out

def project(source):
    state = {k: clone(v) for k, v in source.items() if k in GAMEPLAY}
    kind = state.get('type')
    allowed = {
        'MINION': {'cost', 'attack', 'health'},
        'SPELL': {'cost'},
        'WEAPON': {'cost', 'attack', 'durability'},
        'LOCATION': {'cost', 'durability'},
        'HERO_POWER': {'cost'},
    }
    if kind == 'HERO':
        allowed[kind] = {'cost', 'armor'} if state.get('collectible') else {'health'}
    if kind in allowed:
        for k in STATS - allowed[kind]:
            state.pop(k, None)
    for k, empty in [('race', ''), ('races', []), ('spellSchool', '')]:
        if k in state and state[k] == empty:
            state.pop(k)
    if state.get('heroPowerDbfId') in (None, 0):
        state.pop('heroPowerDbfId', None)
    if isinstance(state.get('text'), str):
        state['text'] = BREAK.sub('<br></br>', state['text'])
    return state

def source_events(raw):
    """Chronological (day, changes, evidence) for the 3 existing API formats."""
    if not isinstance(raw, dict):
        raise ValueError('JSON must be object')
    keys = list(raw)
    if all(is_day(k) for k in keys):
        return [(k, raw[k], {}) for k in sorted(keys)], 'dated'
    if any(is_day(k) for k in keys) and all(is_day(k) or k in ('meta', '_meta', 'schemaVersion') for k in keys):
        return [(k, raw[k], {}) for k in sorted(keys) if is_day(k)], 'dated-with-meta'
    if raw.get('schemaVersion') == 2 and any(is_day(k) for k in keys):
        out = []
        current = raw.get('current') or {}
        for day in sorted(k for k in keys if is_day(k)):
            event = raw[day]
            if not isinstance(event, dict):
                raise ValueError('schema2 event not object')
            changes = event.get('state') if 'state' in event else event.get('changes')
            if not isinstance(changes, dict):
                raise ValueError(day + ' has no state/changes')
            changes = clone(changes)
            if not out:
                for field in ('id', 'dbfId'):
                    if field in current and field not in changes:
                        changes[field] = current[field]
            extras = {k: v for k, v in event.items() if k not in ('state', 'changes')}
            out.append((day, changes, extras))
        return out, 'schema-v2'
    if isinstance(raw.get('timeline'), dict) and isinstance(raw.get('card'), dict):
        timeline = raw['timeline']
        release = timeline.get('releasedAt') or raw['card'].get('releasedAt')
        initial = clone(timeline.get('initialSpec') if isinstance(timeline.get('initialSpec'), dict) else raw['card'])
        for field in ('id', 'dbfId'):
            if field not in initial and field in raw['card']:
                initial[field] = raw['card'][field]
        if not release:
            return [], 'schema-v1-undated'
        out = [(release, initial, {})]
        for p in timeline.get('patches') or []:
            out.append((p['date'], p.get('changes') or {},
                        {k: v for k, v in p.items() if k not in ('date', 'changes')}))
        return sorted(out, key=lambda x: x[0]), 'schema-v1'
    raise ValueError('unrecognized structure: refusing destructive conversion')

def normalize(raw, cid):
    if raw == {}:
        return {}, {}
    events, fmt = source_events(raw)
    if not events:
        if fmt != 'schema-v1-undated':
            raise ValueError('empty history is not an undated source')
        return {}, {
            'sourceFormat': fmt, 'originalSource': raw,
            'undated': {'baseline': raw['timeline'].get('initialSpec'),
                        'patches': raw['timeline'].get('patches', [])},
        }
    if len(events) != len({day for day, _, _ in events}):
        raise ValueError('duplicate dates; no safe way to choose an order')
    current, before, timeline, excluded_by_day = {}, {}, {}, {}
    identity = None
    for day, change, extra in events:
        if not is_day(day):
            raise ValueError('invalid Korean calendar date: ' + repr(day))
        current = apply(current, change)
        state = project(current)
        if state.get('id') != cid or not isinstance(state.get('type'), str):
            raise ValueError(day + ': missing/mismatched card ID or type')
        dbf = state.get('dbfId')
        if dbf is not None and (type(dbf) is not int or dbf <= 0):
            raise ValueError(day + ': invalid DBF ID')
        key = (state['id'], dbf)
        if identity is None:
            identity = key
        elif identity != key:
            raise ValueError(day + ': card ID/DBF identity changed')
        changes = delta(before, state)
        if changes:
            timeline[day] = changes
        before = state
        excluded = {k: clone(v) for k, v in change.items()
                    if k not in GAMEPLAY and k != '__remove'}
        removed = [k for k in change.get('__remove', []) if k not in GAMEPLAY]
        if removed:
            excluded['__remove'] = removed
        if extra:
            excluded['sourceEvent'] = extra
        if excluded:
            excluded_by_day[day] = excluded
    evidence = {}
    if fmt != 'dated':
        evidence.update(sourceFormat=fmt, originalSource=raw)
        if fmt == 'schema-v1' and not isinstance(raw['timeline'].get('initialSpec'), dict):
            evidence['initialSpecMissing'] = True
    if excluded_by_day:
        evidence['datedExcludedFields'] = excluded_by_day
    if not timeline:
        raise ValueError('no dated baseline')
    if list(timeline) != sorted(timeline) or '__remove' in next(iter(timeline.values())):
        raise ValueError('invalid first dated state')
    for day, changes in timeline.items():
        if any(k not in GAMEPLAY | {'__remove'} for k in changes):
            raise ValueError(day + ': unexpected gameplay field')
    original = {}
    for day, changes, _ in events:
        original = apply(original, changes)
        reconstructed = {}
        for d, row in timeline.items():
            if d > day:
                break
            reconstructed = apply(reconstructed, row)
        if not equal(reconstructed, project(original)):
            raise ValueError(day + ': gameplay timeline changed')
    return timeline, evidence

def pretty(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + '\n'

def rewrite_paths(obj, path_map):
    if isinstance(obj, str):
        return path_map.get(obj, obj)
    if isinstance(obj, list):
        return [rewrite_paths(v, path_map) for v in obj]
    if isinstance(obj, dict):
        return {k: rewrite_paths(v, path_map) for k, v in obj.items()}
    return obj

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    root = ROOT
    if not (root / 'data').is_dir():
        raise ValueError('data/ missing')
    catalog = json.loads((root / 'cards.json').read_text(encoding='utf-8'))
    if catalog.get('schema', 1) != 1 or not isinstance(catalog.get('cards'), list):
        raise ValueError('cards.json must match Legacy index schema 1')
    ids = [row.get('id') for row in catalog['cards']]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate card ID in catalog')
    data_files = {p.stem: p for p in (root / 'data').glob('*.json')}
    aggregate_path = data_files.pop('history', None)
    variants = {}
    for key in sorted(list(data_files)):
        if re.fullmatch(r'CAP_405tb[123]_combo_\d{3}', key):
            p = data_files[key]
            doc = json.loads(p.read_text(encoding='utf-8'))
            if (doc.get('schemaVersion') != 1 or
                    not isinstance(doc.get('variantId'), str) or
                    not isinstance(doc.get('combination'), dict) or
                    not isinstance(doc.get('card'), dict) or
                    doc['card'].get('id') not in ids or key in ids):
                raise ValueError(key + ': unexpected pseudo-card variant format')
            variants[key] = data_files.pop(key)
    path_map = {'data/' + key + '.json': 'metadata/variants/' + key + '.json'
                for key in variants}
    if set(ids) != set(data_files):
        raise ValueError('catalog/card ID mismatch: abort instead of dropping cards')
    writes, errors = {}, []
    if aggregate_path:
        raw_history = aggregate_path.read_text(encoding='utf-8')
        # Some repositories have a zero-byte placeholder, not actual evidence.
        if raw_history.strip():
            agg = json.loads(raw_history)
            valid_formats = {(1, 'date-first-delta'), (2, 'date-first-sparse-delta'), (2, 'date-first-delta-v2'), (3, 'date-first-delta-v3')}
            if (not isinstance(agg, dict) or
                    (agg.get('schema'), agg.get('format')) not in valid_formats or
                    not isinstance(agg.get('events'), dict)):
                raise ValueError('unknown data/history.json cannot be relocated')
            evidence_path = root / 'metadata' / 'history-aggregate.json'
            if evidence_path.exists() and json.loads(evidence_path.read_text(encoding='utf-8')) != agg:
                raise ValueError('existing history evidence conflicts; review required')
            writes[evidence_path] = pretty(agg)
    for key, old_path in variants.items():
        new_path = root / 'metadata' / 'variants' / old_path.name
        content = old_path.read_text(encoding='utf-8')
        if new_path.exists() and new_path.read_text(encoding='utf-8') != content:
            raise ValueError(key + ': existing variant metadata conflicts')
        writes[new_path] = content
    if path_map or 'schema' not in catalog:
        updated_catalog = rewrite_paths({'schema': 1, **catalog}, path_map)
        writes[root / 'cards.json'] = pretty(updated_catalog)
    stats = {'scanned': 0, 'normalized': 0, 'metadata': 0, 'wrappers': 0}
    for path in sorted(data_files.values()):
        stats['scanned'] += 1
        try:
            original = json.loads(path.read_text(encoding='utf-8'))
            normalized, extra = normalize(original, path.stem)
            if list(original) != list(normalized) or not equal(original, normalized):
                writes[path] = pretty(normalized)
                stats['normalized'] += 1
            if extra:
                metadata_path = root / 'metadata' / path.name
                existing = (json.loads(metadata_path.read_text(encoding='utf-8'))
                            if metadata_path.exists() else {
                                'schema': 'hscard-date-metadata-1', 'id': path.stem,
                                'timezone': 'Asia/Seoul',
                                'release': {'date': next(iter(normalized), None),
                                            'status': ((original.get('timeline') or {}).get('releaseStatus')
                                                       or (original.get('_meta') or {}).get('releaseStatus')
                                                       or (original.get('card') or {}).get('releaseStatus')
                                                       or 'unverified')},
                                'baselineStatus': ('unverified' if extra.get('initialSpecMissing')
                                                   else 'partially-verified'),
                            })
                if existing.get('id') != path.stem or 'normalization' in existing:
                    raise ValueError('metadata source collision: review required')
                existing['normalization'] = rewrite_paths(extra, path_map)
                writes[metadata_path] = pretty(existing)
                stats['metadata'] += 1
                if extra.get('sourceFormat'):
                    stats['wrappers'] += 1
        except Exception as exc:
            errors.append(path.name + ': ' + str(exc))
    if errors:
        print('\n'.join(errors[:100]), file=sys.stderr)
        raise SystemExit('Aborted without writes: ' + str(len(errors)) + ' cards need review')
    if args.apply:
        for path, content in writes.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists() or path.read_text(encoding='utf-8') != content:
                path.write_text(content, encoding='utf-8', newline='\n')
        if aggregate_path:
            aggregate_path.unlink()
        for old_path in variants.values():
            old_path.unlink()
    print(json.dumps({'mode': 'apply' if args.apply else 'audit',
                      'relocatedHistoryAggregate': bool(aggregate_path),
                      'relocatedVariants': len(variants), **stats}, ensure_ascii=False))

if __name__ == '__main__':
    main()
