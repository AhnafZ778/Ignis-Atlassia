import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { DeleteInvestigationDialog } from './DeleteInvestigationDialog';

let host: HTMLDivElement, root: Root;
beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute('open', ''); };
  HTMLDialogElement.prototype.close = function () { this.removeAttribute('open'); };
  host = document.createElement('div'); document.body.append(host); root = createRoot(host);
});
afterEach(() => { act(() => root.unmount()); host.remove(); vi.restoreAllMocks(); });
const button = (name: string) => [...host.querySelectorAll('button')].find((b) => b.textContent === name)!;

it('names the target and focuses Keep; cancellation never deletes', () => {
  const remove = vi.fn(), close = vi.fn();
  act(() => root.render(<DeleteInvestigationDialog title="Park heatmap" onDelete={remove} onClose={close} />));
  expect(host.textContent).toContain('Park heatmap'); expect(document.activeElement).toBe(button('Keep investigation'));
  act(() => button('Keep investigation').click()); expect(close).toHaveBeenCalledOnce(); expect(remove).not.toHaveBeenCalled();
});
it('Escape dismisses the confirmation without deleting', () => {
  const remove = vi.fn(), close = vi.fn();
  act(() => root.render(<DeleteInvestigationDialog title="Park" onDelete={remove} onClose={close} />));
  act(() => host.querySelector('dialog')!.dispatchEvent(new Event('cancel', { cancelable: true })));
  expect(close).toHaveBeenCalledOnce(); expect(remove).not.toHaveBeenCalled();
});
it('keeps failures visible and closes only after confirmed deletion succeeds', async () => {
  const remove = vi.fn().mockRejectedValueOnce(new Error('Investigation changed. Reload it.')).mockResolvedValueOnce(undefined), close = vi.fn();
  act(() => root.render(<DeleteInvestigationDialog title="Park" onDelete={remove} onClose={close} />));
  await act(async () => button('Delete investigation').click());
  expect(host.querySelector('[role=alert]')?.textContent).toContain('Reload it'); expect(close).not.toHaveBeenCalled();
  await act(async () => button('Delete investigation').click()); expect(close).toHaveBeenCalledOnce(); expect(remove).toHaveBeenCalledTimes(2);
});
it('blocks duplicate confirmation and dismissal while deleting', async () => {
  let finish!: () => void;
  const remove = vi.fn(() => new Promise<void>((resolve) => { finish = resolve; })), close = vi.fn();
  act(() => root.render(<DeleteInvestigationDialog title="Park" onDelete={remove} onClose={close} />));
  act(() => button('Delete investigation').click());
  expect(button('Deleting…').disabled).toBe(true); expect(button('Keep investigation').disabled).toBe(true);
  act(() => host.querySelector('dialog')!.dispatchEvent(new Event('cancel', { cancelable: true })));
  expect(close).not.toHaveBeenCalled(); expect(remove).toHaveBeenCalledOnce();
  await act(async () => finish()); expect(close).toHaveBeenCalledOnce();
});
