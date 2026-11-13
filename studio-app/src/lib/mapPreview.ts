import { heatMapProjection } from './heatMapGeometry';
import {sanitizeFigure} from './investigationReport';
import {geographicBasemap,landscapeImage,mapLandscape} from './mapLandscape';
import type {Snapshot} from '../types';

const displayFont = 'Board Space Grotesk';
const bodyFont = 'Board DM Sans';
let fontsReady: Promise<void> | undefined;

function figureFonts(): Promise<void> {
  if (!fontsReady) {
    fontsReady = typeof FontFace === 'undefined' || !document.fonts
      ? Promise.resolve()
      : Promise.allSettled([
        [displayFont, 'space-grotesk.ttf', '300 700'],
        [bodyFont, 'dm-sans.ttf', '100 1000'],
      ].map(async ([family,file,weight]) => {
        const url=new URL('./fonts/'+file,document.baseURI).href;
        const face=await new FontFace(family,`url("${url}")`,{weight}).load();
        document.fonts.add(face);
      })).then(()=>undefined);
  }
  return fontsReady;
}

function figureCanvas() {
  const canvas=document.createElement('canvas');
  canvas.width=960;
  canvas.height=540;
  const context=canvas.getContext('2d');
  if(!context)throw Error('Map drawing is unavailable in this browser.');
  return {canvas,context};
}

function loadImage(url:string, message:string):Promise<HTMLImageElement> {
  const image=new Image();
  return new Promise((resolve,reject)=>{
    image.onload=()=>resolve(image);
    image.onerror=()=>reject(Error(message));
    image.src=url;
  });
}

function figureText(ctx:CanvasRenderingContext2D, value:string, x:number, y:number,
                    size:number, color:string, weight=500, family=bodyFont, maxWidth?:number) {
  ctx.fillStyle=color;
  ctx.font=`${weight} ${size}px "${family}", Arial, sans-serif`;
  if(maxWidth===undefined)ctx.fillText(value,x,y);
  else ctx.fillText(value,x,y,maxWidth);
}

/** Render an inert server-prepared map to a portable whiteboard image. */
export async function renderMapPreview(svg:string):Promise<string> {
  const parser=new DOMParser();
  const parsed=parser.parseFromString(svg,'image/svg+xml');
  const root=parsed.documentElement;
  if(root.localName!=='svg' || parsed.querySelector('parsererror'))throw Error('The saved map preview could not be read.');
  let safe=sanitizeFigure(root as unknown as SVGSVGElement);
  const labels:Element[]=[];
  if(root.getAttribute('data-board-figure')==='v1'){
    // SVG images isolate document fonts. Paint the vetted flat labels on the
    // canvas so the bundled typefaces are baked into the portable PNG.
    const clean=parser.parseFromString(safe,'image/svg+xml');
    labels.push(...clean.querySelectorAll('text'));
    labels.forEach(label=>label.remove());
    safe=new XMLSerializer().serializeToString(clean.documentElement);
    await figureFonts();
  }
  const url=URL.createObjectURL(new Blob([safe],{type:'image/svg+xml'}));
  try {
    const image=await loadImage(url,'The saved map could not be rendered.');
    const {canvas,context}=figureCanvas();
    context.fillStyle='#ffffff';
    context.fillRect(0,0,960,540);
    context.drawImage(image,0,0,960,540);
    for(const label of labels){
      const x=Number(label.getAttribute('x')), y=Number(label.getAttribute('y'));
      const size=Number(label.getAttribute('font-size')) || 14;
      const weight=Number(label.getAttribute('font-weight')) || 500;
      const family=label.getAttribute('font-family')?.startsWith('Space Grotesk') ? displayFont : bodyFont;
      const anchor=label.getAttribute('text-anchor');
      context.textAlign=anchor==='end'?'right':anchor==='middle'?'center':'left';
      if(Number.isFinite(x) && Number.isFinite(y)){
        const width=anchor==='end' || anchor==='middle' ? undefined : 928-x;
        figureText(context,label.textContent || '',x,y,size,label.getAttribute('fill') || '#264541',weight,family,width);
      }
    }
    return canvas.toDataURL('image/png');
  } finally {URL.revokeObjectURL(url);}
}

