/** Return a representative only when the board has one unambiguous linked table. */
export function boardDataset(elements:readonly any[],documentId:string):any | null {
  const candidates=elements.filter(item=>{
    const ref=item.customData?.fireatlas;
    return !item.isDeleted && ref?.documentId===documentId && typeof ref.datasetId==='string' && !!ref.datasetId && typeof ref.datasetHash==='string' && !!ref.datasetHash;
  });
  const keys=new Set(candidates.map(item=>JSON.stringify([item.customData.fireatlas.datasetId,item.customData.fireatlas.datasetHash])));
  if(keys.size!==1)return null;
  return candidates.find(item=>item.type==='frame') || candidates.find(item=>!Number.isInteger(item.customData.fireatlas.rowOffset)) || candidates[0] || null;
}
