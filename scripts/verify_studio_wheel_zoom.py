"""Verify canvas wheel input zooms without scrolling nested content or the page."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',default='http://127.0.0.1:8000')
    parser.add_argument('--output',type=Path,default=Path('docs/implementation/studio-wheel-zoom'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    report={'checks':[],'page_errors':[],'wheel_warnings':[]}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1100},reduced_motion='reduce')
        page=context.new_page();page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        page.on('console',lambda msg:report['wheel_warnings'].append(msg.text) if 'passive' in msg.text.lower() and 'prevent' in msg.text.lower() else None)
        page.goto(args.base+'/studio.html')
        expect(page.get_by_label('Board title')).to_be_visible(timeout=30000)
        def api(method,path,body=None):
            response=context.request.fetch(args.base+'/api/studio/'+path,method=method,data=body,headers={'Origin':args.base})
            assert response.ok,response.text();return response.json()
        doc=api('POST','documents',{'title':'Wheel zoom acceptance','study':{'context':{'case':'grove-2025'}}})
        doc=api('POST',f"documents/{doc['id']}/transactions",{'base_revision':doc['revision'],'ops':[{'op':'add_card','card':{'id':'note','type':'text','title':'Scrollable note','text':'\n'.join('Evidence line '+str(i) for i in range(120)),'transform':{'x':40,'y':40,'w':420,'h':350}}}]})
        page.goto(args.base+'/studio.html?board='+doc['id'])
        expect(page.get_by_label('Board title')).to_have_value(doc['title'],timeout=30000)
        board=page.locator('.board-wrap[role=region]');board.scroll_into_view_if_needed()
        body=page.locator('.card-body');button=page.get_by_role('button',name='Open details',exact=True)
        def state():
            return page.evaluate('''()=>{const b=document.querySelector('.board-wrap[role=region]'),c=document.querySelector('.board-canvas'),inner=document.querySelector('.card-body'),m=new DOMMatrix(getComputedStyle(c).transform);return {zoom:m.a,x:m.e,y:m.f,boardX:b.scrollLeft,boardY:b.scrollTop,cardY:inner.scrollTop,pageY:scrollY}}''')
        for name,locator in [('card content',body),('card control',button),('card heading',page.get_by_label('Move Scrollable note',exact=True))]:
            page.get_by_role('button',name='Reset view',exact=True).click();box=locator.bounding_box();page.mouse.move(box['x']+box['width']/2,box['y']+min(45,box['height']/2))
            before=state();page.mouse.wheel(0,120)
            page.wait_for_function('z=>new DOMMatrix(getComputedStyle(document.querySelector(".board-canvas")).transform).a<z',arg=before['zoom'])
            after=state();assert after['boardY']==before['boardY'] and after['cardY']==before['cardY'] and after['pageY']==before['pageY'],(name,before,after)
            page.mouse.wheel(0,-120)
            page.wait_for_function('z=>new DOMMatrix(getComputedStyle(document.querySelector(".board-canvas")).transform).a>z',arg=after['zoom'])
            report['checks'].append('Wheel zooms both directions over '+name+' without scrolling the board, card or page.')
        page.get_by_role('button',name='Reset view',exact=True).click()
        board.evaluate('(n)=>{n.scrollLeft=100;n.scrollTop=20}')
        box=board.bounding_box();px=box['x']+box['width']-120;py=box['y']+120;page.mouse.move(px,py)
        before=state();page.mouse.wheel(0,-120)
        page.wait_for_function('z=>new DOMMatrix(getComputedStyle(document.querySelector(".board-canvas")).transform).a>z',arg=before['zoom'])
        after=state();ox=px-box['x']-board.evaluate('(n)=>n.clientLeft');oy=py-box['y']-board.evaluate('(n)=>n.clientTop')
        assert abs((ox+before['boardX']-before['x'])/before['zoom']-(ox+after['boardX']-after['x'])/after['zoom'])<1
        assert abs((oy+before['boardY']-before['y'])/before['zoom']-(oy+after['boardY']-after['y'])/after['zoom'])<1
        report['checks'].append('Pointer anchor includes manually scrolled canvas offsets; manual scrolling remains available.')
        # A nested handler (such as a live map) must never also consume the wheel.
        page.get_by_role('button',name='Reset view',exact=True).click()
        body.evaluate('(n)=>{window.nestedWheels=0;n.addEventListener("wheel",()=>window.nestedWheels++)}')
        box=body.bounding_box();page.mouse.move(box['x']+100,box['y']+50);page.mouse.wheel(0,80);page.wait_for_timeout(100)
        assert page.evaluate('window.nestedWheels')==0
        report['checks'].append('Native non-passive capture prevents nested handlers from scrolling or applying a second zoom.')
        before=state();page.mouse.move(5,600);page.mouse.wheel(0,160);page.wait_for_timeout(150)
        assert state()['zoom']==before['zoom']
        assert api('GET','documents/'+doc['id'])['state']['cards']['note']['transform']==doc['state']['cards']['note']['transform']
        report['checks'].append('Outside-canvas wheel leaves canvas zoom unchanged; zoom does not mutate card positions.')
        assert not report['page_errors'],report['page_errors'];assert not report['wheel_warnings'],report['wheel_warnings']
        browser.close()
    (args.output/'browser-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
