import { describe, expect, it } from 'vitest';
import { barsFor, initialPlayer, reduce, sceneIndexAt, totalSeconds } from './scenes';

const scene = (id: string, start: number, extra: any = {}) => ({
  chapter_id: id, title: id, start_seconds: start, duration_seconds: 20, transition: 'fade', caption: id, narration_text: '', narration_checked: true,
  narration_unmatched_numbers: [], question: null, card: null, evidence: [], scale: null,
  fallback: { kind: 'table', unit: null, rows: [], scope: null }, ...extra
});
const story: any = { scenes: [scene('a', 0), scene('b', 20, { question: { prompt: 'What is unknown?' } }), scene('c', 40)] };

describe('story player state machine', () => {
  it('finds the scene for a time and clamps beyond the end', () => {
    expect(totalSeconds(story)).toBe(60);
    expect([0, 19.9, 20, 59, 500].map((t) => sceneIndexAt(story, t))).toEqual([0, 0, 1, 2, 2]);
  });
  it('plays, ticks, and pauses at an unanswered question until it is answered', () => {
    let s = reduce(story, initialPlayer(), { type: 'play' });
    s = reduce(story, s, { type: 'seek', seconds: 39 });
    s = reduce(story, s, { type: 'tick', delta: 2 });
    expect(s.viewer).toBe('question-paused');
    expect(s.playing).toBe(false);
    expect(reduce(story, s, { type: 'play' })).toEqual(s);
    s = reduce(story, s, { type: 'answer', chapter: 'b' });
    expect(s.viewer).toBe('reading');
    expect(s.answered.b).toBe(true);
    s = reduce(story, s, { type: 'tick', delta: 5 });
    expect(s.position).toBeGreaterThan(20);
  });
  it('exploring remembers the position and returning restores it', () => {
    let s = reduce(story, initialPlayer(), { type: 'seek', seconds: 12 });
    s = reduce(story, s, { type: 'play' });
    s = reduce(story, s, { type: 'explore' });
    expect(s).toMatchObject({ viewer: 'exploring', playing: false, resume: 12 });
    expect(reduce(story, s, { type: 'tick', delta: 5 }).position).toBe(12);
    s = reduce(story, s, { type: 'return' });
    expect(s.viewer).toBe('returning');
    s = reduce(story, s, { type: 'returned' });
    expect(s).toMatchObject({ viewer: 'reading', position: 12, resume: null });
  });
  it('a delayed tick pauses at the first crossed unanswered question and rejects a stale answer', () => {
    let s = reduce(story, initialPlayer(), { type: 'play' });
    s = reduce(story, s, { type: 'tick', delta: 65 });
    expect(s).toMatchObject({ viewer: 'question-paused', playing: false, position: 39.999 });
    expect(reduce(story, s, { type: 'answer', chapter: 'a' })).toEqual(s);
    s = reduce(story, s, { type: 'answer', chapter: 'b' });
    s = reduce(story, s, { type: 'tick', delta: 65 });
    expect(s).toMatchObject({ playing: false, position: 60, answered: { b: true } });
  });
  it('invalid timer or seek values cannot corrupt the applied frame', () => {
    const s = reduce(story, initialPlayer(), { type: 'play' });
    for (const delta of [-1, NaN, Infinity]) expect(reduce(story, s, { type: 'tick', delta })).toEqual(s);
    expect(reduce(story, s, { type: 'seek', seconds: NaN })).toEqual(s);
  });
  it('stops at the end and replays from the start', () => {
    let s = reduce(story, initialPlayer(), { type: 'play' });
    s = reduce(story, { ...s, position: 59 }, { type: 'tick', delta: 5 });
    s = { ...s, answered: { b: true } };
    expect(s.position).toBe(60);
    expect(s.playing).toBe(false);
    expect(reduce(story, s, { type: 'play' }).position).toBe(0);
  });
  it('bars use the study-fixed domain, never a per-scene auto-range', () => {
    const withScale = scene('s', 0, {
      scale: { mode: 'study', basis: 'full applicable study', unit: 'records', domain: [0, 1000], observed_values: 3, statistic: '/x' },
      fallback: { kind: 'bars', unit: 'records', domain: [0, 10], bars: [{ label: 'x', value: 250, state: 'observed' }], scope: null }
    });
    const model = barsFor(withScale as any)!;
    expect(model.domain).toEqual([0, 1000]);
    expect(model.bars[0].fraction).toBeCloseTo(0.25);
    expect(barsFor(scene('t', 0) as any)).toBeNull();
  });
});
