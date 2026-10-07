"""Whole saved-board portability. Frozen evidence is transported, never recalculated."""
from __future__ import annotations
import base64
import copy
import hashlib
import html
import io
import json
import math
import os
import secrets
import shutil
import stat
import subprocess
import threading
import zipfile
from pathlib import Path, PurePosixPath

from ..provenance import sanitize_public_payload
from . import graph, evidence, visuals, story, heat
from .store import dumps, sha256_text
from .errors import StudioError, Conflict, LimitExceeded, NotFound, Unavailable
from .resources import StorageBudget

SCHEMA='fireatlas-board-v1'
COMPRESSED=512*1024**2
EXPANDED=1024**3
ENTRIES=4096
JSON_LIMIT=32*1024**2
ROOT=Path(__file__).resolve().parents[2]
FORMATS={'native','excalidraw','svg','png','pdf'}


def browser_path():
    # Ubuntu's Chromium command can be a Snap launcher that cannot start on
    # hosted runners. Prefer the installed Chrome binary when available.
    return next((shutil.which(n) for n in ('google-chrome','google-chrome-stable','chromium','chromium-browser') if shutil.which(n)),None)

def image(data,mime):
    return {'sha256':hashlib.sha256(data).hexdigest(),'mime':mime,'data_url':'data:'+mime+';base64,'+base64.b64encode(data).decode()}


def board_svg(ir, objects=None):
    objects=copy.deepcopy(objects if objects is not None else ir['objects'])
    import textwrap
    for obj in objects:
        t=obj['transform'];lines=textwrap.wrap(obj.get('caption') or obj.get('text') or '',max(20,int((t['w']-24)/7)))
        t['h']=max(t['h'],64+len(lines)*16+(100 if obj.get('image') else 0))
    if not objects: raise StudioError('There are no objects in this export scope.')
    x=min(o['transform']['x'] for o in objects)-24;y=min(o['transform']['y'] for o in objects)-24
    right=max(o['transform']['x']+o['transform']['w'] for o in objects)+24
    bottom=max(o['transform']['y']+o['transform']['h'] for o in objects)+24
    esc=lambda s:html.escape(str(s),quote=True)
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x} {y} {right-x} {bottom-y}" width="{right-x}" height="{bottom-y}"><rect x="{x}" y="{y}" width="{right-x}" height="{bottom-y}" fill="#fbf7ef"/>']
    lookup={o['id']:o for o in objects}
    for link in ir['connectors']:
        if link['source'] not in lookup or link['target'] not in lookup:continue
        a,b=lookup[link['source']]['transform'],lookup[link['target']]['transform']
        out.append(f'<path d="M {a["x"]+a["w"]/2} {a["y"]+a["h"]/2} L {b["x"]+b["w"]/2} {b["y"]+b["h"]/2}" stroke="#47758d" fill="none"/>')
    import textwrap
    for obj in objects:
        t=obj['transform'];cx=t['x']+t['w']/2;cy=t['y']+t['h']/2
        out.append(f'<g transform="rotate({t.get("rotation",0)} {cx} {cy})"><rect x="{t["x"]}" y="{t["y"]}" width="{t["w"]}" height="{t["h"]}" rx="6" fill="#fffdf7" stroke="#cbbd9e"/><text x="{t["x"]+14}" y="{t["y"]+28}" font-family="sans-serif" font-size="16" fill="#183b42">{esc(obj["title"])}</text>')
        if obj.get('image'):
            out.append(f'<image href="{obj["image"]["data_url"]}" x="{t["x"]+12}" y="{t["y"]+42}" width="{t["w"]-24}" height="{max(40,t["h"]-110)}" preserveAspectRatio="xMidYMid meet"/>')
        caption=obj.get('caption') or obj.get('text') or ''
        lines=textwrap.wrap(caption,max(20,int((t['w']-24)/7)))
        # All text is retained. Grow the export object if required rather than omit labels.
        start=t['y']+t['h']-16*len(lines) if obj.get('image') else t['y']+50
        for i,line in enumerate(lines):
            out.append(f'<text x="{t["x"]+14}" y="{start+i*16}" font-family="sans-serif" font-size="12" fill="#45636b">{esc(line)}</text>')
        out.append('</g>')
    out.append('</svg>');return ''.join(out)


