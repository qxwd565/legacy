#!/usr/bin/env python3
"""Normalize display strings only; retain archived and native raw evidence verbatim."""
from __future__ import annotations
import json
import re
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
BREAK = re.compile(r'<br\s*/?>\s*(?:</br>)?|\\r\\n|\\n|\\r|\r\n?|\n|/n', re.IGNORECASE)
FIELDS = ('text', 'flavor')

def normalize(value):
    return BREAK.sub('<br></br>', value) if isinstance(value, str) else value

def main():
    files = fields = redundant = 0
    for path in sorted((ROOT/'data').glob('*.json')):
        before = path.read_text(encoding='utf-8')
        doc = json.loads(before)
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
