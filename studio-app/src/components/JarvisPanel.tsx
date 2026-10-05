import { useEffect, useRef, useState } from 'react';
import { api, uid, idempotencyKey } from '../api';
import { useStudio } from '../store';
import { effectiveStudy } from '../lib/graph';

export function JarvisPanel({ chapter, workflow }: { chapter?: { story_id: string; story_revision: number; chapter_id: string }; workflow?: { workflow_id: string; workflow_revision: number; node_id: string } }) {
  const { doc, caps, selected, displaySelections, isCurrent, open, canEdit } = useStudio();
  const [message, setMessage] = useState('');
  const [result, setResult] = useState<any>(null);
  const [status, setStatus] = useState('Questions stay attached to this board and its frozen evidence.');
  const [working, setWorking] = useState(false);
  const [presets, setPresets] = useState<{id:string; title:string; prompt:string; operation?:string}[]>([]);
  const [pending, setPending] = useState<{body:any; key:string; choices:{id:string; title:string; revision:number}[]} | null>(null);
  const [destination, setDestination] = useState('');
  const instance = useRef(uid('jarvis'));
  const alive = useRef(true);
  const currentRun = useRef<string | null>(null);
  const running = useRef(false); running.current = working;
  const timer = useRef<number | undefined>(undefined);
  const board = doc!;
  useEffect(() => { let active=true; api.promptPresets().then((result)=>active&&setPresets(result.presets)).catch(()=>undefined); return ()=>{active=false;}; }, []);
  useEffect(() => { setPending(null); setDestination(''); }, [board.id,board.revision,board.context_revision,selected]);
  useEffect(() => { alive.current = true; setWorking(false); setResult(null); return () => { alive.current = false; clearTimeout(timer.current); if (currentRun.current && running.current) void api.jarvisCancel(board.id, currentRun.current).catch(() => undefined); currentRun.current=null; }; }, [board.id,board.context_revision]); // eslint-disable-line react-hooks/exhaustive-deps
  const followCommand = async (id: string) => {
    try {
      const command = await api.getCommand(id);
      if (!alive.current || !isCurrent(board.id, board.context_revision)) return;
      setResult((previous: any) => ({ ...previous, command }));
      setStatus(`${command.status}: ${command.message}`);
      if (command.status === 'awaiting_view_ack' && command.outputs.document_id) {
        const url = new URL(location.href); url.searchParams.set('board',command.outputs.document_id); url.searchParams.set('command',command.id); url.searchParams.delete('tab'); location.assign(url.href);
      } else if (!['completed','failed','partial','cancelled'].includes(command.status)) {
        timer.current = window.setTimeout(() => void followCommand(id), 700);
      } else setWorking(false);
    } catch (error) {
      if (alive.current) { setWorking(false); setStatus(error instanceof Error ? error.message : 'Saved command progress is unavailable.'); }
    }
  };
  const poll = async (id: string) => {
    try {
      const next = await api.jarvisRun(board.id, id);
      if (!alive.current || !isCurrent(board.id, board.context_revision)) return;
      setResult(next);
      if (['queued', 'running'].includes(next.status)) timer.current = window.setTimeout(() => void poll(id), 700);
      else { setWorking(false); setStatus(next.body?.error || `Investigation ${next.status}. Numerical claims below come from checked receipts.`);
        if (next.status === 'completed') {
          const saved = next.body?.studio_commands?.[0];
          if (saved) { setWorking(true); void followCommand(saved.id); }
          else { const result = await api.instanceCommands(instance.current); const command = result.commands.find((c: any) => c.context.destination.board_id === board.id && c.status === 'awaiting_view_ack'); if (command && alive.current && isCurrent(board.id, board.context_revision)) { const url = new URL(location.href); url.searchParams.set('board',board.id); url.searchParams.set('command',command.id); location.assign(url.href); } }
        }
      }
    } catch (error) { if (alive.current) { setWorking(false); setStatus(error instanceof Error ? error.message : 'JARVIS is unavailable.'); } }
  };
  const sourceContext = () => {
    const card=selected ? board.state.cards[selected] : Object.values(board.state.cards).find((c)=>c.type==='map'&&c.snapshot_id) || Object.values(board.state.cards).find((c)=>c.snapshot_id);
    const snapshot=card?.snapshot_id ? board.snapshots?.[card.snapshot_id] : null;
    const study={...(card ? effectiveStudy(card,board.state).context : board.state.study.context),
      ...(card?.display.day?{day:card.display.day}:{}),...(card?.display.source?{source:card.display.source}:{}),
      ...(card&&displaySelections[card.id]?.day?{day:displaySelections[card.id].day}: {})};
    return {schema:'fireatlas-jarvis-context-v1',surface:'studio',origin_instance_id:instance.current,origin_tab_id:sessionStorage.getItem('fireatlas-jarvis-tab')||instance.current,
      context_revision:board.context_revision,source_document_revision:board.revision,study_selection:study||{},
      active_view:{...(card?.display.captured_view||{}),kind:card?.type||'board',operation:snapshot?.operation||'replay',...(study.day?{day:study.day}:{}),...(study.source?{source:study.source}:{})},
      selected_object_ids:selected?[selected]:[],result_refs:snapshot?[{document_id:board.id,snapshot_id:snapshot.id}]:[],
      destination:{intent:'append',board_id:board.id,revision:board.revision},return_destination:''};
  };
  const startPrompt = async (body:any,key:string) => {
    const response=await api.promptCommand(body,key);
    if(!alive.current||!isCurrent(board.id,board.context_revision))return true;
    if(response.status==='needs_destination') { setPending({body,key,choices:response.choices});setDestination('');setStatus(response.question);setWorking(false);return true; }
    if(response.operation){await ask(response.operation);return true;}
    if(response.command){setPending(null);setResult({command:response.command});setStatus('Preparing the saved investigation…');void followCommand(response.command.id);return true;}
    return false;
  };
  const ask = async (operation?: string) => {
    setWorking(true); setResult(null);
    try {
      if(!operation && await startPrompt({message,context:sourceContext()},idempotencyKey()))return;
      if(!operation && !assistant?.ai_available)throw new Error('Conversational inference is unavailable. Select a supported prompt preset or use a stored-data action.');
      const job = await api.jarvisStart(board.id, { base_revision: board.revision, instance_id: instance.current, tab_id: sessionStorage.getItem('fireatlas-jarvis-tab') || instance.current, message, operation, selected_cards: selected ? [selected] : [], ...chapter, ...workflow });
      if (!alive.current || !isCurrent(board.id, board.context_revision)) return;
      currentRun.current = job.id; setStatus(operation ? 'Running the existing stored-data calculation…' : 'JARVIS is inspecting this board…'); void poll(job.id);
    } catch (error) { if (alive.current) { setWorking(false); setStatus(error instanceof Error ? error.message : 'JARVIS could not start.'); } }
  };
  const assistant = caps?.assistant as { ai_available?: boolean; reason?: string } | undefined;
  return <details className="jarvis-panel"><summary>JARVIS · {chapter ? 'this saved chapter' : workflow ? 'this saved node' : 'this investigation'}</summary>
    <p role="status">{status}</p><div className="jarvis-prompt-presets" role="group" aria-label="Reliable JARVIS prompts">{presets.map((preset)=><button className="btn small" key={preset.id} disabled={working||!canEdit&& !preset.operation} onClick={()=>{setMessage(preset.prompt);setPending(null);if(preset.operation)void ask(preset.operation);}}>{preset.title}</button>)}</div><p className="muted">Choose a prompt, then ask JARVIS. Presentation and checked-data presets use the saved recipe runner and work without inference.</p><label className="field">Question for JARVIS<textarea value={message} maxLength={3000} disabled={working} onChange={(e) => {setMessage(e.target.value);setPending(null);}} placeholder="Create a comprehensive presentation on Canvas from this study." /></label>
    <div className="row"><button className="btn primary" disabled={working || !message.trim()} onClick={() => void ask()}>Ask JARVIS</button><button className="btn" disabled={working} onClick={() => void ask('missingness')}>Check source states</button>{working ? <button className="btn" onClick={() => {if(result?.command){void api.commandAction(result.command.id,'cancel').then(()=>{setWorking(false);setStatus('Canvas operation cancelled. Saved evidence remains available.');});clearTimeout(timer.current);}else if(currentRun.current)void api.jarvisCancel(board.id,currentRun.current).then(()=>{setWorking(false);setStatus('Investigation canceled.');});}}>Cancel investigation</button> : null}</div>
    {pending ? <fieldset className="jarvis-destination"><legend>Which Canvas should receive this investigation?</legend><label className="field">Canvas destination<select value={destination} onChange={(e)=>setDestination(e.target.value)}><option value="">Select a Canvas</option><option value="new">Create a new investigation Canvas</option>{pending.choices.map((choice)=><option key={choice.id} value={choice.id}>{choice.title}{choice.id===board.id?' · current Canvas':''}</option>)}</select></label><p>The submitted study stays frozen. Existing cards keep their positions; new evidence is arranged below them.</p><button className="btn primary" disabled={!destination||working} onClick={async()=>{setWorking(true);try{const choice=pending.choices.find((c)=>c.id===destination);await startPrompt({...pending.body,destination:destination==='new'?{intent:'new-board'}:{intent:'append',board_id:choice!.id,revision:choice!.revision}},pending.key);}catch(error){setWorking(false);setStatus(error instanceof Error?error.message:'Canvas operation could not start.');}}}>Create presentation on selected Canvas</button><button className="btn" onClick={()=>{setPending(null);setStatus('Canvas delivery cancelled. Nothing was inserted.');}}>Cancel Canvas selection</button></fieldset> : null}
    {!assistant?.ai_available ? <p className="muted">{assistant?.reason || 'Conversational inference is unavailable. Stored-data actions remain usable.'}</p> : null}
    {result?.body?.title ? <article><h3>{result.body.title}</h3><p>{result.body.summary || result.body.interpretation}</p><table className="facts"><thead><tr><th>Checked claim</th><th>Value</th><th>Unit</th></tr></thead><tbody>{(result.body.claims || []).map((fact: any, index: number) => <tr key={index}><td>{fact.label}</td><td>{String(fact.value)}</td><td>{fact.unit}</td></tr>)}</tbody></table>{(result.body.limitations || []).map((line: string) => <p className="muted" key={line}>{line}</p>)}</article> : null}
    {result?.command ? <article aria-label="Saved JARVIS command"><h3>Saved Canvas operation</h3><p>{result.command.status}: {result.command.message}</p>{result.command.outputs.document_id ? <a className="btn" href={`./studio.html?board=${encodeURIComponent(result.command.outputs.document_id)}&command=${encodeURIComponent(result.command.id)}`}>Open saved board</a> : null}<details><summary>Actual command outputs</summary><pre>{JSON.stringify(result.command.outputs,null,2)}</pre></details></article> : null}
    {(result?.proposals || []).map((proposal: any) => <article className="chapter" key={proposal.id}><h3>Presentation draft</h3><p>{proposal.summary}</p><details><summary>Inspect typed changes</summary><pre>{JSON.stringify(proposal.body, null, 2)}</pre></details><button className="btn" disabled={!canEdit || proposal.base_revision !== doc?.revision || working} onClick={async () => { try { const applied = await api.jarvisApply(board.id, proposal.id); if (!alive.current || !isCurrent(board.id, board.context_revision)) return; if (applied.document) open(applied.document); if (applied.workflow_draft) { const projects = await api.projects(board.id); if (!alive.current || !isCurrent(board.id, board.context_revision)) return; localStorage.setItem(`fireatlas-workflow-draft:${board.id}`, JSON.stringify({ baseRevision: projects.workflow?.revision || 0, definition: applied.workflow_draft.definition })); setStatus('Workflow draft loaded. Open Workflow to inspect and edit it, then explicitly save and run.'); return; } if (applied.story_generation) { setStatus('JARVIS is creating your infographic story. Opening its progress…'); window.dispatchEvent(new CustomEvent('fireatlas-studio-open-story')); return; } setStatus(applied.story ? 'Story draft saved. Open Story Director to edit and resolve it.' : 'Presentation change applied as a reversible transaction.'); } catch (error) { setStatus(error instanceof Error ? error.message : 'Draft could not be applied.'); } }}>Apply presentation draft</button></article>)}
  </details>;
}
