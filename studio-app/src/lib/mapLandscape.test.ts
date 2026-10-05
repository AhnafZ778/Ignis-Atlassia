import { expect, it, vi } from 'vitest';
vi.mock('../api', () => ({ api: { snapshotLandscape: vi.fn() } }));
import { api } from '../api';
import { mapLandscape, vegetationRequest } from './mapLandscape';
const snapshot = { id: 'snap-a', receipt_sha256: 'frozen', scope: { bbox: [-122.2, 38.8, -120, 41], start: '2024-07-30', day: '2024-07-30' } } as any;

it('requests the exact footprint with longitude first and a UTC 16-day composite', () => {
  const result = vegetationRequest(snapshot.scope.bbox, '2024-07-30'), query = new URL(result.url).searchParams;
  expect(result.date).toBe('2024-07-27'); expect(query.get('BBOX')).toBe('-122.2,38.8,-120,41'); expect(query.get('VERSION')).toBe('1.1.1'); expect(query.get('SRS')).toBe('EPSG:4326');
  expect(vegetationRequest(snapshot.scope.bbox, '2024-01-01').date).toBe('2024-01-01');
});
it('keeps verified supplied vegetation and shares one request across sensor panes', async () => {
  vi.mocked(api.snapshotLandscape).mockResolvedValue({ selected: 'ndvi', available: ['ndvi', 'terrain'], layers: [{ name: 'ndvi', data: 'supplied' }] });
  const first = mapLandscape('board-local', snapshot), second = mapLandscape('board-local', snapshot);
  expect(first).toBe(second); expect((await first).selected).toBe('ndvi'); expect((await first).layers[0].url).toBeUndefined();
});
it('supports online vegetation for a regional footprint without substituting Park', async () => {
  vi.mocked(api.snapshotLandscape).mockResolvedValue({ selected: 'none', available: [], layers: [] });
  const result = await mapLandscape('board-regional', snapshot);
  expect(result.selected).toBe('ndvi-online'); expect(new URL(result.layers[0].url).searchParams.get('BBOX')).toBe('-122.2,38.8,-120,41'); expect(result.note).toContain('not a fire-day measurement');
});
it('heat only does not request an online vegetation image', async () => {
  vi.mocked(api.snapshotLandscape).mockResolvedValue({ selected: 'none', available: ['ndvi'], layers: [] });
  expect((await mapLandscape('board-heat-only', snapshot, 'none')).layers).toEqual([]);
});
