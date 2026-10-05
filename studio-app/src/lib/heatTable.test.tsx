import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { expect, it } from 'vitest';
import { FrozenHeatTable } from '../components/FrozenHeatTable';

it('exposes each frozen frame count, distinguishing unknown from zero and export completeness from exposure', () => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  const host = document.createElement('div'), root = createRoot(host);
  act(() => root.render(<FrozenHeatTable views={[
    { id: 'm', type: 'map', title: 'M', text: '', frozen: true, visual: { kind: 'heat', source: 'MODIS_SP', day: '2024-07-30', count: 0, products: { MODIS_SP: { state: 'complete_export' } }, domain: [0, 6.24321] } },
    { id: 'v', type: 'map', title: 'V', text: '', frozen: true, visual: { kind: 'heat', source: 'VIIRS_SNPP_SP', day: '2024-07-30', count: null, products: { VIIRS_SNPP_SP: { state: 'unknown_export' } }, domain: [0, 6.24321] } },
  ]} />));
  const rows = host.querySelectorAll('tbody tr');
  expect(rows[0].querySelectorAll('td')[1].textContent).toBe('0');
  expect(rows[1].querySelectorAll('td')[1].textContent).toBe('unknown');
  expect(rows[0].textContent).toContain('complete export');
  expect(rows[1].textContent).toContain('unknown export');
  expect(rows[0].querySelector('td[title]')?.getAttribute('title')).toBe('0–6.24321');
  expect(host.textContent).toContain('Incomplete exports do not establish an observed zero');
  expect(host.querySelector('[data-heat-table]')?.getAttribute('tabindex')).toBe('0');
  act(() => root.unmount());
});
