import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { StudioProvider, useStudio, type StudioValue } from '../store';
import { StoryDirector } from '../components/StoryDirector';
import { api } from '../api';
import type { DocumentView, RenderJob, StoryView } from '../types';
vi.mock('../api', () => ({ ApiError: class extends Error {}, uid: () => 'unused', api: {
  projects: vi.fn(), getStory: vi.fn(), getRender: vi.fn(), cancelRender: vi.fn(), artifactUrl: (id: string) => `/exports/${id}`,
  generateStory: vi.fn(), storyGeneration: vi.fn(), cancelStoryGeneration: vi.fn(), resumeStoryGeneration: vi.fn(), exportUrl: (id: string) => `/stories/${id}/export`,
} }));
vi.mock('../components/StoryPlayer', () => ({ StoryPlayer: () => null }));
let value: StudioValue, root: ReturnType<typeof createRoot>, host: HTMLDivElement;
const board = (): DocumentView => ({ id: 'board', revision: 1, context_revision: 1, role: 'owner', state: { cards: {}, connections: {}, order: [], study: {} }, selection: { card_id: null } } as unknown as DocumentView);
const story = (id: string): StoryView => ({ id, document_id: 'board', revision: 2, latest_revision: 2, title: id,
  body: { title: id, profile: 'briefing-1080p-landscape', chapters: [{ id: 'chapter', title: 'Saved chapter', caption: '', narration: 'Explanation', card_id: null, evidence_cards: [], duration_seconds: 20, transition: 'cut' }] }, resolved: null,
  profile: { width: 1920, height: 1080, fps: 30, duration_seconds: 20 } });
const render = (id: string, storyId = 'Alpha'): RenderJob => ({ id, story_id: storyId, story_revision: 1, created: 1, status: 'completed', progress: 1, error: null,
  manifest: { narration: { status: 'captions-only', reason: `${id}: complete silent captions.` }, captions_fallback: true }, artifacts: { video: `/exports/${id}` } });
function Probe() { value = useStudio(); return value.doc ? <StoryDirector /> : null; }
const select = async (label: string, option: string) => {
  const element = [...host.querySelectorAll('label')].find((l) => l.textContent?.startsWith(label))!.querySelector('select')!;
  await act(async () => { element.value = option; element.dispatchEvent(new Event('change', { bubbles: true })); });
};
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear(); (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  host = document.createElement('div'); document.body.append(host); root = createRoot(host);
  vi.mocked(api.projects).mockResolvedValue({ stories: [{ id: 'Alpha', title: 'Alpha', revision: 2 }, { id: 'Beta', title: 'Beta', revision: 2 }], workflow: null,
    renders: [{ ...render('new'), created: 2 }, { ...render('old'), created: 1 }, { ...render('beta', 'Beta'), created: 0 }] });
  vi.mocked(api.getStory).mockImplementation(async (id) => story(id));
  vi.mocked(api.getRender).mockImplementation(async (id) => render(id, id === 'beta' ? 'Beta' : 'Alpha'));
  act(() => root.render(<StudioProvider><Probe /></StudioProvider>));
});
afterEach(() => { act(() => root.unmount()); host.remove(); });
it('restores the latest owned export with its original revision and complete caption outcome', async () => {
  await act(async () => value.open(board()));
  expect(api.getRender).toHaveBeenCalledWith('new');
  expect(host.textContent).toContain('This export uses saved story revision 1. The editor is on revision 2');
  expect(host.querySelector('[data-narration-outcome]')?.textContent).toContain('new: complete silent captions');
  expect(host.querySelector('a[href="/exports/new"]')).toBeTruthy();
});
it('ignores a delayed export response after selecting another story', async () => {
  let finish: (job: RenderJob) => void = () => undefined;
  vi.mocked(api.getRender).mockImplementation((id) => id === 'new' ? new Promise((resolve) => { finish = resolve; }) : Promise.resolve(render(id, 'Beta')));
  await act(async () => value.open(board()));
  await select('Saved story', 'Beta');
  await act(async () => finish(render('new')));
  expect(host.querySelector('[data-narration-outcome]')?.textContent).toContain('beta: complete silent captions');
  expect(host.querySelector('a[href="/exports/new"]')).toBeNull();
  expect(host.querySelector('a[href="/exports/beta"]')).toBeTruthy();
});
it('keeps the selected recent export when an older request finishes late', async () => {
  let finish: (job: RenderJob) => void = () => undefined;
  vi.mocked(api.getRender).mockImplementation((id) => id === 'old' ? new Promise((resolve) => { finish = resolve; }) : Promise.resolve(render(id)));
  await act(async () => value.open(board()));
  await select('Recent video exports', 'old');
  await select('Recent video exports', 'new');
  await act(async () => finish(render('old')));
  expect(host.querySelector('[data-narration-outcome]')?.textContent).toContain('new: complete silent captions');
  expect(host.querySelector('a[href="/exports/old"]')).toBeNull();
});

