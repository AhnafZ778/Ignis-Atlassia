"""Verify destination choice, captured Canvas delivery and refresh persistence without inference."""
from playwright.sync_api import sync_playwright,expect
import shutil,json
from pathlib import Path
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base',default='http://127.0.0.1:8000')
parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'docs/implementation/workspace-polish')
args=parser.parse_args();base=args.base.rstrip('/');out=args.output;out.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
 b=p.chromium.launch(headless=True,executable_path=shutil.which('chromium'))
 context=b.new_context(viewport={'width':1440,'height':1100},reduced_motion='reduce')
 page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(base+'/investigate.html?case=grove-2025&day=2025-07-04',wait_until='domcontentloaded')
 page.wait_for_function("document.querySelector('#mission-day')?.disabled===false",timeout=90000)
 page.get_by_role('button',name='Send to Canvas',exact=True).click()
 page.get_by_role('combobox',name='Canvas destination',exact=True).select_option('new',timeout=30000)
 page.get_by_role('button',name='Create presentation on selected Canvas',exact=True).click()
 page.wait_for_url('**/studio.html?*',timeout=90000)
 page.wait_for_function("document.querySelectorAll('article.card').length>0",timeout=30000)
 page.wait_for_timeout(2000)
 docs=context.request.get(base+'/api/studio/documents').json()['documents'];assert len(docs)==1
 board=context.request.get(base+'/api/studio/documents/'+docs[0]['id']).json()
 # The API returns the owned canonical Studio document.
 state=board.get('document',board).get('state',board.get('state'))
 assert state is not None,board.keys()
 report={'checks':['Send to Canvas asks for the destination, then opens the persisted board after capture.','The new board retains the Grove case and fixed submitted date.'],'errors':errors}

 selection=state.get('study',state.get('study_context',{}))
 if isinstance(selection,dict):
  assert 'grove-2025' in json.dumps(selection),selection
  assert '2025-07-04' in json.dumps(selection),selection
 page.screenshot(path=str(out/'canvas-handoff.png'))
 page.reload();page.wait_for_function("document.querySelectorAll('article.card').length>0",timeout=30000)
 report['checks'].append('Refresh restores the captured cards; no browser exceptions occurred.')
 assert not errors,errors
 # Clean only the document created in this isolated acceptance workspace.
 latest=context.request.get(base+'/api/studio/documents/'+docs[0]['id']).json()
 obj=latest.get('document',latest)
 r=context.request.delete(base+'/api/studio/documents/'+docs[0]['id'],data={'expected_revision':obj['revision']},headers={'Origin':base})
 assert r.ok,r.text()
 (out/'canvas-handoff-report.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2));b.close()
