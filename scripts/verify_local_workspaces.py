import json
from pathlib import Path
from playwright.sync_api import sync_playwright
import argparse
parser=argparse.ArgumentParser(description='Check a running no-provider scientific service and stale tab bodies.');parser.add_argument('--base',default='http://127.0.0.1:8074/');args=parser.parse_args()
out=Path(__file__).resolve().parents[1]/'docs/implementation/artifacts'
checks=[]
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
    page=context.new_page();errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.route('https://**/*',lambda r:r.abort())
    base=args.base.rstrip('/')+'/'
    page.goto(base+'investigate.html?case=grove-2025')
    page.wait_for_function("document.querySelector('#mission-frame-state').textContent.includes('Complete export')")
    page.wait_for_function("window.FireAtlasAssistant?.isReady()")
    assert page.locator('#mission-split').get_attribute('aria-pressed')=='true'
    page.screenshot(path=str(out/'after-local-investigation.png'),full_page=True)
    assert page.locator('#assistant-send').is_disabled()
    checks.append('No-provider service: deterministic study and comparison initialize; conversational send disabled')
    page.goto(base+'research.html?start=2025-07-04&end=2025-07-06&bbox=-121.55,39.25,-121.28,39.48')
    page.wait_for_function("document.querySelector('#overview-union').textContent==='4'")
    current=page.evaluate('FireAtlasContext.read()')
    page.locator('#overview-distance').evaluate("n=>{for(let p=n;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;}")
    page.locator('#overview-distance').select_option('5')
    assert page.evaluate('FireAtlasContext.read().distance_km')==current['distance_km']
    page.locator('#overview-run').click()
    page.wait_for_function("FireAtlasContext.read().distance_km===5 && document.querySelector('#overview-union').textContent==='4'")
    page.screenshot(path=str(out/'after-local-research.png'),full_page=True)
    checks.append('Grove research union 4; draft distance preserves applied context until completed calculation')
    page.locator('[data-workspace-tab="candidates"]').click()
    page.wait_for_function("document.querySelector('#candidate-count').textContent.includes('groups')")
    assert page.locator('#candidate-table tr').count()>0
    page.screenshot(path=str(out/'after-local-candidates.png'),full_page=True)
    page.locator('[data-workspace-tab="exposure"]').click()
    page.wait_for_function("document.querySelector('#exposure-detections').textContent==='7'")
    assert page.locator('#exposure-mask-status').inner_text()=='Unavailable'
    assert 'Exposure is unknown.' in page.locator('#coverage-output').inner_text()
    page.locator('[data-workspace-tab="sensitivity"]').click()
    page.wait_for_function('window.FireAtlasAssistant.isReady()')
    page.wait_for_timeout(600)
    page.locator('#sensitivity-run').click()
    page.wait_for_function("document.querySelector('#sensitivity-status').textContent.includes('Calculated from stored')",timeout=30000)
    assert page.locator('#sensitivity-output table tr').count()>1
    page.screenshot(path=str(out/'after-local-sensitivity.png'),full_page=True)
    checks.append('Candidate membership table, unavailable unsupplied exposure denominator and model-free sensitivity configurations')
    # Hold an already-returned response body, then unmount its controller.
    page.add_init_script("""const nativeFetch=window.fetch; window.fetch=async(...args)=>{const r=await nativeFetch(...args);if(String(args[0]).includes('/api/research?'))return new Proxy(r,{get(t,k){if(k==='json')return async()=>{const body=await t.json();window.__bodyPending=true;await new Promise(resolve=>window.__releaseBody=resolve);return body;};const v=Reflect.get(t,k,t);return typeof v==='function'?v.bind(t):v;}});return r;};""")
    page.goto(base+'research.html?start=2025-07-04&end=2025-07-06&bbox=-121.55,39.25,-121.28,39.48')
    page.wait_for_function('window.__bodyPending===true')
    page.locator('[data-workspace-tab="sensitivity"]').click()
    page.wait_for_function("document.querySelector('[data-workspace-tab=sensitivity]').getAttribute('aria-selected')==='true'")
    revision=page.evaluate('FireAtlasContext.revision')
    page.evaluate('window.__releaseBody()')
    page.wait_for_timeout(700)
    assert page.evaluate('FireAtlasContext.revision')==revision
    assert page.locator('#overview-result').count()==0
    checks.append('Delayed response body from inactive tab cannot commit context or repaint active tab')
    assert not errors,errors
    browser.close()
(out/'local-browser-checks.json').write_text(json.dumps({'passed':checks,'model_provider':'not configured','external_imagery':'blocked'},indent=2))
print(json.dumps(checks,indent=2))
