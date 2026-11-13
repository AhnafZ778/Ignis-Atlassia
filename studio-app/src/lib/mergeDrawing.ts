/** Remap an imported drawing so it can be added without taking over the board. */
export function mergeDrawing(elements:readonly any[], files:readonly any[], existing:readonly any[], unique:()=>string) {
  const live=elements.filter(item=>!item.isDeleted);
  if(!live.length)throw Error('This drawing has no visible objects to add.');
  const ids=new Map<string,string>(),fileIds=new Map<string,string>(),groups=new Map<string,string>();
  for(const item of live){if(!item.id || ids.has(item.id))throw Error('The drawing contains duplicate object IDs.');ids.set(item.id,unique());}
  for(const file of files){if(!file.id || fileIds.has(file.id))throw Error('The drawing contains duplicate file IDs.');fileIds.set(file.id,unique());}
  const ref=(id:string|null|undefined)=>{
    if(!id)return null;
    const mapped=ids.get(id);if(!mapped)throw Error('The drawing contains a reference to a missing object.');return mapped;
  };
  const boxes=live.map(item=>[item.x,item.y,item.width,item.height]);
  if(boxes.some(box=>box.some(value=>!Number.isFinite(value))))throw Error('The drawing contains invalid positions.');
  const left=Math.min(...live.map(item=>item.x)),top=Math.min(...live.map(item=>item.y));
  const right=Math.max(...live.map(item=>item.x+item.width)),bottom=Math.max(...live.map(item=>item.y+item.height));
  if(right-left>20000 || bottom-top>20000)throw Error('This drawing is too large to add.');
  const target=existing.length?Math.max(...existing.map(item=>item.x+item.width))+160:100;
  const dx=target-left,dy=100-top;
  const copied=live.map(item=>{
    const customData=item.customData?{...item.customData}:undefined;
    const hadSource=Boolean(customData?.fireatlas);
    const isWebLink=customData?.fireatlas?.kind==='external-link';
    if(customData)delete customData.fireatlas;
    const groupIds=(item.groupIds || []).map((group:string)=>{if(!groups.has(group))groups.set(group,unique());return groups.get(group);});
    const binding=(value:any)=>value?{...value,elementId:ref(value.elementId)}:null;
    const fileId=item.fileId ? fileIds.get(item.fileId) : item.fileId;
    if(item.fileId && !fileId)throw Error('The drawing is missing an embedded image.');
    return {...item,id:ids.get(item.id),x:item.x+dx,y:item.y+dy,groupIds,
      frameId:ref(item.frameId),containerId:ref(item.containerId),
      boundElements:item.boundElements?.map((bound:any)=>({...bound,id:ref(bound.id)})) || null,
      ...('startBinding' in item?{startBinding:binding(item.startBinding),endBinding:binding(item.endBinding)}:{}),
      ...('fileId' in item?{fileId}:{}),customData,link:hadSource && !isWebLink?null:item.link};
  });
  return {elements:copied,files:files.map(file=>({...file,id:fileIds.get(file.id)})),bounds:{x:target,y:100,width:right-left,height:bottom-top}};
}