/** Frame the existing Python-produced heat raster with geographic and source context. */
export async function renderHeatPreview(visual:any,documentId:string,snapshot:Snapshot,title='Thermal concentration'):Promise<{dataURL:string;background:string}> {
  if(visual?.kind!=='heat' || visual.mime!=='image/png' || typeof visual.data!=='string' || !Array.isArray(visual.scope?.bbox) || visual.scope.bbox.length!==4 || !Array.isArray(visual.domain))throw Error('The saved heatmap is unavailable.');
  const [image]=await Promise.all([loadImage('data:image/png;base64,'+visual.data,'The saved heatmap could not be rendered.'),figureFonts()]);
  const {canvas,context:ctx}=figureCanvas();
  const [west,south,east,north]=visual.scope.bbox;
  const {x,y,width,height,project}=heatMapProjection(visual.scope.bbox);
  ctx.fillStyle='#f7faf7';
  ctx.fillRect(0,0,960,540);
  ctx.fillStyle='#183837';
  ctx.fillRect(32,102,604,365);
  let background='Geographic frame';
  try {
    // A comparison panel has its own extent; the parent snapshot may describe
    // another panel. Never stretch that parent's local landscape over this map.
    if(visual.comparison_scale)throw Error('Use the panel geographic context.');
    const landscape=await mapLandscape(documentId,snapshot,'auto',visual.day);
    const requested=visual.interval && landscape.selected==='ndvi-online' ? [] : landscape.layers;
    const layers=await Promise.allSettled(requested.map(async (layer:any)=>({layer,image:await landscapeImage(layer,layer.url?4500:12000)})));
    const loaded=layers.flatMap((entry)=>entry.status==='fulfilled'?[entry.value]:[]);
    for(const item of loaded){
      ctx.save();
      ctx.globalAlpha=item.layer.name.startsWith('ndvi')?.82:.45;
      ctx.drawImage(item.image,x,y,width,height);
      ctx.restore();
    }
    if(loaded.length)background=loaded.length===landscape.layers.length?landscape.label:'Supplied terrain context';
  }catch { /* Retain the heatmap when the optional geographic layer is unavailable. */ }
  if(background==='Geographic frame'){
    try {
      ctx.drawImage(await geographicBasemap(visual.scope.bbox,'terrain'),x,y,width,height);
      background='NASA GIBS · Blue Marble shaded relief';
    }catch { /* The verified heat stays visible when imagery is unavailable. */ }
  }
  if(background==='Geographic frame'){
    try {
      ctx.drawImage(await geographicBasemap(visual.scope.bbox,'reference'),x,y,width,height);
      background='© OpenStreetMap contributors';
    }catch { /* The map still shows its verified heat and coordinate frame. */ }
  }
  if(background!=='Geographic frame'){
    ctx.fillStyle='rgba(0,0,0,.38)';
    ctx.fillRect(x,y,width,height);
  }
  ctx.drawImage(image,x,y,width,height);
  ctx.save();
  ctx.beginPath();
  ctx.rect(x,y,width,height);
  ctx.clip();
  for(const point of visual.points || []){
    if(!Number.isFinite(point.longitude) || !Number.isFinite(point.latitude) || point.longitude<west || point.longitude>east || point.latitude<south || point.latitude>north)continue;
    const [px,py]=project(point.longitude,point.latitude);
    ctx.beginPath();
    ctx.arc(px,py,2,0,Math.PI*2);
    ctx.fillStyle='#ffca7b';
    ctx.fill();
  }
  ctx.strokeStyle='#ccdfd0';
  for(const ring of visual.outline || []){
    ctx.beginPath();
    ring.forEach(([longitude,latitude]:number[],index:number)=>{
      const [px,py]=project(longitude,latitude);
      if(index===0)ctx.moveTo(px,py);else ctx.lineTo(px,py);
    });
    ctx.closePath();ctx.stroke();
  }
  if(visual.reference){
    const [px,py]=project(visual.reference.longitude,visual.reference.latitude);
    ctx.beginPath();ctx.arc(px,py,4,0,Math.PI*2);
    ctx.strokeStyle='#ccebe4';ctx.stroke();
    figureText(ctx,visual.reference.name,px+8,py-7,13,'#eff9f4',700);
  }
  ctx.restore();
  ctx.strokeStyle='#72978a';
  ctx.strokeRect(x,y,width,height);
  const source=({joint:'Combined detections',MODIS_SP:'MODIS',VIIRS_SNPP_SP:'VIIRS S-NPP',VIIRS_NOAA20_SP:'VIIRS NOAA-20',VIIRS_NOAA21_SP:'VIIRS NOAA-21'} as Record<string,string>)[visual.source] || visual.source;
  figureText(ctx,title,32,46,34,'#102d2b',700,displayFont,896);
  const interval=visual.interval;
  const dates=interval && interval.start!==interval.end ? `${interval.start} – ${interval.end}` : visual.day;
  figureText(ctx,`${dates} UTC · ${visual.sensor || source}`,32,73,14,'#526a64',600);
  ctx.fillStyle='#d7e5dd';
  ctx.fillRect(32,86,896,1);
  ctx.fillRect(32,483,896,1);
  ctx.fillStyle='#143532';
  ctx.fillRect(654,102,274,365);
  figureText(ctx,'THERMAL OBSERVATIONS',676,136,13,'#a8d2c4',700);
  figureText(ctx,Number(visual.count).toLocaleString('en-US'),676,205,63,'#f9fffc',700,displayFont);
  figureText(ctx,interval ? 'distinct occupied 1 km cells' : 'occupied grid cells',677,231,15,'#d1e7dd',600);
  ctx.fillStyle='#45635a';
  ctx.fillRect(676,252,230,1);
  figureText(ctx,'Heat concentration',677,286,17,'#f6fff9',700);
  const gradient=ctx.createLinearGradient(677,0,905,0);
  ['#fff2b2','#fec44f','#fc8d3c','#e34a33','#b30000'].forEach((color,index)=>gradient.addColorStop(index/4,color));
  ctx.fillStyle=gradient;
  ctx.fillRect(677,308,228,10);
  figureText(ctx,'0',677,341,13,'#d1e7dd');
  ctx.textAlign='right';
  figureText(ctx,Number(visual.domain[1]).toPrecision(3),905,341,13,'#d1e7dd');
  ctx.textAlign='left';
  figureText(ctx,visual.comparison_scale?'Shared scale · 1 km Gaussian':'1 km Gaussian · occupied cells',677,378,13,'#d1e7dd',500,bodyFont,229);
  if(interval)figureText(ctx,`${Number(visual.detections).toLocaleString('en-US')} FIRMS detections in this window`,677,407,13,'#d1e7dd',500,bodyFont,229);
  figureText(ctx,'NASA FIRMS',32,513,13,'#234f43',700);
  figureText(ctx,`${west}° to ${east}° lon · ${south}° to ${north}° lat`,142,513,13,'#526a64',500,bodyFont,520);
  ctx.textAlign='right';
  figureText(ctx,background==='Geographic frame'?'Landscape unavailable':background,928,513,13,'#526a64',500,bodyFont,300);
  return {dataURL:canvas.toDataURL('image/png'),background};
}
