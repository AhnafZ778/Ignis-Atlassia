import { api } from '../api';
import type { Snapshot } from '../types';

const cache = new Map<string, Promise<any>>();
const gibsWms='https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?';
function gibsUrl(bounds:number[], layer:string, format:string, date?:string) {
  if(bounds.length!==4 || !bounds.every(Number.isFinite))throw Error('Invalid landscape footprint.');
  // WMS expects literal slashes, commas and colon in these controlled values.
  return gibsWms+`SERVICE=WMS&REQUEST=GetMap&VERSION=1.1.1&LAYERS=${layer}&STYLES=&FORMAT=${format}&WIDTH=720&HEIGHT=340&SRS=EPSG:4326&BBOX=${bounds.join(',')}`+(date?`&TIME=${date}&TRANSPARENT=TRUE`:'');
}

export function vegetationRequest(bounds: number[], day: string) {
  const chosen = new Date(day + 'T00:00:00Z'), first = new Date(Date.UTC(chosen.getUTCFullYear(), 0, 1));
  const block = Math.floor((chosen.getTime() - first.getTime()) / (86400000 * 16));
  first.setUTCDate(1 + block * 16); const date = first.toISOString().slice(0, 10);
  return { date, url:gibsUrl(bounds,'MODIS_Terra_L3_NDVI_16Day','image/png',date) };
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

export function landscapeImage(layer: any, timeoutMs=12000): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => { const image = new Image(); const timeout = setTimeout(() => { image.src = ''; reject(new Error('Landscape imagery did not load.')); }, timeoutMs); image.onload = () => { clearTimeout(timeout); resolve(image); }; image.onerror = () => { clearTimeout(timeout); reject(new Error('Landscape imagery could not load.')); }; if (layer.url) image.crossOrigin = 'anonymous'; image.src = layer.url || `data:${layer.mime};base64,${layer.data}`; });
}


/** Align the website's reference basemaps with the frozen geographic heat raster. */
export async function geographicBasemap(bounds:number[], style:'terrain'|'reference'):Promise<HTMLCanvasElement> {
  const [west,south,east,north]=bounds;
  if(bounds.length!==4 || !bounds.every(Number.isFinite) || south < -85 || north > 85 || west>=east || south>=north)throw Error('Reference basemap unavailable for these bounds.');
  const tileSize=256;
  const mercator=(latitude:number)=>(1-Math.asinh(Math.tan(latitude*Math.PI/180))/Math.PI)/2;
  const top=mercator(north),bottom=mercator(south);
  let zoom=style==='terrain'?8:10, scale=0, left=0,right=0,first=0,last=0;
  do {
    scale=2**zoom;
    left=Math.floor((west+180)/360*scale);
    right=Math.ceil((east+180)/360*scale)-1;
    first=Math.floor(top*scale);
    last=Math.ceil(bottom*scale)-1;
    if((right-left+1)*(last-first+1)<=9)break;
    zoom--;
  }while(zoom>=0);
  const tiles=[];
  for(let col=left;col<=right;col++)for(let row=first;row<=last;row++){
    const url=style==='terrain'
      ? 'https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief/default/GoogleMapsCompatible_Level8/'+zoom+'/'+row+'/'+col+'.jpg'
      : 'https://tile.openstreetmap.org/'+zoom+'/'+col+'/'+row+'.png';
    tiles.push(landscapeImage({url},5000).then(image=>({image,col,row})));
  }
  const mosaic=document.createElement('canvas');
  mosaic.width=(right-left+1)*tileSize;
  mosaic.height=(last-first+1)*tileSize;
  const atlas=mosaic.getContext('2d');
  if(!atlas)throw Error('Reference basemap unavailable.');
  for(const {image,col,row} of await Promise.all(tiles))atlas.drawImage(image,(col-left)*tileSize,(row-first)*tileSize);
  const map=document.createElement('canvas');
  map.width=720;map.height=340;
  const raster=map.getContext('2d');
  if(!raster)throw Error('Reference basemap unavailable.');
  const sx=((west+180)/360*scale-left)*tileSize,sw=(east-west)/360*scale*tileSize;
  // Heat is drawn in lon/lat. Reproject each destination row to its Mercator source row.
  for(let row=0;row<map.height;row++){
    const latitude=north-(north-south)*(row+.5)/map.height;
    const sy=(mercator(latitude)*scale-first)*tileSize;
    raster.drawImage(mosaic,sx,sy,sw,1,0,row,map.width,1);
  }
  return map;
}
