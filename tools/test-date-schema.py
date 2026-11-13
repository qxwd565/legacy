#!/usr/bin/env python3
"""All-card boundary, losslessness, type/presence and aggregate regressions."""
from __future__ import annotations
import copy
import hashlib
import json
import subprocess
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from date_schema import (SPECS, REMOVE, apply, delta, fold, load, project,
                         read_card, resolve, validate_timeline, UncertainHistory, has_unverified_native_mapping)
ROOT=Path(__file__).resolve().parents[1]


def require_source_commit(root, commit):
    result=subprocess.run(['git','cat-file','-e',commit+':data'],cwd=root,capture_output=True)
    if result.returncode:
        raise RuntimeError('Pinned migration source commit unavailable: '+commit+
                           '. Fetch full history (checkout fetch-depth: 0) or explicitly fetch this commit; preservation checks cannot be skipped.')


def independent_expected(meta, day):
    raw=copy.deepcopy(meta['originalSource']['card'])
    if meta.get('nativeIdentityVerification'):
        assert not has_unverified_native_mapping(meta)
        approved=meta['currentCatalog']
        for field in ('dbfId','rarity','race','races','text'):
            if field in approved: raw[field]=copy.deepcopy(approved[field])
    for event in raw.get('patches',[]):
        # Keep originalSource immutable, but replay North American beta patch
        # 4217 on its agreed KST day rather than the Korean region rollout.
        effective = '2013-12-11' if event['date'] == '2013-12-12' else event['date']
        # This unused-now recruit was retired before the Draenei minion-type rollout.
        # Its installed-client 31.0 tag is evidence, not a playable card change.
        if raw['id'] == 'CS2_101t6' and event['date'] == '2024-10-30':
            continue
        if day is None or effective <= day:
            raw.update(copy.deepcopy(event['changes']))
    result={k:copy.deepcopy(v) for k,v in raw.items() if k in SPECS}
    kind=raw['type']
    # Independently recognized source encoding: 11 legacy weapon entries had
    # native tag45 durability stored as health, not canonical durability=0.
    if meta.get('legacyWeaponEncoding'):
        assert kind=='WEAPON' and raw['durability']==0
        result['durability']=raw['health']
    if raw['id']=='EX1_323':
        if day is not None and day<'2021-03-26':
            result.update(type='MINION',attack=3,health=15,races=['DEMON'],race='악마')
            result.pop('heroPowerDbfId',None);kind='MINION'
        else:
            result.update(type='HERO',armor=5,heroPowerDbfId=1178)
            result.pop('races',None);result.pop('race',None)
    keep={'MINION':{'cost','attack','health'},'SPELL':{'cost'},
          'WEAPON':{'cost','attack','durability'},'HERO_POWER':{'cost'},
          'HERO':{'cost','armor'} if raw.get('collectible') else {'health'}}[kind]
    for key in {'cost','attack','health','durability','armor'}-keep:result.pop(key,None)
    for field,empty in (('race',''),('races',[]),('spellSchool','')):
        if result.get(field)!=None and result.get(field)==empty:result.pop(field,None)
    if result.get('heroPowerDbfId') in (None,0):result.pop('heroPowerDbfId',None)
    return result


def reverse(record, day):
    if record['releaseStatus']=='verified' and day<record['releasedAt']:return None
    state=copy.deepcopy(record['current']);state.pop('art',None)
    matches=[r for r in record['history'] if r.get('from','0001-01-01')<=day<r.get('before','9999-12-31')]
    # The compiler emits disjoint intervals.
    assert len(matches)<=1
    for rev in matches:state=apply(state,rev['changes'])
    return state


