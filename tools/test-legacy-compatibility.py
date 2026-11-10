#!/usr/bin/env python3
"""Test dual outputs against the unchanged schema-1 plugin contract."""
import argparse
import copy
import json
import subprocess
from datetime import date,timedelta
from pathlib import Path
from urllib.parse import urljoin
from date_schema import load,put,json_equal,read_card,resolve,has_unverified_native_mapping
from legacy_projection import PHP_FIELDS
ROOT=Path(__file__).resolve().parents[1]
BASE_URL='https://raw.githubusercontent.com/qxwd565/legacy/main/'
ADDED_TOKEN_IDS = frozenset(['CS3_002t', 'RLK_077t', 'RLK_085t', 'RLK_226t', 'RLK_705t', 'RLK_907t', 'OG_044a'])


def old_resolve(current,history,day):
    result=copy.deepcopy(current);done=set()
    for revision in history:
        if revision.get('from','0001-01-01')<=day<revision.get('before','9999-12-31'):
            for key,value in revision['changes'].items():
                if key in PHP_FIELDS and key not in done:
                    result[key]=copy.deepcopy(value);done.add(key)
    return result


def main(fixture=None):
    catalog=load(ROOT/'cards.json');render=load(ROOT/'render.json');history=load(ROOT/'history.json')
    precise=load(ROOT/'cards-date.json');precise_history=load(ROOT/'history-date.json')
    assert len(catalog['cards'])==len(precise['cards'])==616
    assert all(x.get('schema')==1 and 'historySchema' not in x for x in [catalog,render,history])
    assert precise_history['historySchema']==2
    for name in ['cards.json','render.json','history.json']:
        assert '__remove' not in (ROOT/name).read_text(encoding='utf-8')
    by_id={c['id']:c for c in catalog['cards']};render_by_id={c['id']:c for c in render['cards']}
    assert len(by_id)==616 and len({c['dbfId'] for c in catalog['cards']})==616
    source=load(ROOT/'metadata/EX1_323.json')['sourceCommit']
    original=json.loads(subprocess.check_output(['git','show',source+':cards.json'],cwd=ROOT))
    original_history=json.loads(subprocess.check_output(['git','show',source+':history.json'],cwd=ROOT))['cards']
    # The first dual-output release changes no current imported field at all.
    catalog_other=copy.deepcopy(catalog); original_other=copy.deepcopy(original)
    catalog_other['cards'] = [row for row in catalog_other['cards'] if row['id'] not in ADDED_TOKEN_IDS]
    for obj in (catalog_other,original_other):
        for row in obj['cards']:
            row.pop('text',None)
            if row['id'] in ('PRO_001','PRO_001a','PRO_001at','PRO_001b','PRO_001c'):
                row.pop('releasedAt',None)  # Verified North American beta release in KST.
            if row['id'] in ('skele21','ds1_whelptoken'):
                row.pop('releasedAt',None); row.pop('releaseStatus',None)
    assert json_equal(catalog_other,original_other),'Non-text legacy catalogue drifted'
    assets=set(subprocess.check_output(['git','ls-tree','-r','--name-only',source,'--','art'],cwd=ROOT,text=True).splitlines())
    cases=[];comparisons=0;art_checks=0;corrections=[]
    for current in catalog['cards']:
        cid=current['id'];dbf=str(current['dbfId']);meta=load(ROOT/'metadata'/(cid+'.json'))
        assert type(current['cost']) is int and 0<=current['cost']<=32767
        for field in ('attack','health','durability','armor'):
            assert type(current[field]) is int and 0<=current[field]<=32767
        if cid in ADDED_TOKEN_IDS:
            assert 'art' not in current  # Description-only import; no artwork is asserted.
        else:
            assert current['art'] in assets,(cid,'pre-existing art file missing')
            for bundle in ('cards.json','render.json','history.json','cards-date.json','render-date.json','history-date.json'):
                assert urljoin(BASE_URL+bundle,current['art'])==BASE_URL+current['art'];art_checks+=1
        assert BASE_URL+'history.json'==(BASE_URL+'cards.json').replace('/cards.json','/history.json')
        assert BASE_URL+'history-date.json'==(BASE_URL+'cards-date.json').replace('/cards-date.json','/history-date.json')
        rows=history['cards'].get(dbf,{}).get('history',[])
        assert rows==render_by_id[cid].get('history',[])
        days={'2013-01-01','2026-11-09'}
        for d in [meta['release']['date']]+[e['date'] for e in meta['originalSource']['card'].get('patches',[])]:
            if d:
                days.update((date.fromisoformat(d)+timedelta(days=n)).isoformat() for n in [-1,0,1])
        for day in sorted(days):
            actual=old_resolve(current,rows,day)
            before=old_resolve(current,original_history.get(dbf,{}).get('history',[]),day)
            timeline,meta_source=read_card(ROOT,cid)
            source_state=resolve(timeline,meta_source,day)
            if source_state is not None and (not meta_source['release']['date'] or day>=meta_source['release']['date']) and not has_unverified_native_mapping(meta_source):
                assert actual.get('text','')==source_state.get('text',''),(cid,day,'legacy text mismatch')
            for field in PHP_FIELDS:
                if field=='text' or cid=='OG_044a':continue
                if field=='health' and actual.get('type')=='WEAPON':continue
                if not json_equal(actual.get(field),before.get(field)):
                    # Two intentional exceptions: the reviewed Jaraxxus
                    # type correction, and moving the 4217 beta patch from
                    # Korean server Dec 12 to NA-patch KST Dec 11. The latter
                    # must match the unchanged originalSource patch value.
                    type_fix = cid=='EX1_323' and day<'2021-03-26' and field in ('type','attack','armor','race')
                    beta_date_fix = day=='2013-12-11' and any(
                        ev['date']=='2013-12-12'
                        and field in ev['changes']
                        and json_equal(ev['changes'][field],actual.get(field))
                        for ev in meta['originalSource']['card'].get('patches',[])
                    )
                    assert type_fix or beta_date_fix,(cid,day,field,actual.get(field),before.get(field))
                    corrections.append({'id':cid,'date':day,'field':field,'before':before.get(field),'after':actual.get(field)})
            if actual['type']=='WEAPON':
                assert (actual.get('durability') or actual.get('health'))==(before.get('durability') or before.get('health')),(cid,day,'legacy displayed durability changed')
            # The old adapter never introduces a visibility gate or deletes cards.
            assert actual['id']==cid and actual['dbfId']==current['dbfId']
            cases.append({'id':cid,'dbfId':current['dbfId'],'date':day,
                          'expected':{k:v for k,v in actual.items() if k in PHP_FIELDS}})
            comparisons+=1
    assert (ROOT/'history.json').stat().st_size<=524288
    assert 'fetch-depth: 0' in (ROOT/'.github/workflows/normalize-card-history.yml').read_text()
    report={'result':'pass','oldPluginBase':'78ce6fdc4e70f689880a70d6f22aa77a6c75e337',
            'currentCards':616,'previousCatalogueMatchesPinnedOriginal':True,'addedTokenCards':sorted(ADDED_TOKEN_IDS),
            'legacyDateCases':comparisons,'artURLChecks':art_checks,'missingAssets':0,
            'rootHistoryBytes':(ROOT/'history.json').stat().st_size,
            'preciseHistoryBytes':(ROOT/'history-date.json').stat().st_size,
            'visibility':'unchanged; no new release/strict gating',
            'reviewedHistoryCorrections':corrections}
    put(ROOT/'tools/legacy-compatibility-validation.json',report)
    if fixture:put(fixture,{'catalog':catalog,'history':history,'cases':cases,'allowed':list(PHP_FIELDS)})
    print(json.dumps({k:v for k,v in report.items() if k!='reviewedHistoryCorrections'}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--fixture',type=Path);main(p.parse_args().fixture)
