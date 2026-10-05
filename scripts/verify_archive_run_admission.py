"""Archive/map browsing must work in a workspace with more than twenty runs."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',default='http://127.0.0.1:8000')
    parser.add_argument('--output',type=Path,default=Path('docs/implementation/archive-run-admission'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    report={'checks':[],'page_errors':[],'inference_requests':[]}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
        page=context.new_page();page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        def requests(request):
            if request.method=='POST' and request.url.endswith('/api/assistant/runs') and not (request.post_data_json or {}).get('operation'):
                report['inference_requests'].append('conversation')
        page.on('request',requests)
        page.goto(args.base+'/investigate.html?case=park-2024&day=2024-07-30')
        page.wait_for_function("window.FireAtlasAssistant?.isReady() && !FireAtlasAssistant.isBusy() && window.FireAtlasViews?.adapter()?.state?.().ready",timeout=60000)
        def api(path,body=None):
            response=context.request.fetch(args.base+'/api/assistant/'+path,method='GET' if body is None else 'POST',data=body,headers={'Origin':args.base})
            assert response.ok,response.text();return response.json()
        # Use actual deterministic API calls, not fabricated production history.
        for index in range(21):
            session=api('sessions')
            run=api('runs',{'nonce':'archive-admission-'+str(index),'context':session['context'],'view':session['view'],'operation':'method','message':'Read the stored method.'})
            result={}
            for _ in range(100):
                result=api('runs/'+run['id'])
                if result['status'] in {'completed','failed'}:break
                page.wait_for_timeout(50)
            assert result['status']=='completed',result
        answers=api('notebook')['items'];assert len([a for a in answers if a['kind']=='answer'])>=21
        report['checks'].append('An existing browser workspace completes more than twenty requests and retains its saved answers.')
        page.locator('#mission-archive-drawer > summary').click()
        page.locator('#mission-first-year').fill('2006');page.locator('#mission-last-year').fill('2026')
        page.locator('#mission-search-archive').click()
        expect(page.locator('#mission-archive-results .mission-window-open').first).to_be_visible(timeout=60000)
        text=page.locator('#mission-archive-results > p').first.inner_text();assert 'monthly windows' in text and 'imported rows' in text
        report['archive_summary']=text
        assert 'turn limit reached' not in page.locator('#mission-archive-results').inner_text()
        report['checks'].append('The real Search historical readings button returns authentic stored monthly windows after the former daily threshold.')
        page.screenshot(path=str(args.output/'historical-search-restored.png'),full_page=False)
        page.reload()
        page.wait_for_function("window.FireAtlasAssistant?.isReady() && !FireAtlasAssistant.isBusy() && window.FireAtlasViews?.adapter()?.state?.().ready",timeout=60000)
        expect(page.locator('#mission-modis-count')).to_have_text('159')
        expect(page.locator('#mission-viirs-count')).to_have_text('558')
        assert len([a for a in api('notebook')['items'] if a['kind']=='answer'])>=21
        report['checks'].append('Refreshing the same workspace loads the selected Park frame (159 MODIS / 558 VIIRS) without resetting history or replacing its selection.')
        assert not report['page_errors'],report['page_errors'];assert not report['inference_requests'],report['inference_requests'];browser.close()
    (args.output/'browser-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
