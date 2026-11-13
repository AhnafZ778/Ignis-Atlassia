type SceneItem={id:string;isDeleted?:boolean;customData?:any};

/** Resolve only extant objects on this board, never substitute a different finding. */
export function challengeOriginals<T extends SceneItem>(items:readonly T[],selected:Record<string,boolean>,documentId:string):{targets:T[];missing:number} {
  const challenge=items.find(item=>selected[item.id] && item.customData?.fireatlas?.documentId===documentId && Array.isArray(item.customData?.fireatlas?.originalElementIds));
  if(!challenge)throw Error('Select a challenge or assistant diagram on the board first.');
  const ids=[...new Set((challenge.customData.fireatlas.originalElementIds as unknown[]).filter((id):id is string=>typeof id==='string' && id!==challenge.id))];
  const targets=items.filter(item=>!item.isDeleted && ids.includes(item.id));
  if(!targets.length)throw Error('The original material is no longer on this board.');
  return {targets,missing:Math.max(ids.length-targets.length,challenge.customData.fireatlas.reference_state==='unavailable-after-import'?1:0)};
}
