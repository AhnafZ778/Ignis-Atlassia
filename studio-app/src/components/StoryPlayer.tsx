import { useEffect, useReducer, useRef, useState } from 'react';
import { initialPlayer, reduce, sceneIndexAt, formatClock, totalSeconds } from '../lib/scenes';
import type { ResolvedStory } from '../types';
import { JarvisPanel } from './JarvisPanel';
import { FactTable } from './CardBody';
import { cameraSvg } from '../../../studio-render/camera.mjs';
import { FrozenHeatTable } from './FrozenHeatTable';

export function StoryPlayer({ story, identity }: { story: ResolvedStory; identity?: { story_id: string; story_revision: number } }) {
  const [state, dispatch] = useReducer((s: ReturnType<typeof initialPlayer>, event: Parameters<typeof reduce>[2]) => reduce(story, s, event), undefined, initialPlayer);
  const at = sceneIndexAt(story, state.position), scene = story.scenes[at];
  const [followScroll, setFollowScroll] = useState(false);
  const transcript = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!followScroll || state.viewer === 'exploring' || state.viewer === 'question-paused' || !transcript.current) return;
    let queued = 0;
    const focusVisible = () => {
      queued = 0;
      const bounds = transcript.current?.getBoundingClientRect();
      if (!bounds) return;
      const top = Math.max(0, bounds.top), bottom = Math.min(innerHeight, bounds.bottom), center = (top + bottom) / 2;
      if (bottom <= top) return;
      const articles = Array.from(transcript.current?.querySelectorAll<HTMLElement>('[data-chapter]') || []);
      const target = articles.map((element) => ({ element, box: element.getBoundingClientRect() }))
        .filter(({ box }) => box.bottom > top && box.top < bottom)
        .sort((a, b) => Math.abs((a.box.top + a.box.bottom) / 2 - center) - Math.abs((b.box.top + b.box.bottom) / 2 - center))[0];
      const chapter = story.scenes.find((s) => s.chapter_id === target?.element.dataset.chapter);
      if (chapter) { dispatch({ type: 'pause' }); dispatch({ type: 'seek', seconds: chapter.start_seconds }); }
    };
    const schedule = () => { if (!queued) queued = requestAnimationFrame(focusVisible); };
    const observer = new IntersectionObserver(schedule, { threshold: [0.6, 0.9] });
    transcript.current.querySelectorAll('[data-chapter]').forEach((element) => observer.observe(element));
    window.addEventListener('scroll', schedule, { capture: true, passive: true });
    return () => { observer.disconnect(); cancelAnimationFrame(queued); window.removeEventListener('scroll', schedule, true); };
  }, [followScroll, state.viewer, story]);
  useEffect(() => {
    const follow = (event: Event) => {
      const target = (event as CustomEvent).detail;
      if (target.story_id && target.story_id !== identity?.story_id) return;
      if (target.story_revision && target.story_revision !== identity?.story_revision) return;
      const index = story.scenes.findIndex((item) => item.chapter_id === target.scene);
      if (index < 0) return;
      dispatch({ type: 'pause' });
      dispatch({ type: 'seek', seconds: story.scenes[index].start_seconds });
    };
    window.addEventListener('fireatlas-studio-presenter', follow);
    return () => window.removeEventListener('fireatlas-studio-presenter', follow);
  }, [story, identity?.story_id, identity?.story_revision]);
  useEffect(() => { if (scene) window.dispatchEvent(new CustomEvent('fireatlas-studio-chapter', { detail: { chapter_id: scene.chapter_id, ...identity } })); }, [scene?.chapter_id, identity?.story_id, identity?.story_revision]);
  useEffect(() => {
    if (!state.playing) return;
    const start = performance.now(); let previous = start;
    const timer = window.setInterval(() => { const now = performance.now(); dispatch({ type: 'tick', delta: (now - previous) / 1000 }); previous = now; }, 100);
    const visibility = () => { if (document.hidden) dispatch({ type: 'pause' }); };
    document.addEventListener('visibilitychange', visibility);
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', visibility); };
  }, [state.playing]);
  if (!scene) return <p>No chapters in this story.</p>;
  const move = (delta: number) => { dispatch({ type: 'pause' }); dispatch({ type: 'seek', seconds: story.scenes[Math.max(0, Math.min(story.scenes.length - 1, at + delta))].start_seconds }); };
  const facts = scene.evidence.flatMap((id) => story.snapshots[id]?.facts || []);
  const localProgress = Math.max(0, Math.min(1, (state.position - scene.start_seconds) / Math.max(0.001, scene.duration_seconds)));
  const sceneSvg = cameraSvg(scene.visual_svg || '', scene.visual, window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : localProgress);
  return <section className="player" aria-label="Interactive story preview" tabIndex={0} onKeyDown={(e) => {
    if ((e.target as HTMLElement).matches('input,textarea,select,button') || (e.target as HTMLElement).closest('[data-heat-table]')) return;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); move(e.key === 'ArrowLeft' ? -1 : 1); }
    if (e.key === ' ') { e.preventDefault(); dispatch({ type: state.playing ? 'pause' : 'play' }); }
  }}>
    <div className="player-stage" aria-live={state.playing ? 'off' : 'polite'}><span>Chapter {at + 1} of {story.scenes.length} · {state.viewer} · {scene.audience || story.audience || 'researcher'}</span><h3>{scene.title}</h3>{scene.visual_svg ? <div className="scene-schematic-wrap"><img className="scene-schematic" src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(sceneSvg)}`} alt={`${scene.title} — frozen evidence schematic`} /></div> : null}{scene.visible_card_views?.length ? <p className="muted">Visible evidence cards: {scene.visible_card_views.map((card) => card.title).join(' · ')}</p> : null}<FrozenHeatTable views={scene.visible_card_views} /><p className="player-caption">{scene.caption}</p><p>{scene.narration_text}</p><p className="muted" data-narration-grounding>{scene.narration_grounding?.note || 'Legacy authored narration; interpret alongside its cited fields.'}</p><FactTable facts={facts} />
      {state.viewer === 'exploring' ? <div className="question"><strong>Frozen chapter evidence</strong><p>Exploration stays attached to this chapter. The authored scene remains unchanged.</p><FactTable facts={facts} />{identity ? <JarvisPanel key={scene.chapter_id} chapter={{ ...identity, chapter_id: scene.chapter_id }} /> : null}<button className="btn" onClick={() => { dispatch({ type: 'return' }); dispatch({ type: 'returned' }); }}>Resume story</button></div> : scene.question ? <div className="question"><p>{scene.question.prompt}</p><p><strong>Author’s interpretation: </strong>{scene.question.answer || 'Inspect the frozen chapter evidence to explore this question.'}</p>{state.viewer === 'question-paused' ? <button className="btn" onClick={() => dispatch({ type: 'answer', chapter: scene.chapter_id })}>Continue reading</button> : null}</div> : null}
      {state.viewer !== 'exploring' ? <button className="btn" onClick={() => dispatch({ type: 'explore' })}>Explore chapter evidence</button> : null}
    </div><div className="player-controls"><button className="btn" onClick={() => move(-1)} disabled={state.viewer === 'exploring' || at === 0}>Previous</button><button className="btn" disabled={state.viewer !== 'reading'} onClick={() => dispatch({ type: state.playing ? 'pause' : 'play' })}>{state.playing ? 'Pause' : 'Play'}</button><button className="btn" onClick={() => move(1)} disabled={state.viewer === 'exploring' || at === story.scenes.length - 1}>Next</button><label>Position<input type="range" min={0} max={totalSeconds(story)} step={0.1} value={state.position} disabled={state.viewer === 'exploring'} onChange={(e) => dispatch({ type: 'seek', seconds: Number(e.target.value) })} /></label><span>{formatClock(state.position)} / {formatClock(totalSeconds(story))}</span></div>
    <details className="player-note"><summary>Transcript and limitations</summary><label><input type="checkbox" checked={followScroll} onChange={(e) => setFollowScroll(e.target.checked)} /> Follow chapters as I scroll</label><div ref={transcript} className="chapter-transcript">{story.scenes.map((s) => <article data-chapter={s.chapter_id} key={s.chapter_id}><h4><button className="link-button" disabled={state.viewer === 'exploring'} onClick={() => { dispatch({ type: 'pause' }); dispatch({ type: 'seek', seconds: s.start_seconds }); }}>{s.title}</button></h4><p>{s.narration_text}</p></article>)}</div>{story.limitations.map((line) => <p key={line}>{line}</p>)}</details>
  </section>;
}
