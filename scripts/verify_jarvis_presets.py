"""Exercise prompt choices and real authentic presentation delivery, without inference."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from playwright.sync_api import sync_playwright, expect


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',default='http://127.0.0.1:8000')
    parser.add_argument('--output',type=Path,default=Path('docs/implementation/jarvis-preset-checks'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    report={'checks':[],'page_errors':[],'inference_requests':[]}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
        page=context.new_page();page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        def record_request(request):
            path=urlsplit(request.url).path
            if request.method=='POST' and path=='/api/assistant/runs':
                body=request.post_data_json or {}
                if not body.get('operation'):report['inference_requests'].append(path)
            elif '/assistant/start' in path:report['inference_requests'].append(path)
        page.on('request',record_request)
        page.goto(args.base+'/studio.html?case=park-2024')
        expect(page.get_by_label('Board title')).to_be_visible(timeout=30000)
        def api(method,path,body=None):
            response=context.request.fetch(args.base+'/api/studio/'+path,method=method,data=body,headers={'Origin':args.base})
            assert response.ok,response.text()
            return response.json()
        target=api('POST','documents',{'title':'Presentation destination QA','study':{'context':{'case':'park-2024'}}})
        target=api('POST',f"documents/{target['id']}/transactions",{'base_revision':target['revision'],'ops':[{'op':'add_card','card':{'id':'keep-note','type':'text','title':'Existing note','text':'Preserve this unrelated note.'}}]})
        original=target['state']['cards']['keep-note']
        page.locator('.jarvis-panel > summary').click()
        page.get_by_role('button',name='Grove Fire 2025 presentation',exact=True).click()
        page.get_by_role('button',name='Ask JARVIS',exact=True).click()
        expect(page.get_by_role('group',name='Which Canvas should receive this investigation?')).to_be_visible()
        assert len(api('GET',f"documents/{target['id']}")['state']['cards'])==1
        page.get_by_role('combobox',name='Canvas destination',exact=True).select_option(target['id'])
        page.screenshot(path=str(args.output/'canvas-choice.png'),full_page=True)
        page.get_by_role('button',name='Create presentation on selected Canvas',exact=True).click()
        page.wait_for_url('**/studio.html?**command=**',timeout=120000)
        expect(page.get_by_label('Board title')).to_have_value('Presentation destination QA',timeout=30000)
        doc=api('GET',f"documents/{target['id']}")
        assert doc['state']['cards']['keep-note']==original
        assert len(doc['state']['cards'])>=12 and len(doc['state']['groups'])==4
        assert all(c['pinned_study']['context']['case']=='grove-2025' for cid,c in doc['state']['cards'].items() if cid!='keep-note')
        query=parse_qs(urlsplit(page.url).query);command=api('GET','commands/'+query['command'][0])
        for _ in range(30):
            if command['status']=='completed':break
            page.wait_for_timeout(200);command=api('GET','commands/'+command['id'])
        assert command['status']=='completed',command
        package=api('GET','packages/'+command['outputs']['package_id'])
        story=api('GET','stories/'+command['outputs']['story_id'])
        assert len(story['body']['chapters'])==6 and story['resolved']
        assert not [w for w in story['resolved']['warnings'] if w['problem']=='scene-context'],story['resolved']['warnings']
        facts=[f for snapshot in doc['snapshots'].values() for f in snapshot['facts']]
        assert any(f['value']==7 and f['unit']=='records' for f in facts)
        assert any(f['value']==4 and f['unit']=='cell-days' for f in facts)
        page.get_by_role('button',name='Fit all cards',exact=True).click()
        page.get_by_role('region',name='Evidence canvas',exact=True).scroll_into_view_if_needed()
        expect(page.locator('canvas[data-source="MODIS_SP"]')).to_have_attribute('data-day','2025-07-04',timeout=30000)
        expect(page.locator('canvas[data-source="VIIRS_SNPP_SP"]')).to_have_attribute('data-day','2025-07-04',timeout=30000)
        page.screenshot(path=str(args.output/'grove-composed-canvas.png'),full_page=True)
        page.get_by_role('button',name='Workflow',exact=True).click()
        expect(page.get_by_role('heading',name='Workflow Composer')).to_be_visible(timeout=30000)
        page.get_by_role('button',name='Validate graph',exact=True).click()
        expect(page.get_by_text('Valid graph:',exact=False)).to_be_visible()
        report['checks'] += ['Studio prompt asks for destination before any board change.','Named Grove presentation appends to the chosen Canvas without changing its existing note or board study.','Grove retains seven authentic eligible detections and four joint cell-days.','Composed cards, four groups, six resolved story chapters and registered workflow persist and acknowledge the actual destination.']
        page.goto(args.base+'/investigate.html?case=park-2024&day=2024-07-30')
        page.wait_for_function("window.FireAtlasOrchestration && window.FireAtlasViews?.adapter()?.describeView && window.FireAtlasAssistant?.isReady()",timeout=60000)
        expect(page.get_by_role('button',name='Present this study',exact=True)).to_be_enabled(timeout=60000)
        assert not page.get_by_text('Selection unavailable:',exact=False).count()
        page.get_by_role('button',name='Present this study',exact=True).click()
        expect(page.get_by_role('group',name='Which Canvas should receive this investigation?')).to_be_visible(timeout=30000)
        page.get_by_role('combobox',name='Canvas destination',exact=True).select_option('new')
        page.get_by_role('button',name='Create presentation on selected Canvas',exact=True).click()
        page.wait_for_url('**/studio.html?**command=**',timeout=120000)
        expect(page.get_by_label('Board title')).to_be_visible(timeout=30000)
        query=parse_qs(urlsplit(page.url).query);park=api('GET','documents/'+query['board'][0])
        assert len(park['state']['cards'])>=11
        assert park['state']['study']['context']['day']=='2024-07-30'
        facts=[f for snapshot in park['snapshots'].values() for f in snapshot['facts']]
        assert any(f['value']==6224 and f['unit']=='records' for f in facts)
        assert any(f['value']==2228 and f['unit']=='cell-days' for f in facts)
        report['checks'].append('Investigate prompt captures the selected Park frame and creates a comprehensive new Canvas with 6,224 detections and 2,228 joint cell-days.')
        page.get_by_role('button',name='Fit all cards',exact=True).click()
        page.get_by_role('region',name='Evidence canvas',exact=True).scroll_into_view_if_needed()
        expect(page.locator('canvas[data-source="MODIS_SP"]')).to_have_attribute('data-day','2024-07-30',timeout=30000)
        expect(page.locator('canvas[data-source="VIIRS_SNPP_SP"]')).to_have_attribute('data-day','2024-07-30',timeout=30000)
        page.screenshot(path=str(args.output/'park-composed-canvas.png'),full_page=True)
        modis=page.locator('canvas[data-source="MODIS_SP"]');viirs=page.locator('canvas[data-source="VIIRS_SNPP_SP"]')
        domain=modis.get_attribute('data-maximum');assert domain==viirs.get_attribute('data-maximum')
        canvas=page.locator('.board-wrap');viewport_before=page.locator('.board-canvas').get_attribute('style')
        box=canvas.bounding_box();page.mouse.move(box['x']+box['width']-30,box['y']+80);page.mouse.wheel(0,-120)
        page.wait_for_function("before => document.querySelector('.board-canvas').getAttribute('style') !== before",arg=viewport_before)
        assert modis.get_attribute('data-maximum')==domain
        head=page.get_by_label('Move MODIS · occupied-cell heat',exact=True);head.focus();head.press('ArrowRight')
        page.wait_for_function("card => document.querySelector('[aria-label=\"Move MODIS · occupied-cell heat\"]').closest('article').style.left !== card",arg='500px')
        for _ in range(30):
            revised=api('GET','documents/'+query['board'][0]);moved=next(c for c in revised['state']['cards'].values() if c['title']=='MODIS · occupied-cell heat')
            if moved['transform']['x']>500:break
            page.wait_for_timeout(100)
        assert moved['transform']['x']>500
        report['checks'].append('Prepared paired heat maps share their study domain; pointer zoom and keyboard card movement work after packaging.')

        assert not report['page_errors'],report['page_errors']
        assert not report['inference_requests'],report['inference_requests']
        browser.close()
    (args.output/'browser-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
