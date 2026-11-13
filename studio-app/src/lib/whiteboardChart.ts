/** Build editable presentation shapes from the Python-prepared frozen values. */
export function comparisonChart(visual: any, title: string, ref: Record<string, string | undefined> & {documentId:string}, x: number, y: number): any[] {
  if (visual?.kind !== 'monthly-comparison' || !Array.isArray(visual.rows) || !visual.rows.length || visual.rows.length > 24) {
    throw Error('This saved item does not contain a supported monthly comparison chart.');
  }
  const series = [
    { key: 'modis', label: 'MODIS observed', color: '#b2680a' },
    { key: 'reference', label: 'VIIRS observed', color: '#087b99' },
    { key: 'prediction', label: 'MODIS estimate', color: '#7155c3' },
  ];
  const rows = visual.rows.map((row: any) => {
    if (typeof row.date !== 'string' || !/^\d{4}-\d{2}/.test(row.date)) throw Error('The saved chart has an invalid month.');
    const values = series.map(({ key }) => {
      const value = row[key];
      if (value == null) return null;
      if (typeof value !== 'number' || !Number.isFinite(value) || value < 0) throw Error('The saved chart has an invalid value.');
      return value;
    });
    return { date: row.date, values };
  });
  const metadata = { fireatlas: { ...ref, kind: 'comparison-chart' } };
  const link = new URL(`./studio.html?board=${encodeURIComponent(ref.documentId)}`, document.baseURI).href;
  const elements: any[] = [];
  const text = (dx: number, dy: number, value: string, fontSize = 18, color = '#183149') => elements.push({ type: 'text', x: x + dx, y: y + dy, text: value, fontSize, strokeColor: color, link, customData: metadata });
  const rect = (dx: number, dy: number, width: number, height: number, color: string) => elements.push({ type: 'rectangle', x: x + dx, y: y + dy, width, height, strokeColor: color, backgroundColor: color, fillStyle: 'solid', customData: metadata });
  text(0, 0, title, 24);
  text(0, 36, String(visual.unit || ''), 14);
  series.forEach((item, i) => { rect(i * 205, 67, 14, 14, item.color); text(i * 205 + 21, 64, item.label, 14); });
  const max = Math.max(0, ...rows.flatMap((row: any) => row.values.filter((value: number | null) => value !== null)));
  const plotHeight = 220, base = 330, groupWidth = Math.max(72, Math.floor(740 / rows.length));
  text(0, 100, `Maximum: ${max}`, 13);
  rect(12, base, rows.length * groupWidth, 1, '#9aaaba');
  rows.forEach((row: any, index: number) => {
    const left = 20 + index * groupWidth;
    row.values.forEach((value: number | null, si: number) => {
      if (value === null || value === 0 || max === 0) return;
      const height = Math.max(1, value / max * plotHeight);
      rect(left + si * 17, base - height, 13, height, series[si].color);
    });
    text(left, base + 8, row.date, 12);
  });
  const lines = ['UTC month  |  MODIS observed  |  VIIRS observed  |  MODIS estimate', ...rows.map((row: any) => `${row.date}  |  ${row.values.map((value: number | null) => value === null ? 'unavailable' : String(value)).join('  |  ')}`)];
  text(0, base + 52, lines.join('\n'), 15);
  text(0, base + 82 + lines.length * 20, 'Values from the saved evidence · Select a bar or label to ask AI', 13);
  return elements;
}
