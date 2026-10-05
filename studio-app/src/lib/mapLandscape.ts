import { api } from '../api';
import type { Snapshot } from '../types';

const cache = new Map<string, Promise<any>>();
export function vegetationRequest(bounds: number[], day: string) {
  const chosen = new Date(day + 'T00:00:00Z'), first = new Date(Date.UTC(chosen.getUTCFullYear(), 0, 1));
  const block = Math.floor((chosen.getTime() - first.getTime()) / (86400000 * 16));
  first.setUTCDate(1 + block * 16); const date = first.toISOString().slice(0, 10);
  const query = new URLSearchParams({ SERVICE: 'WMS', REQUEST: 'GetMap', VERSION: '1.1.1', LAYERS: 'MODIS_Terra_L3_NDVI_16Day', STYLES: '', FORMAT: 'image/png', TRANSPARENT: 'TRUE', WIDTH: '720', HEIGHT: '340', SRS: 'EPSG:4326', BBOX: bounds.join(','), TIME: date });
  return { date, url: 'https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?' + query };
}
export function mapLandscape(documentId: string, snapshot: Snapshot, background = 'auto', day?: string): Promise<any> {
  const requested = vegetationRequest(snapshot.scope.bbox, day || snapshot.scope.day || snapshot.scope.start);
  const key = [documentId, snapshot.id, snapshot.receipt_sha256, background, requested.date].join(':');
  const saved = cache.get(key); if (saved) return saved;
  const request = api.snapshotLandscape(documentId, snapshot.id, background === 'ndvi-online' ? 'none' : background).then((result) => {
    const available = [...result.available, 'ndvi-online'];
    if (background !== 'ndvi-online' && !(background === 'auto' && result.selected === 'none')) return { ...result, available };
    return { choice: background, selected: 'ndvi-online', available,
      label: `Vegetation · NASA GIBS · requested ${requested.date} composite`,
      note: 'Online 16-day vegetation context; not a fire-day measurement or part of the frozen scientific receipt.',
      layers: [{ name: 'ndvi-online', mime: 'image/png', url: requested.url, metadata: { bounds: snapshot.scope.bbox, product: 'MODIS NDVI via GIBS', version: 'online', composite_start: requested.date } }] };
  }).catch(() => { cache.delete(key); return { selected: 'none', available: ['ndvi-online'], layers: [], label: 'Heat only', note: 'Landscape unavailable. The frozen heat and source evidence remain available.' }; });
  cache.set(key, request); if (cache.size > 16) cache.delete(cache.keys().next().value!);
  return request;
}

export function landscapeImage(layer: any): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => { const image = new Image(); const timeout = setTimeout(() => { image.src = ''; reject(new Error('Landscape imagery did not load.')); }, 12000); image.onload = () => { clearTimeout(timeout); resolve(image); }; image.onerror = () => { clearTimeout(timeout); reject(new Error('Landscape imagery could not load.')); }; if (layer.url) image.crossOrigin = 'anonymous'; image.src = layer.url || `data:${layer.mime};base64,${layer.data}`; });
}
