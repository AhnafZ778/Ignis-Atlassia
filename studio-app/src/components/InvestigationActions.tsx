import { useEffect, useRef, useState } from 'react';
import { api, idempotencyKey, uid } from '../api';
import { useStudio } from '../store';
import { effectiveStudy } from '../lib/graph';

/** Durable command feedback, board-scoped continuation and revision-bound portability. */
export function InvestigationActions() {
  const { doc, caps, selected, busy, canEdit, open, reload, isCurrent } = useStudio();
  const instance = useRef(uid('canvas'));
  const revision = useRef(0);
  const [command, setCommand] = useState<any>(null);
  const [working, setWorking] = useState(false);
  const [job, setJob] = useState<any>(null);
  const [preparedExports, setPreparedExports] = useState<any[]>([]);
  const [format, setFormat] = useState('native');
  const [scope, setScope] = useState('whole');
  const [status, setStatus] = useState('');
  const [details, setDetails] = useState<any>(null);
  const [miroBoard, setMiroBoard] = useState('');
  const [miroMode, setMiroMode] = useState('first');
  const [priorTransfer, setPriorTransfer] = useState('');
  const [imported, setImported] = useState<any[]>([]);
  const capability = caps as any;
  const context = (surface = 'studio') => ({
    schema: 'fireatlas-jarvis-context-v1', surface, origin_instance_id: instance.current,
    origin_tab_id: sessionStorage.getItem('fireatlas-jarvis-tab') || instance.current,
    context_revision: ++revision.current, study_selection: selected ? effectiveStudy(doc!.state.cards[selected], doc!.state).context : doc!.state.study.context,
    source_document_revision: doc!.revision, selected_object_ids: selected ? [selected] : [],
    result_refs: selected && doc!.state.cards[selected]?.snapshot_id ? [{ document_id: doc!.id, snapshot_id: doc!.state.cards[selected].snapshot_id }] : [],
    active_view: selected ? { ...(doc!.state.cards[selected].display.captured_view as object || {}), kind: doc!.state.cards[selected].type } : { kind: 'board' },
    destination: { intent: 'update-selection', board_id: doc!.id, revision: doc!.revision }, return_destination: String(selected && doc!.state.cards[selected]?.provenance.return_destination || command?.outputs.return_destination || ''),
  });
  useEffect(() => {
    const id = new URLSearchParams(location.search).get('command');
    if (!doc || !id) return;
    let active = true;
    (async () => {
      try {
        const saved = await api.getCommand(id);
        if (!active || saved.outputs.document_id !== doc.id) return;
        setCommand(saved);
        if (saved.outputs.export_job_ids?.length) { const exports = await Promise.all(saved.outputs.export_job_ids.map((id: string) => api.getExport(id))); if (!active) return; setPreparedExports(exports); }
        if (saved.status === 'awaiting_view_ack') {
          // DOM committed and board loaded before acknowledgment. Never acknowledge a mere navigation request.
          await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
          if (!active || !isCurrent(doc.id, doc.context_revision) || saved.outputs.object_ids.some((oid: string) => !doc.state.cards[oid])) return;
          await api.registerContext(context());
          if (!active || !isCurrent(doc.id, doc.context_revision)) return;
          const acknowledged = await api.commandAction(id, 'ack', { instance_id: instance.current, document_id: doc.id, revision: doc.revision, object_ids: saved.outputs.object_ids });
          if (active) setCommand(acknowledged);
        }
      } catch (e) { if (active) setStatus((e as Error).message); }
    })();
    return () => { active = false; };
  }, [doc?.id, doc?.revision]);
  useEffect(() => { if (!doc) return; let active = true; api.projects(doc.id).then((p: any) => { if (active) setImported(p.imported_annotations || []); }); return () => { active = false; }; }, [doc?.id]);
  if (!doc) return null;
  const continuation = async (action: string, extra: object = {}) => {
    setWorking(true); setStatus('Saving your command…'); const board = doc.id;
    try {
      const request = await api.submitCommand({ recipe: 'continue_investigation', context: context(), arguments: { action, ...extra } }, idempotencyKey());
      const url = new URL(location.href); url.searchParams.set('command',request.id); history.replaceState({},'',url.href);
      setCommand(request); let saved = request;
      while (!['completed', 'awaiting_view_ack', 'failed', 'partial', 'cancelled'].includes(saved.status)) {
        await new Promise((r) => setTimeout(r, 500)); saved = await api.getCommand(request.id);
        if (!isCurrent(board)) return; setCommand(saved); setStatus(saved.message);
      }
      if (!isCurrent(board)) return;
      if (saved.status === 'awaiting_view_ack') {
        const fresh = await api.getDocument(board); open(fresh);
        const ctx = { ...context(), study_selection: fresh.state.study.context, destination: { intent: 'update-selection', board_id: board, revision: fresh.revision } };
        await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
        if (!isCurrent(board)) return;
        await api.registerContext({ ...ctx, source_document_revision: fresh.revision });
        saved = await api.commandAction(saved.id, 'ack', { instance_id: instance.current, document_id: board, revision: fresh.revision, object_ids: saved.outputs.object_ids });
      }
      setCommand(saved); setStatus(saved.message);
      if (saved.outputs.snapshot_id) setDetails(await api.snapshotReceipt(board, saved.outputs.snapshot_id));
      if (saved.outputs.node) setDetails(saved.outputs.node);
      if (saved.outputs.run_id) {
        let run = await api.getRun(saved.outputs.run_id);
        while (run.status === 'running') { if (!isCurrent(board)) return; setDetails(run); setStatus('Running the saved workflow: ' + run.status); await new Promise((r) => setTimeout(r, 650)); run = await api.getRun(run.id); }
        if (!isCurrent(board)) return; setDetails(run); await reload(); setStatus('Workflow ' + run.status + (run.error ? ': ' + run.error : '. New results retain separate revisions.'));
        const exportId = (Object.values(run.outputs) as any[]).find((o) => o.type === 'export_job')?.job_id;
        if (exportId) { let ready = await api.getExport(exportId); while (['queued','preparing'].includes(ready.status)) { await new Promise((r) => setTimeout(r, 650)); if (!isCurrent(board)) return; ready = await api.getExport(exportId); } setJob(ready); }
      }
    } catch (e) { if (isCurrent(board)) setStatus((e as Error).message); }
    finally { setWorking(false); }
  };
  const exportBoard = async () => {
    setWorking(true); setStatus('Freezing saved board revision…'); const board = doc.id;
    try {
      // Wait for any editor blur save; a concurrent change is rejected by the revision check.
      const saved = await api.getDocument(board); if (!isCurrent(board)) return;
      const exportScope = scope === 'whole' ? { kind: 'whole' } : scope === 'selection' ? { kind: 'selection', object_ids: [selected] } : { kind: 'frame', frame_id: scope };
      let result = await api.prepareExport(board, { format, revision: saved.revision, scope: exportScope }); setJob(result);
      while (['queued', 'preparing'].includes(result.status)) {
        await new Promise((r) => setTimeout(r, 650)); result = await api.getExport(result.id); if (!isCurrent(board)) return; setJob(result);
      }
      setStatus(result.status === 'completed' ? 'Export ready. Frozen values were reused without rerunning science.' : result.error || 'Export failed.');
    } catch (e) { setStatus((e as Error).message); } finally { setWorking(false); }
  };
  const transfer = async () => {
    setWorking(true);
    try {
      let result = await api.transferMiro(doc.id, { board_id: miroBoard, mode: miroMode, previous_job_id: priorTransfer || undefined, revision: doc.revision });
      while (['queued', 'preparing'].includes(result.status)) { setStatus('Transferring individual objects to Miro…'); await new Promise((r) => setTimeout(r, 650)); result = await api.getMiroTransfer(result.id); }
      setStatus(result.error || result.status); setDetails(result);
    } catch (e) { setStatus((e as Error).message); } finally { setWorking(false); }
  };
  const cancel = async () => { if (command) { const saved = await api.commandAction(command.id, 'cancel'); setCommand(saved); setStatus(saved.message); } };
  const workflow = command?.outputs.workflow_id || (selected && doc.state.cards[selected]?.provenance.workflow_id);
  const applied = (selected ? effectiveStudy(doc.state.cards[selected], doc.state).context : doc.state.study.context) || {};
  const selectedCard = selected ? doc.state.cards[selected] : null;
  const metric = selectedCard ? String((selectedCard.display.captured_view as any)?.metric || doc.snapshots?.[selectedCard.snapshot_id || '']?.unit || 'Authored object') : 'Saved investigation';
  return <section className="panel orchestration-panel" aria-label="Investigation and portability">
    <div className="row"><strong>Investigation tools</strong><span className="muted">{selectedCard?.title || 'Whole saved board'} · {String(applied.case || applied.region || 'Custom study')} · {String(applied.day || `${applied.start}–${applied.end}`)} UTC · {metric} · Canvas: {doc.state.title} · revision {doc.revision}</span>
      {command?.outputs.return_destination ? <a className="btn" href={command.outputs.return_destination}>Return to captured source</a> : null}
      {workflow ? <button className="btn" disabled={working || busy || !canEdit} onClick={() => void continuation('run_workflow', { workflow_id: workflow })}>Run captured workflow</button> : null}
      {command?.outputs.transaction_id && !command.outputs.undone ? <button className="btn" disabled={working || busy || !canEdit} onClick={async () => { try { setCommand(await api.commandAction(command.id, 'undo')); await reload(); setStatus('This command was undone. Unrelated edits were retained.'); } catch (e) { setStatus((e as Error).message); } }}>Undo this JARVIS change</button> : null}
      {command && ['partial', 'failed'].includes(command.status) ? <button className="btn" onClick={async () => { setWorking(true); try { let saved = await api.commandAction(command.id, 'resume'); while (!['awaiting_view_ack','completed','cancelled','partial','failed'].includes(saved.status)) { await new Promise((r) => setTimeout(r,650)); saved = await api.getCommand(saved.id); if (!isCurrent(doc.id)) return; setCommand(saved); setStatus(saved.message); } const url = new URL(location.href); url.searchParams.set('command',saved.id); location.assign(url.href); } catch (e) { setStatus((e as Error).message); } finally { setWorking(false); } }}>Resume saved command</button> : null}
    </div>
    <div className="row"><button className="btn small" disabled={!selected || working || busy || !canEdit} onClick={() => void continuation('pin')}>Pin selected card to this date</button><button className="btn small" disabled={!selected || working || busy} onClick={() => void continuation('show_data')}>Inspect frozen data</button><button className="btn small" disabled={!selected || working || busy || !canEdit} onClick={() => void continuation('arrange')}>Arrange selected card</button></div>
    <details><summary>Export or restore the editable whiteboard</summary>
      <p>Whole board includes offscreen objects, saved workflows, stories, frozen evidence and attributed discussion. Native archives restore FireAtlas objects. Excalidraw keeps text, shapes, images and bound arrows editable.</p>
      <div className="row"><label className="field">Format<select value={format} onChange={(e) => setFormat(e.target.value)}>{['native', 'excalidraw', 'svg', 'png', 'pdf'].map((f) => <option key={f} value={f} disabled={capability?.portability?.[f]?.available === false}>{f === 'native' ? 'Native .fireatlas.zip + Excalidraw companion' : f.toUpperCase()}</option>)}</select></label><label className="field">Export scope<select value={scope} onChange={(e) => setScope(e.target.value)}><option value="whole">Whole board · including offscreen</option><option value="selection" disabled={!selected}>Selected card</option>{Object.values(doc.state.groups || {}).map((g) => <option key={g.id} value={g.id}>Frame: {g.title}</option>)}</select></label><button className="btn primary" disabled={working || busy || !doc.state.order.length} onClick={() => void exportBoard()}>Prepare export</button>{job?.status === 'completed' ? <a className="btn" href={api.exportDownload(job.id)} download>Download {job.format}</a> : null}</div>
      <label className="field">Restore native archive into a new board<input type="file" accept=".zip,application/zip" disabled={working || busy} onChange={async (e) => { const file = e.target.files?.[0]; if (!file) return; if (file.size > 512 * 1024 ** 2) { setStatus('Choose an archive up to 512 MiB.'); return; } setWorking(true); try { const result = await api.restoreArchive(file); const url = new URL(location.href); url.search = new URLSearchParams({ board: result.document.id }).toString(); location.assign(url.href); } catch (error) { setStatus((error as Error).message); } finally { setWorking(false); } }} /></label>
      <p className="muted">Imported receipts remain attributed frozen provenance. Scientific reruns require compatible local inputs. <a href="./studio-excalidraw.html">Open the Excalidraw continuation editor</a></p>
    </details>
    {capability?.miro?.available ? <details><summary>Explicitly send to an allowed Miro destination</summary><div className="row"><label className="field">Allowed destination<select value={miroBoard} onChange={(e) => setMiroBoard(e.target.value)}><option value="">Choose destination</option>{(capability.miro.destinations || []).map((id: string) => <option key={id}>{id}</option>)}</select></label><label className="field">Transfer mode<select value={miroMode} onChange={(e) => setMiroMode(e.target.value)}><option value="first">First transfer</option><option value="repeat-as-new">Repeat as new</option><option value="update-existing">Update existing mapped objects</option></select></label>{miroMode === 'update-existing' ? <label className="field">Previous transfer ID<input value={priorTransfer} onChange={(e) => setPriorTransfer(e.target.value)} /></label> : null}<button className="btn" disabled={!miroBoard || working || busy || !canEdit} onClick={() => void transfer()}>Send to Miro</button></div></details> : <p className="muted">Miro transfer requires an operator token and an explicitly allowed destination.</p>}
    {working && command && !['completed','cancelled','failed'].includes(command.status) ? <button className="btn" onClick={() => void cancel()}>Cancel this command</button> : null}
    {preparedExports.map((item) => item.status === 'completed' ? <a key={item.id} className="btn" href={api.exportDownload(item.id)} download>Download prepared {item.format}</a> : null)}
    <p role="status">{status || (command ? `${command.status}: ${command.message}` : 'Frozen captures and exports work without a model provider.')}</p>
    {command?.outputs.package_id ? <button className="btn small" onClick={async () => setDetails(await api.getPackage(command.outputs.package_id))}>Inspect package, workflow inputs and actual operation trace</button> : null}
    {details ? <details open><summary>Saved operation details</summary><button className="btn small" onClick={() => setDetails(null)}>Close details</button><pre className="portable-details">{JSON.stringify(details, null, 2)}</pre></details> : null}
    {imported.length ? <details><summary>Imported historical discussion ({imported.length})</summary>{imported.map((c) => <p key={c.id}><strong>{c.author_label}</strong>: {c.body}</p>)}</details> : null}
  </section>;
}
