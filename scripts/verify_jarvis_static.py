"""Measure analytical cold entries and exercise frozen portability under a project subpath.

No API is mocked as successful. Static authoring must explain its missing backend.
"""
import argparse
import json
import shutil
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site',type=Path,default=Path('site'))
    parser.add_argument('--output',type=Path,default=Path('docs/implementation/jarvis-checks'))
    args=parser.parse_args();site=args.site.resolve();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*a,**kw):super().__init__(*a,directory=str(site),**kw)
        def translate_path(self,path):
            if path.startswith('/project/'):path=path[len('/project'):]
            else:return str(site/'nonexistent-outside-application')
            return super().translate_path(path)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{server.server_port}/project/'
    report={'cold_entries':{},'checks':[],'page_errors':[],'comparison':'Final build only. No before/after improvement claimed.'}
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,executable_path=next((shutil.which(n) for n in ('chromium','chromium-browser','google-chrome') if shutil.which(n)),None))
            for name,route in [('Explore','atlas.html?region=norcal&year=2026&month=6'),('Investigate','investigate.html?case=park-2024'),('Evidence','evidence.html?tab=method')]:
                ctx=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce');page=ctx.new_page();responses=[]
                ctx.route('**/*',lambda r:r.continue_() if urlsplit(r.request.url).hostname=='127.0.0.1' else r.abort())
                page.on('pageerror',lambda e:report['page_errors'].append(str(e)));page.on('response',lambda r:responses.append(r))
                page.goto(base+route,wait_until='domcontentloaded');expect(page.get_by_role('button',name='Send to Canvas',exact=True)).to_be_visible()
                if name=='Explore':page.wait_for_function("document.querySelector('main').textContent.includes('113')",timeout=30000)
                if name=='Investigate':page.wait_for_function("(()=>{try{return !!FireAtlasOrchestration.source().view.domain}catch{return false}})()",timeout=30000)
                page.wait_for_timeout(1500)
                entries=[]
                for r in responses:
                    if urlsplit(r.url).hostname!='127.0.0.1':continue
                    try:size=len(r.body())
                    except Exception:size=0
                    entries.append({'path':urlsplit(r.url).path,'status':r.status,'response_body_bytes':size})
                assert not any('/observations/' in e['path'] or e['path'].endswith('.zip') for e in entries),entries
                report['cold_entries'][name]={'requests':len(entries),'decoded_response_body_bytes':sum(e['response_body_bytes'] for e in entries),'measurement':'Fresh browser context; summaries ready, then 1.5 seconds; external imagery blocked.','entries':entries}
                page.screenshot(path=str(output/('static-'+name.lower()+'.png')),full_page=True)
                page.get_by_role('button',name='Send to Canvas',exact=True).click()
                expect(page.get_by_role('status').filter(has_text='Saving investigations requires the local service')).to_be_visible()
                assert not any('/api/studio/commands' in urlsplit(r.url).path for r in responses)
                ctx.close()
            report['checks'].append('Explore, Investigate and Evidence preserve project-relative assets; initial summaries fetch no full regional row archives or result ZIPs; static saving reports the missing service.')
            ctx=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce');page=ctx.new_page()
            page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
            page.goto(base+'studio-excalidraw.html',wait_until='domcontentloaded')
            page.get_by_label('Open Excalidraw scene').set_input_files(output/'park-investigation.excalidraw')
            page.wait_for_function('!!window.FireAtlasExcalidraw?.getSceneElements().length',timeout=30000)
            assert page.evaluate('Object.keys(FireAtlasExcalidraw.getFiles()).length')>0
            page.screenshot(path=str(output/'static-excalidraw-subpath.png'))
            report['checks'].append('Actual editable Excalidraw companion opens with embedded images under /project/ without a scientific or private backend.')
            browser.close()
    finally:server.shutdown();server.server_close()
    (output/'static-loading-report.json').write_text(json.dumps(report,indent=2))
    assert not report['page_errors'],report['page_errors']
    for check in report['checks']:print(check)
    for name,m in report['cold_entries'].items():print(f"{name}: {m['requests']} requests / {m['decoded_response_body_bytes']} decoded response bytes")


if __name__=='__main__':main()
