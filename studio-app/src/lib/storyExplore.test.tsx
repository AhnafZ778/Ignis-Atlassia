import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { expect, it, vi } from 'vitest';
import { StoryPlayer } from '../components/StoryPlayer';

vi.mock('../components/JarvisPanel', () => ({ JarvisPanel: ({ chapter }: any) => <output data-chapter-context>{JSON.stringify(chapter)}</output> }));

it('a chapter without an authored question can explore its exact saved context and resume without editing it', () => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  vi.stubGlobal('matchMedia', () => ({ matches: true }));
  const story: any = { title: 'Frozen preset', snapshots: {}, limitations: [], scenes: [{
    chapter_id: 'orientation', title: 'Orientation', start_seconds: 0, duration_seconds: 20,
    question: null, evidence: [], narration_text: 'Inspect the saved window.', caption: 'UTC study',
  }] };
  const frozen = JSON.stringify(story);
  const host = document.createElement('div'), root = createRoot(host);
  act(() => root.render(<StoryPlayer story={story} identity={{ story_id: 'saved-story', story_revision: 4 }} />));
  const button = (name: string) => Array.from(host.querySelectorAll('button')).find((b) => b.textContent === name)!;
  const slider = host.querySelector<HTMLInputElement>('input[type=range]')!;
  act(() => button('Explore chapter evidence').click());
  expect(host.querySelector('[data-chapter-context]')?.textContent).toBe(JSON.stringify({ story_id: 'saved-story', story_revision: 4, chapter_id: 'orientation' }));
  expect(slider.disabled).toBe(true);
  act(() => button('Resume story').click());
  expect(slider.disabled).toBe(false);
  expect(slider.value).toBe('0');
  expect(button('Play').disabled).toBe(false);
  expect(host.querySelector('[data-chapter-context]')).toBeNull();
  expect(JSON.stringify(story)).toBe(frozen);
  act(() => root.unmount());
  vi.unstubAllGlobals();
});
