"""Check native validity gates, Investigate controls and subpath/static presentation."""
from __future__ import annotations
import argparse, json, shutil, threading
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT/'site'),**kwargs)
    def do_GET(self):
        if self.path.startswith('/demo/'):self.path=self.path[5:]
        super().do_GET()
    def log_message(self,*args):pass

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',default='http://127.0.0.1:8000')
    parser.add_argument('--output',type=Path,default=ROOT/'docs/implementation/workspace-polish')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    report={'checks':[],'errors':[],'sizes':[]}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path=shutil.which('chromium'))
        for mode,base in [('local',args.base.rstrip('/')),('static',f'http://127.0.0.1:{server.server_port}/demo')]:
            context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
            page=context.new_page();page.on('pageerror',lambda e:report['errors'].append(str(e)))
            css=context.request.get(base+'/workspace-polish.css');assert css.ok and 'text/css' in css.headers.get('content-type','')
            page.goto(base+'/evidence.html?tab=validity&case=park-2024',wait_until='domcontentloaded')
            page.wait_for_function("document.querySelector('#validity-overview-title')?.textContent.includes('Park Fire')",timeout=90000)
            expect(page.locator('#validity-validation')).to_have_count(1)
            assert page.locator('#validity-validation li.passed').count()==2
            assert page.locator('#validity-validation li.pending').count()==2
            text=page.locator('#validity-validation').inner_text().replace(',','')
            for value in ['114 / 114', '3431 / 3431' if mode=='local' else '3137 / 3137','0 / 30','0 / 1']:assert value in text,value
            assert '1,372,872' in page.locator('#validity-audit-facts').inner_text()
            assert 'Separate gate' in page.locator('.validity-exposure').inner_text()
            assert '2024-07-17' in page.locator('#validity-overview-scope').inner_text()
            assert '[-122, 39.5, -121.3, 40.5]' in page.locator('#validity-overview-scope').inner_text()
            expect(page.locator('.validity-counting-details')).not_to_have_attribute('open','')
            # This assertion prevents a missing CSS route from passing a text-only check.
            assert page.locator('.validity-validation-path').evaluate("n=>getComputedStyle(n).display")=='grid'
            page.screenshot(path=str(args.output/f'validity-{mode}-desktop.png'))
            page.locator('[data-validity-case=grove-2025]').click()
            page.wait_for_function("document.querySelector('#validity-overview-title').textContent.includes('Grove Fire')",timeout=90000)
            text=page.locator('#validity-validation').inner_text()
            for value in ['20 / 20','7 / 7','0 / 30','0 / 1']:assert value in text
            assert 'case=grove-2025' in page.locator('#validity-overview-review').get_attribute('href')
            assert 'case=grove-2025' in page.locator('#validity-overview-download').get_attribute('href') or 'grove-2025.zip' in page.locator('#validity-overview-download').get_attribute('href')
            page.locator('#run-recount').scroll_into_view_if_needed();page.locator('#run-recount').click()
            page.wait_for_function("document.querySelector('#proof-label').textContent.includes('All plotted totals reproduce')",timeout=90000)
            for width in [360,390,768]:
                page.set_viewport_size({'width':width,'height':950});page.evaluate('scrollTo(0,0)')
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(mode,'validity',width)
                page.screenshot(path=str(args.output/f'validity-{mode}-{width}.png'))
                report['sizes'].append({'mode':mode,'page':'validity','width':width,'scroll_width':page.evaluate('document.documentElement.scrollWidth')})
            report['checks'].append(mode+': native gates, distinct exposure boundary, exact scope, case switch, recount and 360/390/768 layout')
            page.set_viewport_size({'width':1440,'height':1000})
            page.goto(base+'/investigate.html?case=park-2024',wait_until='domcontentloaded')
            page.wait_for_function("document.querySelector('#mission-day')?.disabled===false",timeout=90000)
            assert page.locator('.jarvis-transfer-compact').count()==1
            assert page.locator('.mission-grid').evaluate("n=>getComputedStyle(n).borderTopWidth")=='0px'
            expect(page.locator('#investigate-studio-link')).to_be_visible()
            assert page.locator('.jarvis-transfer-compact').evaluate("n=>n.getBoundingClientRect().top>document.querySelector('.mission-timeline').getBoundingClientRect().bottom")
            maximum=page.locator('canvas[data-maximum]').evaluate_all('ns=>ns.map(n=>n.dataset.maximum)')
            assert maximum and all(float(v)>0 for v in maximum)
            page.locator('#mission-next').click();page.locator('button[data-source=MODIS_SP]').click()
            assert maximum==page.locator('canvas[data-maximum]').evaluate_all('ns=>ns.map(n=>n.dataset.maximum)')
            page.locator('.jarvis-transfer-details summary').click();expect(page.get_by_role('button',name='Choose canvas',exact=True)).to_be_visible()
            if mode=='local':
                page.get_by_role('button',name='Choose canvas',exact=True).click();expect(page.get_by_role('combobox',name='Investigation destination')).to_be_visible()
                expect(page.get_by_role('button',name='Park Fire 2024 presentation',exact=True)).to_be_visible()
            page.locator('.jarvis-transfer-details summary').click()
            page.evaluate('scrollTo(0,0)');page.screenshot(path=str(args.output/f'investigate-{mode}-desktop.png'))
            for width in [360,390,768]:
                page.set_viewport_size({'width':width,'height':950});page.evaluate('scrollTo(0,0)')
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),(mode,'investigate',width,page.evaluate('document.documentElement.scrollWidth'))
                page.screenshot(path=str(args.output/f'investigate-{mode}-{width}.png'))
                report['sizes'].append({'mode':mode,'page':'investigate','width':width,'scroll_width':page.evaluate('document.documentElement.scrollWidth')})
            # Keyboard disclosure and all advanced controls retain their native semantics.
            page.locator('.jarvis-transfer-details summary').focus();page.keyboard.press('Enter');assert page.locator('.jarvis-transfer-details').get_attribute('open') is not None
            report['checks'].append(mode+': Studio handoff visibility, compact controls, fixed map scale, keyboard disclosure, 360/390/768 layout')
            context.close()
        assert not report['errors'],report['errors'];browser.close()
    server.shutdown();server.server_close()
    (args.output/'browser-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
