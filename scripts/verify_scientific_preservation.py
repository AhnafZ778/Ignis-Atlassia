"""Compare scientific outputs to the recorded original commit using one SQLite snapshot."""
import argparse,json,os,sqlite3,subprocess,tempfile,gzip
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUNNER='''import json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from fireatlas.calendar_v2 import calendar_v2,prepare_calendar_v2
from fireatlas.core import calendar
from fireatlas.replay import build_case
from fireatlas.research import report
from fireatlas.provenance import sanitize_public_payload
from fireatlas.regions import REGIONS
con=sqlite3.connect(Path(sys.argv[2]).as_uri()+'?mode=ro',uri=True);con.row_factory=sqlite3.Row;con.execute('PRAGMA query_only=ON');con.execute('BEGIN')
out={'regional':{},'replay':{},'generic':{},'research':{}}
for region in REGIONS:
 prepared=prepare_calendar_v2(con,region=region,fallback_year=2026)
 for year in [2024,2026]:
  r=calendar_v2(con,region=region,year=year,month=7 if year==2024 else 6,prepared=prepared)
  out['regional'][region+'/'+str(year)]={'calibration':r['calibration'],'days':r['days'],'availability':r['availability'],'months':[{k:v for k,v in m.items() if k!='verdict'} for m in r['months']]}
for case in ['park-2024','camp-2018','grove-2025']:
 r=build_case(con,case);out['replay'][case]={'summary':r['summary'],'frames':[{k:v for k,v in f.items() if k!='cells'} for f in r['frames']]}
bbox=[-121.55,39.25,-121.28,39.48]
out['generic']=calendar(con,bbox=bbox,year=2025,series='joint')
out['research']=report(con,bbox=bbox,year=2025,month=7,as_of='2025-07-06')
print(json.dumps(sanitize_public_payload(out),sort_keys=True,separators=(',',':')))
'''
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',type=Path,default=ROOT/'data/fireatlas.sqlite3');p.add_argument('--output',type=Path,default=ROOT/'docs/implementation/artifacts');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='ignis-original-science-') as tmp:
  tmp=Path(tmp);snapshot=tmp/'science.sqlite3'
  with sqlite3.connect(a.db.resolve().as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(snapshot) as target:source.backup(target)
  original=tmp/'original';original.mkdir();files=subprocess.check_output(['git','ls-tree','-r','--name-only','9e9f682','fireatlas'],cwd=ROOT,text=True).splitlines()
  for name in files:
   if not(name.endswith('.py') or name in ['fireatlas/samples/sensor_notices.json','fireatlas/samples/mcd64_corroboration.json']):continue
   target=original/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(subprocess.check_output(['git','show','9e9f682:'+name],cwd=ROOT))
  runner=tmp/'recount.py';runner.write_text(RUNNER)
  reference=subprocess.check_output([str(ROOT/'.venv/bin/python'),str(runner),str(original),str(snapshot)],cwd=tmp)
  current=subprocess.check_output([str(ROOT/'.venv/bin/python'),str(runner),str(ROOT),str(snapshot)],cwd=tmp)
  before=json.loads(reference);after=json.loads(current)
  if before!=after:raise SystemExit('Scientific preservation differs from the original calculation outputs.')
  (a.output/'scientific-reference.json.gz').write_bytes(gzip.compress(reference,mtime=0))
  checks={'status':'preserved','reference_commit':'9e9f682','scope':'Both regional daily calendars 2024/2026, calibration/composition/baselines, three named replays, Grove generic union calendar and Grove research report','comparison':'Exact structured equality; presentation verdicts and additive result identities excluded','replay':{k:v['summary'] for k,v in after['replay'].items()},'research_method':after['research']['method_version']}
  (a.output/'scientific-preservation.json').write_text(json.dumps(checks,indent=2));print(json.dumps(checks,indent=2))
if __name__=='__main__':main()
