"""Real-browser creation, renaming and persisted investigation names."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from playwright.sync_api import sync_playwright, expect


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',default='http://127.0.0.1:8000')
    parser.add_argument('--output',type=Path,default=Path('docs/implementation/investigation-names'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    report={'checks':[],'page_errors':[],'layouts':[]}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
        page=context.new_page();page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        page.goto(args.base+'/studio.html')
        expect(page.get_by_label('Board title')).to_be_visible(timeout=30000)
        original_name=page.get_by_label('Board title').input_value()
        page.get_by_role('button',name='Blank investigation',exact=True).click()
        dialog=page.get_by_role('dialog',name='Name your investigation',exact=True)
        expect(dialog).to_be_visible()
        dialog.get_by_label('Investigation name',exact=True).fill('Park sensor comparison')
        dialog.get_by_label('Investigation name',exact=True).press('Enter')
        expect(dialog).not_to_be_visible(timeout=15000)
        expect(page.get_by_label('Board title')).to_have_value('Park sensor comparison')
        identifier=parse_qs(urlsplit(page.url).query)['board'][0]
        response=context.request.get(args.base+'/api/studio/documents/'+identifier);assert response.ok
        original=response.json()['state']
        assert original['title']=='Park sensor comparison'
        name=page.get_by_label('Board title');name.fill('Northern California · July analysis')
        page.get_by_role('button',name='Save name',exact=True).click()
        expect(page.get_by_text('Investigation name saved.',exact=True)).to_be_visible(timeout=10000)
        response=context.request.get(args.base+'/api/studio/documents/'+identifier);changed=response.json()
        assert changed['title']=='Northern California · July analysis'
        assert changed['state']['cards']==original['cards'] and changed['state']['study']==original['study']
        expect(page.get_by_label('Saved investigation').locator('option:checked')).to_have_text(changed['title'])
        page.reload();expect(page.get_by_label('Board title')).to_have_value(changed['title'],timeout=30000)
        report['checks'].append('Named creation and explicit rename persist through refresh, retaining cards and scientific selection.')
        page.get_by_role('button',name='Undo',exact=True).click()
        expect(page.get_by_label('Board title')).to_have_value('Park sensor comparison')
        page.get_by_role('button',name='Redo',exact=True).click()
        expect(page.get_by_label('Board title')).to_have_value(changed['title'])
        report['checks'].append('Renaming uses the existing revisioned transaction and supports Undo/Redo.')
        page.get_by_role('button',name='Blank investigation',exact=True).click()
        dialog.get_by_label('Investigation name',exact=True).fill('Do not create this')
        dialog.get_by_role('button',name='Cancel',exact=True).click()
        assert page.get_by_label('Board title').input_value()==changed['title']
        expect(page.get_by_role('button',name='Blank investigation',exact=True)).to_be_focused()
        report['checks'].append('Cancel leaves the investigation unchanged and restores focus.')
        page.get_by_role('button',name='Blank investigation',exact=True).click()
        dialog.get_by_label('Investigation name',exact=True).fill('Second investigation')
        dialog.get_by_role('button',name='Create investigation',exact=True).click()
        expect(dialog).not_to_be_visible(timeout=15000)
        page.get_by_label('Saved investigation').select_option(identifier)
        expect(page.get_by_label('Board title')).to_have_value(changed['title'])
        page.reload();expect(page.get_by_label('Board title')).to_have_value(changed['title'],timeout=30000)
        report['checks'].append('Renamed investigations remain correctly labeled after switching away, returning and refreshing.')
        for width in (360,390,768):
            page.set_viewport_size({'width':width,'height':1000})
            expect(page.get_by_role('button',name='Save name',exact=True)).to_be_visible()
            size=page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})');assert size['scroll']<=width+1,size
            report['layouts'].append(size)
        page.screenshot(path=str(args.output/'investigation-name.png'),full_page=False)
        assert not report['page_errors'],report['page_errors'];browser.close()
    (args.output/'browser-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':main()
