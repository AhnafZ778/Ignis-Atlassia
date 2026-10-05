from pathlib import Path
import json
from playwright.sync_api import sync_playwright
import argparse
parser=argparse.ArgumentParser(description='Exercise connected optional terrain on a running local service.');parser.add_argument('--base',default='http://127.0.0.1:8074/');args=parser.parse_args()
out=Path(__file__).resolve().parents[1]/'docs/implementation/artifacts'
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(args.base.rstrip('/')+'/investigate.html?case=grove-2025',wait_until='domcontentloaded')
    page.wait_for_function("document.querySelector('#mission-frame-state').textContent.includes('Complete export')")
    page.locator('#workspace-terrain').evaluate("n=>{for(let p=n;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;}")
    page.locator('#workspace-terrain').click()
    try:page.wait_for_function("document.querySelector('#investigation-terrain').dataset.date || document.querySelector('#mission-map-feedback').textContent.includes('Terrain unavailable')",timeout=40000)
    except Exception:pass
    page.wait_for_timeout(8000)
    domain=page.locator('#investigation-terrain').get_attribute('data-maximum')
    page.locator('#mission-next').click()
    page.wait_for_function("document.querySelector('#investigation-terrain').dataset.date==='2025-07-05'")
    assert page.locator('#investigation-terrain').get_attribute('data-maximum')==domain
    page.locator('#mission-first').click() if page.locator('#mission-first').count() else page.locator('#mission-prev').click()
    state=page.locator('#mission-map-feedback').inner_text()
    ready=page.locator('#investigation-terrain').get_attribute('data-date')
    page.evaluate('window.scrollTo(0,0)')
    page.wait_for_timeout(300)
    page.screenshot(path=str(out/'after-terrain-connected-attempt.png'),full_page=True)
    (out/'terrain-connected-check.json').write_text(json.dumps({'rendered_date':ready,'feedback':state,'browser_errors':errors,'meaning':'Actual SDK connection attempted; readiness requires render date.'},indent=2))
    print(json.dumps({'ready':ready,'feedback':state,'errors':errors}))
    if ready:
        page.locator('#workspace-terrain').click()
        assert page.locator('#investigation-terrain').is_hidden()
        assert page.locator('#mission-split').get_attribute('aria-pressed')=='true'
        assert page.locator('#assistant-current-dates').inner_text().startswith('2025-07-04')
    browser.close()