def fixtures():
    states=[
        {'id':'TEST','type':'MINION','cost':1,'attack':0,'health':3,'text':'Taunt','mechanics':['TAUNT']},
        {'id':'TEST','type':'SPELL','cost':0,'text':'','mechanics':[]},
        {'id':'TEST','type':'WEAPON','cost':0,'attack':1,'durability':0,'text':''},
        {'id':'TEST','type':'HERO','cost':0,'armor':5,'text':''},
        {'id':'TEST','type':'LOCATION','cost':1,'durability':2,'text':''},
        {'id':'TEST','type':'HERO_POWER','cost':0,'text':''},
        {'id':'TEST','type':'ENCHANTMENT','text':'','effectData':{'amount':0},'explicitNull':None},
    ]
    timeline={};previous={}
    for i,state in enumerate(states,1):
        timeline[f'2020-01-0{i}']=delta(previous,state);previous=state
    validate_timeline(timeline)
    assert fold(timeline,'2019-12-31') is None
    for i,state in enumerate(states,1):assert fold(timeline,f'2020-01-0{i}')==state
    assert 'attack' not in fold(timeline,'2020-01-02')
    assert fold(timeline,'2020-01-01')['attack']==0
    assert fold(timeline,'2020-01-02')['text']==''
    assert fold(timeline,'2020-01-07')['explicitNull'] is None
    assert apply({'x':None},{})=={'x':None}
    assert apply({'x':None},{REMOVE:['x']})=={}
    for before,after in ((False,0),(True,1),({'nested':[False,{'x':True}]},{'nested':[0,{'x':1}]})):
        patch=delta({'effect':before},{'effect':after})
        assert patch=={'effect':after} and patch
        assert apply({'effect':before},patch,validate=True)=={'effect':after}
    assert project({'id':'BASE','type':'HERO','health':30,'attack':0,'armor':0},native_tags=[{'id':45,'value':30}])=={'id':'BASE','type':'HERO','health':30}
    assert project({'id':'EN','type':'ENCHANTMENT','attack':0,'text':''})['attack']==0
    effect={'id':'EN','type':'ENCHANTMENT','effectData':{'amount':0},'text':'','actualZero':0,'nullableEffect':None}
    assert project(effect,gameplay_fields={'effectData','actualZero','nullableEffect'})==effect
    try:project(effect)
    except ValueError:pass
    else:raise AssertionError('Unclassified effect fields silently dropped or backdated')
    raw={'id':'RAW','type':'SPELL','cost':0,'nativeSetId':1635,'installed':True,
         'techLevel':0,'battlegroundsNormalDbfId':0,'isBattlegroundsBuddy':False,
         'nativeTags':[{'id':1720,'value':1}],'releasedAt':'2013-08-17','releaseStatus':'estimated'}
    assert project(raw)=={'id':'RAW','type':'SPELL','cost':0}
    for race in ('DEMON','BEAST'):
        spell={'id':'CHOICE','type':'SPELL','cost':0,'text':'','race':race,'races':[race]}
        assert project(spell)==spell
    assert project({'id':'NO','type':'SPELL','cost':0,'race':'','races':[],'spellSchool':''})=={'id':'NO','type':'SPELL','cost':0}
    # Attribute loss creates explicit removal, never a future empty placeholder.
    before=project({'id':'RACE','type':'MINION','race':'BEAST','races':['BEAST'],'cost':1,'attack':1,'health':1})
    after=project({'id':'RACE','type':'MINION','race':'','races':[],'cost':1,'attack':1,'health':1})
    assert delta(before,after)=={REMOVE:['race','races']}
    for bad in ({'2020-02-30':states[0]}, {'2020-01-01':states[0],'2020-01-02':{'attack':0}}, {'2020-01-01':states[0],'2020-01-02':{REMOVE:['missing']}}, {'2020-01-01':states[0],'2020-01-02':{REMOVE:['attack'],'attack':1}}):
        try:validate_timeline(bad)
        except ValueError:pass
        else:raise AssertionError('Invalid/redundant timeline accepted')
    for change in ({'id':'OTHER'}, {REMOVE:['id']}, {'dbfId':456}, {REMOVE:['dbfId']}):
        bad={'2020-01-01':dict(states[0],dbfId=123),'2020-01-02':change}
        try:validate_timeline(bad)
        except ValueError:pass
        else:raise AssertionError('Card identity mutation accepted')
    for field,value in (('nativeTags',[]),('installed',True),('nativeSetId',1635),('techLevel',0),('set','LEGACY')):
        try:validate_timeline({'2020-01-01':states[0],'2020-01-02':{field:value}})
        except ValueError:pass
        else:raise AssertionError('Current-only field dated directly: '+field)


