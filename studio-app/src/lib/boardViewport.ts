export type BoardViewport = {scrollX:number;scrollY:number;zoom:{value:number}};

/** View position belongs to this browser and board, never to the shared scene. */
export function readBoardViewport(id:string):BoardViewport|null {
  try {
    const value=JSON.parse(localStorage.getItem(`fireatlas-board-viewport:${id}`) || 'null');
    if(!value || !Number.isFinite(value.scrollX) || !Number.isFinite(value.scrollY) ||
       !Number.isFinite(value.zoom) || value.zoom<0.1 || value.zoom>30 ||
       Math.abs(value.scrollX)>1e7 || Math.abs(value.scrollY)>1e7)return null;
    return {scrollX:value.scrollX,scrollY:value.scrollY,zoom:{value:value.zoom}};
  } catch {return null;}
}

export function saveBoardViewport(id:string,state:{scrollX:number;scrollY:number;zoom:{value:number}}):void {
  if(!Number.isFinite(state.scrollX) || !Number.isFinite(state.scrollY) || !Number.isFinite(state.zoom?.value) ||
     state.zoom.value<0.1 || state.zoom.value>30 || Math.abs(state.scrollX)>1e7 || Math.abs(state.scrollY)>1e7)return;
  try {localStorage.setItem(`fireatlas-board-viewport:${id}`,JSON.stringify({scrollX:state.scrollX,scrollY:state.scrollY,zoom:state.zoom.value}));} catch { /* Browser storage is optional. */ }
}
