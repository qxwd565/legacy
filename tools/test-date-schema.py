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
    assert len(current)==len(rendered)==len(histories)==616
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
    assert statuses=={'estimated':522,'verified':94}
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
    report={'result':'pass','sourceCards':616,'currentCards':616,'datedSources':616,
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
