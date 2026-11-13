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
REMOVED_SKIN_HERO_POWERS = frozenset({'CS2_102_H3'})
ADDED_TOKEN_IDS = frozenset(['CS3_002t', 'RLK_077t', 'RLK_085t', 'RLK_226t', 'RLK_705t', 'RLK_907t', 'OG_044a'])
VERIFIED_BETA_DEBUT_IDS = frozenset(['EX1_112','Mekka1','Mekka2','Mekka3','Mekka4','Mekka4t','EX1_062','NEW1_016', *(f'HERO_{n:02d}bp' for n in range(1,10)), 'NEW1_010','EX1_012','EX1_100','NEW1_029','EX1_557','EX1_590','EX1_014','EX1_083','EX1_005','EX1_002','NEW1_024','EX1_558','EX1_116','EX1_110','NEW1_040','EX1_016','EX1_577','EX1_614','EX1_249','NEW1_038','EX1_298','EX1_561','EX1_563','EX1_560','EX1_562','EX1_572','NEW1_030'])
VERIFIED_BETA_DEBUT_IDS = VERIFIED_BETA_DEBUT_IDS | frozenset(('EX1_621','EX1_332','CS1_130','CS1_129','CS2_003','CS2_004','CS2_236','EX1_341','DS1_233','EX1_622','CS2_234','EX1_625','EX1_339','CS1_112','EX1_334','EX1_591','EX1_626','EX1_345','EX1_624','EX1_350','CS1_113','EX1_623','EX1_091','DS1_185','EX1_549','EX1_544','CS2_084','EX1_610','EX1_533','EX1_554','EX1_609','NEW1_031','EX1_617','EX1_536','DS1_183','EX1_537','DS1_175','EX1_611','EX1_531','CS2_237','EX1_539','EX1_538','DS1_070','DS1_178','EX1_543'))
VERIFIED_BETA_DEBUT_IDS = VERIFIED_BETA_DEBUT_IDS | frozenset(('EX1_169','CS2_005','EX1_578','CS2_013','CS2_011','EX1_158','EX1_570','EX1_571','EX1_164','NEW1_007','EX1_573','CS2_008','CS2_009','EX1_154','CS2_007','EX1_166','EX1_165','EX1_178','EX1_251','EX1_238','CS2_038','CS2_053','EX1_241','EX1_243','CS2_045','EX1_248','EX1_246','EX1_259','EX1_258','CS2_046','EX1_567','EX1_250','CS2_042','EX1_360','EX1_130','CS2_093','CS2_094','CS2_097','EX1_354','EX1_383','CS2_063','EX1_319','EX1_302','EX1_596','CS2_062','CS2_057','EX1_303','EX1_309','EX1_315','EX1_320','CS2_072','EX1_145','EX1_144','CS2_074','CS2_075','EX1_126','CS2_233','EX1_581','EX1_278','EX1_613','EX1_133','CS2_080','CS2_077'))
VERIFIED_BETA_DEBUT_IDS = VERIFIED_BETA_DEBUT_IDS | frozenset(('DREAM_01','DREAM_02','DREAM_03','DREAM_04','DREAM_05','EX1_110t','EX1_tk29','EX1_tk28','NEW1_040t','EX1_014t','NEW1_032','NEW1_033','NEW1_034','EX1_383t','EX1_573t','EX1_554t','EX1_130a','EX1_158t','EX1_165a','EX1_165b','EX1_165t1','EX1_165t2','EX1_625t','EX1_625t2','EX1_345t','EX1_614t'))
VERIFIED_HERO_POWER_RELEASES = frozenset([*(f'HERO_{n:02d}bp2' for n in range(1, 10)), 'HERO_10bp', 'HERO_10bp2'])
CORRECTED_FIRST_PLAYABLE_IDS = VERIFIED_HERO_POWER_RELEASES | frozenset(
    [*(f'LEG_RLK_{s}' for s in ('034','039','071','077','079','082','085','101','115',
                               '125','224','226','705','710','715','744','752','753')),
     'LEG_TTN_908', *(f'EX1_{n}' for n in range(183,193)), 'OG_047a', 'OG_047b',
     'CS2_058', 'LEG_CS3_001','LEG_CS3_013','LEG_CS3_015','LEG_CS3_017',
     'LEG_CS3_028','LEG_CS3_031','LEG_CS3_032','LEG_CS3_033',
     'LEG_CS3_034','LEG_CS3_036','LEG_CS3_037',
     'CS2_101t2','CS2_101t3','CS2_101t4','CS2_101t5','CS2_101t6','CS2_101t7','CS2_101t8',
     'TOY_100','TOY_101','TOY_102','TOY_103'])


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
    assert len(catalog['cards'])==len(precise['cards'])==615
    assert not any(c['id'] in REMOVED_SKIN_HERO_POWERS for c in catalog['cards']+precise['cards'])
    assert '58799' not in precise_history['cards']
    assert not any(x['id'] in REMOVED_SKIN_HERO_POWERS for x in render['cards'])
    assert not any(x['id'] in REMOVED_SKIN_HERO_POWERS for x in load(ROOT/'render-date.json')['cards'])
    assert all(x.get('schema')==1 and 'historySchema' not in x for x in [catalog,render,history])
    assert precise_history['historySchema']==2
    for name in ['cards.json','render.json','history.json']:
        assert '__remove' not in (ROOT/name).read_text(encoding='utf-8')
    by_id={c['id']:c for c in catalog['cards']};render_by_id={c['id']:c for c in render['cards']}
    assert len(by_id)==615 and len({c['dbfId'] for c in catalog['cards']})==615
    source=load(ROOT/'metadata/EX1_323.json')['sourceCommit']
    original=json.loads(subprocess.check_output(['git','show',source+':cards.json'],cwd=ROOT))
    original_history=json.loads(subprocess.check_output(['git','show',source+':history.json'],cwd=ROOT))['cards']
    # The first dual-output release changes no current imported field at all.
    catalog_other=copy.deepcopy(catalog); original_other=copy.deepcopy(original)
    # The archived source must remain intact, but excluded skin-only powers
    # are intentionally absent from the current public catalog.
    original_other['cards']=[row for row in original_other['cards'] if row['id'] not in REMOVED_SKIN_HERO_POWERS]
    catalog_other['cards'] = [row for row in catalog_other['cards'] if row['id'] not in ADDED_TOKEN_IDS]
    for obj in (catalog_other,original_other):
        for row in obj['cards']:
            row.pop('text',None)
            if row['id'] == 'CS2_101t6':
                # Installed 31.0 Draenei type never applied to the already
                # retired recruit; raw DBF records remain in originalSource.
                row.pop('race',None); row.pop('races',None)
            if row['id'] in ('PRO_001','PRO_001a','PRO_001at','PRO_001b','PRO_001c'):
                row.pop('releasedAt',None)  # Verified North American beta release in KST.
            if row['id'] in ('skele21','ds1_whelptoken'):
                row.pop('releasedAt',None); row.pop('releaseStatus',None)
            if row['id'] in CORRECTED_FIRST_PLAYABLE_IDS or row['id'] in VERIFIED_BETA_DEBUT_IDS:
                # Approved date changes or beta-debut release confidence reviews relative to pinned source.
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
                    # Original compatibility rendering has no pre-release visibility gate.
                    # The 2022-11-30 client-side Undead tag is correctly folded into
                    # Death Knight cards' 2022-12-07 debut, but legacy consumers
                    # still display present-day race before cards are playable.
                    first_release_race_fix = (
                        cid.startswith('LEG_RLK_')
                        and day < meta['release']['date']
                        and field == 'race'
                    )
                    # This recruit was playable in 29.0 but retired before
                    # the later 31.0 client-only Draenei race tag appeared.
                    unused_draenei_race_fix = (
                        cid == 'CS2_101t6' and field == 'race'
                    )
                    assert type_fix or beta_date_fix or first_release_race_fix or unused_draenei_race_fix,(
                        cid,day,field,actual.get(field),before.get(field))
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
            'currentCards':615,'previousCatalogueMatchesPinnedOriginal':True,'addedTokenCards':sorted(ADDED_TOKEN_IDS),
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
