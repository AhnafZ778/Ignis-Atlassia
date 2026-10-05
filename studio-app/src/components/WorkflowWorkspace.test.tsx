import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { api } from '../api';
import { presentationWorkflow } from '../lib/presentation';
import { WorkflowPanel } from './WorkflowPanel';
import { WorkflowWorkspace, workflowRefreshURL } from './WorkflowWorkspace';

const diagram = vi.hoisted(() => ({ fail: false }));
vi.mock('../store', () => ({ useStudio: () => ({
  doc: { id: 'preset-board', revision: 8 }, canEdit: true, open: vi.fn(), isCurrent: () => true,
}) }));
vi.mock('../api', () => ({ api: {
  workflowTemplates: vi.fn(), projects: vi.fn(), saveWorkflow: vi.fn(),
}, uid: () => 'new-node' }));
vi.mock('./JarvisPanel', () => ({ JarvisPanel: () => null }));
vi.mock('@xyflow/react', () => ({
  ReactFlow: () => { if (diagram.fail) throw new Error('Diagram initialization failed'); return <div data-diagram />; },
  Background: () => null, Controls: () => null, Handle: () => null,
  Position: { Left: 'left', Right: 'right' }, applyNodeChanges: vi.fn(),
}));

let host: HTMLDivElement, root: ReturnType<typeof createRoot>;
const button = (name: string) => [...host.querySelectorAll('button')].find((item) => item.textContent === name)!;
beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  vi.resetAllMocks(); localStorage.clear(); diagram.fail = false;
  vi.mocked(api.workflowTemplates).mockResolvedValue({ templates: [] });
  vi.mocked(api.projects).mockResolvedValue({ stories: [], workflow: { id: 'workflow', revision: 3, definition: presentationWorkflow() } });
  vi.mocked(api.saveWorkflow).mockResolvedValue({ id: 'workflow', revision: 4 });
  host = document.createElement('div'); document.body.append(host);
  root = createRoot(host, { onCaughtError: () => undefined });
});
afterEach(() => { act(() => root.unmount()); host.remove(); vi.unstubAllGlobals(); });

it('contains a failed lazy download and retries with a fresh lazy promise without losing Studio navigation', async () => {
  const load = vi.fn()
    .mockRejectedValueOnce(new Error('Failed to fetch dynamically imported module'))
    .mockResolvedValueOnce({ default: () => <h2>Workflow Composer</h2> });
  const back = vi.fn();
  await act(async () => root.render(<><nav>Studio views</nav><WorkflowWorkspace load={load} onReturnToBoard={back} /></>));
  expect(host.textContent).toContain('Studio views');
  expect(host.textContent).toContain('Workflow could not open');
  expect(load).toHaveBeenCalledTimes(1);
  const refresh = host.querySelector('a')!;
  expect(new URL(refresh.href).searchParams.get('board')).toBe('preset-board');
  expect(new URL(refresh.href).searchParams.get('tab')).toBe('workflow');
  await act(async () => button('Return to Board').click());
  expect(back).toHaveBeenCalledOnce();
  await act(async () => button('Retry Workflow').click());
  expect(load).toHaveBeenCalledTimes(2);
  expect(host.textContent).toContain('Workflow Composer');
  expect(host.textContent).not.toContain('Workflow could not open');
});

it('contains editor render errors and never retries automatically in a loop', async () => {
  const load = vi.fn().mockResolvedValue({ default: () => { throw new Error('Editor render failed'); } });
  await act(async () => root.render(<WorkflowWorkspace load={load} onReturnToBoard={() => undefined} />));
  expect(host.textContent).toContain('Workflow could not open');
  expect(load).toHaveBeenCalledTimes(1);
  await act(async () => button('Retry Workflow').click());
  expect(load).toHaveBeenCalledTimes(2);
  expect(host.textContent).toContain('Workflow could not open');
});

it('keeps the curated workflow table, edits and saving usable when the diagram fails', async () => {
  diagram.fail = true;
  await act(async () => root.render(<WorkflowPanel />));
  expect(host.textContent).toContain('The interactive diagram could not initialize.');
  expect(host.querySelectorAll('tbody tr')).toHaveLength(7);
  expect(host.textContent).toContain('Editable evidence briefing');
  await act(async () => button('Edit Daily activity').click());
  const label = host.querySelector<HTMLInputElement>('.wf-inspector input')!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(label, 'Presentation activity');
    label.dispatchEvent(new Event('input', { bubbles: true }));
  });
  await act(async () => button('Save workflow').click());
  expect(api.saveWorkflow).toHaveBeenCalledWith('preset-board', expect.objectContaining({
    nodes: expect.arrayContaining([expect.objectContaining({ id: 'chart', label: 'Presentation activity' })]),
  }), 3);
  diagram.fail = false;
  await act(async () => button('Retry diagram').click());
  expect(host.querySelector('[data-diagram]')).not.toBeNull();
  expect(host.textContent).toContain('Presentation activity');
});

it('refreshes the current board and Workflow while preserving incoming scope and project subpath', () => {
  const url = new URL(workflowRefreshURL('https://example.test/NASA-Spaceapps/studio.html?year=2024&month=7&start=2024-07-24&end=2024-08-14&board=old#evidence', 'curated-board'));
  expect(url.pathname).toBe('/NASA-Spaceapps/studio.html');
  expect(url.searchParams.get('board')).toBe('curated-board');
  expect(url.searchParams.get('tab')).toBe('workflow');
  expect(url.searchParams.get('start')).toBe('2024-07-24');
  expect(url.searchParams.get('end')).toBe('2024-08-14');
  expect(url.hash).toBe('#evidence');
});
