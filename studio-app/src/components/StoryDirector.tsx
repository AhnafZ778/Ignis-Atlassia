import { useEffect, useRef, useState } from 'react';
import { api, ApiError, uid } from '../api';
import { useStudio } from '../store';
import type { Chapter, StoryBody, StoryView, RenderJob, RenderSummary, StoryGenerationJob } from '../types';
import { StoryPlayer } from './StoryPlayer';
import { adaptAudience } from '../lib/audience';

const errorText = (error: unknown) => error instanceof ApiError ? error.message : 'The request failed. Your draft is retained.';
const clone = <T,>(value: T): T => structuredClone(value);
export function StoryDirector() {
  const { doc, canEdit, notify, caps } = useStudio();
  const boardId = doc!.id;
  const active = useRef(boardId); active.current = boardId;
  const [story, setStory] = useState<StoryView | null>(null);
  const [draft, setDraft] = useState<StoryBody | null>(null);
  const [savedStories, setSavedStories] = useState<{ id: string; title: string }[]>([]);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('Opening saved stories…');
  const [selected, setSelected] = useState(0);
  const [narrate, setNarrate] = useState(false);
  const [render, setRender] = useState<RenderJob | null>(null);
  const [savedRenders, setSavedRenders] = useState<RenderSummary[]>([]);
  const renderEpoch = useRef(0), activeStory = useRef<string | null>(null);
  const storyRequest = useRef(0);
  const [chosenCards, setChosenCards] = useState<string[]>(doc!.state.order);
  const timer = useRef<number | undefined>(undefined);
  const generationTimer = useRef<number | undefined>(undefined);
  const generationEpoch = useRef(0);
  const [generation, setGeneration] = useState<StoryGenerationJob | null>(null);
  const dirty = Boolean(story && draft && JSON.stringify(story.body) !== JSON.stringify(draft));

  const accept = (next: StoryView, history = savedRenders) => {
    if (active.current !== next.document_id) return;
    activeStory.current = next.id;
    const epoch = ++renderEpoch.current; window.clearTimeout(timer.current); setRender(null);
    setStory(next); setDraft(clone(next.body)); setSelected(0);
    setSavedStories((all) => [{ id: next.id, title: next.body.title }, ...all.filter((s) => s.id !== next.id)]);
    const latest = history.find((job) => job.story_id === next.id);
    if (latest) void poll(latest.id, epoch);
  };
  useEffect(() => {
    let live = true; const request = ++storyRequest.current;
    setStory(null); setDraft(null); setRender(null); setSavedRenders([]); activeStory.current = null; setStatus('Opening saved stories…');
    api.projects(boardId).then(async (projects) => {
      if (!live || request !== storyRequest.current) return;
      setSavedStories(projects.stories);
      setSavedRenders(projects.renders || []);
      const pending = projects.story_generations?.[0];
      if (pending && (!pending.story_id || pending.story_id === projects.stories[0]?.id)) {
        setBusy(true); void watchGeneration(pending.id, ++generationEpoch.current);
      }
      if (!projects.stories.length) { setStatus('Choose evidence cards on the board, then create your story.'); return; }
      const next = await api.getStory(projects.stories[0].id);
      if (!live || request !== storyRequest.current) return;
      accept(next, projects.renders || []);
      const local = localStorage.getItem(`fireatlas-story-draft:${boardId}:${next.id}`);
      if (local) {
        try { const pending = JSON.parse(local); if (pending.baseRevision === next.revision) { setDraft(pending.body); setStatus('Recovered your unsaved local draft. Save it to create a story revision.'); return; } } catch { /* invalid draft is never applied */ }
      }
      setStatus(`Restored saved story revision ${next.revision}.`);
    }).catch((error) => live && setStatus(errorText(error)));
    return () => { live = false; ++storyRequest.current; ++renderEpoch.current; ++generationEpoch.current; window.clearTimeout(timer.current); window.clearTimeout(generationTimer.current); };
  }, [boardId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!story || !draft) return;
    try {
      const key = `fireatlas-story-draft:${boardId}:${story.id}`;
      if (dirty) localStorage.setItem(key, JSON.stringify({ baseRevision: story.revision, body: draft }));
      else localStorage.removeItem(key);
    } catch { notify('Browser draft storage is unavailable. Save this revision before leaving.'); }
  }, [boardId, story, draft, dirty, notify]);

  const watchGeneration = async (id: string, epoch: number) => {
    try {
      const job = await api.storyGeneration(id);
      if (active.current !== boardId || epoch !== generationEpoch.current) return;
      setGeneration(job);
      if (job.story_id && activeStory.current !== job.story_id) {
        const next = await api.getStory(job.story_id);
        if (active.current !== boardId || epoch !== generationEpoch.current) return;
        accept(next);
      }
      if (job.render) setRender(job.render);
      setStatus(job.error || (job.status === 'completed' ? 'Your infographic story is ready.' : 'JARVIS is preparing your infographic story…'));
      if (['queued', 'running'].includes(job.status)) generationTimer.current = window.setTimeout(() => void watchGeneration(id, epoch), 900);
      else setBusy(false);
    } catch (error) {
      if (active.current === boardId && epoch === generationEpoch.current) { setStatus(errorText(error)); setBusy(false); }
    }
  };
  const create = async () => {
    setBusy(true);
    const epoch = ++generationEpoch.current;
    window.clearTimeout(generationTimer.current); setGeneration(null);
    setStatus('Capturing the investigation for JARVIS…');
    try {
      const job = await api.generateStory(boardId, doc!.revision, chosenCards);
      if (active.current !== boardId || epoch !== generationEpoch.current) return;
      setGeneration(job); void watchGeneration(job.id, epoch);
    } catch (error) { if (active.current === boardId && epoch === generationEpoch.current) { setStatus(errorText(error)); setBusy(false); } }
  };
  const save = async (): Promise<StoryView | null> => {
    if (!story || !draft) return null;
    if (!dirty) return story;
    const next = await api.updateStory(story.id, story.revision, draft);
    if (active.current !== boardId) return null;
    setStory(next); setDraft(clone(next.body)); setStatus(`Saved story revision ${next.revision}.`);
    return next;
  };
  const resolve = async () => {
    setBusy(true);
    try { const next = await save(); if (!next) return; const result = await api.resolveStory(next.id); if (active.current === boardId) { setStory({ ...next, resolved: result.resolved }); setStatus('Resolved this revision against its frozen evidence.'); } }
    catch (error) { setStatus(errorText(error)); } finally { setBusy(false); }
  };
  const poll = async (id: string, epoch: number) => {
    try {
      const current = await api.getRender(id);
      if (active.current !== boardId || epoch !== renderEpoch.current || current.story_id !== activeStory.current) return;
      setRender(current);
      setSavedRenders((all) => all.map((job) => job.id === current.id ? { ...job, status: current.status } : job));
      if (['queued', 'running'].includes(current.status)) timer.current = window.setTimeout(() => void poll(id, epoch), 800);
      else setStatus(current.error || `Video ${current.status}.`);
    } catch (error) { if (active.current === boardId && epoch === renderEpoch.current) setStatus(errorText(error)); }
  };
  const startRender = async () => {
    if (!story || dirty) return;
    setBusy(true);
    const epoch = ++renderEpoch.current; window.clearTimeout(timer.current);
    try { const job = await api.startRender(story.id, narrate); if (active.current !== boardId || epoch !== renderEpoch.current || activeStory.current !== story.id) return; setRender(job); setSavedRenders((all) => [{ id: job.id, story_id: job.story_id, story_revision: job.story_revision, status: job.status, created: job.created }, ...all.filter((old) => old.id !== job.id)].slice(0, 30)); void poll(job.id, epoch); }
    catch (error) { if (active.current === boardId && epoch === renderEpoch.current) setStatus(errorText(error)); } finally { if (active.current === boardId) setBusy(false); }
  };
  const selectStory = async (id: string) => {
    ++generationEpoch.current; window.clearTimeout(generationTimer.current); setGeneration(null);
    const request = ++storyRequest.current;
    ++renderEpoch.current; window.clearTimeout(timer.current); setRender(null); activeStory.current = id;
    setBusy(true);
    try { const next = await api.getStory(id); if (active.current === boardId && request === storyRequest.current) accept(next); }
    catch (error) { if (active.current === boardId && request === storyRequest.current) { activeStory.current = story?.id || null; setStatus(errorText(error)); } }
    finally { if (active.current === boardId && request === storyRequest.current) setBusy(false); }
  };
  const cancelSelectedRender = async () => {
    if (!render) return;
    const epoch = renderEpoch.current;
    try { const next = await api.cancelRender(render.id); if (active.current === boardId && epoch === renderEpoch.current && next.story_id === activeStory.current) setRender(next); }
    catch (error) { if (active.current === boardId && epoch === renderEpoch.current) setStatus(errorText(error)); }
  };
  const edit = (index: number, patch: Partial<Chapter>) => setDraft((body) => body && ({ ...body, chapters: body.chapters.map((c, i) => i === index ? { ...c, ...patch, ...('narration' in patch || 'narration_segments' in patch ? { narration_template: null } : {}) } : c) }));
  const reorder = (index: number, delta: number) => {
    if (!draft) return;
    const at = index + delta; if (at < 0 || at >= draft.chapters.length) return;
    const chapters = [...draft.chapters]; [chapters[index], chapters[at]] = [chapters[at], chapters[index]];
    setDraft({ ...draft, chapters }); setSelected(at);
  };
  const add = (copy?: Chapter) => {
    if (!draft || draft.chapters.length >= 24) return;
    const next: Chapter = copy ? { ...clone(copy), id: uid('chapter'), title: `${copy.title} (copy)` } : { id: uid('chapter'), title: 'New chapter', caption: '', narration: '', card_id: null, duration_seconds: 20, transition: 'fade', evidence_cards: [], visible_cards: [] };
    setDraft({ ...draft, chapters: [...draft.chapters, next] }); setSelected(draft.chapters.length);
  };
  const chapter = draft?.chapters[selected];
  const running = generation && ['queued', 'running'].includes(generation.status);
  const labels: Record<string, string> = { capturing: 'Capturing your evidence', 'writing-story': 'AI& is writing the story', 'checking-evidence': 'Checking citations and composing scenes', 'preparing-assets': 'Preparing infographic visuals', rendering: 'Animating the film', encoding: 'Encoding your video', finalizing: 'Preparing downloads', completed: 'Your film is ready', saved: 'Your story is ready', 'story-ready': 'Your story is ready', failed: 'Story preparation stopped', cancelled: 'Cancelled', interrupted: 'Preparation interrupted' };
  return <section className="panel story-panel" aria-label="Story Director">
    <header className="story-hero"><div className="story-spark" aria-hidden="true">✦</div><div><span className="st-eyebrow">JARVIS · Infographic stories</span><h2>Turn evidence into a story.</h2><p>Maps, checked charts and a clear narrative, composed from this investigation.</p></div><button className="btn primary story-create" disabled={busy || !canEdit || dirty || !chosenCards.length || !caps?.story_generation?.available} onClick={() => void create()}>{running ? 'Creating your story…' : '✦ Create story'}</button></header>
    {!caps?.story_generation?.available ? <p className="muted">{caps?.story_generation?.reason || 'AI& story creation requires the local service.'}</p> : null}
    {generation ? <div className={`story-progress ${running ? 'active' : ''}`} aria-label="Story preparation"><div className="row"><strong>{labels[generation.phase] || generation.phase.replaceAll('-', ' ')}</strong><span>{Math.round(generation.progress * 100)}%</span>{running ? <button className="btn small" onClick={async () => { const id = generation.id, epoch = generationEpoch.current; try { const job = await api.cancelStoryGeneration(id); if (epoch === generationEpoch.current) { ++generationEpoch.current; window.clearTimeout(generationTimer.current); setGeneration(job); setBusy(false); setStatus('Cancelled. Saved story material remains available.'); } } catch (error) { setStatus(errorText(error)); } }}>Cancel</button> : null}</div><div className="story-progress-track" role="progressbar" aria-label="Story creation progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(generation.progress * 100)}><div style={{ width: `${generation.progress * 100}%` }} /></div><ol className="story-steps"><li>Evidence</li><li>Narrative</li><li>Infographics</li><li>Film</li></ol></div> : null}
    <p role="status" className="muted">{status}</p>
    {generation?.can_resume ? <button className="btn" disabled={busy || !canEdit} onClick={async () => { setBusy(true); const epoch = ++generationEpoch.current; try { const job = await api.resumeStoryGeneration(generation.id); if (active.current === boardId && epoch === generationEpoch.current) { setGeneration(job); void watchGeneration(job.id, epoch); } } catch (error) { if (epoch === generationEpoch.current) { setBusy(false); setStatus(errorText(error)); } } }}>Finish saved storyboard</button> : null}
    {render?.status === 'completed' && render.artifacts.video ? <div className="story-film"><video controls preload="metadata" aria-label="Generated infographic film" src={api.artifactUrl(render.id, 'video')}><track default kind="captions" srcLang="en" label="Checked story narration" src={api.artifactUrl(render.id, 'captions')} /></video><div className="row"><a className="btn primary" download="ignis-infographic.mp4" href={api.artifactUrl(render.id, 'video')}>Download film</a>{story?.resolved ? <a className="btn" href={api.exportUrl(story.id)}>Download interactive story</a> : null}</div></div> : story?.resolved && !dirty ? <StoryPlayer key={story.resolved.sha256} story={story.resolved} identity={{ story_id: story.id, story_revision: story.revision }} /> : !story ? <div className="story-empty" aria-hidden="true"><span>◉</span><span>▥</span><span>✦</span><p>Your investigation, beautifully connected.</p></div> : null}
    <details className="story-edit"><summary>Edit story &amp; export settings{dirty ? ' · unsaved changes' : ''}</summary>
    <details><summary>Choose material for the story</summary><div className="row">{doc!.state.order.map((id) => <label key={id}><input type="checkbox" checked={chosenCards.includes(id)} onChange={(e) => setChosenCards((all) => e.target.checked ? [...all, id] : all.filter((v) => v !== id))} /> {doc!.state.cards[id].title}</label>)}</div></details>
    <div className="row"><button className="btn" disabled={busy || !canEdit || dirty || !chosenCards.length} onClick={async () => { setBusy(true); try { const next = await api.createStory(boardId, { selected_cards: chosenCards }); if (active.current === boardId) { accept(next); setStatus('Manual draft created. Save and resolve to preview.'); } } catch (error) { setStatus(errorText(error)); } finally { setBusy(false); } }}>Start a manual draft</button>{savedStories.length ? <label className="field">Saved story<select value={story?.id || ''} disabled={dirty || busy} onChange={(e) => void selectStory(e.target.value)}>{savedStories.map((s) => <option value={s.id} key={s.id}>{s.title}</option>)}</select></label> : null}</div>
    {draft && story ? <>
      <div className="grid2"><label className="field">Story title<input maxLength={120} value={draft.title} disabled={!canEdit || busy} onChange={(e) => setDraft({ ...draft, title: e.target.value })} /></label><label className="field">Audience<select value={draft.audience || 'researcher'} disabled={!canEdit || busy} onChange={(e) => setDraft(adaptAudience(draft, e.target.value as NonNullable<StoryBody['audience']>))}>{['public', 'student', 'researcher', 'reviewer', 'presenter'].map((v) => <option key={v}>{v}</option>)}</select></label><label className="field">Target reading duration (seconds)<input type="number" min={10} max={600} value={draft.target_duration_seconds || 120} disabled={!canEdit || busy} onChange={(e) => setDraft({ ...draft, target_duration_seconds: Number(e.target.value) })} /></label></div>
      <p className="muted">Audience changes adapt marked starter prose and explanatory detail. Your manual text and checked fields stay unchanged; values, methods and evidence scope stay fixed.</p><div className="row"><button className="btn primary" disabled={busy || !dirty || !canEdit} onClick={async () => { setBusy(true); try { await save(); } catch (error) { setStatus(errorText(error)); } finally { setBusy(false); } }}>Save revision</button><button className="btn" disabled={busy || !canEdit} onClick={() => void resolve()}>Resolve checked scenes</button><button className="btn" disabled={!canEdit || busy || draft.chapters.length >= 24} onClick={() => add()}>Add chapter</button><a className="btn" aria-disabled={dirty || !story.resolved} href={!dirty && story.resolved ? api.exportUrl(story.id) : undefined}>Export reader ZIP</a><button className="btn" disabled={busy || dirty || !story.resolved || !canEdit || !caps?.video.available} onClick={() => void startRender()}>Render documentary</button></div>
      <p className="muted">{String((caps?.video.available ? caps.video.disclosure : caps?.video.reason) || '')}</p>{story.resolved?.warnings?.length ? <details><summary>Scene checks and limitations ({story.resolved.warnings.length})</summary>{story.resolved.warnings.map((warning, i) => <p key={i}>{warning.chapter ? `${warning.chapter}: ` : ""}{warning.message || warning.problem}</p>)}</details> : null}
      <label><input type="checkbox" checked={narrate} disabled={!caps?.narration.available || busy} onChange={(e) => setNarrate(e.target.checked)} /> AI narration through the existing assistant speech budget</label><p className="muted">{caps?.narration.available ? "Narration uses the saved text and its checked fields; explanatory prose remains authored interpretation. Provider failure keeps captions and transcript." : caps?.narration.reason}</p>
      {render ? <div className="row"><span>Video {(render.phase || render.status).replaceAll('-', ' ')} · {Math.round(render.progress * 100)}%</span>{['queued', 'running'].includes(render.status) ? <button className="btn" onClick={() => void cancelSelectedRender()}>Cancel render</button> : null}{Object.keys(render.artifacts || {}).map((name) => <a className="btn" key={name} href={api.artifactUrl(render.id, name)}>Download {name}</a>)}</div> : null}
      {savedRenders.some((job) => job.story_id === story.id) ? <label className="field">Recent video exports<select value={render?.id || ''} onChange={(e) => { const epoch = ++renderEpoch.current; window.clearTimeout(timer.current); setRender(null); if (e.target.value) void poll(e.target.value, epoch); }}><option value="">Choose a saved export</option>{savedRenders.filter((job) => job.story_id === story.id).map((job) => <option value={job.id} key={job.id}>Revision {job.story_revision} · {job.status} · {new Date(job.created * 1000).toISOString().slice(0, 19).replace('T', ' ')} UTC</option>)}</select></label> : null}
      {render ? <p className="muted">This export uses saved story revision {render.story_revision}.{render.story_revision !== story.revision ? ` The editor is on revision ${story.revision}; exporting again is an explicit action.` : ''}</p> : null}
      {render?.manifest ? <p className="muted" role="status" data-narration-outcome>Narration: {render.manifest.narration.status}. {render.manifest.narration.reason || render.manifest.narration.disclosure}</p> : null}
      <div className="director-layout"><nav className="chapter-list" aria-label="Chapter order">{draft.chapters.map((c, i) => <button className="btn" key={c.id} aria-current={selected === i ? 'step' : undefined} onClick={() => setSelected(i)}>{i + 1}. {c.title || 'Untitled'} · {c.duration_seconds}s</button>)}</nav>
      {chapter ? <article className="chapter"><div className="row"><button className="btn" aria-label="Move chapter earlier" disabled={!canEdit || busy || selected === 0} onClick={() => reorder(selected, -1)}>↑ Earlier</button><button className="btn" disabled={!canEdit || busy || selected >= draft.chapters.length - 1} onClick={() => reorder(selected, 1)}>↓ Later</button><button className="btn" disabled={!canEdit || busy} onClick={() => add(chapter)}>Duplicate</button><button className="btn danger" disabled={!canEdit || busy || draft.chapters.length <= 1} onClick={() => { setDraft({ ...draft, chapters: draft.chapters.filter((_, i) => i !== selected) }); setSelected(Math.max(0, selected - 1)); }}>Delete</button></div>
        <label className="field">Chapter title<input maxLength={120} disabled={!canEdit || busy} value={chapter.title} onChange={(e) => edit(selected, { title: e.target.value })} /></label>
        <label className="field">Primary visual<select value={chapter.card_id || ''} disabled={!canEdit || busy} onChange={(e) => edit(selected, { card_id: e.target.value || null, evidence_cards: e.target.value ? [e.target.value] : [], visible_cards: e.target.value ? [e.target.value] : [] })}><option value="">Text chapter</option>{doc!.state.order.map((id) => <option key={id} value={id}>{doc!.state.cards[id].title} ({doc!.state.cards[id].type})</option>)}</select></label>
        <label className="field">Caption<textarea maxLength={300} disabled={!canEdit || busy} value={chapter.caption} onChange={(e) => edit(selected, { caption: e.target.value })} /></label>
        <label className="field">Narration prose<textarea maxLength={1200} disabled={!canEdit || busy} value={chapter.narration} onChange={(e) => edit(selected, { narration: e.target.value, narration_segments: [] })} /></label>
        <label className="field">Append a checked value<select value="" disabled={!canEdit || busy} onChange={(e) => { if (!e.target.value) return; const [snapshot_id, path] = JSON.parse(e.target.value); edit(selected, { narration_segments: [...(chapter.narration_segments?.length ? chapter.narration_segments : [{ kind: 'text' as const, text: chapter.narration, author: 'user' as const }]), { kind: 'checked-field', snapshot_id, path, format: 'with-unit' }] }); }}><option value="">Select a cited field</option>{chapter.evidence_cards.flatMap((id) => { const sid = doc!.state.cards[id]?.snapshot_id; return sid ? (doc!.snapshots?.[sid]?.facts || []).map((fact) => <option key={`${id}:${fact.path}`} value={JSON.stringify([sid, fact.path])}>{fact.label}: {fact.value ?? fact.state} {fact.unit}</option>) : []; })}</select></label>
        {chapter.narration_segments?.length ? <p className="muted">Structured narration: {chapter.narration_segments.map((part) => part.kind === 'text' ? part.text : `[checked ${part.path}]`).join(' ')}</p> : null}
        <div className="grid2"><label className="field">Duration (seconds)<input type="number" min={2} max={300} disabled={!canEdit || busy} value={chapter.duration_seconds} onChange={(e) => edit(selected, { duration_seconds: Number(e.target.value) })} /></label><label className="field">Transition<select value={chapter.transition} disabled={!canEdit || busy} onChange={(e) => edit(selected, { transition: e.target.value as Chapter['transition'] })}>{['cut', 'fade', 'slide'].map((v) => <option key={v}>{v}</option>)}</select></label><label className="field">Selected UTC date<input type="date" disabled={!canEdit || busy} value={String(chapter.selection?.day || '')} onChange={(e) => edit(selected, { selection: { ...chapter.selection, day: e.target.value || undefined } })} /></label><label className="field">Visible sources<select value={typeof chapter.source_filter === 'string' ? chapter.source_filter : 'joint'} disabled={!canEdit || busy} onChange={(e) => edit(selected, { source_filter: e.target.value })}><option value="joint">Both sources</option><option value="MODIS_SP">MODIS</option><option value="VIIRS_SNPP_SP">VIIRS S-NPP</option></select></label></div>
        <div className="grid2"><label className="field">Interval start (UTC)<input type="date" disabled={!canEdit || busy} value={String(chapter.selection?.start || '')} onChange={(e) => edit(selected, { selection: { ...chapter.selection, start: e.target.value || undefined } })} /></label><label className="field">Interval end (UTC)<input type="date" disabled={!canEdit || busy} value={String(chapter.selection?.end || '')} onChange={(e) => edit(selected, { selection: { ...chapter.selection, end: e.target.value || undefined } })} /></label></div>
        <label className="field">Highlight common cells (grid_x:grid_y, comma-separated)<input disabled={!canEdit || busy} placeholder="Only cells present in the frozen interval" value={Array.isArray(chapter.selection?.highlight_cells) ? chapter.selection!.highlight_cells.join(', ') : ''} onChange={(e) => edit(selected, { selection: { ...chapter.selection, highlight_cells: e.target.value.split(',').map((v) => v.trim()).filter(Boolean) } })} /></label>
        <fieldset><legend>Visible evidence cards in this chapter</legend><div className="row">{doc!.state.order.map((id) => <label key={`visible-${id}`}><input type="checkbox" disabled={!canEdit || busy} checked={(chapter.visible_cards || []).includes(id)} onChange={(e) => edit(selected, { visible_cards: e.target.checked ? [...(chapter.visible_cards || []), id] : (chapter.visible_cards || []).filter((v) => v !== id) })} /> {doc!.state.cards[id].title}</label>)}</div><p className="muted">The selected cards are resolved into one frozen gallery shared by the reader and video. Their source values remain in the cited evidence receipts.</p></fieldset>
        <label className="field">Camera focus bounds (display only; optional)<input disabled={!canEdit || busy} value={Array.isArray(chapter.camera?.bbox) ? chapter.camera.bbox.join(', ') : ''} placeholder="west, south, east, north inside frozen study" onChange={(e) => edit(selected, { camera: { ...chapter.camera, bbox: e.target.value.trim() ? e.target.value.split(',').map((v) => v.trim() === '' ? null : Number(v.trim())) : undefined } })} /></label>
        <div className="grid2"><label className="field">Camera transition from<input disabled={!canEdit || busy} value={Array.isArray(chapter.camera?.from_bbox) ? chapter.camera.from_bbox.join(', ') : ''} placeholder="optional bounds" onChange={(e) => edit(selected, { camera: { ...chapter.camera, from_bbox: e.target.value.trim() ? e.target.value.split(',').map(Number) : undefined } })} /></label><label className="field">Camera transition to<input disabled={!canEdit || busy} value={Array.isArray(chapter.camera?.to_bbox) ? chapter.camera.to_bbox.join(', ') : ''} placeholder="optional bounds" onChange={(e) => edit(selected, { camera: { ...chapter.camera, to_bbox: e.target.value.trim() ? e.target.value.split(',').map(Number) : undefined } })} /></label></div>
        <fieldset><legend>Supplied landscape context</legend>{Object.entries((caps?.context_layers || {}) as Record<string, Record<string, { bounds: number[]; product: string; version: string }>>).flatMap(([caseId, layers]) => Object.entries(layers).filter(([, layer]) => JSON.stringify(layer.bounds) === JSON.stringify(doc!.state.study.context?.bbox)).map(([name, layer]) => <label key={`${caseId}:${name}`}><input type="checkbox" disabled={!canEdit || busy || doc!.state.cards[chapter.card_id || '']?.type !== 'map'} checked={(chapter.layers || []).includes(name)} onChange={(e) => edit(selected, { layers: e.target.checked ? [...(chapter.layers || []), name] : (chapter.layers || []).filter((v) => v !== name) })} /> {name} · {layer.product} {layer.version}</label>))}</fieldset><p className="muted">Layers use supplied dated products for their exact footprint. They are frozen with the scene and retain their actual temporal meaning. Camera focus crops the display and preserves full-study counts. Missing layers remain unavailable.</p>
        <label className="field">Viewer question<input maxLength={300} disabled={!canEdit || busy} value={chapter.question?.prompt || ''} onChange={(e) => edit(selected, { question: e.target.value ? { prompt: e.target.value, answer: chapter.question?.answer || '' } : null })} /></label>
        {chapter.question ? <label className="field">Author's answer (interpretation)<textarea maxLength={600} disabled={!canEdit || busy} value={chapter.question.answer || ''} onChange={(e) => edit(selected, { question: { ...chapter.question!, answer: e.target.value } })} /></label> : null}
      </article> : null}</div>
      <p className="muted">Editing the draft does not change a saved film. Save and resolve your changes before rendering another revision.</p>
    </> : null}
    </details>
  </section>;
}
