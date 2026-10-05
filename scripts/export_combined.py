"""Export separate generic-union reference calendars from a captured database."""
import argparse,hashlib,json,sqlite3,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fireatlas.core import connect,calendar
from fireatlas.regions import REGIONS
from fireatlas.result_identity import encoded,digest

def export(database,site):
    root=site/'data/combined'
    if root.exists():raise ValueError('Refusing to overwrite frozen combined outputs.')
    manifest={'schema':'fireatlas-combined-static-v1','metric':'daily occupied-cell union','series':'joint','files':{}}
    with tempfile.TemporaryDirectory(prefix='ignis-combined-') as tmp:
        snapshot=Path(tmp)/'science.sqlite3'
        with sqlite3.connect('file:'+str(database.resolve())+'?mode=ro',uri=True) as source,sqlite3.connect(snapshot) as dest:source.backup(dest)
        with connect(snapshot) as db:
            for region in REGIONS:
                for year in [2024,2026]:
                    value=calendar(db,bbox=tuple(REGIONS[region]['bbox']),year=year,series='joint');body=encoded(value);relative=f'{region}-{year}.json';target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(body);manifest['files'][f'{region}/{year}']={'path':relative,'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body),'bbox':list(REGIONS[region]['bbox'])};print('Combined '+region+' '+str(year),flush=True)
    manifest['release_id']=digest(manifest['files']);(root/'manifest.json').write_bytes(encoded(manifest))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',type=Path,default=ROOT/'data/fireatlas.sqlite3');p.add_argument('--site',type=Path,default=ROOT/'site');a=p.parse_args();export(a.db,a.site)
