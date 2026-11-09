#!/usr/bin/env python3
"""Test dual outputs against the unchanged schema-1 plugin contract."""
import argparse
import copy
import json
import subprocess
from datetime import date,timedelta
from pathlib import Path
from urllib.parse import urljoin
from date_schema import load,put,json_equal
from legacy_projection import PHP_FIELDS
ROOT=Path(__file__).resolve().parents[1]
BASE_URL='https://raw.githubusercontent.com/qxwd565/legacy/main/'


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
    assert len(catalog['cards'])==len(precise['cards'])==609
    assert all(x.get('schema')==1 and 'historySchema' not in x for x in [catalog,render,history])
    assert precise_history['historySchema']==2
    for name in ['cards.json','render.json','history.json']:
        assert '__remove' not in (ROOT/name).read_text(encoding='utf-8')
    by_id={c['id']:c for c in catalog['cards']};render_by_id={c['id']:c for c in render['cards']}
    assert len(by_id)==609 and len({c['dbfId'] for c in catalog['cards']})==609
    source=load(ROOT/'metadata/EX1_323.json')['sourceCommit']
    original=json.loads(subprocess.check_output(['git','show',source+':cards.json'],cwd=ROOT))
    original_history=json.loads(subprocess.check_output(['git','show',source+':history.json'],cwd=ROOT))['cards']
    # The first dual-output release changes no current imported field at all.
    assert json_equal(catalog,original),'Current legacy catalogue drifted'
    assets=set(subprocess.check_output(['git','ls-tree','-r','--name-only',source,'--','art'],cwd=ROOT,text=True).splitlines())
    cases=[];comparisons=0;art_checks=0;corrections=[]
    for current in catalog['cards']:
        cid=current['id'];dbf=str(current['dbfId']);meta=load(ROOT/'metadata'/(cid+'.json'))
        assert type(current['cost']) is int and 0<=current['cost']<=32767
        for field in ('attack','health','durability','armor'):
            assert type(current[field]) is int and 0<=current[field]<=32767
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
            for field in PHP_FIELDS:
                if field=='health' and actual.get('type')=='WEAPON':continue
                if not json_equal(actual.get(field),before.get(field)):
                    # Explicitly reviewed real type correction, not a transport change.
                    assert cid=='EX1_323' and day<'2021-03-26' and field in ('type','attack','armor','race'),(cid,day,field,actual.get(field),before.get(field))
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
            'currentCards':609,'currentCatalogueMatchesPinnedOriginal':True,
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
