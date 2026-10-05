import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { InvestigationName, NewInvestigationDialog } from './InvestigationName';
let host: HTMLDivElement, root: ReturnType<typeof createRoot>;
beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  host = document.createElement('div'); document.body.append(host); root = createRoot(host);
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
});
afterEach(() => { act(() => root.unmount()); host.remove(); vi.restoreAllMocks(); });
function type(value: string) {
  const input = host.querySelector('input')!;
  act(() => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value); input.dispatchEvent(new Event('input', { bubbles: true })); });
}
it('explicit naming trims and saves through the existing transaction callback', async () => {
  const save = vi.fn().mockResolvedValue(true);
  act(() => root.render(<InvestigationName title="Original" disabled={false} onSave={save} />));
  type('  Park presentation  ');
  await act(async () => host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(save).toHaveBeenCalledWith('Park presentation');expect(host.textContent).toContain('Investigation name saved.');
});
it('failed saves retain the draft and never claim success', async () => {
  const save = vi.fn().mockResolvedValue(false);
  act(() => root.render(<InvestigationName title="Original" disabled={false} onSave={save} />));type('My draft');
  await act(async () => host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(host.querySelector('input')!.value).toBe('My draft');expect(host.textContent).toContain('Name was not saved.');
});
it('read-only names and whitespace drafts cannot save; external titles restore correctly', async () => {
  const save = vi.fn();act(() => root.render(<InvestigationName title="Original" disabled={true} onSave={save} />));
  expect(host.querySelector('input')!.disabled).toBe(true);expect(host.querySelector('button')!.disabled).toBe(true);
  act(() => root.render(<InvestigationName title="Updated elsewhere" disabled={false} onSave={save} />));expect(host.querySelector('input')!.value).toBe('Updated elsewhere');
  type('   ');await act(async () => host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(save).not.toHaveBeenCalled();expect(host.textContent).toContain('1–120 characters');
});
it('new investigations ask for a name and cancel without creating anything', () => {
  const create = vi.fn(), close = vi.fn();act(() => root.render(<NewInvestigationDialog defaultName="Untitled investigation" onCreate={create} onClose={close} />));
  expect(host.querySelector('dialog')!.open).toBe(true);expect(document.activeElement).toBe(host.querySelector('input'));
  act(() => [...host.querySelectorAll('button')].find((b) => b.textContent === 'Cancel')!.click());expect(close).toHaveBeenCalledOnce();expect(create).not.toHaveBeenCalled();
});
it('new investigations create the entered name and preserve it on an error', async () => {
  const create = vi.fn().mockRejectedValueOnce(new Error('Connection interrupted')).mockResolvedValueOnce(undefined), close = vi.fn();
  act(() => root.render(<NewInvestigationDialog defaultName="Untitled investigation" onCreate={create} onClose={close} />));type('  Named investigation  ');
  await act(async () => host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(host.textContent).toContain('Connection interrupted');expect(close).not.toHaveBeenCalled();expect(host.querySelector('input')!.value).toContain('Named investigation');
  await act(async () => host.querySelector('form')!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })));
  expect(create).toHaveBeenLastCalledWith('Named investigation');expect(close).toHaveBeenCalledOnce();
});
