import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { StudioProvider, useStudio, type StudioValue } from '../store';
import { StoryDirector } from '../components/StoryDirector';
import { api } from '../api';
import type { DocumentView, RenderJob, StoryView } from '../types';
vi.mock('../api', () => ({ ApiError: class extends Error {}, uid: () => 'unused', api: {
  projects: vi.fn(), getStory: vi.fn(), getRender: vi.fn(), cancelRender: vi.fn(), artifactUrl: (id: string) => `/exports/${id}`,
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
