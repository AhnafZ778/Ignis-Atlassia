"""Exercise analytical routes, public context, scales and graceful static degradation."""
from __future__ import annotations
import argparse,json,threading,subprocess
from pathlib import Path
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT/'site'),**kwargs)
    def do_GET(self):
        if self.path.startswith('/demo/'):self.path=self.path[5:]
        if self.path.split('?')[0]=='/__original_landing__':
            body=subprocess.check_output(['git','show','9e9f682:site/index.html'],cwd=ROOT)
            self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
        try:super().do_GET()
        except (BrokenPipeError,ConnectionResetError):pass
    def log_message(self,*args):pass

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,default=ROOT/'docs/implementation/artifacts');args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{server.server_port}';records={};checks=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        def visit(path,width=1440):
            context=browser.new_context(viewport={'width':width,'height':1000},reduced_motion='reduce');page=context.new_page();errors=[];responses=[]
            page.on('pageerror',lambda e:errors.append(str(e)));page.route('https://**/*',lambda r:r.abort())
            def response(r):
                try:responses.append({'url':r.url.replace(base,''),'status':r.status,'bytes':len(r.body())})
                except Exception:pass
            page.on('response',response);page.goto(base+'/demo/'+path,wait_until='domcontentloaded');return context,page,errors,responses
        c,page,errors,responses=visit('atlas.html');page.wait_for_function("document.querySelector('#harm-verdict').textContent.includes('113 harmonized')");page.wait_for_timeout(800)
        assert '4 above the median of 3' in page.locator('#harm-verdict').inner_text()
        destinations=page.locator('#site-navigation a[data-destination]').evaluate_all('(links)=>links.map(link=>link.dataset.destination)')
        assert sorted(destinations)==['evidence','explore','investigate','research','studio'],destinations
        assert not any('bundles/' in r['url'] or 'history/' in r['url'] or '/observations/' in r['url'] for r in responses);assert not errors,errors
        records['calendar']=responses.copy();page.screenshot(path=str(args.output/'after-calendar.png'),full_page=True);page.locator('#harm-bridge-method').scroll_into_view_if_needed();page.screenshot(path=str(args.output/'after-sensor-bridge.png'))
        page.locator('#harm-month').select_option('7');page.wait_for_function("document.querySelector('#harm-verdict').textContent.includes('July 2026')");page.go_back();page.wait_for_function("document.querySelector('#harm-verdict').textContent.includes('June 2026')")
        checks.append('Explore defaults, supported median, lazy archives, committed Back/Forward and subpath');c.close()
        for region,total in [('norcal','3,450'),('punjab-haryana','221')]:
            c,page,errors,_=visit(f'atlas.html?region={region}&year=2024&month=7');page.wait_for_function("document.querySelector('#harm-value').textContent.trim()!=='…'");page.wait_for_timeout(900)
            assert total in page.locator('#harm-value').inner_text(),page.locator('#harm-value').inner_text();assert page.locator('#harm-download').get_attribute('href').endswith(f'{region}-2024-07.zip');assert not errors,errors;c.close()
        c,page,errors,_=visit('atlas.html?region=norcal&year=2026&month=5');page.wait_for_timeout(1500);assert 'unknown' in page.locator('#harm-verdict').inner_text().lower() or 'unavailable' in page.locator('#harm-verdict').inner_text().lower();assert page.locator('#harm-download').get_attribute('aria-disabled')=='true';c.close()
        c,page,errors,_=visit('atlas.html?bbox=-121,39,-120,40&year=2026&month=6');page.wait_for_timeout(1500);assert 'incoming selection is retained' in page.locator('#harm-status').inner_text();assert 'bbox=-121' in page.url;c.close();checks.append('Mixed gap totals, exact bundle links, unknown state and unsupported AOI retention')
        for path in ['investigate.html','research.html','evidence.html']:
            c,page,errors,_=visit(path+'?bbox=broken&start=2024-02-30&end=2024-03-04');page.wait_for_timeout(1600)
            assert 'bbox=broken' in page.url and 'start=2024-02-30' in page.url
            assert 'selection retained' in page.locator('main').inner_text().lower() or 'selection unavailable' in page.locator('main').inner_text().lower()
            assert not errors,errors;c.close()
        c,page,errors,_=visit('investigate.html?case=unrecognized-study');page.wait_for_timeout(1400);assert 'Unknown named study' in page.locator('main').inner_text();assert 'case=unrecognized-study' in page.url;assert not errors,errors;c.close()
        checks.append('Malformed AOI/dates and unknown studies retain incoming selection and show useful errors without controller exceptions')
        c,page,errors,responses=visit('investigate.html?case=grove-2025');page.wait_for_function("document.querySelector('#mission-frame-state').textContent.includes('Complete export')");page.wait_for_timeout(600);assert page.locator('#mission-split').get_attribute('aria-pressed')=='true';records['investigation']=responses.copy();page.screenshot(path=str(args.output/'after-investigation.png'),full_page=True)
        domains=page.locator('canvas[data-maximum]').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.maximum)');page.locator('#mission-next').click();page.locator('button[data-source="MODIS_SP"]').click();assert domains==page.locator('canvas[data-maximum]').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.maximum)'),domains
        page.locator('#workspace-scale').select_option('relative');assert 'brightness not comparable' in page.locator('#workspace-scale').inner_text()
        page.locator('#workspace-open-jarvis').click();page.keyboard.press('Escape');assert page.locator('#workspace-open-jarvis').get_attribute('aria-expanded')=='false'
        page.locator('#workspace-terrain').click();page.wait_for_function("document.querySelector('#mission-map-feedback').textContent.includes('Terrain unavailable')");page.screenshot(path=str(args.output/'after-terrain-unavailable.png'));assert not errors,errors;c.close();checks.append('Synchronized panes, stable heat domain after day/source changes, explicit relative setting and blocked terrain fallback')
        c,page,errors,responses=visit('evidence.html?tab=calibration&region=norcal');page.wait_for_function("document.querySelector('#calibration-status')?.textContent.includes('41 matched')");records['evidence']=responses.copy();page.screenshot(path=str(args.output/'after-calibration.png'),full_page=True)
        page.locator('[data-workspace-tab="reproduce"]').click();page.wait_for_function("document.querySelector('#regional-download')&&!document.querySelector('#regional-download').hidden");assert 'norcal-2026-06.zip' in page.locator('#regional-download').get_attribute('href');page.screenshot(path=str(args.output/'after-reproduction.png'),full_page=True)
        page.go_back();page.wait_for_function("document.querySelector('[data-workspace-tab=calibration]').getAttribute('aria-selected')==='true'");assert not errors,errors
        page.locator('#site-navigation [data-destination=research]').click();page.wait_for_url('**/research.html?*');page.wait_for_function("document.querySelector('#overview-result')!==null");assert 'tab=calibration' not in page.url;assert not errors,errors;c.close();checks.append('Actual calendar calibration, matching reproduction link, lazy-tab Back/Forward and cross-workspace tab isolation')
        c,page,errors,_=visit('research.html?start=2024-07-24&end=2024-08-14&bbox=-122,39.5,-121.3,40.5');page.wait_for_timeout(600);assert 'spans multiple UTC months' in page.locator('#workspace-panel').inner_text();page.locator('[aria-label="Research UTC month intersection"]').select_option('2024-08');page.wait_for_timeout(600);assert 'start=2024-07-24' in page.url and 'end=2024-08-14' in page.url;assert 'local analysis service' in page.locator('#overview-error').inner_text();assert not errors,errors;c.close();checks.append('Explicit research month intersection preserves full originating interval; static local-service limitation')
        for alias,target,tab in [('replay','investigate',None),('assistant','investigate',None),('data','evidence','sources'),('method','evidence','method'),('review','evidence','reproduce'),('research-candidates','research','candidates'),('research-exposure','research','exposure'),('research-validation','evidence','method')]:
            c,page,errors,_=visit(alias+'.html?region=punjab-haryana&year=2024&month=7#retained');page.wait_for_url('**/'+target+'.html?*');assert '#retained' in page.url and 'region=punjab-haryana' in page.url
            if tab:assert 'tab='+tab in page.url
            c.close()
        for fragment in ['atlas-section','calendar-section','harmonized-calendar','study-workspace']:
            c,page,errors,_=visit('index.html?region=punjab-haryana&year=2024&month=7#'+fragment);page.wait_for_url('**/demo/atlas.html?*');assert 'region=punjab-haryana' in page.url and '#'+fragment in page.url;c.close()
        checks.append('Eight real aliases retain query, fragment and project base')
        for width in [360,390,768]:
            for path in ['atlas.html','investigate.html?case=grove-2025','evidence.html?tab=calibration']:
                c,page,errors,_=visit(path,width);page.wait_for_timeout(1400);assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(width,path,page.evaluate('document.documentElement.scrollWidth'))
                page.keyboard.press('Tab');assert page.evaluate('document.activeElement!==document.body');page.screenshot(path=str(args.output/f'after-{path.split(".")[0]}-{width}.png'),full_page=True);assert not errors,errors;c.close()
        checks.append('360/390/768 widths, keyboard entry and reduced motion')
        # Reconstruct the original landing from the recorded commit, rather than overwriting baseline screenshots.
        for path,name in [('__original_landing__','landing-original-restored'),('index.html','landing-current')]:
            c,page,errors,_=visit(path);page.wait_for_timeout(1800);page.screenshot(path=str(args.output/(name+'.png')),clip={'x':0,'y':100,'width':1440,'height':900});c.close()
        browser.close()
    server.shutdown();(args.output/'after-loading.json').write_text(json.dumps(records,indent=2));(args.output/'workspace-checks.json').write_text(json.dumps({'checks':checks,'external_imagery':'blocked to verify deterministic degradation','terrain':'SDK failure exercised; connected terrain requires network/WebGL'},indent=2));print(json.dumps({'passed':checks,'loading':{k:{'requests':len(v),'bytes':sum(x['bytes'] for x in v)} for k,v in records.items()}},indent=2))
if __name__=='__main__':main()
