/** Table and CSV use the exact prepared, frozen series; no inference or rounding. */
export type ChartTable = { headers: string[]; rows: (string | number | null)[][]; unit: string; note: string };
export function chartTable(visual: any): ChartTable | null {
  if (!visual || !['calendar', 'daily-bars', 'availability'].includes(visual.kind)) return null;
  const unit = String(visual.unit || '');
  if (visual.kind === 'calendar') return { unit, note: String(visual.label || ''), headers: ['UTC date', unit, 'Evidence state', 'Estimate type', 'Coverage state'], rows: visual.days.map((d: any) => [d.date, d.value, d.evidence_state, d.estimate_type, d.coverage_state]) };
  if (visual.kind === 'daily-bars') return { unit, note: String(visual.label || ''), headers: ['UTC date', unit, 'MODIS export state', 'S-NPP export state'], rows: visual.values.map((d: any) => [d.date, d.value, d.states?.MODIS_SP, d.states?.VIIRS_SNPP_SP]) };
  return { unit, note: String(visual.label || ''), headers: ['UTC date', 'MODIS export state', 'S-NPP export state'], rows: visual.days.map((d: any) => [d.date, d.products?.MODIS_SP?.state, d.products?.VIIRS_SNPP_SP?.state]) };
}
export function chartCsv(table: ChartTable): string {
  const escape = (v: unknown) => { let value = v == null ? 'unknown' : String(v); if (typeof v !== 'number' && /^[=+\-@\t\r]/.test(value)) value = "'" + value; return '"' + value.replaceAll('"', '""') + '"'; };
  return [table.headers, ...table.rows].map((row) => row.map(escape).join(',')).join('\r\n') + '\r\n';
}
export function downloadCard(filename: string, content: string, mime: string) {
  const url = URL.createObjectURL(new Blob([content], { type: mime }));
  const link = document.createElement('a'); link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
