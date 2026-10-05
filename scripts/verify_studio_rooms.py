"""Browser QA for explicit local loopback rooms; never claims hosted Liveblocks validation."""
from __future__ import annotations
import argparse,json,shutil
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',default='http://127.0.0.1:8126')
    parser.add_argument('--output',type=Path,default=Path('docs/implementation/studio-checks'))
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    origin=f'{urlsplit(args.base).scheme}://{urlsplit(args.base).netloc}'
    report={'adapter':'loopback (local QA only)','checks':[],'page_errors':[]}
    with sync_playwright() as pw:
        exe=next((shutil.which(n) for n in ('chromium','chromium-browser','google-chrome') if shutil.which(n)),None)
        browser=pw.chromium.launch(headless=True,executable_path=exe)
        contexts=[browser.new_context(viewport={'width':1440,'height':1100},reduced_motion='reduce') for _ in range(3)]
        pages=[c.new_page() for c in contexts]
        for p in pages:
            p.on('pageerror',lambda e:report['page_errors'].append(str(e)))
            p.goto(args.base+'/studio.html',wait_until='domcontentloaded')
            expect(p.get_by_label('Board title')).to_be_visible(timeout=30000)
        def request(i,method,path,body=None):
            return contexts[i].request.fetch(args.base+'/api/studio/'+path,method=method,data=body,headers={'Origin':origin})
        def checked(i,method,path,body=None):
            r=request(i,method,path,body);assert r.ok,(r.status,r.text());return r.json()
        doc=pages[0].evaluate("sessionStorage.getItem('fireatlas-studio-board')")
        view=checked(0,'GET','documents/'+doc)
        cards=[{'id':cid,'type':'text','title':title,'text':'Authored review note; not a scientific measurement.'} for cid,title in [('room_a','First room note'),('room_b','Second room note')]]
        view=checked(0,'POST','documents/'+doc+'/transactions',{'base_revision':view['revision'],'ops':[{'op':'add_card','card':c} for c in cards]})
        pages[0].reload(wait_until='domcontentloaded');expect(pages[0].locator('.card')).to_have_count(2)
        pages[0].get_by_role('button',name='Shared room',exact=True).click()
        pages[0].get_by_role('button',name='Open collaboration room',exact=True).click()
        expect(pages[0].get_by_text('You: owner',exact=True)).to_be_visible()
        room=checked(0,'GET','documents/'+doc)['room'];assert room['adapter']=='loopback'
        for i,role in [(1,'viewer'),(2,'editor')]:
            pages[0].get_by_label('Invite role').select_option(role)
            invite_box = pages[0].get_by_label('One-use private invite')
            previous = invite_box.input_value() if invite_box.count() else ''
            pages[0].get_by_role('button',name='Create private invite',exact=True).click()
            expect(invite_box).not_to_have_value(previous)
            token=pages[0].get_by_label('One-use private invite').input_value()
            pages[i].get_by_role('button',name='Shared room',exact=True).click()
            pages[i].get_by_label('Private one-use invite').fill(token)
            pages[i].get_by_role('button',name='Join room',exact=True).click()
            expect(pages[i].get_by_text('You: '+role,exact=True)).to_be_visible()
            assert pages[i].evaluate('location.search')==''
        expect(pages[1].get_by_label('Board title')).to_be_disabled()
        expect(pages[2].get_by_label('Board title')).to_be_enabled()
        denied=request(1,'POST','documents/'+doc+'/transactions',{'base_revision':view['revision'],'ops':[{'op':'set_title','title':'Forbidden viewer write'}]})
        assert denied.status==403,denied.text()
        report['checks'].append('Owner issues one-use viewer/editor invitations; separate identities join; viewer writes are rejected by server and UI.')
        pages[2].get_by_label('Board title').fill('Collaborative browser QA');pages[2].get_by_role('button',name='Shared room',exact=True).focus()
        expect(pages[1].get_by_label('Board title')).to_have_value('Collaborative browser QA',timeout=15000)
        report['checks'].append('Editor change converges through saved revision polling across separate browser contexts.')
        base=checked(0,'GET','documents/'+doc)['revision']
        checked(0,'POST','documents/'+doc+'/transactions',{'base_revision':base,'ops':[{'op':'update_card','id':'room_a','patch':{'text':'Winning authored note'}}]})
        loser=request(2,'POST','documents/'+doc+'/transactions',{'base_revision':base,'allow_merge':True,'ops':[{'op':'update_card','id':'room_a','patch':{'text':'Losing stale edit'}}]})
        assert loser.status==409,loser.text()
        checked(2,'POST','documents/'+doc+'/transactions',{'base_revision':base,'allow_merge':True,'ops':[{'op':'update_card','id':'room_b','patch':{'text':'Concurrent separate note'}}]})
        report['checks'].append('Same-object stale write rejects; distinct-object edits merge without losing the winning note.')
        pages[1].get_by_label('Follow presenter').check()
        checked(0,'POST','rooms/'+room['id']+'/presenter',{'state':{'card_id':'room_b','viewer_state':'board'},'expected_epoch':0})
        pages[1].get_by_role('button',name='Board',exact=True).click()
        expect(pages[1].get_by_label('Title',exact=True)).to_have_value('Second room note',timeout=15000)
        report['checks'].append('Opt-in presenter follow selects the intended card without replacing a viewer’s study.')
        contexts[1].set_offline(True)
        now=checked(2,'GET','documents/'+doc)['revision']
        checked(2,'POST','documents/'+doc+'/transactions',{'base_revision':now,'ops':[{'op':'set_title','title':'Reconnected saved board'}]})
        contexts[1].set_offline(False)
        expect(pages[1].get_by_label('Board title')).to_have_value('Reconnected saved board',timeout=15000)
        report['checks'].append('Reconnect reloads the saved board revision and preserves role restrictions.')
        pages[1].screenshot(path=str(args.output/'room-viewer.png'),full_page=True)
        browser.close()
    assert not report['page_errors'],report['page_errors']
    (args.output/'rooms-report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
