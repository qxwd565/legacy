#!/usr/bin/env python3
"""Normalize display strings only; retain archived and native raw evidence verbatim."""
from __future__ import annotations
import json
import re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
BREAK = re.compile(r'<br\s*/?>\s*(?:</br>)?|\\r\\n|\\n|\\r|\r\n?|\n|/n', re.IGNORECASE)
FIELDS = ('text', 'flavor')

STRAY_AMP = re.compile(r"(?<=[:가-힣])&(?=\\s|<br>)")

def normalize(value):
    if not isinstance(value, str):
        return value
    return STRAY_AMP.sub('', BREAK.sub('<br></br>', value))

def main():
    files = fields = redundant = 0
    for path in sorted((ROOT/'data').glob('*.json')):
        before = path.read_text(encoding='utf-8')
        doc = json.loads(before)
        if "card" not in doc:
            from date_schema import apply, delta, put, validate_timeline
            before_state = {}
            normalized_state = {}
            cleaned = {}
            states_by_kst_day = {}
            for day, change in doc.items():
                before_state = apply(before_state, change)
                # Patch 1.0.0.4217 was deployed in Korea on December 12.
                # Merge the formerly NA-dated December 11 wording with the
                # already-KST-dated December 12 gameplay deltas.
                kst_day = '2013-12-12' if day == '2013-12-11' else day
                states_by_kst_day[kst_day] = dict(before_state)
            for day, state in sorted(states_by_kst_day.items()):
                for field in FIELDS:
                    if field in state:
                        value = normalize(state[field]); fields += value != state[field]; state[field] = value
                diff = delta(normalized_state, state)
                if diff: cleaned[day] = diff
                else: redundant += 1
                normalized_state = state
            validate_timeline(cleaned)
            files += put(path, cleaned)
            continue
        card = doc.get('card', {})
        for field in FIELDS:
            if field in card:
                value = normalize(card[field]); fields += value != card[field]; card[field] = value
        prior = {f:card[f] for f in FIELDS if f in card}
        patches = card.get('patches')
        if isinstance(patches, list):
            cleaned = []
            for patch in patches:
                changes = patch['changes']
                for field in FIELDS:
                    if field not in changes: continue
                    value = normalize(changes[field]); fields += value != changes[field]
                    if field in prior and value == prior[field]:
                        del changes[field]; redundant += 1
                    else:
                        changes[field] = value; prior[field] = value
                if changes: cleaned.append(patch)
            card['patches'] = cleaned
        # Transitional reverse-format records keep their boundaries unchanged.
        for patch in card.get('history', []):
            for field in FIELDS:
                if field in patch.get('changes', {}):
                    old = patch['changes'][field]; patch['changes'][field] = normalize(old)
                    fields += old != patch['changes'][field]
        after = json.dumps(doc, ensure_ascii=False, indent=2)+'\n'
        if before != after:
            path.write_text(after, encoding='utf-8', newline='\n'); files += 1
    print(json.dumps({'changedFiles':files,'normalizedDisplayFields':fields,'formatOnlyRedundantChangesRemoved':redundant}))

if __name__ == '__main__': main()
