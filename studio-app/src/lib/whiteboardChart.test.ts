import { expect, it } from 'vitest';
import { comparisonChart } from './whiteboardChart';

const ref = { documentId: 'board', cardId: 'card', snapshotId: 'snapshot', snapshotHash: 'hash' };
it('keeps exact values, unknowns, units and source identity in an editable comparison', () => {
  const shapes = comparisonChart({ kind: 'monthly-comparison', unit: 'cell-days', rows: [
    { date: '2020-05', modis: 0, reference: 12, prediction: 2.75 },
    { date: '2021-05', modis: 8, reference: null, prediction: 5.125 },
  ] }, 'Two months', ref, 0, 0);
  const table = shapes.find((item) => item.text?.startsWith('UTC month'));
  expect(table.text).toContain('2020-05  |  0  |  12  |  2.75');
  expect(table.text).toContain('2021-05  |  8  |  unavailable  |  5.125');
  expect(shapes.every((item) => item.customData.fireatlas.snapshotHash === 'hash')).toBe(true);
  expect(shapes.some((item) => item.text === 'cell-days')).toBe(true);
});
it('rejects unsupported or malformed data rather than inventing plotted values', () => {
  expect(() => comparisonChart({ kind: 'daily-bars', rows: [] }, 'Test', ref, 0, 0)).toThrow();
  expect(() => comparisonChart({ kind: 'monthly-comparison', rows: [{ date: '2020-01', modis: -1 }] }, 'Test', ref, 0, 0)).toThrow();
});
