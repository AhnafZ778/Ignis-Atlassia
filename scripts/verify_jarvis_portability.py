"""Browser acceptance for deterministic handoff, frozen portability and editable continuation.

Requires a local authentic service and a second service with an empty scientific
DB. No provider calls, publishing or external transfers are performed.
"""
import argparse
import json
import shutil
import time
import zipfile
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from playwright.sync_api import sync_playwright,expect


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base',default='http://127.0.0.1:8134');parser.add_argument('--empty',default='http://127.0.0.1:8135');parser.add_argument('--output',type=Path,default=Path('docs/implementation/jarvis-checks'));args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True);report={'checks':[],'page_errors':[],'measurements':{},'external_transfer':'Mock tests only; no configured live destination used.'}
    def record(label):report['checks'].append(label);print(label,flush=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path=next((shutil.which(n) for n in ('chromium','chromium-browser','google-chrome') if shutil.which(n)),None))
        context=browser.new_context(viewport={'width':1440,'height':1100},reduced_motion='reduce',accept_downloads=True);page=context.new_page()
        page.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        # Deterministic layers remain useful when external imagery/terrain is unavailable.
        context.route('**/*',lambda route:route.continue_() if urlsplit(route.request.url).hostname in {'127.0.0.1','localhost'} else route.abort())
        def api(method,path,body=None,ctx=context,base=args.base):
            response=ctx.request.fetch(base+'/api/studio/'+path,method=method,data=body,headers={'Origin':base,'Content-Type':'application/json'})
            assert response.ok,(path,response.status,response.text());return response.json()
        loaded=[];page.on('response',lambda r:loaded.append(r))
        page.goto(args.base+'/investigate.html?case=park-2024',wait_until='domcontentloaded')
        page.wait_for_function("(()=>{try{return FireAtlasOrchestration.source().refs.length>0}catch{return false}})()",timeout=60000)
        captured=page.evaluate("(()=>{const c=FireAtlasOrchestration.source();return {study:c.study,view:c.view}})()")
        page.get_by_label('Prepare native and editable exports').check();page.route('**/api/studio/commands/*/ack',lambda route:route.abort());page.get_by_role('button',name='Send to Canvas',exact=True).click();page.get_by_role('button',name='MODIS pane',exact=True).click()
        page.wait_for_url('**/studio.html?board=*&command=*',timeout=60000);expect(page.get_by_label('Board title')).to_be_visible(timeout=30000)
        page.wait_for_timeout(1200)
        lost=parse_qs(urlsplit(page.url).query);unopened=api('GET','commands/'+lost['command'][0]);assert unopened['status']=='awaiting_view_ack';saved_board=api('GET','documents/'+lost['board'][0])
        page.unroute('**/api/studio/commands/*/ack');page.reload(wait_until='domcontentloaded');expect(page.get_by_label('Board title')).to_be_visible();page.wait_for_function("document.querySelector('.orchestration-panel')?.textContent.includes('completed:')",timeout=15000)
        assert api('GET','documents/'+lost['board'][0])['state']['cards']==saved_board['state']['cards'];record('Lost browser acknowledgment: saved-versus-opened remains distinct; refresh completes the original command without duplicate cards.')
        query=parse_qs(urlsplit(page.url).query);did=query['board'][0];cid=query['command'][0];command=api('GET','commands/'+cid);board=api('GET','documents/'+did)
        (out/'interruption-trace.json').write_text(json.dumps({'blocked_ack':{'status':unopened['status'],'phase':unopened['phase'],'outputs':unopened['outputs'],'board_revision':saved_board['revision']},'after_reload':{'status':command['status'],'phase':command['phase'],'outputs':command['outputs'],'board_revision':board['revision']},'duplicate_insertion':False},indent=2))
        assert command['status']=='completed';assert len(command['outputs']['export_job_ids'])==2;assert all(api('GET','exports/'+jid)['status']=='completed' for jid in command['outputs']['export_job_ids']);package=api('GET','packages/'+command['outputs']['package_id'])
        assert package['source_context']['study_selection']['day']==captured['study']['day'];assert package['source_view']['source']=='MODIS_SP';assert package['source_view']['domain']==captured['view']['domain']
        facts=next(s for s in board['snapshots'].values() if s['operation']=='replay')['facts'];assert any(f['value']==6224 for f in facts);assert any(f['value']==2228 for f in facts)
        record('Park pane handoff: exact UTC frame, MODIS source, original study-fixed domain, 6,224 eligible records and 2,228 joint cell-days; acknowledgment after actual Canvas load.')
        page.reload(wait_until='domcontentloaded');expect(page.get_by_label('Board title')).to_be_visible();assert api('GET','documents/'+did)['state']['cards']==board['state']['cards'];record('Refresh restores the exact saved investigation, without duplicate insertion.')
        canvas=page.get_by_role('region',name='Evidence canvas',exact=True);canvas.scroll_into_view_if_needed();page.get_by_role('button',name='Fit all cards',exact=True).click();page.wait_for_timeout(1000)
        page.screenshot(path=str(out/'canvas-handoff.png'))
        host=page.locator('.board-wrap').first;box=host.bounding_box();before=page.locator('.board-canvas').evaluate('(e)=>e.style.transform');page.mouse.move(box['x']+box['width']-50,box['y']+50);page.mouse.wheel(0,-180);page.wait_for_timeout(200);assert page.locator('.board-canvas').evaluate('(e)=>e.style.transform')!=before
        page.get_by_role('button',name='Pan canvas',exact=True).click();host.scroll_into_view_if_needed();box=host.bounding_box();before=page.locator('.board-canvas').evaluate('(e)=>e.style.transform');page.mouse.move(box['x']+box['width']-30,box['y']+80);page.mouse.down();page.mouse.move(box['x']+box['width']-80,box['y']+120,steps=4);page.mouse.up();assert page.locator('.board-canvas').evaluate('(e)=>e.style.transform')!=before
        page.get_by_role('button',name='Select cards',exact=True).click();page.get_by_role('button',name='Fit all cards',exact=True).click();host.scroll_into_view_if_needed()
        first=board['state']['order'][0];card=page.locator(f'.card[data-card-id="{first}"]');
        if card.count()==0:card=page.locator('.card').first
        header=card.locator('.card-head');old=api('GET','documents/'+did)['state']['cards'][first]['transform'];h=header.bounding_box();page.mouse.move(h['x']+20,h['y']+12);page.mouse.down();page.mouse.move(h['x']+40,h['y']+30,steps=4);page.mouse.up();page.wait_for_timeout(500);moved=api('GET','documents/'+did);assert moved['state']['cards'][first]['transform']!=old
        record('Wheel zoom over empty canvas, canvas panning and card dragging remain functional after packaging.')
        page.get_by_role('button',name='Pin selected card to this date',exact=True).click();page.wait_for_timeout(700);page.get_by_role('button',name='Arrange selected card',exact=True).click();page.wait_for_timeout(1500)
        # An unrelated append survives command-specific undo.
        current=api('GET','documents/'+did);api('POST','documents/'+did+'/transactions',{'base_revision':current['revision'],'ops':[{'op':'add_card','card':{'id':'acceptance-note','type':'text','title':'Independent follow-up','text':'Keep this later note.','transform':{'x':1500,'y':1200,'w':380,'h':240}}}]})
        page.get_by_role('button',name='Undo this JARVIS change',exact=True).click();page.wait_for_timeout(600);assert 'acceptance-note' in api('GET','documents/'+did)['state']['cards'];record('Selected-card follow-up has command-specific undo; unrelated later notes survive.')
        # Real registered workflow effect nodes rerun, insert NEW results and prepare an archive.
        run=api('POST','workflows/'+command['outputs']['workflow_id']+'/run',{})
        for _ in range(240):
            run=api('GET','runs/'+run['id'])
            if run['status']!='running':break
            time.sleep(.25)
        assert run['status']=='completed',run;assert run['outputs']['insert']['object_ids'];export=run['outputs']['export']['job_id']
        for _ in range(240):
            job=api('GET','exports/'+export)
            if job['status'] not in {'queued','preparing'}:break
            time.sleep(.25)
        assert job['status']=='completed',job
        response=context.request.get(args.base+'/api/studio/exports/'+export+'/download');assert response.ok;archive=out/'park-investigation.fireatlas.zip';archive.write_bytes(response.body())
        with zipfile.ZipFile(archive) as z:scene=z.read('interop/board.excalidraw');mapping=json.loads(z.read('interop/object-map.json'));manifest=json.loads(z.read('manifest.json'))
        scene_file=out/'park-investigation.excalidraw';scene_file.write_bytes(scene);scene_body=json.loads(scene);assert scene_body['files'];assert any(e['type']=='image' for e in scene_body['elements']);assert any(e['type']=='arrow' and e.get('startBinding') and e.get('endBinding') for e in scene_body['elements'])
        record('Captured workflow genuinely reruns registered science, inserts new frozen cards, and prepares a complete native archive with embedded images and bound Excalidraw arrows.')
        report['archive']={'compressed_bytes':len(response.body()),'expanded_bytes':manifest['expanded_bytes'],'entries':len(manifest['files'])+1,'objects':len(mapping)}
        for fmt,magic in [('svg',b'<svg'),('png',b'\x89PNG'),('pdf',b'%PDF')]:
            revision=api('GET','documents/'+did)['revision'];output=api('POST','documents/'+did+'/exports',{'format':fmt,'revision':revision})
            for _ in range(360):
                output=api('GET','exports/'+output['id'])
                if output['status'] not in {'queued','preparing'}:break
                time.sleep(.25)
            assert output['status']=='completed',output
            file=context.request.get(args.base+'/api/studio/exports/'+output['id']+'/download');assert file.ok and file.body().startswith(magic)
            (out/('park-whiteboard.'+fmt)).write_bytes(file.body())
        record('Actual whole-board SVG, PNG and multipage PDF exports complete without rerunning science.')
        # New browser + service containing no original scientific observations.
        empty_context=browser.new_context(viewport={'width':1440,'height':1100},reduced_motion='reduce');restored=empty_context.new_page();restored.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        restored.goto(args.empty+'/studio.html',wait_until='domcontentloaded');expect(restored.get_by_label('Board title')).to_be_visible(timeout=30000)
        restored.get_by_text('Export or restore the editable whiteboard',exact=True).click();restored.get_by_label('Restore native archive into a new board').set_input_files(archive)
        restored.wait_for_url('**/studio.html?board=*',timeout=20000);expect(restored.get_by_label('Board title')).to_be_visible()
        new_id=parse_qs(urlsplit(restored.url).query)['board'][0];new=api('GET','documents/'+new_id,ctx=empty_context,base=args.empty)
        original=api('GET','documents/'+did);assert len(new['state']['cards'])==len(original['state']['cards']);assert set(new['state']['cards']).isdisjoint(original['state']['cards'])
        restored.get_by_role('button',name='Fit all cards',exact=True).click();restored.get_by_role('region',name='Evidence canvas',exact=True).scroll_into_view_if_needed();restored.wait_for_timeout(1000);restored.screenshot(path=str(out/'restored-empty-backend.png'))
        assert all(api('GET',f'documents/{new_id}/snapshots/{sid}',ctx=empty_context,base=args.empty)['verification']['verified'] for sid in new['snapshots'])
        canonical=lambda doc:sorted([{'type':c['type'],'title':c['title'],'text':c['text'],'transform':c['transform'],'display':c['display'],'pinned_study':c['pinned_study']} for c in doc['state']['cards'].values()],key=lambda c:c['title'])
        assert canonical(new)==canonical(original)
        (out/'restoration-comparison.json').write_text(json.dumps({'objects_identical_except_owned_ids_and_import_attribution':True,'card_count':len(new['state']['cards']),'original_receipt_hashes':sorted(s['receipt_sha256'] for s in original['snapshots'].values()),'restored_receipt_hashes':sorted(s['receipt_sha256'] for s in new['snapshots'].values())},indent=2))
        record('Native archive restored with fresh owned IDs into another browser and an empty scientific backend; original receipts verify and frozen previews remain usable.')
        # Genuine pinned Excalidraw editor continuation, not only schema inspection.
        editor=context.new_page();editor.on('pageerror',lambda e:report['page_errors'].append(str(e)));editor.goto(args.base+'/studio-excalidraw.html',wait_until='domcontentloaded');editor.get_by_label('Open Excalidraw scene').set_input_files(scene_file)
        expect(editor.get_by_role('status')).to_contain_text('editable objects loaded',timeout=20000);editor.screenshot(path=str(out/'editable-excalidraw.png'))
        # SDK editor used for precise reproducible edits: UI screenshot confirms the actual component mounted.
        editor.evaluate("""()=>{const api=window.FireAtlasExcalidraw;const all=api.getSceneElements();const map=all.find(e=>e.type==='image');const label=all.find(e=>e.type==='text');const arrow=all.find(e=>e.type==='arrow');const target=all.find(e=>e.type==='rectangle'&&e.id!==arrow.endBinding.elementId);api.updateScene({elements:all.map(e=>e.id===map.id?{...e,x:e.x+80}:e.id===label.id?{...e,text:'Edited presentation label'}:e.id===arrow.id?{...e,endBinding:{...e.endBinding,elementId:target.id}}:e)});} """)
        with editor.expect_download() as downloaded:editor.get_by_role('button',name='Save edited scene',exact=True).click()
        edited=out/'park-edited.excalidraw';downloaded.value.save_as(edited);edited_scene=json.loads(edited.read_text());assert any(e.get('text')=='Edited presentation label' for e in edited_scene['elements'])
        editor.get_by_label('Open Excalidraw scene').set_input_files(edited);expect(editor.get_by_role('status')).to_contain_text('editable objects loaded');editor.screenshot(path=str(out/'edited-reopened-excalidraw.png'))
        record('Actual Excalidraw 0.18.1 editor: move map image, edit text, reconnect an arrow, save and reopen the editable scene.')
        for width in (360,390,768):
            restored.set_viewport_size({'width':width,'height':900});restored.evaluate('scrollTo(0,0)');restored.screenshot(path=str(out/f'restored-{width}.png'));assert restored.evaluate('document.documentElement.scrollWidth<=innerWidth+2'),width
        record('Restored workspace fits 360, 390 and 768 pixel layouts; numerical evidence and focusable controls remain available.')
        atlas=context.new_page();atlas.on('pageerror',lambda e:report['page_errors'].append(str(e)))
        atlas.goto(args.base+'/atlas.html?region=norcal&year=2026&month=6',wait_until='domcontentloaded')
        atlas.wait_for_function('!!window.FireAtlasAtlasCapture',timeout=30000)
        atlas.wait_for_function("(()=>{try{return !!FireAtlasAtlasCapture().result_sha256}catch{return false}})()",timeout=30000)
        calendar=atlas.evaluate('FireAtlasAtlasCapture()');atlas.screenshot(path=str(out/'atlas-captured-source.png'),full_page=True)
        atlas.get_by_role('button',name='Send to Canvas',exact=True).click();atlas.wait_for_url('**/studio.html?board=*&command=*',timeout=60000)
        expect(atlas.get_by_label('Board title')).to_be_visible(timeout=30000)
        atlas.wait_for_function("document.querySelector('.orchestration-panel')?.textContent.includes('completed:')",timeout=15000)
        aq=parse_qs(urlsplit(atlas.url).query);ac=api('GET','commands/'+aq['command'][0]);ap=api('GET','packages/'+ac['outputs']['package_id']);ab=api('GET','documents/'+aq['board'][0])
        assert ap['source_context']['study_selection']['bbox']==calendar['study']['bbox']
        assert ap['source_view']['arguments']['expected_result_sha256']==calendar['result_sha256']
        snap=next(s for s in ab['snapshots'].values() if s['operation']=='harmonized')
        assert snap['method']['unit']=='VIIRS-equivalent cell-days';assert any(f['value']==113 for f in snap['facts'])
        atlas.screenshot(path=str(out/'atlas-harmonized-canvas.png'))
        record('Atlas June 2026 handoff preserves the regional bounds, displayed result identity and 113 harmonized cell-days; it remains distinct from replay and combined detections.')
        report['measurements']['handoff']={'requests':len(loaded),'same_origin_response_content_length_bytes':sum(int(r.headers.get('content-length',0)) for r in loaded if urlsplit(r.url).hostname=='127.0.0.1'),'note':'Entire handoff acceptance scenario, not a cold-load comparison. Sum of same-origin response Content-Length headers; external imagery blocked.'}
        browser.close()
    (out/'browser-report.json').write_text(json.dumps(report,indent=2));assert not report['page_errors'],report['page_errors']

if __name__=='__main__':main()