def main():
    fixtures()
    current={c['id']:c for c in load(ROOT/'cards-date.json')['cards']}
    rendered={c['id']:c for c in load(ROOT/'render-date.json')['cards']}
    histories=load(ROOT/'history-date.json')['cards']
    taxonomy=load(ROOT/'taxonomy-history.json')
    assert len(current)==len(rendered)==len(histories)==615
    checks=0;statuses=Counter();types=Counter();raw_checks=0;differences=[]
    for commit in {load(p)['sourceCommit'] for p in (ROOT/'metadata').glob('*.json')}:
        require_source_commit(ROOT,commit)
    for path in sorted((ROOT/'data').glob('*.json')):
        cid=path.stem;timeline,meta=read_card(ROOT,cid)
        validate_timeline(timeline);statuses[meta['release']['status']]+=1
        original=meta['originalSource'];raw_checks+=1
        original_bytes=subprocess.check_output(['git','show',f"{meta['sourceCommit']}:data/{path.name}"],cwd=ROOT)
        archived = json.loads(original_bytes)
        assert archived == original, (cid, 'raw loss')
        assert original['card']['id']==cid
        assert meta['currentCatalog']['id']==current[cid]['id']
        assert meta['currentCatalog']['dbfId']==current[cid]['dbfId']
        assert meta['currentCatalog'].get('art')==current[cid].get('art')
        for field in ('relatedDbfIds','nativeTags','portrait','artist','flavor','watermark','set'):
            assert meta['currentCatalog'].get(field)==current[cid].get(field),(cid,field,'current metadata changed')
        assert current[cid]['releaseStatus']==meta['currentCatalog']['releaseStatus']
        assert current[cid]['releasedAt']==meta['currentCatalog']['releasedAt']
        assert not any('nativeTags' in changes or 'nativeRawText' in changes for changes in timeline.values())
        days=set(timeline)
        days.update(e['date'] for e in original['card'].get('patches',[]))
        for d in list(days):
            days.add((date.fromisoformat(d)-timedelta(days=1)).isoformat())
            days.add((date.fromisoformat(d)+timedelta(days=1)).isoformat())
        days.add('2026-11-09')
        unmapped=has_unverified_native_mapping(meta)
        for day in sorted(days):
            actual=resolve(timeline,meta,day)
            if meta['release']['status']=='verified' and day<meta['release']['date']:
                assert actual is None
            else:
                expected=independent_expected(meta,day); actual_other={k:v for k,v in actual.items() if k!='text'}; expected_other={k:v for k,v in expected.items() if k!='text'}; assert actual_other==expected_other,(cid,day,actual_other,expected_other)
            if not unmapped:
                assert reverse(histories[str(current[cid]['dbfId'])],day)==actual,(cid,day,'transport mismatch')
            checks+=1
        try:resolve(timeline,meta,'2020-01-01',strict=True)
        except UncertainHistory:pass
        else:raise AssertionError('Strict mode silently promoted partial baseline')
        if timeline:
            state={};roundtrip={}
            for day,change in timeline.items():
                nxt=apply(state,change);roundtrip[day]=delta(state,nxt);state=nxt
                for race in state.get('races',[]):
                    introduced=taxonomy.get('cardTypeIntroductions',{}).get(cid,{}).get(race,taxonomy['minionTypes'].get(race))
                    assert not introduced or introduced<=day,(cid,day,race,'future race backdated')
                school=state.get('spellSchool')
                introduced=taxonomy['spellSchools'].get(school)
                assert not introduced or introduced<=day,(cid,day,school,'future school backdated')
            assert roundtrip==timeline
            assert fold(timeline,(date.fromisoformat(next(iter(timeline)))-timedelta(days=1)).isoformat()) is None
        if not unmapped:
            latest=resolve(timeline,meta)
            assert {k:v for k,v in current[cid].items() if k in SPECS}==latest
        # Every generated current row is type-safe, including the separately
        # retained catalogue row that has no proven archived DBF mapping.
        validate_timeline({'2026-11-09':{k:v for k,v in current[cid].items() if k in SPECS}})
        types[current[cid]['type']]+=1
        old=meta['currentCatalog']
        diff=delta(old,current[cid])
        if diff:differences.append({'id':cid,'changes':diff})
        for change in timeline.values():
            if 'text' in change:
                assert '\n' not in change['text'] and '\\n' not in change['text'] and '/n' not in change['text']
    # Historical existence must start on the verified first normal-play day.
    releases = {**{f'HERO_{n:02d}bp2': '2015-08-25' for n in range(1, 10)},
                'HERO_10bp': '2020-04-08', 'HERO_10bp2': '2020-04-08'}
    for cid, first_day in releases.items():
        history, evidence = read_card(ROOT, cid)
        assert list(history)[0] == first_day and '2013-08-17' not in history, cid
        assert evidence['release'] == {'date': first_day, 'status': 'verified'}, cid
        assert resolve(history, evidence, (date.fromisoformat(first_day) - timedelta(days=1)).isoformat()) is None, cid
        assert history[first_day]['text'], (cid, 'first-playable text missing')
    # A later Legacy ID must inherit its first actually playable Core-era debut.
    for cid, day in ({f'LEG_RLK_{suffix}' : '2022-12-07' for suffix in
                      ('034','039','071','077','079','082','085','101','115',
                       '125','224','226','705','710','715','744','752','753')}
                     | {'LEG_TTN_908': '2023-07-26'}).items():
        timeline, meta = read_card(ROOT,cid)
        assert list(timeline)[0] == day and timeline[day].get('text'), (cid, list(timeline))
        assert meta['release'] == {'date':day, 'status':'verified'}, cid
        assert resolve(timeline,meta,(date.fromisoformat(day)-timedelta(days=1)).isoformat()) is None, cid
        assert not any(k < day for k in timeline), cid
    # Korean official live release of ten 14.6 Basic/Classic replacements and OG_047 choice tokens.
    for cid, day in ({f'EX1_{n}': '2019-07-02' for n in range(183, 193)}
                      | {'OG_047a': '2016-04-27', 'OG_047b': '2016-04-27'}).items():
        history, proof = read_card(ROOT, cid)
        assert list(history)[0] == day and proof['release'] == {'date':day, 'status':'verified'}, cid
        assert resolve(history,proof,(date.fromisoformat(day)-timedelta(days=1)).isoformat()) is None, cid
    # Strength Totem was not present in initial 2013 Shaman hero-power pool.
    totem, proof = read_card(ROOT, 'CS2_058')
    assert list(totem)==['2021-03-31'] and proof['release']=={'date':'2021-03-31','status':'verified'}
    assert resolve(totem,proof,'2021-03-30') is None
    for cid in ('LEG_CS3_001','LEG_CS3_013','LEG_CS3_015','LEG_CS3_017',
                'LEG_CS3_028','LEG_CS3_031','LEG_CS3_032','LEG_CS3_033',
                'LEG_CS3_034','LEG_CS3_036','LEG_CS3_037'):
        history, evidence = read_card(ROOT,cid)
        assert list(history)[0]=='2021-03-31' and evidence['release']=={'date':'2021-03-31','status':'verified'},cid
        assert resolve(history,evidence,'2021-03-30') is None,cid
    # Six recruit art variants only became summonable on Korea 29.0 date,
    # even though they appeared in installed 28.0 client files.
    for cid in ('CS2_101t2','CS2_101t3','CS2_101t4',
                'CS2_101t5','CS2_101t7','CS2_101t8'):
        card, evidence = read_card(ROOT, cid)
        assert list(card)==['2024-03-12'] and evidence['release']=={'date':'2024-03-12','status':'verified'},cid
        assert resolve(card,evidence,'2024-03-11') is None,cid
    # Draenei recruit was playable with the 29.0 visual recruits before
    # retirement just before Draenei became a distinct minion tribe.
    draenei, draenei_meta = read_card(ROOT, 'CS2_101t6')
    assert list(draenei)==['2024-03-12']
    assert draenei_meta['release']=={'date':'2024-03-12','status':'verified'}
    assert 'undated' not in draenei_meta
    assert resolve(draenei,draenei_meta,'2024-03-11') is None
    assert resolve(draenei,draenei_meta,'2024-03-12')['id']=='CS2_101t6'
    assert draenei_meta['appearanceRetirement']['exactDate']=='2024-03-12'
    assert draenei_meta['appearanceRetirement']['dateConfidence']=='provisional'
    assert draenei_meta['appearanceRetirement']['beforeDate']=='2024-10-30'
    assert draenei_meta['originalSource']['card']['patches'][0]['date']=='2024-10-30'
    assert draenei_meta['releaseEvidence']['nativeDraeneiTagIsNotGameplayHistory']
    assert current['CS2_101t6']['releasedAt']=='2024-03-12'
    # Four Warcraft Rumble cards were accessible in Core on Korea March 12,
    # eight days BEFORE the new expansion release on March 20.
    for cid in ('TOY_100','TOY_101','TOY_102','TOY_103'):
        history, proof = read_card(ROOT,cid)
        assert list(history)==['2024-03-12'],cid
        assert proof['release']=={'date':'2024-03-12','status':'verified'},cid
        assert resolve(history,proof,'2024-03-11') is None,cid
        assert resolve(history,proof,'2024-03-12') is not None,cid
    # Gelbin and all five normal-play invention/Chicken tokens became
    # accessible with the beta, not on earlier alpha client-import days.
    for cid in ('EX1_112','Mekka1','Mekka2','Mekka3','Mekka4','Mekka4t'):
        timeline, proof = read_card(ROOT,cid)
        assert list(timeline)[0]=='2013-08-17',cid
        assert proof['release']=={'date':'2013-08-17','status':'verified'},cid
        assert proof['releaseEvidence']['date']=='2013-08-17',cid
        assert resolve(timeline,proof,'2013-08-16') is None,cid
        assert resolve(timeline,proof,'2013-08-17')['id']==cid,cid
        assert proof['originalSource']['card']['releaseStatus']=='estimated',cid
    # Beta Reward cards were available through their collection achievements,
    # rather than only after a later 2013 achievement-description update.
    for cid in ('EX1_062','NEW1_016'):
        timeline, proof = read_card(ROOT,cid)
        assert list(timeline)[0]=='2013-08-17',cid
        assert proof['release']=={'date':'2013-08-17','status':'verified'},cid
        assert proof['releaseEvidence']['date']=='2013-08-17',cid
        assert proof['currentCatalog']['releaseStatus']=='verified',cid
        assert resolve(timeline,proof,'2013-08-16') is None,cid
        assert resolve(timeline,proof,'2013-08-17')['id']==cid,cid
    # All original class starting Hero Powers already existed in live beta play.
    for cid in (f'HERO_{n:02d}bp' for n in range(1,10)):
        timeline, proof = read_card(ROOT,cid)
        assert list(timeline)[0]=='2013-08-17',cid
        assert proof['release']=={'date':'2013-08-17','status':'verified'},cid
        assert proof['currentCatalog']['releaseStatus']=='verified',cid
        assert proof['releaseEvidence']['date']=='2013-08-17',cid
        assert resolve(timeline,proof,'2013-08-16') is None,cid
        assert resolve(timeline,proof,'2013-08-17')['id']==cid,cid
    # Skin-only hero powers are excluded entirely from canonical sources,
    # art resources and every generated API transport.
    assert 'CS2_102_H3' not in current
    assert 'CS2_102_H3' not in rendered
    assert '58799' not in histories
    assert not (ROOT/'data/CS2_102_H3.json').exists()
    assert not (ROOT/'metadata/CS2_102_H3.json').exists()
    assert not (ROOT/'art/CS2_102_H3.png').exists()
    assert not (ROOT/'golden/cards/CS2_102_H3.json').exists()
    original, original_meta = read_card(ROOT, 'HERO_01bp')
    assert list(original)[0]=='2013-08-17'
    assert original_meta['releaseEvidence']['originalHeroPowerIdIn2013']=='CS2_102'
    assert original_meta['release']=={'date':'2013-08-17','status':'verified'}
    assert resolve(original,original_meta,'2013-08-17')['dbfId']==725
    # Original 3664 live-beta deck IDs, cross-checked to the historical
    # Korean CardText archive. US Aug 16 evening is Aug 17 in Korea.
    beta_deck_ids = ('NEW1_010','EX1_012','EX1_100','NEW1_029','EX1_557','EX1_590','EX1_014','EX1_083','EX1_005','EX1_002','NEW1_024','EX1_558','EX1_116','EX1_110','NEW1_040','EX1_016','EX1_577','EX1_614','EX1_249','NEW1_038','EX1_298','EX1_561','EX1_563','EX1_560','EX1_562','EX1_572','NEW1_030')
    beta_archive = load(ROOT/'original/1.0.0.3664-descriptions.json')['cards']
    for cid in beta_deck_ids:
        card, evidence = read_card(ROOT,cid)
        assert list(card)[0]=='2013-08-17' and card['2013-08-17']['collectible'],cid
        assert beta_archive[cid]['status']=='available',cid
        assert evidence['release']=={'date':'2013-08-17','status':'verified'},cid
        assert evidence['releaseEvidence']['deckTimestampKST'].startswith('2013-08-17'),cid
        assert resolve(card,evidence,'2013-08-16') is None,cid
    # Contemporaneous Priest/Hunter day-one beta decks (16-17 Aug 2013 US)
    # cross-checked against every original 3664 CardTextInHand card ID.
    new_beta_deck_ids = ('EX1_621','EX1_332','CS1_130','CS1_129','CS2_003','CS2_004','CS2_236','EX1_341','DS1_233','EX1_622','CS2_234','EX1_625','EX1_339','CS1_112','EX1_334','EX1_591','EX1_626','EX1_345','EX1_624','EX1_350','CS1_113','EX1_623','EX1_091','DS1_185','EX1_549','EX1_544','CS2_084','EX1_610','EX1_533','EX1_554','EX1_609','NEW1_031','EX1_617','EX1_536','DS1_183','EX1_537','DS1_175','EX1_611','EX1_531','CS2_237','EX1_539','EX1_538','DS1_070','DS1_178','EX1_543')
    beta_archive_cards = load(ROOT/'original/1.0.0.3664-descriptions.json')['cards']
    for cid in new_beta_deck_ids:
        history, proof = read_card(ROOT,cid)
        assert list(history)[0]=='2013-08-17' and history['2013-08-17']['collectible'],cid
        assert proof['release']=={'date':'2013-08-17','status':'verified'},cid
        assert beta_archive_cards[cid]['status']=='available',cid
        assert proof['releaseEvidence']['deckEffectiveDayKST']=='2013-08-17',cid
        assert resolve(history,proof,'2013-08-16') is None,cid
    # Live day-one closed-beta decks: Druid, Shaman, Paladin, Warlock, Rogue.
    # All recorded last-updates convert to Aug 17 2013 in Asia/Seoul.
    beta_first_day_ids = ('EX1_169','CS2_005','EX1_578','CS2_013','CS2_011','EX1_158','EX1_570','EX1_571','EX1_164','NEW1_007','EX1_573','CS2_008','CS2_009','EX1_154','CS2_007','EX1_166','EX1_165','EX1_178','EX1_251','EX1_238','CS2_038','CS2_053','EX1_241','EX1_243','CS2_045','EX1_248','EX1_246','EX1_259','EX1_258','CS2_046','EX1_567','EX1_250','CS2_042','EX1_360','EX1_130','CS2_093','CS2_094','CS2_097','EX1_354','EX1_383','CS2_063','EX1_319','EX1_302','EX1_596','CS2_062','CS2_057','EX1_303','EX1_309','EX1_315','EX1_320','CS2_072','EX1_145','EX1_144','CS2_074','CS2_075','EX1_126','CS2_233','EX1_581','EX1_278','EX1_613','EX1_133','CS2_080','CS2_077')
    archived_3664 = load(ROOT/'original/1.0.0.3664-descriptions.json')['cards']
    for cid in beta_first_day_ids:
        history, source = read_card(ROOT,cid)
        assert list(history)[0]=='2013-08-17' and history['2013-08-17']['collectible'],cid
        assert source['release']=={'date':'2013-08-17','status':'verified'},cid
        assert archived_3664[cid]['status'] in ('available','no-description-tag'),cid
        assert source['releaseEvidence']['deckLastUpdatedKST'].startswith('2013-08-17'),cid
        assert resolve(history,source,'2013-08-16') is None,cid
    # Original beta-generated child card IDs. Each parent existed in a
    # first-day playable 3664 deck and its original text created the child.
    token_parent_pairs=(('DREAM_01','EX1_572'),('DREAM_02','EX1_572'),('DREAM_03','EX1_572'),('DREAM_04','EX1_572'),('DREAM_05','EX1_572'),('EX1_110t','EX1_110'),('EX1_tk29','EX1_083'),('EX1_tk28','EX1_083'),('NEW1_040t','NEW1_040'),('EX1_014t','EX1_014'),('NEW1_032','NEW1_031'),('NEW1_033','NEW1_031'),('NEW1_034','NEW1_031'),('EX1_383t','EX1_383'),('EX1_573t','EX1_573'),('EX1_554t','EX1_554'),('EX1_130a','EX1_130'),('EX1_158t','EX1_158'),('EX1_165a','EX1_165'),('EX1_165b','EX1_165'),('EX1_165t1','EX1_165'),('EX1_165t2','EX1_165'),('EX1_625t','EX1_625'),('EX1_625t2','EX1_625'),('EX1_345t','EX1_345'),('EX1_614t','EX1_614'))
    archived_children=load(ROOT/'original/1.0.0.3664-descriptions.json')['cards']
    for cid, pid in token_parent_pairs:
        token, meta = read_card(ROOT,cid)
        parent, parent_meta = read_card(ROOT,pid)
        assert meta['release']=={'date':'2013-08-17','status':'verified'},cid
        assert parent_meta['release']=={'date':'2013-08-17','status':'verified'},pid
        assert list(token)[0]=='2013-08-17' and not token['2013-08-17']['collectible'],cid
        assert archived_children[cid]['status'] in ('available','no-description-tag'),cid
        assert meta['releaseEvidence']['parentCardId']==pid,cid
        assert resolve(token,meta,'2013-08-16') is None,cid
    # EX1_538t originally had a different ENCHANTMENT role; parent
    # availability alone is insufficient to verify its modern Hound form.
    hound, hound_meta = read_card(ROOT,'EX1_538t')
    assert hound_meta['release']['status']=='estimated'
    assert hound['2013-12-11']['name']=='사냥개'
    # Four contemporaneous live beta (build 3664) decks confirm 46 more first-use IDs.
    continued_beta_deck_ids = ('EX1_287','EX1_295','EX1_612','tt_010','EX1_559','EX1_279','EX1_080','NEW1_021','EX1_055','NEW1_020','EX1_584','EX1_093','NEW1_026','EX1_620','EX1_277','CS2_031','NEW1_012','CS2_025','EX1_608','CS2_023','CS2_026','EX1_294','EX1_594','CS2_029','CS2_022','CS2_033','NEW1_023','EX1_049','CS2_197','CS2_227','EX1_283','EX1_390','EX1_096','CS2_125','CS2_124','EX1_043','EX1_284','NEW1_041','CS2_150','EX1_162','EX1_160','EX1_155','CS2_012','EX1_173','NEW1_008','EX1_017')
    for cid in continued_beta_deck_ids:
        history, proof = read_card(ROOT, cid)
        assert list(history)[0]=='2013-08-17' and history['2013-08-17']['collectible'], cid
        assert proof['release']=={'date':'2013-08-17','status':'verified'}, cid
        assert proof['currentCatalog']['releaseStatus']=='verified', cid
        assert archived_3664[cid]['status']=='available', cid
        assert proof['releaseEvidence']['deckEffectiveDayKST']=='2013-08-17', cid
        assert resolve(history,proof,'2013-08-16') is None, cid
    # First-day children: independent playable parent deck + archived original
    # Korean effect text + the same original native child ID.
    continued_beta_child_pairs = (('EX1_160t','EX1_160'),('CS2_tk1','CS2_022'),('NEW1_026t','NEW1_026'),('EX1_155a','EX1_155'),('EX1_155b','EX1_155'),('EX1_160a','EX1_160'),('EX1_160b','EX1_160'),('NEW1_008a','NEW1_008'),('NEW1_008b','NEW1_008'))
    for cid, pid in continued_beta_child_pairs:
        history, meta = read_card(ROOT, cid)
        parent_history, parent_meta = read_card(ROOT, pid)
        assert meta['release']=={'date':'2013-08-17','status':'verified'}, cid
        assert parent_meta['release']=={'date':'2013-08-17','status':'verified'}, pid
        assert meta['currentCatalog']['releaseStatus']=='verified', cid
        assert meta['releaseEvidence']['parentCardId']==pid, cid
        assert archived_3664[cid]['status'] in ('available','no-description-tag'), cid
        assert list(history)[0]=='2013-08-17' and not history['2013-08-17']['collectible'], cid
        assert list(parent_history)[0]=='2013-08-17' and parent_history['2013-08-17']['collectible'], pid
        assert resolve(history,meta,'2013-08-16') is None, cid
    # More verified 2013 first-day generated children, including starting hero powers.
    verified_beta_child_pairs = (('EX1_finkle','EX1_577'),('CS2_101t','HERO_04bp'),('CS2_050','HERO_02bp'),('CS2_051','HERO_02bp'),('CS2_052','HERO_02bp'),('NEW1_009','HERO_02bp'),('CS2_082','HERO_03bp'),('EX1_tk9','EX1_571'),('hexfrog','EX1_246'),('EX1_154a','EX1_154'),('EX1_154b','EX1_154'),('EX1_166a','EX1_166'),('EX1_166b','EX1_166'),('EX1_178a','EX1_178'),('EX1_178b','EX1_178'),('EX1_164a','EX1_164'),('EX1_164b','EX1_164'),('EX1_573a','EX1_573'),('EX1_573b','EX1_573'),('NEW1_007a','NEW1_007'),('NEW1_007b','NEW1_007'))
    for cid,pid in verified_beta_child_pairs:
        history, meta = read_card(ROOT,cid)
        parent_history, parent_meta = read_card(ROOT,pid)
        assert meta['release']=={'date':'2013-08-17','status':'verified'},cid
        assert parent_meta['release']=={'date':'2013-08-17','status':'verified'},pid
        assert meta['currentCatalog']['releaseStatus']=='verified',cid
        assert meta['releaseEvidence']['parentCardId']==pid,cid
        assert archived_3664[cid]['status'] in ('available','no-description-tag'),cid
        assert list(history)[0]=='2013-08-17' and not history['2013-08-17']['collectible'],cid
        assert list(parent_history)[0]=='2013-08-17',pid
        assert resolve(history,meta,'2013-08-16') is None,cid
    # First-day community beta deck builder + independent native 3664 cards.
    additional_beta_day_deck_ids = ('EX1_607','EX1_409','EX1_400','EX1_402','EX1_392','CS2_114','CS2_105','CS2_104','CS2_103','EX1_408','CS2_112','EX1_407','EX1_411','EX1_009','EX1_004','EX1_393','NEW1_018','NEW1_019','NEW1_037','CS2_181','CS2_122','CS2_108','EX1_391','CS2_106','EX1_398','EX1_606','CS2_231','CS2_146','EX1_015','DS1_055','EX1_410','NEW1_036','NEW1_011','CS2_171','EX1_059','CS2_121','CS2_203','CS2_118','NEW1_022','EX1_399','EX1_593','CS2_221','CS2_162','EX1_032','EX1_414','CS2_131','EX1_586','EX1_105','EX1_023','EX1_097','EX1_067','EX1_564','EX1_011','EX1_604','EX1_084','EX1_045','EX1_102','CS2_087','EX1_619','CS2_089','EX1_382','EX1_349','EX1_366','CS2_092','EX1_355','EX1_384','CS2_088','EX1_371','CS2_091','EX1_362','CS2_161','EX1_025','EX1_008','CS2_168','EX1_506','EX1_509','EX1_007','CS2_147','EX1_046','EX1_365','EX1_583','CS2_169','EX1_020','EX1_033','EX1_363','EX1_132','EX1_136','EX1_379','EX1_507','CS2_151','EX1_001','EX1_131','EX1_137','EX1_134','EX1_129','CS2_076','EX1_095','CS2_119','CS1_042','EX1_050','EX1_085','EX1_582','NEW1_005','NEW1_004','EX1_128','NEW1_014','CS2_073','EX1_124','EX1_522','NEW1_027','CS2_059','EX1_301','EX1_313','EX1_310','CS2_065','CS2_064','EX1_312','EX1_317','EX1_316','EX1_304','EX1_306','EX1_308','NEW1_003','EX1_048','EX1_597','EX1_029','EX1_405','EX1_082','CS2_117','EX1_556','EX1_595','CS2_226','EX1_412','EX1_323','DS1_188','EX1_534','EX1_396','CS2_172','CS2_120','EX1_170','CS2_141','CS2_127','DS1_184','CS2_201','CS2_182','EX1_089','EX1_103','CS2_041','EX1_244','EX1_245','CS2_037','CS2_039','EX1_565','EX1_575','EX1_587','EX1_021','EX1_076','CS2_235','EX1_335','EX1_275','EX1_289','CS2_024','CS2_028','CS2_155','CS2_032','EX1_274','CS2_179','CS2_186','tt_004','CS2_213','CS2_188','EX1_616','CS2_173','CS2_187','EX1_019','EX1_028')
    for cid in additional_beta_day_deck_ids:
        history, meta = read_card(ROOT, cid)
        assert list(history)[0]=='2013-08-17' and history['2013-08-17']['collectible'], cid
        assert meta['release']=={'date':'2013-08-17','status':'verified'}, cid
        assert meta['currentCatalog']['releaseStatus']=='verified', cid
        assert archived_3664[cid]['status'] in ('available','no-description-tag'), cid
        assert meta['releaseEvidence']['deckEffectiveDayKST']=='2013-08-17', cid
        assert resolve(history,meta,'2013-08-16') is None, cid
    assert statuses=={'estimated':41,'verified':574}
    expected_tokens = {'CS3_002t': ('2021-03-31', 'CS3_002'), 'RLK_077t': ('2022-12-07', 'LEG_RLK_077'), 'RLK_085t': ('2022-12-07', 'LEG_RLK_085'), 'RLK_226t': ('2022-12-07', 'LEG_RLK_226'), 'RLK_705t': ('2022-12-07', 'LEG_RLK_705'), 'RLK_907t': ('2022-12-07', 'LEG_RLK_752')}
    for token_id, (release_day, parent_id) in expected_tokens.items():
        token, token_meta = read_card(ROOT, token_id)
        assert list(token) == [release_day] and token[release_day]['collectible'] is False
        assert token_meta['release'] == {'date': release_day, 'status': 'verified'}
        assert token_meta['originalSource']['historicalTokenSources']['parents'] == [parent_id]
        assert token[release_day]['text'] == token_meta['originalSource']['card']['text']
        assert resolve(token, token_meta, (date.fromisoformat(release_day)-timedelta(days=1)).isoformat()) is None
    combined, combined_meta = read_card(ROOT, 'OG_044a')
    assert combined_meta['release'] == {'date': '2016-04-27', 'status': 'verified'}
    assert combined_meta['originalSource']['historicalTokenSources']['parents'] == ['EX1_165']
    assert resolve(combined, combined_meta, '2016-04-26') is None
    assert resolve(combined, combined_meta, '2016-04-27')['text'] == '<b>돌진</b><br></br><b>도발</b>'
    assert resolve(combined, combined_meta, '2021-03-26')['text'] == '<b>속공</b><br></br><b>도발</b>'
    assert resolve(combined, combined_meta, '2023-04-05')['attack'] == 7
    for token_id in ('skele21','ds1_whelptoken'):
        token, token_meta=read_card(ROOT,token_id)
        assert next(iter(token)) == '2013-08-17' and token['2013-08-17']['text'] == ''
        assert token_meta['release'] == {'date':'2013-08-17','status':'verified'}
    assert current['ds1_whelptoken']['dbfId']==54
    proof=load(ROOT/'metadata/ds1_whelptoken.json')['nativeIdentityVerification']
    assert proof['cardId']=='ds1_whelptoken' and proof['dbfId']==54 and proof['ipaVersion']=='37.0.255790'
    assert proof['archiveSha256']=='5196f322ce5423a0af64f13db0a000bfd167e4dee60eea0965eb1909e8441adc'
    jar,meta=read_card(ROOT,'EX1_323')
    assert resolve(jar,meta,'2021-03-25')['attack']==3
    assert resolve(jar,meta,'2021-03-26')['armor']==5
    assert 'health' not in resolve(jar,meta,'2021-03-26')
    assert current['EX1_323h']['health']==15 and 'armor' not in current['EX1_323h']
    assert current['DS1_188']['durability']==2 and current['EX1_567']['durability']==8
    assert current['EX1_411']['durability']==1
    assert (ROOT/'history-date.json').stat().st_size<=524288
    # Source relations and assets are byte-for-byte untouched by this migration.
    changed=subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).splitlines()
    assert not any(p.startswith(('art/','golden/')) for p in changed)
    report={'result':'pass','sourceCards':615,'currentCards':615,'datedSources':615,
            'undatedSources':[],'sourceReleaseStatus':dict(statuses),
            'boundarySnapshots':checks,'losslessSourceChecks':raw_checks,
            'runtimeTypes':dict(types),'syntheticTypes':['MINION','SPELL','WEAPON','HERO','LOCATION','HERO_POWER','ENCHANTMENT'],
            'strict':'opt-in; all incompletely verified baselines refused, no confidence promotion',
            'historyBytes':(ROOT/'history-date.json').stat().st_size,
            'intentionalCurrentProjectionChanges':differences}
    from date_schema import put
    put(ROOT/'tools/date-schema-validation.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='intentionalCurrentProjectionChanges'},ensure_ascii=False))


if __name__=='__main__':main()