it('Create story calls the AI director with the applied revision and shows real progress in the lean view', async () => {
  vi.mocked(api.projects).mockResolvedValue({ stories: [], workflow: null });
  const job = { id: 'generation', document_id: 'board', document_revision: 1, status: 'running', phase: 'writing-story', progress: .18, story_id: null, render_id: null, error: null };
  vi.mocked(api.generateStory).mockResolvedValue(job);
  vi.mocked(api.storyGeneration).mockResolvedValue(job);
  await act(async () => { value.setCaps({ story_generation: { available: true } } as any); value.open({ ...board(), state: { ...board().state, order: ['c1'], cards: { c1: { title: 'Checked map' } as any } } }); });
  expect(host.querySelector<HTMLDetailsElement>('.story-edit')!.open).toBe(false);
  await act(async () => { [...host.querySelectorAll('button')].find((b) => b.textContent === '✦ Create story')!.click(); });
  expect(api.generateStory).toHaveBeenCalledWith('board', 1, ['c1']);
  expect(host.querySelector('[role=progressbar]')?.getAttribute('aria-valuenow')).toBe('18');
  expect(host.textContent).toContain('AI& is writing the story');
});

it('cancellation prevents a late completed storyboard from replacing the selected story', async () => {
  vi.mocked(api.projects).mockResolvedValue({ stories: [], workflow: null });
  const job = { id: 'generation', document_id: 'board', document_revision: 1, status: 'running', phase: 'writing-story', progress: .18, story_id: null, render_id: null, error: null };
  let finish: (v: any) => void = () => undefined;
  vi.mocked(api.generateStory).mockResolvedValue(job);
  vi.mocked(api.storyGeneration).mockReturnValue(new Promise((resolve) => { finish = resolve; }));
  vi.mocked(api.cancelStoryGeneration).mockResolvedValue({ ...job, status: 'cancelled', phase: 'cancelled' });
  await act(async () => { value.setCaps({ story_generation: { available: true } } as any); value.open({ ...board(), state: { ...board().state, order: ['c1'], cards: { c1: { title: 'Map' } as any } } }); });
  await act(async () => { [...host.querySelectorAll('button')].find((b) => b.textContent === '✦ Create story')!.click(); });
  await act(async () => { [...host.querySelectorAll('button')].find((b) => b.textContent === 'Cancel')!.click(); });
  await act(async () => finish({ ...job, status: 'completed', story_id: 'Late story' }));
  expect(api.getStory).not.toHaveBeenCalled();
  expect(host.textContent).toContain('Cancelled. Saved story material remains available.');
});

it('refresh reconnects to a saved generation without creating another AI request', async () => {
  vi.mocked(api.projects).mockResolvedValue({ stories: [], workflow: null, story_generations: [{ id: 'saved-generation', status: 'running', story_id: null }] });
  vi.mocked(api.storyGeneration).mockResolvedValue({ id: 'saved-generation', document_id: 'board', document_revision: 1, status: 'running', phase: 'rendering', progress: .75, story_id: null, render_id: null, error: null });
  await act(async () => value.open(board()));
  expect(api.storyGeneration).toHaveBeenCalledWith('saved-generation');
  expect(api.generateStory).not.toHaveBeenCalled();
  expect(host.querySelector('[role=progressbar]')?.getAttribute('aria-valuenow')).toBe('75');
});
