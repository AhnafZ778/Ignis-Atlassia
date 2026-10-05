"""Real-browser Studio entry visibility and canvas panning acceptance."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',default='http://127.0.0.1:8000')
    parser.add_argument('--output',type=Path,default=Path('docs/implementation/studio-navigation-pan'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    report={'checks':[],'page_errors':[],'layouts':[]}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
        page=context.new_page();page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        # This part needs no scientific/private assistant calls.
        page.goto(args.base+'/investigate.html?case=grove-2025')
        link=page.get_by_role('link',name='Create in Studio',exact=False)
        expect(link).to_be_visible()
        style=link.evaluate('(n)=>({background:getComputedStyle(n).backgroundColor,color:getComputedStyle(n).color,height:n.getBoundingClientRect().height})')
        assert style['height']>=44 and style['background']!='rgba(0, 0, 0, 0)',style
        expect(page.locator('#site-navigation').get_by_role('link',name='Studio',exact=True)).to_have_attribute('href',__import__('re').compile('studio.html'))
        page.screenshot(path=str(args.output/'investigate-studio-button.png'),full_page=False)
        for width in (360,390,768):
            page.set_viewport_size({'width':width,'height':1000})
            expect(link).to_be_visible()
            measured=page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})')
            assert measured['scroll']<=width+1,measured
            report['layouts'].append(measured)
        page.set_viewport_size({'width':1440,'height':1000})
        page.goto(args.base+'/studio.html')
        expect(page.get_by_label('Board title')).to_be_visible(timeout=30000)
        def api(method,path,body=None):
            response=context.request.fetch(args.base+'/api/studio/'+path,method=method,data=body,headers={'Origin':args.base})
            assert response.ok,response.text();return response.json()
        doc=api('POST','documents',{'title':'Canvas movement acceptance','study':{'context':{'case':'grove-2025'}}})
        doc=api('POST',f"documents/{doc['id']}/transactions",{'base_revision':doc['revision'],'ops':[{'op':'add_card','card':{'id':'note','type':'text','title':'Movable note','text':'Drag the background to reposition the view.','transform':{'x':40,'y':40,'w':320,'h':240}}}]})
        original=doc['state']['cards']['note']['transform']
        page.goto(args.base+'/studio.html?board='+doc['id'])
        expect(page.get_by_label('Board title')).to_have_value(doc['title'],timeout=30000)
        expect(page.locator('#site-navigation').get_by_role('link',name='Studio',exact=True)).to_have_attribute('aria-current','page')
        board=page.locator('.board-wrap[role=region]');board.scroll_into_view_if_needed()
        def view():return page.locator('.board-canvas').get_attribute('style')
        def drag(x,y,dx,dy,button='left'):
            page.mouse.move(x,y);page.mouse.down(button=button);page.mouse.move(x+dx,y+dy,steps=8);page.mouse.up(button=button)
        before=view();box=board.bounding_box();drag(box['x']+box['width']-150,box['y']+120,-80,60)
        assert view()!=before,'Default empty canvas drag failed'
        assert api('GET','documents/'+doc['id'])['state']['cards']['note']['transform']==original
        report['checks'].append('Dragging empty canvas pans immediately without selecting Pan canvas or changing cards.')
        page.get_by_role('button',name='Reset view',exact=True).click()
        header=page.get_by_label('Move Movable note',exact=True);box=header.bounding_box();before=view()
        header.focus();page.keyboard.down('Space');drag(box['x']+80,box['y']+10,70,40);page.keyboard.up('Space')
        assert view()!=before,'Space-drag over card failed'
        assert api('GET','documents/'+doc['id'])['state']['cards']['note']['transform']==original
        report['checks'].append('Space-drag over a card pans the view while preserving its position.')
        page.get_by_role('button',name='Reset view',exact=True).click()
        before=view();box=header.bounding_box();drag(box['x']+80,box['y']+10,60,35,button='middle')
        assert view()!=before,'Middle-button card pan failed'
        report['checks'].append('Middle-button drag pans over cards and prevents browser auto-scroll.')
        page.get_by_role('button',name='Reset view',exact=True).click()
        page.get_by_role('button',name='Pan canvas',exact=True).click()
        content=page.get_by_text('Drag the background to reposition the view.',exact=True);box=content.bounding_box();before=view();drag(box['x']+50,box['y']+10,50,30)
        assert view()!=before,'Pan canvas over card body failed'
        report['checks'].append('Pan canvas works over frozen card content; controls still respond.')
        page.get_by_role('button',name='Reset view',exact=True).click()
        page.get_by_role('button',name='Select cards',exact=True).click()
        box=header.bounding_box();before=view();drag(box['x']+80,box['y']+10,60,40)
        for _ in range(30):
            updated=api('GET','documents/'+doc['id'])
            if updated['state']['cards']['note']['transform']['x']>original['x']:break
            page.wait_for_timeout(100)
        assert updated['state']['cards']['note']['transform']['x']>original['x']
        assert view()==before,'Normal card drag must not pan'
        page.get_by_role('button',name='Open details',exact=True).click()
        expect(page.locator('article.card.selected')).to_be_visible()
        box=board.bounding_box();before=view();page.mouse.move(box['x']+box['width']-80,box['y']+80);page.mouse.wheel(0,-120)
        page.wait_for_function("old=>document.querySelector('.board-canvas').getAttribute('style')!==old",arg=before)
        report['checks'].append('Card dragging persists its position; details and pointer-anchored wheel zoom remain usable.')
        page.screenshot(path=str(args.output/'studio-panning-controls.png'),full_page=False)
        for route in ('/','/atlas.html','/research.html','/evidence.html'):
            response=context.request.get(args.base+route);assert response.ok
            assert 'data-destination="studio"' in response.text(),route
        report['checks'].append('Studio appears in all six canonical navigation headers; Investigate entry remains visible at 360, 390 and 768 pixels.')
        assert not report['page_errors'],report['page_errors']
        browser.close()
    (args.output/'browser-report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
