import { describe, it, expect } from 'vitest';
import { chartTable, chartCsv } from './chartValues';
import { presentationWorkflow } from './presentation';
import { parseDraft } from './workflow';
describe('frozen chart alternatives', () => {
  it('retains zero, fractional estimates, and unknowns in tables and CSV', () => {
    const table = chartTable({ kind: 'calendar', unit: 'VIIRS-equivalent cell-days', days: [{ date: '2026-06-01', value: 0, evidence_state: 'observed' }, { date: '2026-06-02', value: 2.224169, evidence_state: 'scaled' }, { date: '2026-06-03', value: null, evidence_state: 'unknown' }] })!;
    expect(table.rows.map((r) => r[1])).toEqual([0, 2.224169, null]);
    expect(chartCsv(table)).toContain('"2026-06-03","unknown","unknown"');
    expect(chartCsv(table)).toContain('"2026-06-01","0","observed"');
  });
  it('preserves partial-export states and protects spreadsheet text fields', () => {
    const table = chartTable({ kind: 'daily-bars', unit: 'occupied cells', values: [{ date: '2024-07-24', value: 1, states: { MODIS_SP: 'partial', VIIRS_SNPP_SP: '=malicious' } }] })!;
    expect(chartCsv(table)).toContain('"partial","\'=malicious"');
    expect(chartTable({ kind: 'map', points: [] })).toBeNull();
  });
  it('creates a connected typed presentation recipe without invented numeric nodes', () => {
    const graph = presentationWorkflow(); expect(parseDraft(graph)).toEqual(graph);
    expect(graph.nodes.filter((n) => n.type === 'operation').map((n) => n.params?.operation)).toEqual(['replay', 'missingness']);
    expect(graph.nodes.find((n) => n.id === 'story')?.inputs?.items).toEqual(['map', 'chart', 'timeline']);
  });
});
