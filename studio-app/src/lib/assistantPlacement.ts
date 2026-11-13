import { exportToSvg, getCommonBounds } from '@excalidraw/excalidraw';
import type { ExcalidrawImperativeAPI } from '@excalidraw/excalidraw/types';

type Element = NonNullable<Parameters<ExcalidrawImperativeAPI['updateScene']>[0]['elements']>[number];
type Files = ReturnType<ExcalidrawImperativeAPI['getFiles']>;
type Point = {x:number;y:number};
type Rect = Point & {width:number;height:number};
const cameraTime = 300;
const approachTime = 420;
const revealTime = 560;
const totalTime = approachTime + revealTime + 120;
const clamp = (value:number,min:number,max:number) => Math.min(max,Math.max(min,value));
const ease = (value:number) => value*value*(3-2*value);

export function placementFrame(ms:number, origin:Point, target:Rect, arrow?:readonly [Point,Point]) {
  const arrival=arrow?.[0] || {x:target.x,y:target.y};
  const approach=ease(clamp(ms/approachTime,0,1));
  const drawing=clamp((ms-approachTime)/revealTime,0,1);
  const reveal=ease(arrow?drawing:clamp((drawing-.23)/.77,0,1));
  const across=arrow?reveal:ease(clamp(drawing/.23,0,1));
  const destination=arrow?.[1] || {x:target.x+target.width,y:target.y+target.height};
  const x=origin.x+(arrival.x-origin.x)*approach+(destination.x-arrival.x)*across;
  const arc=ms<approachTime?Math.sin(Math.PI*approach)*Math.min(70,Math.abs(arrival.x-origin.x)*.14):0;
  const y=origin.y+(arrival.y-origin.y)*approach+(destination.y-arrival.y)*reveal-arc;
  return {x,y,reveal,across,done:ms>=totalTime};
}

export function placementCanvas(launcher:HTMLElement|null) {
  const canvas=launcher?.closest('.whiteboard-shell')?.querySelector<HTMLElement>('.whiteboard-canvas');
  return canvas && canvas.clientWidth>0 && canvas.clientHeight>0 && document.visibilityState!=='hidden' && window.matchMedia?.('(prefers-reduced-motion: no-preference)').matches ? canvas : null;
}

export async function animatePlacement({
  editor, canvas, focus, files, origin, label, current, viewportZoomFactor, preview=true,
}:{
  editor:ExcalidrawImperativeAPI;canvas:HTMLElement;focus:readonly Element[];files:Files;
  origin:Point;label:string;current:()=>boolean;viewportZoomFactor?:number;preview?:boolean;
}):Promise<void> {
  const [left,top,right,bottom]=getCommonBounds(focus);
  if(![left,top,right,bottom].every(Number.isFinite))return;
  const stage=document.createElement('div');
  stage.className='assistant-placement';
  stage.setAttribute('aria-hidden','true');
  stage.innerHTML='<div class="assistant-placement-art"></div><div class="assistant-placement-scan"></div><div class="assistant-placement-cursor"><svg viewBox="0 0 20 24" width="22" height="26"><path d="M2 1 17 12l-7 1-3 8z"/></svg><span></span></div>';
  const art=stage.children[0] as HTMLDivElement;
  const scan=stage.children[1] as HTMLDivElement;
  const cursor=stage.children[2] as HTMLDivElement;
  (cursor.lastElementChild as HTMLElement).textContent=label;
  const line=focus.length===1 && focus[0].type==='arrow' && focus[0].points.length===2 && !focus[0].angle ? focus[0] : undefined;
  // Build the reveal from the actual scene objects and image files. Nothing is added to
  // editor history or exposed to autosave until the caller commits the complete edit.
  let svg:SVGSVGElement|undefined;
  if(preview){
    void exportToSvg({
      elements:focus,files,appState:{exportBackground:false,exportWithDarkMode:editor.getAppState().theme==='dark'},
      exportPadding:0,skipInliningFonts:true,
    }).then((image:SVGSVGElement)=>{svg=image;}).catch(()=>{});
  }
  editor.scrollToContent(focus,{fitToViewport:true,viewportZoomFactor:viewportZoomFactor ?? .8,maxZoom:1,animate:true,duration:cameraTime});
  document.body.append(stage);
  try {
    await new Promise<void>(resolve=>{
      let start:number|undefined;
      let revealed=false;
      let pending=0;
      const finish=()=>{cancelAnimationFrame(pending);document.removeEventListener('visibilitychange',onVisibility);resolve();};
      const onVisibility=()=>{if(document.visibilityState==='hidden')finish();};
      document.addEventListener('visibilitychange',onVisibility);
      const tick=(now:number)=>{
        if(!current() || !canvas.isConnected){finish();return;}
        start ??= now;
        const ms=now-start;
        const bounds=canvas.getBoundingClientRect(), state=editor.getAppState(), zoom=state.zoom?.value || 1;
        const project=(x:number,y:number)=>({x:(x+state.scrollX)*zoom,y:(y+state.scrollY)*zoom});
        const first=project(left,top);
        const target={...first,width:Math.max(2,(right-left)*zoom),height:Math.max(2,(bottom-top)*zoom)};
        const initial={x:clamp(origin.x-bounds.left,12,bounds.width-16),y:clamp(origin.y-bounds.top,8,bounds.height-26)};
        const endpoints=line ? line.points.map(point=>project(line.x+point[0],line.y+point[1])) as [Point,Point] : undefined;
        const frame=placementFrame(ms,initial,target,endpoints);
        const x=clamp(frame.x,4,bounds.width-16), y=clamp(frame.y,4,bounds.height-20);
        Object.assign(stage.style,{left:`${bounds.left}px`,top:`${bounds.top}px`,width:`${bounds.width}px`,height:`${bounds.height}px`});
        cursor.style.transform=`translate3d(${x}px,${y}px,0)`;
        cursor.classList.toggle('near-right',x>bounds.width-126);
        cursor.classList.toggle('near-bottom',y>bounds.height-42);
        if(svg && !revealed && frame.reveal<.15){art.append(svg);revealed=true;}
        if(!endpoints){
          scan.style.transform=`translate3d(${target.x}px,${target.y+target.height*frame.reveal}px,0)`;
          scan.style.width=`${target.width*frame.across}px`;
          scan.style.opacity=frame.reveal<1?'1':'0';
        }
        // The editor supplies native arrow geometry. Reveal it in the direction it was drawn.
        const fromRight=endpoints && endpoints[0].x>endpoints[1].x;
        const fromBottom=endpoints && endpoints[0].y>endpoints[1].y;
        const horizontal=endpoints && Math.abs(endpoints[1].x-endpoints[0].x)>Math.abs(endpoints[1].y-endpoints[0].y);
        const hidden=100*(1-frame.reveal);
        const clip=horizontal ? (fromRight?`0 0 0 ${hidden}%`:`0 ${hidden}% 0 0`) : (fromBottom?`${hidden}% 0 0 0`:`0 0 ${hidden}% 0`);
        Object.assign(art.style,{
          left:`${target.x}px`,top:`${target.y}px`,width:`${target.width}px`,height:`${target.height}px`,
          clipPath:`inset(${clip})`,opacity:frame.reveal>0?'1':'0',
        });
        if(frame.done){finish();return;}
        pending=requestAnimationFrame(tick);
      };
      pending=requestAnimationFrame(tick);
    });
  } finally {
    stage.remove();
  }
}
