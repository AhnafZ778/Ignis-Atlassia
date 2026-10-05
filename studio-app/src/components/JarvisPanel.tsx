import { useEffect, useRef, useState } from 'react';
import { api, uid } from '../api';
import { useStudio } from '../store';

export function JarvisPanel({ chapter, workflow }: { chapter?: { story_id: string; story_revision: number; chapter_id: string }; workflow?: { workflow_id: string; workflow_revision: number; node_id: string } }) {
  const { doc, caps, selected, isCurrent, open, canEdit } = useStudio();
  const [message, setMessage] = useState('');
  const [result, setResult] = useState<any>(null);
  const [status, setStatus] = useState('Questions stay attached to this board and its frozen evidence.');
  const [working, setWorking] = useState(false);
  const instance = useRef(uid('jarvis'));
  const alive = useRef(true);
  const currentRun = useRef<string | null>(null);
  const running = useRef(false); running.current = working;
  const timer = useRef<number | undefined>(undefined);
  const board = doc!;
  useEffect(() => { alive.current = true; setWorking(false); setResult(null); return () => { alive.current = false; clearTimeout(timer.current); if (currentRun.current && running.current) void api.jarvisCancel(board.id, currentRun.current).catch(() => undefined); currentRun.current=null; }; }, [board.id,board.context_revision]); // eslint-disable-line react-hooks/exhaustive-deps
  const followCommand = async (id: string) => {
    try {
      const command = await api.getCommand(id);
      if (!alive.current || !isCurrent(board.id, board.context_revision)) return;
      setResult((previous: any) => ({ ...previous, command }));
      setStatus(`${command.status}: ${command.message}`);
      if (command.status === 'awaiting_view_ack' && command.outputs.document_id === board.id) {
        const url = new URL(location.href); url.searchParams.set('board',board.id); url.searchParams.set('command',command.id); location.assign(url.href);
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
  const ask = async (operation?: string) => {
    setWorking(true); setResult(null);
    try {
      const job = await api.jarvisStart(board.id, { base_revision: board.revision, instance_id: instance.current, tab_id: sessionStorage.getItem('fireatlas-jarvis-tab') || instance.current, message, operation, selected_cards: selected ? [selected] : [], ...chapter, ...workflow });
      if (!alive.current || !isCurrent(board.id, board.context_revision)) return;
      currentRun.current = job.id; setStatus(operation ? 'Running the existing stored-data calculation…' : 'JARVIS is inspecting this board…'); void poll(job.id);
    } catch (error) { if (alive.current) { setWorking(false); setStatus(error instanceof Error ? error.message : 'JARVIS could not start.'); } }
  };
  const assistant = caps?.assistant as { ai_available?: boolean; reason?: string } | undefined;
  return <details className="jarvis-panel"><summary>JARVIS · {chapter ? 'this saved chapter' : workflow ? 'this saved node' : 'this investigation'}</summary>
    <p role="status">{status}</p><label className="field">Question for JARVIS<textarea value={message} maxLength={3000} disabled={working} onChange={(e) => setMessage(e.target.value)} placeholder="Explain the selected evidence, or draft a card arrangement and six-chapter story." /></label>
    <div className="row"><button className="btn primary" disabled={working || !message.trim() || !assistant?.ai_available} onClick={() => void ask()}>Ask JARVIS</button><button className="btn" disabled={working} onClick={() => void ask('missingness')}>Check source states</button>{working ? <button className="btn" onClick={() => currentRun.current && api.jarvisCancel(board.id, currentRun.current).then(() => { setWorking(false); setStatus('Investigation canceled.'); })}>Cancel investigation</button> : null}</div>
    {!assistant?.ai_available ? <p className="muted">{assistant?.reason || 'Conversational inference is unavailable. Stored-data actions remain usable.'}</p> : null}
    {result?.body?.title ? <article><h3>{result.body.title}</h3><p>{result.body.summary || result.body.interpretation}</p><table className="facts"><thead><tr><th>Checked claim</th><th>Value</th><th>Unit</th></tr></thead><tbody>{(result.body.claims || []).map((fact: any, index: number) => <tr key={index}><td>{fact.label}</td><td>{String(fact.value)}</td><td>{fact.unit}</td></tr>)}</tbody></table>{(result.body.limitations || []).map((line: string) => <p className="muted" key={line}>{line}</p>)}</article> : null}
    {result?.command ? <article aria-label="Saved JARVIS command"><h3>Saved Canvas operation</h3><p>{result.command.status}: {result.command.message}</p>{result.command.outputs.document_id ? <a className="btn" href={`./studio.html?board=${encodeURIComponent(result.command.outputs.document_id)}&command=${encodeURIComponent(result.command.id)}`}>Open saved board</a> : null}<details><summary>Actual command outputs</summary><pre>{JSON.stringify(result.command.outputs,null,2)}</pre></details></article> : null}
    {(result?.proposals || []).map((proposal: any) => <article className="chapter" key={proposal.id}><h3>Presentation draft</h3><p>{proposal.summary}</p><details><summary>Inspect typed changes</summary><pre>{JSON.stringify(proposal.body, null, 2)}</pre></details><button className="btn" disabled={!canEdit || proposal.base_revision !== doc?.revision || working} onClick={async () => { try { const applied = await api.jarvisApply(board.id, proposal.id); if (!alive.current || !isCurrent(board.id, board.context_revision)) return; if (applied.document) open(applied.document); if (applied.workflow_draft) { const projects = await api.projects(board.id); if (!alive.current || !isCurrent(board.id, board.context_revision)) return; localStorage.setItem(`fireatlas-workflow-draft:${board.id}`, JSON.stringify({ baseRevision: projects.workflow?.revision || 0, definition: applied.workflow_draft.definition })); setStatus('Workflow draft loaded. Open Workflow to inspect and edit it, then explicitly save and run.'); return; } setStatus(applied.story ? 'Story draft saved. Open Story Director to edit and resolve it.' : 'Presentation change applied as a reversible transaction.'); } catch (error) { setStatus(error instanceof Error ? error.message : 'Draft could not be applied.'); } }}>Apply presentation draft</button></article>)}
  </details>;
}
