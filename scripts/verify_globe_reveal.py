"""Verify the landing globe with Chrome: delayed data, exact return and failure states.
Run with a populated local FireAtlas server and Playwright installed.
"""
import asyncio,argparse
from playwright.async_api import async_playwright,expect
async def main():
 args=argparse.ArgumentParser(description=__doc__)
 args.add_argument('--base',default='http://127.0.0.1:8000')
 args.add_argument('--chrome',default='/usr/bin/google-chrome')
 options=args.parse_args()
 base=options.base.rstrip('/')
 async with async_playwright() as p:
  b=await p.chromium.launch(executable_path=options.chrome,headless=True,args=['--enable-unsafe-swiftshader','--use-angle=swiftshader'])
  ctx=await b.new_context(viewport={'width':1000,'height':760})
  page=await ctx.new_page();errors=[]
  page.on('pageerror',lambda e: errors.append(str(e)))
  response=await ctx.request.get(base+'/api/globe?source=all&date=all',timeout=90000)
  assert response.ok, 'Could not load the verification snapshot'
  payload=await response.text()
  assert (await response.json())['total'] > 0, 'Import NASA observations before running this check'
  gate=asyncio.Event();requested=asyncio.Event()
  async def delayed(route):
   requested.set();await gate.wait();await route.fulfill(content_type='application/json',body=payload)
  await page.route('**/api/globe?*',delayed)
  await page.goto(base+'/',wait_until='domcontentloaded')
  await expect(page.locator('#earth-frame-host.ready')).to_be_visible(timeout=60000)
  await asyncio.wait_for(requested.wait(),15)
  frame=page.frames[1]
  start=await page.evaluate('''()=>{let b=document.querySelector('iframe').contentWindow.fireAtlasEarth;let r=b.view.rotation.slice();let c=document.querySelector('#globe-markers');c.checked=true;c.dispatchEvent(new Event('change'));return r}''')
  await expect(page.locator('#globe-reveal-status')).to_have_text('Loading data…')
  await frame.wait_for_function('fireAtlasEarth.view.revealing === false',timeout=30000)
  assert start==await frame.evaluate('fireAtlasEarth.view.rotation')
  assert await frame.locator('#fire-observations').get_attribute('data-visible')=='0'
  await expect(page.locator('#globe-reveal-status')).to_have_text('Loading data…')
  gate.set()
  await expect(page.locator('#globe-reveal-status')).to_be_hidden(timeout=10000)
  await frame.wait_for_function("Number(document.querySelector('#fire-observations').dataset.visible)>0")
  assert start==await frame.evaluate('fireAtlasEarth.view.rotation')
  print('Delayed data: loading state, full turn, hold exact pose, then reveal PASS',flush=True)
  await page.locator('#globe-markers').uncheck()
  await page.emulate_media(reduced_motion='reduce')
  await page.locator('#globe-markers').check()
  await expect(page.locator('#globe-reveal-status')).to_be_hidden()
  assert await frame.evaluate('fireAtlasEarth.view.playing') is False
  print('Reduced motion: no forced turn PASS',flush=True)
  await page.unroute('**/api/globe?*',delayed)
  await page.route('**/api/globe?*',lambda route:route.fulfill(status=503,content_type='application/json',body='{"error":"Observation service unavailable"}'))
  await page.locator('#globe-date').select_option('2026-09-20')
  await expect(page.locator('#globe-retry')).to_be_visible()
  await expect(page.locator('#globe-markers')).not_to_be_checked()
  await expect(page.locator('#globe-reveal-status')).to_be_hidden()
  assert not errors,errors
  print('Failed data: retry visible, no markers, no stuck loading, no JS errors PASS',flush=True)
  await b.close()
if __name__ == '__main__':
 asyncio.run(main())