class Portability:
    def __init__(self,service):
        self.service,self.store=service,service.store
        self.lock=threading.Lock()
        self.root=(service.root/'portable-exports').resolve();self.root.mkdir(parents=True,exist_ok=True)
        with self.store.connection(write=True) as db:
            db.execute("UPDATE export_jobs SET status='failed',error='Preparation interrupted; request the saved revision again.' WHERE status IN ('queued','preparing') AND format!='miro'")

    def capabilities(self):
        ready=shutil.which('node') and (ROOT/'studio-app/node_modules/jsdom').exists() and (ROOT/'studio-app/node_modules/@napi-rs/canvas').exists() and (ROOT/'fireatlas/static/studio-assets/excalidraw-sdk.mjs').exists()
        return {'native':{'available':bool(ready),'reason':None if ready else 'Run npm ci and npm run build in studio-app to install the pinned export helpers.'},
                'excalidraw':{'available':bool(ready),'version':'0.18.1'},'svg':{'available':True},
                'png':{'available':bool(browser_path())},'pdf':{'available':bool(browser_path())},
                'limits':{'compressed_bytes':COMPRESSED,'expanded_bytes':EXPANDED,'entries':ENTRIES,'json_entry_bytes':JSON_LIMIT},'scope':'whole saved board by default'}

    def capture(self,principal,did,revision=None,scope=None):
        """One SQLite read transaction freezes document and all associated revisions."""
        with self.store.connection() as db:
            db.execute('BEGIN')
            self.store.require(db,principal,did)
            doc=self.store._view(db,did,principal)
            if revision is not None and revision!=doc['revision']: raise Conflict('Finish saving or export the actual board revision.',code='stale-export')
            snapshots={r['id']:json.loads(r['body']) for r in db.execute('SELECT id,body FROM snapshots WHERE document_id=?',(did,))}
            results={}
            for snap in snapshots.values():
                row=db.execute('SELECT body FROM science_results WHERE id=?',(snap['result_id'],)).fetchone()
                if not row:raise StudioError('A scoped scientific receipt is missing.',code='missing-receipt')
                result=json.loads(row['body'])
                report=evidence.verify_snapshot(snap,result)
                if not report['verified']:raise StudioError('Frozen evidence verification failed: '+str(report['problems']),code='invalid-evidence')
                results[snap['result_id']]=result
            workflows=[dict(r)|{'definition':json.loads(r['definition'])} for r in db.execute('SELECT id,revision,definition FROM workflows WHERE document_id=?',(did,))]
            histories=[dict(r)|{'outputs':json.loads(r['outputs']),'receipts':json.loads(r['receipts'])} for r in db.execute("SELECT id,workflow_id,workflow_revision,status,definition_sha256,outputs,receipts,error FROM workflow_runs WHERE workflow_id IN (SELECT id FROM workflows WHERE document_id=?)",(did,))]
            # Workflow outputs can refer to results not yet displayed as cards.
            for run in histories:
                referenced=set()
                def collect(value):
                    if isinstance(value,dict):
                        if isinstance(value.get('result_id'),str): referenced.add(value['result_id'])
                        for child in value.values(): collect(child)
                    elif isinstance(value,list):
                        for child in value: collect(child)
                collect(run)
                for rid in referenced:
                    row=db.execute('SELECT body FROM science_results WHERE id=?',(rid,)).fetchone()
                    if row:results[rid]=json.loads(row['body'])
            stories=[]
            for row in db.execute('SELECT id,revision FROM stories WHERE document_id=?',(did,)):
                saved=self.service._story_view(db,row['id']);story_record={k:saved[k] for k in ('id','revision','body','document_revision')}
                if saved.get('resolved'):story_record['frozen_scenes']=saved['resolved']['scenes']
                stories.append(story_record)
            assets=[dict(r) for r in db.execute('SELECT id,sha256,mime,bytes,license,attribution,path FROM assets WHERE document_id=?',(did,))]
            comments=[{'id':r['id'],'card_id':r['card_id'],'author_label':'participant-'+r['author_id'][-6:],'body':r['body'],'created':r['created'],'resolved':bool(r['resolved']),'chapter':json.loads(r['chapter_ref']) if r['chapter_ref'] else None} for r in db.execute('SELECT c.* FROM comments c JOIN rooms r ON c.room_id=r.id WHERE r.document_id=?',(did,))]
            comments += [json.loads(r['body']) for r in db.execute('SELECT body FROM imported_annotations WHERE document_id=?',(did,))]
            imported_projects=[json.loads(r['body']) for r in db.execute('SELECT body FROM imported_projects WHERE document_id=?',(did,))]
            packages=[json.loads(r['body']) for r in db.execute('SELECT body FROM investigation_packages WHERE document_id=?',(did,))]
            for project in imported_projects:
                histories.extend(project.get('workflow_runs',[]));packages.extend(project.get('packages',[]))
                frozen_stories={s['id']:s for s in project.get('stories',[])}
                for saved in stories:
                    historical=frozen_stories.get(saved['id'])
                    if historical and saved['revision']==historical.get('restored_revision',1) and not saved.get('frozen_scenes'):
                        saved['frozen_scenes']=historical.get('frozen_scenes',[])
            db.execute('COMMIT')
        state=copy.deepcopy(doc['state']);scope=scope or {'kind':'whole'}
        if scope.get('kind')!='whole':
            ids=scope.get('object_ids')
            if scope.get('kind')=='frame': ids=state['groups'].get(scope.get('frame_id'),{}).get('card_ids')
            if not isinstance(ids,list) or not ids or any(i not in state['cards'] for i in ids):raise StudioError('Select actual board objects for a scoped export.')
            state['cards']={i:state['cards'][i] for i in ids};state['order']=[i for i in state['order'] if i in ids]
            state['connections']={k:v for k,v in state['connections'].items() if v['source'] in ids and v['target'] in ids}
            state['groups']={k:v for k,v in state['groups'].items() if all(i in ids for i in v['card_ids'])}
            # Selected-follow references must remain closed; no hidden expansion.
            if any(c.get('follow_card_id') and c['follow_card_id'] not in ids for c in state['cards'].values()):raise StudioError('Include selected-follow dependencies explicitly.')
            comments=[c for c in comments if not c.get('card_id') or c['card_id'] in ids]
            scoped_sids={c['snapshot_id'] for c in state['cards'].values() if c.get('snapshot_id')}
            snapshots={k:v for k,v in snapshots.items() if k in scoped_sids}
            results={v['result_id']:results[v['result_id']] for v in snapshots.values()}
            # Explicit subset archives contain only these objects and closed scientific dependencies.
            workflows=[];histories=[];stories=[];packages=[]
            assets=[a for a in assets if a['id'] in {c.get('asset_id') for c in state['cards'].values()}]
        bundle={'schema':SCHEMA,'source_document':{'id':did,'revision':doc['revision']},'board':state,'snapshots':snapshots,'results':results,
                'workflows':workflows,'workflow_runs':histories,'stories':stories,'comments':comments,'packages':packages,'assets':[],'scope':scope}
        binaries={}
        for asset in assets:
            path=self.service.root/asset['path'];data=path.read_bytes()
            if len(data)!=asset['bytes'] or hashlib.sha256(data).hexdigest()!=asset['sha256']:raise StudioError('An image asset changed during capture.')
            portable='assets/'+asset['sha256']+path.suffix
            binaries[portable]=data;bundle['assets'].append({**{k:v for k,v in asset.items() if k!='path'},'file':portable})
        return sanitize_public_payload(bundle),binaries

    def intermediate(self,bundle,binaries):
        state=bundle['board'];objects=[];conversions=[];asset_index={a['id']:a for a in bundle['assets']}
        for oid in state['order']:
            card=state['cards'][oid];snap=bundle['snapshots'].get(card.get('snapshot_id'));preview=None
            asset=asset_index.get(card.get('asset_id'))
            if asset:preview=image(binaries[asset['file']],asset['mime'])
            elif snap:
                receipt=bundle['results'][snap['result_id']];display=card.get('display') or {}
                chapter={'selection':{'day':display.get('day') or snap['scope'].get('day')},'source_filter':display.get('source') or 'joint'}
                if card['type']=='map' and display.get('preview')=='heat':
                    visual=heat.prepare(snap,receipt,chapter['selection'],chapter['source_filter'])
                    preview=image(base64.b64decode(visual['data']),visual['mime'])
                else:
                    visual=visuals.prepared(card,[snap],{snap['id']:receipt},chapter)
                    scene={'title':card['title'],'caption':'','narration_text':'','figure_version':2,'fallback':story.schematic(card,[snap]),'visual':visual}
                    preview=image(visuals.svg(scene).encode(),'image/svg+xml')
            caption=card['text']
            if snap:caption += '\n'+snap['unit']+' · UTC '+snap['scope']['start']+' → '+snap['scope']['end']+' · receipt '+snap['receipt_sha256'][:12]
            if card['type']=='finding' and snap:
                preview=None
                caption+='\n'+'\n'.join(f"{f['label']}: {f['value'] if f['value'] is not None else f['state']} {f['unit']}" for f in snap['facts'])
            objects.append({'id':oid,'kind':card['type'],'title':card['title'],'text':card['text'],'caption':caption,'transform':card['transform'],'image':preview,
                            'view_descriptor':card['display'].get('captured_view') or card['display'],'result_refs':[snap['result_id']] if snap else []})
        connectors=list(state['connections'].values());frames=[]
        for gid,group in state.get('groups',{}).items():
            selected=[o for o in objects if o['id'] in group['card_ids']]
            if not selected:continue
            x=min(o['transform']['x'] for o in selected)-20;y=min(o['transform']['y'] for o in selected)-40
            w=max(o['transform']['x']+o['transform']['w'] for o in selected)-x+20;h=max(o['transform']['y']+o['transform']['h'] for o in selected)-y+20
            frames.append({'id':gid,'title':group.get('title') or 'Evidence group','x':x,'y':y,'w':w,'h':h})
            for o in selected:o.setdefault('frame_id',gid)
        top=max((o['transform']['y']+o['transform']['h'] for o in objects),default=0)+100
        for wf in bundle['workflows']:
            workflow_top=top
            node_ids={n['id']:wf['id']+'-'+n['id'] for n in wf['definition']['nodes']}
            executions=[r for r in bundle['workflow_runs'] if r.get('workflow_id')==wf['id']]
            for i,node in enumerate(wf['definition']['nodes']):
                nid=node_ids[node['id']];objects.append({'id':nid,'kind':'workflow-node','title':node.get('label') or node['id'],
                    'text':dumps(node.get('params') or {}),'caption':node['type']+' · '+('Explanatory dependency: frozen source reference.' if node['type']=='evidence_input' else 'Runnable workflow: registered operation.')+('\nRecorded execution: '+executions[-1]['id'] if executions and any(r.get('node')==node['id'] for r in executions[-1].get('receipts',[])) else '\nNo recorded execution for this node.'),
                    'transform':{'x':40+(i%3)*410,'y':top+(i//3)*240,'w':380,'h':200},'frame_id':wf['id'],'result_refs':[]})
                for sources in node.get('inputs',{}).values():
                    for source in sources if isinstance(sources,list) else [sources]:connectors.append({'id':nid+'-'+source,'source':node_ids[source],'target':nid,'kind':'workflow'})
            top+=math.ceil(len(node_ids)/3)*240+100
            frames.append({'id':wf['id'],'title':'Runnable workflow · '+wf['id'],'x':20,'y':workflow_top-40,'w':1240,'h':top-workflow_top-40})
        for saved in bundle['stories']:
            start=top;frame_id=saved['id']
            for i,chapter in enumerate(saved['body']['chapters']):
                oid=saved['id']+'-'+chapter['id'];cited=[chapter.get('card_id')]+chapter.get('evidence_cards',[])
                scene=next((s for s in saved.get('frozen_scenes',[]) if s.get('chapter_id')==chapter['id']),{})
                text=scene.get('caption',chapter.get('caption',''))+'\n'+scene.get('narration_text',chapter.get('narration',''))
                objects.append({'id':oid,'kind':'chapter-frame','title':chapter.get('title') or 'Story chapter',
                    'text':text,'caption':text+'\nStory revision '+str(saved['revision'])+' · selection '+dumps(chapter.get('selection') or {}),
                    'transform':{'x':40+(i%3)*410,'y':start+(i//3)*280,'w':380,'h':240},'frame_id':frame_id,'result_refs':[]})
                for cid in cited:
                    if cid in state['cards']:connectors.append({'id':'chapter-link-'+oid+'-'+cid,'source':cid,'target':oid,'kind':'explanatory-dependency'})
            top+=math.ceil(len(saved['body']['chapters'])/3)*280+100
            frames.append({'id':frame_id,'title':saved['body']['title']+' · saved story','x':20,'y':start-40,'w':1240,'h':top-start-40})
        for comment in bundle['comments']:
            objects.append({'id':'comment-'+comment['id'],'kind':'annotation','title':'Archived discussion · '+comment.get('author_label','imported participant'),
                            'text':comment['body'],'caption':comment['body'],'transform':{'x':40,'y':top,'w':600,'h':160}});top+=180
        return {'schema':'fireatlas-board-export-v1','title':state['title'],'source_revision':bundle['source_document'],'scope':bundle['scope'],
                'created_ms':int(self.store.clock()*1000),'objects':objects,'connectors':connectors,'frames':frames,'conversions':[{'id':o['id'],'conversion':'embedded scientific preview with editable caption' if o.get('image') else 'individual editable text and shape'} for o in objects]}

    def get(self,principal,jid):
        with self.store.connection() as db:row=db.execute('SELECT * FROM export_jobs WHERE id=? AND principal_id=?',(jid,principal)).fetchone()
        if not row:raise NotFound('Export not found.')
        self.store.get_document(principal,row['document_id'])
        return {k:json.loads(row[k]) if k=='body' else row[k] for k in row.keys() if k not in {'principal_id','path'}} | {'download':f'api/studio/exports/{jid}/download' if row['status']=='completed' else None}

    def submit(self,principal,did,body,key=None,background=True):
        fmt=body.get('format','native')
        if fmt not in FORMATS:raise StudioError('Choose native, Excalidraw, SVG, PNG or PDF.')
        jid='export_'+hashlib.sha256((principal+':'+key).encode()).hexdigest()[:24] if key else 'export_'+secrets.token_hex(12)
        with self.store.connection() as db:old=db.execute('SELECT id FROM export_jobs WHERE id=?',(jid,)).fetchone()
        if old:
            saved=self.get(principal,jid)
            if saved['document_id']!=did or saved['format']!=fmt or saved['body']['scope']!=body.get('scope',{'kind':'whole'}) or body.get('revision',saved['revision'])!=saved['revision']:
                raise Conflict('This export key already names a different saved export.',code='idempotency-conflict')
            return saved
        if not self.capabilities()[fmt]['available']:raise Unavailable('Install the local export runtime for this format.')
        bundle,binaries=self.capture(principal,did,body.get('revision'),body.get('scope'))
        if not self.lock.acquire(blocking=False):raise Conflict('Another export is preparing. Retry after it finishes.',code='export-busy')
        try:
            StorageBudget(self.service.root).check(EXPANDED,ENTRIES)
            with self.store.connection(write=True) as db:
                now=self.store.clock();db.execute('INSERT INTO export_jobs VALUES(?,?,?,?,?,?,?,NULL,NULL,?,?)',(jid,principal,did,bundle['source_document']['revision'],fmt,'queued',dumps({'scope':bundle['scope']}),now,now))
            if background:threading.Thread(target=self.build,args=(principal,jid,bundle,binaries),daemon=True,name='studio-export').start()
            else:self.build(principal,jid,bundle,binaries)
        except BaseException:
            if self.lock.locked():self.lock.release()
            raise
        return self.get(principal,jid)

    def build(self,principal,jid,bundle,binaries):
        directory=self.root/jid;directory.mkdir()
        try:
            with self.store.connection(write=True) as db:db.execute("UPDATE export_jobs SET status='preparing' WHERE id=?",(jid,))
            job=self.get(principal,jid);fmt=job['format'];ir=self.intermediate(bundle,binaries)
            irpath=directory/'intermediate.json';irpath.write_text(dumps(ir))
            svg=board_svg(ir);(directory/'board.svg').write_text(svg)
            if fmt in {'native','excalidraw'}:
                subprocess.run([shutil.which('node'),'--max-old-space-size=768',str(ROOT/'studio-app/scripts/export-scene.mjs'),str(irpath),str(directory/'board.excalidraw'),str(directory/'object-map.json')],check=True,timeout=120,capture_output=True)
            if fmt=='native':
                path=directory/'board.fireatlas.zip';inventory={};total=0
                with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
                    def write(name,data):
                        nonlocal total
                        total+=len(data)
                        if total>EXPANDED or len(inventory)>=ENTRIES:raise LimitExceeded('The complete board exceeds archive limits; choose a frame or selection.')
                        if name.endswith(('.json','.excalidraw')) and len(data)>JSON_LIMIT:raise LimitExceeded('A JSON entry exceeds 32 MiB; choose a smaller board scope.')
                        archive.writestr(name,data);inventory[name]={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
                        if path.stat().st_size>COMPRESSED:raise LimitExceeded('The compressed archive exceeds 512 MiB.')
                    def write_json(name,value):
                        # Large scientific payloads are UTF-8 JSON split into hash-bound byte chunks.
                        data=dumps(value).encode()
                        if len(data)<=JSON_LIMIT:
                            write(name,data);return name
                        chunks=[]
                        for i,offset in enumerate(range(0,len(data),JSON_LIMIT)):
                            chunk=name+'.part-'+str(i).zfill(4)
                            write(chunk,data[offset:offset+JSON_LIMIT]);chunks.append(chunk)
                        return {'chunks':chunks,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
                    index={}
                    for key in ('board','snapshots','workflows','workflow_runs','stories','comments','packages','source_document','scope','assets'):
                        write(key+'.json',dumps(bundle[key]).encode())
                    write('view-descriptors.json',dumps({c['id']:c['display'] for c in bundle['board']['cards'].values()}).encode())
                    for rid,result in bundle['results'].items():
                        entry='results/'+rid+'.json';index[rid]=write_json(entry,result)
                    write('results/index.json',dumps(index).encode())
                    for name,data in binaries.items():write(name,data)
                    write('interop/board.excalidraw',(directory/'board.excalidraw').read_bytes());write('interop/object-map.json',(directory/'object-map.json').read_bytes())
                    report={'schema':'fireatlas-export-report-v1','scope':bundle['scope'],'objects':len(ir['objects']),'conversions':ir['conversions'],
                            'editability':'Excalidraw text, shapes, frames and connectors are editable. Embedded scientific figures are visual objects. FireAtlas workflows run only in a compatible FireAtlas installation.',
                            'provenance':'User-supplied frozen archive on import; hashes check integrity, not source authenticity.'}
                    write('export-report.json',dumps(report).encode());write('README.txt',b'Restore with Studio > Restore native board. Frozen results work without the original scientific database. Reruns require compatible methods and data. This archive contains board-scoped discussion, not private conversation or room credentials.\n')
                    archive.writestr('manifest.json',dumps({'schema':SCHEMA,'files':inventory,'expanded_bytes':total}))
                if path.stat().st_size>COMPRESSED:raise LimitExceeded('Archive exceeds compressed limit.')
            elif fmt=='svg':path=directory/'board.svg'
            elif fmt=='excalidraw':path=directory/'board.excalidraw'
            else:
                width=max(o['transform']['x']+o['transform']['w'] for o in ir['objects'])-min(o['transform']['x'] for o in ir['objects'])+48
                height=max(o['transform']['y']+o['transform']['h'] for o in ir['objects'])-min(o['transform']['y'] for o in ir['objects'])+48
                if fmt=='png' and (width>16000 or height>16000 or width*height>64_000_000):raise LimitExceeded('Whole-board PNG exceeds 64 million pixels; export a frame or SVG.')
                page=directory/'print.html';profile=directory/'browser';path=directory/('board.png' if fmt=='png' else 'board.pdf')
                parts=[svg]
                if fmt=='pdf':
                    # Overview, group/workflow pages and readable objects. Large regions also get spatial tiles.
                    parts=[svg]
                    for frame in ir['frames']:
                        members=[o for o in ir['objects'] if o.get('frame_id')==frame['id']]
                        if members:parts.append(board_svg(ir,members))
                    if width>1400 or height>900:
                        left=min(o['transform']['x'] for o in ir['objects'])-24;top=min(o['transform']['y'] for o in ir['objects'])-24
                        import re
                        for y in range(math.ceil(height/900)):
                            for x in range(math.ceil(width/1400)):
                                bx,by=left+x*1400,top+y*900
                                if not any(o['transform']['x']<bx+1400 and o['transform']['x']+o['transform']['w']>bx and o['transform']['y']<by+900 and o['transform']['y']+o['transform']['h']>by for o in ir['objects']):continue
                                parts.append(re.sub(r'viewBox="[^"]+" width="[^"]+" height="[^"]+"',f'viewBox="{bx} {by} 1400 900" width="1400" height="900"',svg,count=1))
                                if len(parts)>128:raise LimitExceeded('PDF exceeds 128 pages; choose a frame or selection.')
                    parts += [board_svg(ir,[obj]) for obj in ir['objects']]
                    if len(parts)>128:raise LimitExceeded('PDF exceeds 128 pages; choose a frame or selection.')
                page.write_text('<!doctype html><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'"><style>@page{size:A3 landscape;margin:12mm}body{margin:0;background:#fbf7ef}section{break-after:page}svg{max-width:100%;height:auto}</style>'+''.join('<section>'+s+'</section>' for s in parts))
                command=[browser_path(),'--headless','--no-sandbox','--disable-gpu','--no-first-run','--disable-background-networking','--disable-dev-shm-usage','--user-data-dir='+str(profile),'--virtual-time-budget=4000', '--hide-scrollbars']
                command += ['--screenshot='+str(path),'--window-size='+str(math.ceil(width))+','+str(math.ceil(height))] if fmt=='png' else ['--print-to-pdf='+str(path),'--no-pdf-header-footer']
                subprocess.run(command+[page.as_uri()],check=True,timeout=90,capture_output=True)
                shutil.rmtree(profile,ignore_errors=True)
            if not path.exists() or path.stat().st_size>COMPRESSED:raise LimitExceeded('Export failed or exceeds output limits.')
            with self.store.connection(write=True) as db:
                db.execute("UPDATE export_jobs SET status='completed',path=?,body=?,updated=? WHERE id=?",(str(path.relative_to(self.service.root.resolve())),dumps({'scope':bundle['scope'],'objects':len(ir['objects']),'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}),self.store.clock(),jid))
            # Intermediate inputs can contain duplicated embedded images; retain only final artifacts.
            irpath.unlink(missing_ok=True)
        except Exception as error:
            shutil.rmtree(directory,ignore_errors=True)
            with self.store.connection(write=True) as db:db.execute("UPDATE export_jobs SET status='failed',error=?,updated=? WHERE id=?",(str(error)[:500],self.store.clock(),jid))
        finally:self.lock.release()

    def retry(self,principal,jid):
        """Explicit recovery of an unfinished local export at its original saved revision."""
        job=self.get(principal,jid)
        if job['status']!='failed':return job
        bundle,binaries=self.capture(principal,job['document_id'],job['revision'],job['body']['scope'])
        if not self.lock.acquire(blocking=False):raise Conflict('Another export is preparing.',code='export-busy')
        try:
            StorageBudget(self.service.root).check(EXPANDED,ENTRIES)
            shutil.rmtree(self.root/jid,ignore_errors=True)
            with self.store.connection(write=True) as db:db.execute("UPDATE export_jobs SET status='queued',error=NULL,updated=? WHERE id=?",(self.store.clock(),jid))
            threading.Thread(target=self.build,args=(principal,jid,bundle,binaries),daemon=True,name='studio-export-recovery').start()
        except BaseException:
            self.lock.release();raise
        return self.get(principal,jid)

    def download(self,principal,jid):
        job=self.get(principal,jid)
        if job['status']!='completed':raise Conflict('Export is not complete.')
        with self.store.connection() as db:row=db.execute('SELECT path FROM export_jobs WHERE id=?',(jid,)).fetchone()
        path=(self.service.root/row['path']).resolve()
        roots={self.root,(self.service.root/'renders'/'portable').resolve()}
        if not any(root in path.parents for root in roots) or not path.is_file():raise NotFound('Export file missing.')
        mime={'native':'application/zip','excalidraw':'application/json','svg':'image/svg+xml','png':'image/png','pdf':'application/pdf'}[job['format']]
        return path,mime

    def restore(self,principal,path):
        bundle,binaries=read_archive(path)
        # Validate references/graphs before any persistent mutation.
        state=copy.deepcopy(bundle['board']);graph.validate_groups(state);graph.validate_follow(state['cards']);graph.topological_order(state['cards'],state['connections'])
        state['study']=graph.clean_study(state.get('study'))
        if not isinstance(state.get('title'),str) or len(state['title'])>120:raise StudioError('Invalid imported board title.')
        if len(state.get('order',[]))!=len(set(state.get('order',[]))) or set(state.get('order',[]))!=set(state['cards']):raise StudioError('Imported object order is inconsistent.')
        for cid,card in state['cards'].items():
            if card.get('id')!=cid:raise StudioError('Imported card identity is inconsistent.')
        state['connections']={k:graph.clean_connection(v) for k,v in state['connections'].items()}
        if any(k!=v['id'] for k,v in state['connections'].items()):raise StudioError('Imported connector identity is inconsistent.')
        from .workflow import validate
        for wf in bundle['workflows']:validate(wf['definition'])
        for snap in bundle['snapshots'].values():
            result=bundle['results'].get(snap['result_id'])
            if not result or not evidence.verify_snapshot(snap,result)['verified']:raise StudioError('Imported frozen evidence is inconsistent.',code='invalid-evidence')
        ids=set(state['cards'])|set(state['connections'])|set(state['groups'])|set(bundle['snapshots'])|set(bundle['results'])
        ids|={w['id'] for w in bundle['workflows']}|{s['id'] for s in bundle['stories']}|{a['id'] for a in bundle['assets']}
        ids|={r['id'] for r in bundle['workflow_runs']}|{p['id'] for p in bundle['packages']}
        for saved in bundle['stories']:ids|={c['id'] for c in saved['body'].get('chapters',[])}
        mapping={i:'imp_'+secrets.token_hex(12) for i in ids}
        def remap(value):
            if isinstance(value,str):return mapping.get(value,value)
            if isinstance(value,list):return [remap(v) for v in value]
            if isinstance(value,dict):return {mapping.get(k,k):remap(v) for k,v in value.items()}
            return value
        did='doc_'+secrets.token_hex(12);restored=remap(state);now=self.store.clock()
        result_bodies={mapping[r]:v for r,v in bundle['results'].items()}
        restored_snaps={}
        for sid,source in bundle['snapshots'].items():
            snap=copy.deepcopy(source);snap.update(id=mapping[sid],result_id=mapping[source['result_id']],imported_provenance={'schema':SCHEMA,'source_document':bundle['source_document'],'original_snapshot_id':sid,'original_snapshot_sha256':source['snapshot_sha256']})
            snap['snapshot_sha256']=sha256_text(dumps({k:v for k,v in snap.items() if k!='snapshot_sha256'}));restored_snaps[snap['id']]=snap
        for cid,card in list(restored['cards'].items()):
            if card.get('type') not in graph.CARD_TYPES:
                card['text']='Imported unsupported object: '+str(card.get('type'))+'\n'+str(card.get('text',''));card['type']='method-note'
            card['provenance']={**card.get('provenance',{}),'imported_archive':SCHEMA};restored['cards'][cid]=graph.clean_card(card)
            if card.get('snapshot_id') and card['snapshot_id'] not in restored_snaps:raise StudioError('Missing imported snapshot reference.')
            if card.get('asset_id') and card['asset_id'] not in {mapping[a['id']] for a in bundle['assets']}:raise StudioError('Missing imported image reference.')
        if len(restored['cards'])>100 or len(restored['connections'])>300 or len(dumps(restored))>1_000_000:raise LimitExceeded('Imported board exceeds existing document limits.')
        for saved in bundle['stories']:
            story.clean_story(remap(saved['body']))
            for chapter in saved['body'].get('chapters',[]):
                cited=[chapter.get('card_id')]+chapter.get('evidence_cards',[])+chapter.get('visible_cards',[])
                if any(cid and cid not in state['cards'] for cid in cited): raise StudioError('Story references an absent card.')
        for wf in bundle['workflows']:
            for node in wf['definition']['nodes']:
                if node['type']=='evidence_input' and node.get('params',{}).get('snapshot_id') not in bundle['snapshots']:
                    raise StudioError('Workflow references absent frozen evidence.')
        assets=[]
        for a in bundle['assets']:
            data=binaries[a['file']]
            if len(data)>1_500_000:raise LimitExceeded('Imported asset exceeds existing image limits.')
            if len(data)!=a.get('bytes') or hashlib.sha256(data).hexdigest()!=a.get('sha256'):
                raise StudioError('Imported asset metadata does not match its bytes.')
            if not ((a['mime']=='image/png' and data.startswith(b'\x89PNG\r\n\x1a\n')) or (a['mime']=='image/jpeg' and data.startswith(b'\xff\xd8\xff')) or (a['mime']=='image/webp' and data[:4]==b'RIFF' and data[8:12]==b'WEBP')):raise StudioError('Invalid imported image content.')
            assets.append((a,data))
        with self.store.connection(write=True) as db:
            db.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?,0)',(did,principal,restored['title'],1,dumps({'study':1,'title':1}),dumps(restored),dumps({'board_id':did,'document_revision':1,'epoch':0,'card_id':None}),now,now))
            db.execute('INSERT INTO revisions VALUES(?,?,?,?,?,?,?)',(did,1,principal,None,sha256_text(dumps(restored)),dumps(restored),now))
            for rid,receipt in result_bodies.items():db.execute('INSERT INTO science_results VALUES(?,?,?,?,?,?)',(rid,principal,'evidence',receipt['sha256'],dumps(receipt),now))
            for sid,snap in restored_snaps.items():db.execute('INSERT INTO snapshots VALUES(?,?,?,?,?,?)',(sid,did,principal,snap['snapshot_sha256'],dumps(snap),now))
            for a,data in assets:
                relative='assets/'+hashlib.sha256(data).hexdigest()+Path(a['file']).suffix
                (self.service.root/'assets').mkdir(exist_ok=True);(self.service.root/relative).write_bytes(data)
                db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?,?)',(mapping[a['id']],principal,did,a['sha256'],a['mime'],len(data),a['license'],a['attribution'],relative,now))
            for wf in bundle['workflows']:
                definition=remap(wf['definition']);db.execute('INSERT INTO workflows VALUES(?,?,?,?,?,?,?)',(mapping[wf['id']],did,principal,1,dumps(definition),now,now))
            for saved in bundle['stories']:
                body=remap(saved['body']);sid=mapping[saved['id']]
                story.clean_story(body)
                db.execute('INSERT INTO stories VALUES(?,?,?,?,?,?,?)',(sid,did,principal,body['title'],1,now,now))
                db.execute('INSERT INTO story_revisions VALUES(?,?,?,?,NULL,NULL,?,?)',(sid,1,1,dumps(body),principal,now))
            historical=remap({'workflow_runs':bundle['workflow_runs'],'packages':bundle['packages'],'stories':bundle['stories']})
            for frozen in historical['stories']: frozen['restored_revision']=1
            for run in historical['workflow_runs']: run['provenance']='Imported recorded execution; not run in this installation'
            db.execute('INSERT INTO imported_projects VALUES(?,?)',(did,dumps(historical)))
            for c in bundle['comments']:
                cid='annotation_'+secrets.token_hex(8);body=remap(c)|{'id':cid,'imported':True}
                db.execute('INSERT INTO imported_annotations VALUES(?,?,?)',(did,cid,dumps(body)))
        return {'document':self.service.get_document(principal,did),'id_map':mapping,'provenance':'Imported user-supplied frozen archive',
                'rerun':'Registered definitions are restored. Recompute explicitly with compatible installed scientific inputs; frozen results are unchanged.'}


def read_archive(path):
    if Path(path).stat().st_size>COMPRESSED:raise LimitExceeded('Archive exceeds 512 MiB.')
    with zipfile.ZipFile(path) as z:
        entries=z.infolist();names=[e.filename for e in entries]
        if len(entries)>ENTRIES or len(names)!=len(set(names)):raise StudioError('Duplicate or excessive archive entries.')
        total=0
        for item in entries:
            p=PurePosixPath(item.filename)
            if p.is_absolute() or str(p)!=item.filename or '..' in p.parts or '\\' in item.filename or ':' in item.filename or item.is_dir() or stat.S_ISLNK(item.external_attr>>16):raise StudioError('Unsafe archive entry.')
            allowed={'board.json','snapshots.json','workflows.json','workflow_runs.json','stories.json','comments.json','packages.json','source_document.json','scope.json','assets.json','view-descriptors.json','export-report.json','README.txt','manifest.json','interop/board.excalidraw','interop/object-map.json','results/index.json'}
            import re
            if item.filename not in allowed and not re.fullmatch(r'(?:results/[A-Za-z0-9_-]{1,64}\.json(?:\.part-[0-9]{4})?|assets/[a-f0-9]{64}\.(?:png|jpg|webp))',item.filename):raise StudioError('Unsupported archive content.')
            total+=item.file_size
            if total>EXPANDED or item.file_size>JSON_LIMIT and item.filename.endswith('.json'):raise LimitExceeded('Archive expansion or metadata limit exceeded.')
        def read(name):
            try:
                with z.open(name) as source:data=source.read(JSON_LIMIT+1)
            except KeyError:raise StudioError('A required archive entry is missing.') from None
            if len(data)>JSON_LIMIT:raise LimitExceeded('Archive entry exceeds limit.')
            return data
        manifest=json.loads(read('manifest.json'))
        if manifest.get('schema')!=SCHEMA or set(manifest.get('files',{}))!=set(names)-{'manifest.json'}:raise StudioError('Unsupported schema or unlisted archive entries.')
        data={};actual=0
        for name,meta in manifest['files'].items():
            accumulator=bytearray();checksum=hashlib.sha256()
            with z.open(name) as source:
                while chunk:=source.read(1024*1024):
                    actual+=len(chunk);accumulator.extend(chunk);checksum.update(chunk)
                    if actual>EXPANDED or len(accumulator)>JSON_LIMIT:raise LimitExceeded('Archive expansion or entry limit exceeded.')
            blob=bytes(accumulator)
            if len(blob)!=meta['bytes'] or checksum.hexdigest()!=meta['sha256']:raise StudioError('Archive integrity or expansion check failed.')
            data[name]=blob
        if actual!=manifest['expanded_bytes']:raise StudioError('Incorrect expanded-size manifest.')
        bundle={key:json.loads(data[key+'.json']) for key in ('board','snapshots','workflows','workflow_runs','stories','comments','packages','source_document','scope','assets')}
        if bundle['board'].get('schema')!='fireatlas-studio-document-v1':raise StudioError('Unsupported board schema.')
        index=json.loads(data['results/index.json']);bundle['results']={}
        for rid,entry in index.items():
            graph.check_id(rid,'result identity')
            if isinstance(entry,str):blob=data[entry]
            elif isinstance(entry,dict) and set(entry)=={'chunks','bytes','sha256'} and isinstance(entry['chunks'],list) and len(entry['chunks'])==len(set(entry['chunks'])):
                blob=b''.join(data[name] for name in entry['chunks'])
                if len(blob)!=entry['bytes'] or hashlib.sha256(blob).hexdigest()!=entry['sha256']:raise StudioError('Chunked result integrity check failed.')
            else:raise StudioError('Unsupported result index.')
            bundle['results'][rid]=json.loads(blob)

        binaries={a['file']:data[a['file']] for a in bundle['assets']}
        if len(bundle['assets'])!=len({a['id'] for a in bundle['assets']}):raise StudioError('Duplicate imported asset identities.')
        if len(bundle['assets'])>40 or len(bundle['stories'])>10:raise LimitExceeded('Archive exceeds existing board asset/story limits.')
        return bundle,binaries
