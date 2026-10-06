import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { StudioProvider, useStudio, type StudioValue } from '../store';
import { StoryDirector } from '../components/StoryDirector';
import { api } from '../api';
import type { DocumentView, RenderJob, StoryView } from '../types';
vi.mock('../api', () => ({ ApiError: class extends Error {}, uid: () => 'unused', api: {
  projects: vi.fn(), getStory: vi.fn(), getRender: vi.fn(), startRender: vi.fn(), cancelRender: vi.fn(), artifactUrl: (id: string) => `/exports/${id}`,
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
afterEach(() => { act(() => root.unmount()); host.remove(); vi.useRealTimers(); });
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

it('shows actual native AI& model and chapter status while the provider generates video', async () => {
  const native: RenderJob = { ...render('native'), status: 'running', phase: 'generating-video', progress: .4,
    artifacts: {}, manifest: null, provider_progress: { provider: 'aiand', model: 'minimaxai/minimax-h3', status: 'in_progress', chapter: 2, chapters: 5, quote_usd: 1.2 } };
  vi.mocked(api.getRender).mockResolvedValue(native);
  await act(async () => { value.setCaps({ video: { available: true, engine: 'aiand-native-video', model: 'minimaxai/minimax-h3' }, narration: { available: false }, story_generation: { available: true } } as any); value.open(board()); });
  expect(host.textContent).toContain('minimaxai/minimax-h3');
  expect(host.textContent).toContain('Chapter 2 of 5 · in progress');
  expect(host.textContent).toContain('Provider generation can take several minutes');
  expect(host.querySelector('.story-film video')).toBeNull();
});

it('a saved native refresh is not replaced by the older completed writing job on reload', async () => {
  vi.mocked(api.projects).mockResolvedValue({ stories: [{ id: 'Alpha', title: 'Alpha', revision: 2 }], workflow: null,
    story_generations: [{ id: 'older-writing', status: 'completed', story_id: 'Alpha' }], renders: [{ ...render('native'), created: 3 }] });
  vi.mocked(api.getRender).mockResolvedValue({ ...render('native'), manifest: { narration: { status: 'narrated' }, captions_fallback: false,
    engine: 'aiand-native-video', provider: { model: 'minimaxai/minimax-h3', quoted_cost_usd: 1.2, disclosure: 'Generated motion with exact evidence.' } } });
  await act(async () => value.open(board()));
  expect(api.storyGeneration).not.toHaveBeenCalled();
  expect(host.textContent).toContain('Generated by AI& minimaxai/minimax-h3');
  expect(host.querySelector('video')?.getAttribute('src')).toBe('/exports/native');
});

it('continues past the old 65% completion checkpoint until the film and download are ready', async () => {
  vi.useFakeTimers();
  vi.mocked(api.projects).mockResolvedValue({ stories: [], workflow: null });
  const checkpoint = { id: 'generation', document_id: 'board', document_revision: 1, status: 'completed', phase: 'saved', progress: .65, story_id: 'Alpha', render_id: null, error: null };
  vi.mocked(api.generateStory).mockResolvedValue(checkpoint);
  vi.mocked(api.storyGeneration).mockResolvedValueOnce(checkpoint).mockResolvedValueOnce({ ...checkpoint, status: 'running', phase: 'encoding', progress: .9, render_id: 'film', render: { ...render('film'), status: 'running', phase: 'encoding', progress: .7, artifacts: {} } }).mockResolvedValue({ ...checkpoint, phase: 'completed', progress: 1, render_id: 'film', render: render('film') });
  await act(async () => { value.setCaps({ story_generation: { available: true }, video: { available: true }, narration: { available: false } } as any); value.open({ ...board(), state: { ...board().state, order: ['c1'], cards: { c1: { title: 'Map' } as any } } }); });
  await act(async () => { [...host.querySelectorAll('button')].find((b) => b.textContent === '✦ Create story')!.click(); });
  expect(host.querySelector('[role=progressbar]')?.getAttribute('aria-valuenow')).toBe('65');
  expect(host.textContent).toContain('Storyboard saved · preparing your film');
  expect(host.textContent).not.toContain('Your infographic story is ready.');
  await act(async () => { await vi.advanceTimersByTimeAsync(900); });
  expect(host.querySelector('[role=progressbar]')?.getAttribute('aria-valuenow')).toBe('90');
  await act(async () => { await vi.advanceTimersByTimeAsync(900); });
  expect(host.querySelector('[role=progressbar]')?.getAttribute('aria-valuenow')).toBe('100');
  expect(host.textContent).toContain('Your infographic film is ready.');
  expect(host.querySelector('video[src="/exports/film"]')).toBeTruthy();
  expect(host.querySelector('a[download="ignis-infographic.mp4"]')).toBeTruthy();
  expect(api.generateStory).toHaveBeenCalledTimes(1);
  const polls = vi.mocked(api.storyGeneration).mock.calls.length;
  await act(async () => { await vi.advanceTimersByTimeAsync(1800); });
  expect(api.storyGeneration).toHaveBeenCalledTimes(polls);
});

it('restores an already completed film at 100% without starting another generation', async () => {
  vi.mocked(api.projects).mockResolvedValue({ stories: [{ id: 'Alpha', title: 'Alpha', revision: 2 }], workflow: null, story_generations: [{ id: 'generation', status: 'completed', story_id: 'Alpha' }] });
  vi.mocked(api.storyGeneration).mockResolvedValue({ id: 'generation', document_id: 'board', document_revision: 1, status: 'completed', phase: 'completed', progress: 1, story_id: 'Alpha', render_id: 'film', error: null, render: render('film') });
  await act(async () => value.open(board()));
  expect(host.querySelector('[role=progressbar]')?.getAttribute('aria-valuenow')).toBe('100');
  expect(host.querySelector('video[src="/exports/film"]')).toBeTruthy();
  expect(api.generateStory).not.toHaveBeenCalled();
});

it('refreshes the saved film with narration by default and tracks the new render without another AI request', async () => {
  vi.useFakeTimers();
  const old = render('old'), current = { ...render('voiced'), status: 'running' as const, phase: 'narrating' as const, progress: .1, manifest: null, artifacts: {} };
  vi.mocked(api.projects).mockResolvedValue({ stories: [{ id: 'Alpha', title: 'Alpha', revision: 2 }], workflow: null, renders: [old], story_generations: [{ id: 'generation', status: 'completed', story_id: 'Alpha' }] });
  vi.mocked(api.getStory).mockResolvedValue({ ...story('Alpha'), resolved: {} as any });
  vi.mocked(api.storyGeneration).mockResolvedValue({ id: 'generation', document_id: 'board', document_revision: 1, status: 'completed', phase: 'completed', progress: 1, story_id: 'Alpha', render_id: 'old', error: null, render: old });
  vi.mocked(api.startRender).mockResolvedValue(current);
  vi.mocked(api.getRender).mockImplementation(async (id) => id === 'old' ? old : current);
  await act(async () => { value.setCaps({ video: { available: true }, narration: { available: true, disclosure: 'Locally narrated.' } } as any); value.open(board()); });
  await act(async () => { [...host.querySelectorAll('button')].find((b) => b.textContent === 'Refresh film & voice')!.click(); });
  expect(api.startRender).toHaveBeenCalledWith('Alpha', true);
  expect(host.querySelector('[role=progressbar]')?.getAttribute('aria-valuenow')).toBe('69');
  expect(host.textContent).toContain('Recording the voice narration');
  vi.mocked(api.getRender).mockResolvedValue({ ...render('voiced'), manifest: { narration: { status: 'narrated', disclosure: 'Local checked voice.' }, captions_fallback: false } });
  await act(async () => { await vi.advanceTimersByTimeAsync(800); });
  expect(host.querySelector('[role=progressbar]')?.getAttribute('aria-valuenow')).toBe('100');
  expect(host.textContent).toContain('Voice narration is included in this film.');
  expect(host.querySelector('video[src="/exports/voiced"]')).toBeTruthy();
  expect(api.generateStory).not.toHaveBeenCalled();
});
