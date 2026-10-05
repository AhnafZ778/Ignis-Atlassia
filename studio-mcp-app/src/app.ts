import { App } from '@modelcontextprotocol/ext-apps';
import './style.css';
const app = new App({ name: 'FireAtlas Research Studio', version: '0.1.0' }, {}, { autoResize: true });
const element = (id: string) => document.getElementById(id)!;
const status = (text: string) => { element('status').textContent = text; };
let board: any = null;
let story: any = null;
let chapter = 0;
let sequence = 0;
const instance='mcp-'+crypto.randomUUID().replaceAll('-','').slice(0,20);let contextRevision=0;let activeContext:any=null;
const call=async(name:string,args:Record<string,unknown>)=>decoded(await app.callServerTool({name,arguments:args}));
function contextFor(card:any=null){return {schema:'fireatlas-jarvis-context-v1',surface:'mcp',origin_instance_id:instance,origin_tab_id:instance,context_revision:++contextRevision,source_document_revision:board.revision,study_selection:card?.follow==='pinned'?card.pinned_study.context:board.state.study.context,active_view:card?.display?.captured_view||{kind:card?.type||'board'},selected_object_ids:card?[card.id]:[],result_refs:card?.snapshot_id?[{document_id:board.id,snapshot_id:card.snapshot_id}]:[],destination:{intent:'append',board_id:board.id,revision:board.revision},return_destination:''};}
async function packageSelection(){if(!activeContext)throw Error('Select an owned evidence card first.');const submitting=activeContext;let command=await call('studio_command',{recipe:'visualization_to_investigation',context:submitting,idempotency_key:'mcp-'+crypto.randomUUID(),arguments:{}});while(!['awaiting_view_ack','completed','partial','failed','cancelled'].includes(command.status)){status(command.message);await new Promise(r=>setTimeout(r,600));command=await call('studio_command_status',{command_id:command.id});}if(command.status==='awaiting_view_ack'){const document=await call('studio_get_document',{document_id:command.outputs.document_id});renderBoard({document});const actual=contextFor();await call('studio_register_context',{context:actual});if(!command.outputs.object_ids.every((id:string)=>board.state.cards[id]))throw Error('Saved destination objects are not visible in this host.');command=await call('studio_command_action',{command_id:command.id,action:'ack',arguments:{instance_id:instance,document_id:board.id,revision:board.revision,object_ids:command.outputs.object_ids}});}status(command.message);}
function text(tag: string, value: unknown) { const node = document.createElement(tag); node.textContent = String(value ?? 'unknown'); return node; }
function decoded(result: any) {
  if (result.isError) throw new Error(result.content?.find((c: any) => c.type === 'text')?.text || 'The owned tool request failed.');
  if (result.structuredContent) return result.structuredContent.result || result.structuredContent;
  return JSON.parse(result.content?.find((c: any) => c.type === 'text')?.text || '{}');
}
function button(title: string, action: () => void) { const b = document.createElement('button'); b.type = 'button'; b.textContent = title; b.addEventListener('click', action); return b; }
function table(facts: any[]) {
  const root = document.createElement('table'); const head = document.createElement('tr');
  for (const title of ['Checked value', 'Reading', 'Unit']) head.append(text('th', title)); root.append(head);
  for (const fact of facts) { const row = document.createElement('tr'); for (const value of [fact.label, fact.value ?? fact.state, fact.unit]) row.append(text('td', value)); root.append(row); }
  return root;
}
async function selected(id: string) {
  if (!board) return;
  const version = ++sequence;
  const card = board.state.cards[id];
  const panel = element('evidence'); panel.replaceChildren(text('h2', card.title), text('p', card.text));
  const snapshot = board.snapshots[card.snapshot_id];
  if (snapshot) {
    panel.append(table(snapshot.facts), text('p', 'Method: ' + snapshot.method.id), text('p', 'Receipt: ' + snapshot.receipt_sha256));
    snapshot.limitations.forEach((line: string) => panel.append(text('p', line)));
    try {
      const result = decoded(await app.callServerTool({ name: 'studio_preview_card', arguments: { document_id: board.id, card_id: id } }));
      if (version !== sequence) return;
      const image = document.createElement('img'); image.alt = card.title + ' — frozen evidence schematic'; image.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(result.svg); panel.prepend(image);
    } catch (error) { status(error instanceof Error ? error.message : 'A prepared view is unavailable. Checked values remain usable.'); }
  }
  if (version !== sequence) return;
  activeContext=contextFor(card);await call('studio_register_context',{context:activeContext});
  await app.updateModelContext({ content: [{ type: 'text', text: JSON.stringify({ jarvis_context:activeContext, studio_selection: { document_id: board.id, document_revision: board.revision, card_id: id, snapshot_sha256: snapshot?.snapshot_sha256, study: board.state.study } }) }] });
  status('This selection is attached to the next assistant question. No observations were edited.');
}
function renderStory() {
  const root = element('story'); root.replaceChildren();
  const scene = story?.resolved?.scenes[chapter];
  if (!scene) return;
  root.append(text('h2', story.body.title), text('h3', scene.title));
  const image = document.createElement('img'); image.alt = scene.title + ' — prepared scene'; image.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(scene.visual_svg); root.append(image, text('p', scene.caption), text('p', scene.narration_text));
  const previous = button('Previous chapter', () => { chapter--; renderStory(); void contextChapter().catch((error) => status('Chapter context was not acknowledged: ' + String(error)));  }); previous.disabled = chapter === 0;
  const next = button('Next chapter', () => { chapter++; renderStory(); void contextChapter().catch((error) => status('Chapter context was not acknowledged: ' + String(error)));  }); next.disabled = chapter >= story.resolved.scenes.length - 1;
  root.append(previous, next, text('p', `Chapter ${chapter + 1} of ${story.resolved.scenes.length}`));
}
async function contextChapter() {
  const scene = story.resolved.scenes[chapter];
  await app.updateModelContext({ content: [{ type: 'text', text: JSON.stringify({ studio_story: { story_id: story.id, revision: story.revision, chapter_id: scene.chapter_id, selection: scene.selection, evidence: scene.evidence } }) }] });
}
function renderBoard(data: any) {
  board = data.document || data;
  if (!board?.state) throw new Error('Choose an owned Studio board.');
  story = null; sequence++;
  element('story').replaceChildren(); element('evidence').replaceChildren();
  element('scope').replaceChildren(text('h2', board.title), text('p', 'Revision ' + board.revision), text('p', JSON.stringify(board.state.study.context)));
  element('cards').replaceChildren(...board.state.order.map((id: string) => button(board.state.cards[id].title, () => { void selected(id).catch((error) => status('Selection context was not acknowledged: ' + String(error)));  })));
  if (data.stories?.length) element('cards').append(...data.stories.map((saved: any) => button('Read ' + saved.title, async () => { try { story = decoded(await app.callServerTool({ name: 'studio_read_story', arguments: { story_id: saved.id } })); chapter = 0; renderStory(); await contextChapter(); } catch (error) { status(String(error)); } })));
  element('cards').append(button('Package selected evidence to this canvas',()=>{void packageSelection().catch(e=>status(String(e)));}));
  status('Choose a card or a saved story. Calculations retain their original scope and units.');
}
app.ontoolresult = (result) => { try { const data = decoded(result); if (data.resolved) { story = data; chapter = 0; renderStory(); } else renderBoard(data); } catch (error) { status(String(error)); } };
app.onerror = (error) => status('The host bridge is unavailable. Use the structured tool result or local website. ' + String(error));
void app.connect().catch((error) => status('This host does not provide an MCP Apps bridge. Text and JSON tools remain available. ' + String(error)));
