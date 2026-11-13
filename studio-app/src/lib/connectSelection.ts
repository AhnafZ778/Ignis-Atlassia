import { convertToExcalidrawElements, newElementWith } from '@excalidraw/excalidraw';
import type { ExcalidrawElement } from '@excalidraw/excalidraw/element/types';

/** Add a neutral connector to exactly two selected, unlocked board objects. */
export function connectSelection(elements: readonly ExcalidrawElement[], selected: Record<string,boolean>, documentId: string, id: string): ExcalidrawElement[] {
  // Excalidraw may select a bound label along with its container. The label
  // is part of that object, rather than a third endpoint.
  const selectedItems=elements.filter(item=>!item.isDeleted && selected[item.id]);
  const isDatasetCardLabel=(item:ExcalidrawElement):boolean=>{
    if(item.type!=='text')return false;
    const ref=(item.customData as any)?.fireatlas;
    if(ref?.kind!=='csv-dataset' || !ref.datasetId || !ref.datasetHash)return false;
    return selectedItems.some(card=>{
      const other=(card.customData as any)?.fireatlas;
      return card.type==='rectangle' && other?.kind===ref.kind && other.documentId===ref.documentId &&
        other.datasetId===ref.datasetId && other.datasetHash===ref.datasetHash &&
        item.x>=card.x && item.y>=card.y && item.x+item.width<=card.x+card.width && item.y+item.height<=card.y+card.height;
    });
  };
  const targets=selectedItems.filter(item=>!(item.type==='text' && item.containerId && selected[item.containerId]) && !isDatasetCardLabel(item));
  if(targets.length!==2)throw Error('Select two objects to connect.');
  if(targets.some(item=>item.locked || item.angle!==0 || !['rectangle','ellipse','diamond','text','image'].includes(item.type)))throw Error('Select two unlocked, unrotated shapes, notes or images.');
  const [a,b]=[...targets].sort((left,right)=>left.x-right.x || left.y-right.y || left.id.localeCompare(right.id));
  const dx=(b.x+b.width/2)-(a.x+a.width/2),dy=(b.y+b.height/2)-(a.y+a.height/2);
  if(Math.abs(dx)<(a.width+b.width)/2 && Math.abs(dy)<(a.height+b.height)/2)throw Error('Move the objects apart before connecting them.');
  const horizontal=Math.abs(dx)>=Math.abs(dy);
  const sx=horizontal?a.x+(dx>0?a.width:0):a.x+a.width/2;
  const sy=horizontal?a.y+a.height/2:a.y+(dy>0?a.height:0);
  const ex=horizontal?b.x+(dx>0?0:b.width):b.x+b.width/2;
  const ey=horizontal?b.y+b.height/2:b.y+(dy>0?0:b.height);
  // The converter's binding helper supports rectangles but not images. Use
  // an equal-sized rectangle only while calculating bindings; the actual
  // image and its source metadata remain untouched in the scene.
  const proxy=(item:ExcalidrawElement)=>item.type==='image'?{...item,type:'rectangle' as const}:item;
  const converted=convertToExcalidrawElements([proxy(a) as any,proxy(b) as any,{id,type:'arrow',x:sx,y:sy,points:[[0,0],[ex-sx,ey-sy]],
    start:{id:a.id},end:{id:b.id},strokeColor:'#486884',label:{text:'related',fontSize:14,fontFamily:2},
    customData:{fireatlas:{documentId,kind:'assistant-connector',relation:'related',originalElementIds:[a.id,b.id]}}}],{regenerateIds:false});
  const arrow=converted.find(item=>item.id===id && item.type==='arrow');
  if(!arrow || arrow.type!=='arrow' || arrow.startBinding?.elementId!==a.id || arrow.endBinding?.elementId!==b.id)throw Error('The objects could not be connected.');
  const extras=converted.filter(item=>item.id!==a.id && item.id!==b.id);
  const updated=elements.map(item=>item.id===a.id || item.id===b.id
    ? newElementWith(item,{boundElements:[...(item.boundElements || []),{id:arrow.id,type:'arrow'}]}) : item);
  return [...updated,...extras];
}
