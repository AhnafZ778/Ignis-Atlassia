/** A direct inspector is offered only for one unambiguous, owned selection. */
export function selectedSource(elements:readonly any[],selected:Record<string,boolean>,documentId:string|null):'table'|'document'|'evidence'|null {
  if(!documentId)return null;
  const items=elements.filter(item=>!item.isDeleted && selected[item.id]);
  if(items.length!==1)return null;
  const ref=items[0].customData?.fireatlas;
  if(!ref || ref.documentId!==documentId)return null;
  if(typeof ref.datasetId==='string' && typeof ref.datasetHash==='string')return 'table';
  if(typeof ref.sourceDocumentId==='string' && typeof ref.sourceDocumentHash==='string')return 'document';
  if(typeof ref.snapshotId==='string' && typeof ref.snapshotHash==='string')return 'evidence';
  return null;
}

/** Keep asynchronous inspection attached to the single source the user opened. */
export function sameSelectedSource(elements:readonly any[],selected:Record<string,boolean>,id:string,serializedRef:string):boolean {
  const items=elements.filter(item=>!item.isDeleted && selected[item.id]);
  return items.length===1 && items[0].id===id && JSON.stringify(items[0].customData?.fireatlas)===serializedRef;
}
