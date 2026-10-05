"""Export an isolated analytical release without touching the frozen globe."""
from __future__ import annotations
import argparse, hashlib, json, shutil, sqlite3, sys, tempfile
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fireatlas.core import connect
from fireatlas.calendar_v2 import prepare_calendar_v2,calendar_v2
from fireatlas.regions import REGIONS
from fireatlas.calendar_v2 import region_status
from fireatlas.regional_study import build_bundle,verify_bundle
from fireatlas.result_identity import encoded,digest
from scripts.export_static import _observations_for_region

def export(database,site):
    target=site/'data'/'analysis';target.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ignis-analytical-') as tmp:
        tmp=Path(tmp);snapshot=tmp/'science.sqlite3'
        with sqlite3.connect('file:'+str(database.resolve())+'?mode=ro',uri=True) as source,sqlite3.connect(snapshot) as dest:source.backup(dest)
        staging=tmp/'release';data=staging/'data'/'analysis';data.mkdir(parents=True)
        def write(path,value):p=data/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(encoded(value))
        manifest={'schema':'fireatlas-analytical-release-v1','snapshot_utc':datetime.now(timezone.utc).isoformat(),'snapshot_utc_date':datetime.now(timezone.utc).date().isoformat(),'capabilities':{'regional_calendars':True,'named_replay':True,'custom_research':False,'private_notebooks':False,'inference':False},'results':{},'bundles':{},'frozen_evidence_root':'../v2/'}
        with connect(snapshot) as db:
            db.execute('BEGIN');write(Path('regions.json'),region_status(db))
            for region in REGIONS:
                print('Preparing '+region,flush=True);prepared=prepare_calendar_v2(db,region=region,fallback_year=2026)
                for year in range(2006,2027):
                    result=calendar_v2(db,region=region,year=year,month=6,prepared=prepared)
                    for month in range(1,13):
                        r=calendar_v2(db,region=region,year=year,month=month,prepared=prepared)
                        manifest['results'][f'{region}/{year}/{month}']={'result_sha256':r['meta']['result_sha256'],'release_id':r['meta']['release_id'],'selected_month':r['meta']['period']['selected_month'],'corroboration':r['meta']['corroboration'],'verdict':r['meta']['verdict']}
                    write(Path(f'calendar/{region}/{year}.json'),result)
                full=calendar_v2(db,region=region,year=2026,month=6,prepared=prepared,include_history=True);write(Path(f'history/{region}.json'),full['history']);write(Path(f'calibration/{region}.json'),calibration_asset(full))
                # Existing bounded row-display exporter writes into a temporary v2 root.
                _observations_for_region(db,staging,region,2006,2026)
                shutil.move(staging/'data'/'v2'/'observations'/region,data/'observations'/region) if (data/'observations').exists() else None
                if not (data/'observations').exists():shutil.move(staging/'data'/'v2'/'observations',data/'observations')
                for year,month in [(2026,6),(2024,7)]:
                    key=f'{region}/{year}/{month}';relative=f'bundles/{region}-{year}-{month:02d}.zip';path=data/relative
                    print('Building exact '+key,flush=True);report=build_bundle(db,path,region=region,year=year,month=month,prepared=prepared)
                    print('Verifying '+key,flush=True);checked=verify_bundle(path)
                    manifest['bundles'][key]={'path':relative,'bytes':report['bytes'],'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'result_sha256':report['result_sha256'],'status':'verified'}
                    write(Path(f'checks/{region}-{year}-{month:02d}.json'),checked)
        manifest['files']=[{'path':str(p.relative_to(data)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(data.rglob('*')) if p.is_file()]
        manifest['release_id']=digest(manifest['files']);write(Path('manifest.json'),manifest)
        from scripts.static_bundle_storage import prepare
        prepare(data)
        if target.exists():raise ValueError('Refusing to overwrite an analytical release. Choose a fresh output namespace.')
        shutil.copytree(data,target)
        print('Analytical release ready: '+manifest['release_id'],flush=True)
    return manifest

def calibration_asset(result):
    return {'schema':'fireatlas-calendar-calibration-evidence-v1','calibration':result['calibration'],
            'meta':{k:result['meta'][k] for k in ['region','inputs','calibration_id','release_id']},
            'preparation_horizon':result['meta']['period'].get('history_end')}

def refresh_calibration(site):
    """Extract the exact used calibration from an already checksummed release."""
    data=site/'data/analysis';manifest=json.loads((data/'manifest.json').read_text())
    index={entry['path']:entry for entry in manifest['files']}
    for region in REGIONS:
        source=data/f'calendar/{region}/2026.json';entry=index[str(source.relative_to(data))]
        body=source.read_bytes()
        if len(body)!=entry['bytes'] or hashlib.sha256(body).hexdigest()!=entry['sha256']:raise ValueError('Calendar parity check failed; calibration assets not refreshed.')
        path=data/f'calibration/{region}.json';path.parent.mkdir(exist_ok=True);path.write_bytes(encoded(calibration_asset(json.loads(body))))
        index[str(path.relative_to(data))]={'path':str(path.relative_to(data)),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    manifest['files']=[index[k] for k in sorted(index)];manifest['release_id']=digest(manifest['files']);(data/'manifest.json').write_bytes(encoded(manifest))
    print('Extracted exact frozen calendar calibrations; no observations, calendars, bundles or globe files changed.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',type=Path,default=ROOT/'data/fireatlas.sqlite3');p.add_argument('--site',type=Path,default=ROOT/'site');p.add_argument('--refresh-calibration',action='store_true');a=p.parse_args();refresh_calibration(a.site) if a.refresh_calibration else export(a.db,a.site)
