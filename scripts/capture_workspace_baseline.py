"""Capture dated browser baseline without modifying the scientific release."""
import asyncio,json,argparse
from pathlib import Path
from playwright.async_api import async_playwright

async def main():
    out=Path('docs/implementation/artifacts');out.mkdir(parents=True,exist_ok=True)
    records={}
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=['--no-sandbox'])
        page=await browser.new_page(viewport={'width':1440,'height':1000},reduced_motion='reduce')
        for name,url in [('landing','/'),('calendar','/atlas.html?region=norcal&year=2026&month=6'),('investigation','/assistant.html?case=grove-2025'),('evidence','/method.html?case=grove-2025')]:
            requests=[]
            async def record(response):
                if response.url.startswith('http://127.0.0.1:8073'):
                    try: requests.append({'url':response.url,'bytes':len(await response.body()),'status':response.status})
                    except Exception: pass
            page.on('response',record)
            await page.goto('http://127.0.0.1:8073'+url,wait_until='domcontentloaded')
            await page.wait_for_timeout(8000)
            await page.screenshot(path=str(out/f'before-{name}.png'),full_page=False)
            records[name]=requests
            page.remove_listener('response',record)
        await page.set_viewport_size({'width':390,'height':844})
        await page.goto('http://127.0.0.1:8073/atlas.html?region=norcal&year=2026&month=6',wait_until='domcontentloaded')
        await page.wait_for_timeout(4000)
        await page.screenshot(path=str(out/'before-narrow.png'))
        await browser.close()
    (out/'before-loading.json').write_text(json.dumps(records,indent=2)+'\n')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--capture',action='store_true');args=parser.parse_args()
    if not args.capture:parser.error('Explicit --capture required; baseline screenshots must not be overwritten during verification.')
    if Path('docs/implementation/artifacts/before-loading.json').exists():parser.error('Baseline exists; refusing to replace it.')
    asyncio.run(main())
