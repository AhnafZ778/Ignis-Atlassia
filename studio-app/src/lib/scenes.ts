import type { ResolvedStory, Scene } from '../types';

export type ViewerState = 'reading' | 'question-paused' | 'exploring' | 'returning';

export interface PlayerState {
  viewer: ViewerState; playing: boolean; position: number; // seconds into the story
  resume: number | null; // where a visitor left the story to explore
  answered: Record<string, boolean>;
}

export type PlayerEvent =
  | { type: 'play' } | { type: 'pause' } | { type: 'tick'; delta: number }
  | { type: 'seek'; seconds: number } | { type: 'explore' } | { type: 'return' } | { type: 'returned' } | { type: 'answer'; chapter: string };

export const initialPlayer = (): PlayerState => ({ viewer: 'reading', playing: false, position: 0, resume: null, answered: {} });

export const totalSeconds = (story: Pick<ResolvedStory, 'scenes'>) => story.scenes.reduce((sum, s) => sum + s.duration_seconds, 0);

export function sceneIndexAt(story: Pick<ResolvedStory, 'scenes'>, seconds: number): number {
  if (!story.scenes.length) return -1;
  const clamped = Math.max(0, seconds);
  for (let i = 0; i < story.scenes.length; i++) {
    const s = story.scenes[i];
    if (clamped < s.start_seconds + s.duration_seconds) return i;
  }
  return story.scenes.length - 1;
}

/**
 * Pure transition function for the browser player. A question pauses the story until it is answered; exploring pauses it
 * and remembers the position; returning restores that position before reading resumes.
 */
export function reduce(story: Pick<ResolvedStory, 'scenes'>, state: PlayerState, event: PlayerEvent): PlayerState {
  const total = totalSeconds(story);
  switch (event.type) {
    case 'play':
      if (state.viewer !== 'reading') return state;
      return { ...state, playing: true, position: state.position >= total ? 0 : state.position };
    case 'pause':
      return { ...state, playing: false };
    case 'seek': {
      if (state.viewer === 'exploring' || !Number.isFinite(event.seconds)) return state;
      return { ...state, position: Math.max(0, Math.min(total, event.seconds)), viewer: state.viewer === 'question-paused' ? 'reading' : state.viewer };
    }
    case 'tick': {
      if (!state.playing || state.viewer !== 'reading' || !Number.isFinite(event.delta) || event.delta < 0) return state;
      const before = sceneIndexAt(story, state.position);
      let position = Math.min(total, state.position + event.delta);
      // A delayed browser tick can cross several chapters. Pause at the first
      // unanswered question encountered, even when it wasn't the starting scene.
      for (let i = Math.max(0, before); i < story.scenes.length; i++) {
        const scene = story.scenes[i];
        if (position < scene.start_seconds + scene.duration_seconds) break;
        if (scene.question && !state.answered[scene.chapter_id]) {
          return { ...state, position: scene.start_seconds + scene.duration_seconds - 0.001, playing: false, viewer: 'question-paused' };
        }
      }
      if (position >= total) { position = total; return { ...state, position, playing: false }; }
      return { ...state, position };
    }
    case 'answer':
      if (state.viewer !== 'question-paused' || story.scenes[sceneIndexAt(story, state.position)]?.chapter_id !== event.chapter) return state;
      return { ...state, viewer: 'reading', answered: { ...state.answered, [event.chapter]: true }, position: Math.min(total, state.position + 0.002), playing: true };
    case 'explore':
      if (state.viewer === 'exploring') return state;
      return { ...state, viewer: 'exploring', playing: false, resume: state.position };
    case 'return':
      if (state.viewer !== 'exploring') return state;
      return { ...state, viewer: 'returning' };
    case 'returned':
      if (state.viewer !== 'returning') return state;
      return { ...state, viewer: 'reading', position: state.resume ?? state.position, resume: null, playing: false };
  }
}

export function formatClock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}

export interface BarModel { label: string; value: number; fraction: number; state: string }
/** Bars share the study-fixed domain from the scale contract when one exists; a per-scene auto-range is never used for comparisons. */
export function barsFor(scene: Scene): { bars: BarModel[]; domain: [number, number]; unit: string; warning?: string; basis: string } | null {
  const fallback = scene.fallback;
  if (fallback.kind !== 'bars' || !fallback.bars?.length) return null;
  const domain: [number, number] = scene.scale?.domain ?? (fallback.domain as [number, number]) ?? [0, Math.max(...fallback.bars.map((b) => b.value))];
  const span = domain[1] - domain[0] || 1;
  return {
    bars: fallback.bars.map((b) => ({ label: b.label, value: b.value, state: b.state, fraction: Math.max(0, Math.min(1, (b.value - domain[0]) / span)) })),
    domain, unit: fallback.unit || scene.scale?.unit || '', warning: scene.scale?.warning,
    basis: scene.scale ? `Study-fixed ${scene.scale.mode} scale · ${scene.scale.basis}` : 'Frozen cited values'
  };
}
