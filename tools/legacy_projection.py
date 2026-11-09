"""Explicit lossy schema-1 boundary for the unchanged installed plugin.

Never write this projection back to canonical data or confidence sidecars.
"""
from __future__ import annotations
import copy
from date_schema import SPECS, apply, json_equal, resolve

LEGACY_FIELDS = ("name", "type", "cardClass", "classes", "rarity", "collectible",
                 "cost", "attack", "health", "durability", "armor", "text",
                 "races", "race", "spellSchool", "mechanics", "legacyArt")
RENDER_FIELDS = ("id", "dbfId", "name", "type", "cardClass", "rarity", "collectible",
                 "cost", "text", "attack", "health", "durability", "armor", "art",
                 "races", "race", "spellSchool", "set", "nativeTags", "mechanics",
                 "watermark", "classes", "releasedAt", "releaseStatus")
PHP_FIELDS = ("name", "cost", "text", "attack", "health", "durability", "armor",
              "race", "spellSchool", "art", "legacyArt", "type", "cardClass",
              "rarity", "watermark", "mechanics", "nativeTags")


def project_legacy(state, meta):
    """Represent exact state using documented old wire sentinels only."""
    original = meta['currentCatalog']
    managed = set(meta.get('canonicalFields', [])) | set(original)
    result = {k:copy.deepcopy(v) for k,v in state.items() if k in LEGACY_FIELDS}
    for key in ('cost','attack','health','durability','armor'):
        if key not in result:
            # The old renderer/exporter used health as the weapon's mirror.
            # Preserve that legacy representation only at this output boundary.
            if key == 'health' and state.get('type') == 'WEAPON':
                result[key] = state.get('durability',0)
            elif key == 'health' and state.get('type') == 'HERO' and meta.get('heroRole') == 'playable-card':
                result[key] = original.get('health',0)
            else:
                result[key] = 0
    for key,empty in (('text',''),('race',''),('races',[]),('spellSchool',''),('mechanics',[]),('classes',[])):
        if key not in result and (key == 'text' or key in managed):
            result[key] = copy.deepcopy(empty)
    if meta.get('legacyWeaponEncoding') and state.get('type')=='WEAPON':
        result['health']=state['durability']
        result['durability']=0
    # Old JSON always has these required common fields in this Legacy corpus.
    # Do not invent unsupported data for a different expansion silently.
    for field in ('name','type','cardClass','rarity','collectible'):
        if field not in result:
            raise ValueError(f"Legacy compatibility cannot supply missing {field}: {state.get('id')}")
    return result


def compile_legacy(timeline, meta, precise_record):
    record = copy.deepcopy(meta['currentCatalog'])
    unmapped = meta['originalSource'].get('apiAvailability','').startswith('standalone historical source;')
    if unmapped:
        # This catalogue row still has no proven relationship to the native
        # historical token. Keep its approved import behavior, never link it.
        return record, []
    latest = resolve(timeline,meta)
    current = project_legacy(latest,meta)
    for field in LEGACY_FIELDS:
        if field == 'legacyArt':
            continue  # old current catalogue never advertised this flag
        if field in current:
            if field in ('race','races') and field not in record and not current[field]:
                continue
            record[field] = copy.deepcopy(current[field])
    record['releasedAt'] = meta['release']['date']
    record['releaseStatus'] = meta['release']['status']
    if timeline:
        points=list(timeline.items())
        start,state=points[0]
        events=[{'date':d,'changes':c} for d,c in points[1:]]
    else:
        start=None
        state=copy.deepcopy(meta['undated']['baseline'])
        events=meta['undated']['patches']
    revisions=[]
    for event in events:
        old=project_legacy(state,meta)
        changes={k:copy.deepcopy(v) for k,v in old.items()
                 if k not in current or not json_equal(v,current[k])}
        # Every old field is representable or normalized to the legacy
        # sentinel. No __remove operation reaches an old parser.
        if changes:
            revision={'before':event['date'],'changes':changes}
            if start:revision['from']=start
            revisions.append(revision)
        state=apply(state,event['changes'])
        start=event['date']
    return record,revisions


def loss_report():
    return {
        'schema':1,'scope':'root compatibility endpoints only; canonical and -date outputs remain precise',
        'source':'data date maps + metadata; regenerated on every build, not frozen copies',
        'legacyConsumer':'qxwd565/HSdeck-plugin 78ce6fdc4e70f689880a70d6f22aa77a6c75e337 (unmodified)',
        'rules':[
            'Missing numeric fields use the prior integer-zero wire convention; cost is always present for old imports.',
            'Weapon health mirrors durability only in this compatibility projection. Playable hero client health retains its legacy current-only value.',
            'Absent race/spell school becomes an empty string, absent races/mechanics/classes an empty array when that field belongs to the card.',
            'Reverse intervals contain ordinary changed values, never __remove, authoritative state or historySchema:2.',
            'All original current catalogue IDs, DBFs, current nativeTags, relationship and artwork metadata are retained.',
            'Root intervals retain inclusive from/exclusive before boundaries, including the old before-release fallback behavior. No new hiding or strict gating is enabled.',
        ],
        'limitations':[
            'Old consumers cannot distinguish absent numeric fields from zero, or faithfully implement arbitrary attribute removal.',
            'The old PHP history whitelist does not apply races/classes/collectible/heroPowerDbfId or arbitrary effect data; precise information remains in canonical/-date outputs.',
            'Installed current nativeTags can still leak into historical browser state. This cannot be fixed by API shape alone without the postponed plugin change.',
            'The existing HERO_POWER/ENCHANTMENT frame restrictions, database zero storage and zero-durability renderer fallback remain unchanged.',
            'Historical corrections work relative to imported current DB data; no live import or reconfiguration is performed here.',
        ],
        'preciseEndpoints':{'cards':'cards-date.json','render':'render-date.json','history':'history-date.json'},
        'siblingRule':'Explicit -date consumers map cards-date.json to render-date.json and history-date.json. Existing configured cards.json sources remain unchanged.',
        'artRule':'All six bundles are siblings at the repository root; art/<ID> paths retain their original base directory.',
    }
