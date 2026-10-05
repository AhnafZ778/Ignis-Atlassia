"""Browser regression for model tool selection, verified fallback and automatic capture.

Uses authentic existing scientific inputs read-only and isolated private stores.
Inference is mocked at the model transport; no keys or provider requests are used.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=ROOT/'data/fireatlas.sqlite3')
    parser.add_argument('--output',type=Path,default=ROOT/'docs/implementation/jarvis-tool-routing')
    args=parser.parse_args()
    from playwright.sync_api import sync_playwright, expect
    from pydantic_ai.models.function import FunctionModel
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from fireatlas.assistant.agent import run_agent
    from fireatlas.assistant.service import AssistantService
    from fireatlas.studio.service import StudioService
    from fireatlas.web import handler_factory
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    trace=[];errors=[]
    configuration={'provider':'openai','model':'mock-transport','configured':True,'input_price':.1,'output_price':.2,'free_only':False}
    def coordinated(service,owner,message,context,view,cancel,deadline,progress,images=None):
        calls=[]
        def respond(messages,info):
            calls.append(1)
            if len(calls)==1:
                if 'canvas' in message.lower():
                    assert any(t.name=='run_studio_recipe' for t in info.function_tools),'Canvas tool must be attached before submission.'
                    name='run_studio_recipe';arguments={'recipe':'visualization_to_investigation','arguments':{}}
                else:
                    name='investigate';arguments={'operation':'replay'}
                trace.append({'tool':name,'arguments':arguments,'day':context['day'],'source':context['source']})
                return ModelResponse(parts=[ToolCallPart(name,arguments)])
            # Intentionally bad final prose/references exercise the exact failure
            # the user reported, after a real registered tool has completed.
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,{'title':'Unchecked answer','interpretation':'There were 999999 fires.','claims':[{'result_id':'not-a-receipt','path':'/invented','label':'Invented'}]})])
        return run_agent(service,owner,message,context,view,cancel,deadline,progress,images,model=FunctionModel(respond))

    with tempfile.TemporaryDirectory(prefix='jarvis-routing-') as temporary,contextlib.ExitStack() as stack:
        private=Path(temporary)
        assistant=AssistantService(args.db,private/'assistant.sqlite3');stack.callback(assistant.close)
        studio=StudioService(args.db,root=private/'studio',assistant=assistant);stack.callback(studio.close)
        stack.enter_context(patch('fireatlas.assistant.AssistantService',return_value=assistant))
        stack.enter_context(patch('fireatlas.studio.service.StudioService',return_value=studio))
        stack.enter_context(patch('fireatlas.assistant.agent.provider_config',return_value=configuration))
        stack.enter_context(patch('fireatlas.assistant.service.provider_config',return_value=configuration))
        stack.enter_context(patch('fireatlas.assistant.service.run_agent',side_effect=coordinated))
        handler=handler_factory(args.db);handler.log_message=lambda *_:None
        server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        stack.callback(server.server_close);stack.callback(server.shutdown)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        base=f'http://127.0.0.1:{server.server_port}'
        stack.enter_context(patch.dict('os.environ',{'FIREATLAS_ASSISTANT_ORIGIN':base}))
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,executable_path=next((shutil.which(n) for n in ('chromium','chromium-browser','google-chrome') if shutil.which(n)),None))
            context=browser.new_context(viewport={'width':1440,'height':1000},reduced_motion='reduce')
            context.route('**/*',lambda route:route.continue_() if urlsplit(route.request.url).hostname=='127.0.0.1' else route.abort())
            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(base+'/investigate.html?case=park-2024',wait_until='domcontentloaded')
            page.wait_for_function("FireAtlasAssistant.isReady() && (()=>{try{return FireAtlasOrchestration.source().refs.length>0}catch{return false}})()",timeout=60000)
            selected=page.evaluate('FireAtlasOrchestration.source().study')
            page.evaluate("window.dispatchEvent(new CustomEvent('fireatlas:show-assistant-chat'))")
            page.locator('#assistant-question').fill('Compare the observations in this study.')
            page.locator('#assistant-question-form').evaluate('(e)=>e.requestSubmit()')
            page.wait_for_function("document.querySelector('#assistant-messages')?.textContent.includes('6,224')",timeout=45000)
            expect(page.locator('#assistant-messages')).not_to_contain_text('could not verify')
            expect(page.locator('#assistant-messages')).not_to_contain_text('999999')
            page.screenshot(path=str(output/'checked-tool-fallback.png'))
            page.wait_for_function('!FireAtlasAssistant.isBusy()')
            page.locator('#assistant-question').fill('Package this heatmap on my canvas with the relevant charts and a workflow.')
            page.locator('#assistant-question-form').evaluate('(e)=>e.requestSubmit()')
            page.wait_for_url('**/studio.html?board=*&command=*',timeout=60000)
            expect(page.get_by_label('Board title')).to_be_visible(timeout=30000)
            page.wait_for_function("document.querySelector('.orchestration-panel')?.textContent.includes('completed:')",timeout=20000)
            selection=parse_qs(urlsplit(page.url).query)
            response=context.request.get(base+'/api/studio/commands/'+selection['command'][0]);assert response.ok
            command=response.json()
            assert command['status']=='completed',command
            assert command['context']['study_selection']['day']==selected['day']
            assert command['context']['study_selection']['bbox']==selected['bbox']
            board=context.request.get(base+'/api/studio/documents/'+selection['board'][0]).json()
            facts=[fact for snapshot in board['snapshots'].values() for fact in snapshot['facts']]
            assert any(f['value']==6224 for f in facts)
            assert any(f['value']==2228 for f in facts)
            page.screenshot(path=str(output/'automatic-canvas-handoff.png'))
            page.reload(wait_until='domcontentloaded');expect(page.get_by_label('Board title')).to_be_visible()
            reloaded=context.request.get(base+'/api/studio/documents/'+selection['board'][0]).json()
            assert reloaded['state']['cards']==board['state']['cards']
            browser.close()
        assert not errors,errors
        report={'inference':'mocked model transport; no provider calls','inputs':'existing authentic database, read-only',
                'private_stores':'isolated temporary stores','checks':['AI selects registered scientific tool','Invalid final references return exact checked evidence',
                'Canvas source captured automatically before submission','Actual recipe persists matching cards, charts and workflow',
                'Navigation acknowledged only after board DOM load','Refresh preserves cards without duplicates'],
                'tool_trace':trace,'page_errors':errors}
        (output/'report.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
