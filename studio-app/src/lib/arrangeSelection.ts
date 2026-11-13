import { newElementWith } from '@excalidraw/excalidraw';
import type { ExcalidrawElement } from '@excalidraw/excalidraw/element/types';

type Box = { items: ExcalidrawElement[]; left: number; top: number; width: number; height: number };

/** Move selected items, complete groups, and frames without detaching relationships. */
export function arrangeSelection(elements: readonly ExcalidrawElement[], selectedIds: Record<string, boolean>): ExcalidrawElement[] {
  const live = elements.filter(e => !e.isDeleted);
  const selected = live.filter(e => selectedIds[e.id]);
  const moving = new Set(selected.map(e => e.id));
  // Expand groups, frame contents, labels, and fully enclosed connections.
  let changed = true;
  while (changed) {
    changed = false;
    const groups = new Set(live.filter(e => moving.has(e.id)).flatMap(e => e.groupIds));
    for (const e of live) {
      if (!moving.has(e.id) && (e.groupIds.some(id => groups.has(id)) || (!!e.frameId && moving.has(e.frameId)) || (e.type === 'text' && !!e.containerId && moving.has(e.containerId)) ||
          ((e.type === 'arrow' || e.type === 'line') && !!e.startBinding && !!e.endBinding && moving.has(e.startBinding.elementId) && moving.has(e.endBinding.elementId)))) {
        moving.add(e.id); changed = true;
      }
    }
    if (moving.size > 200) throw Error('Select smaller groups to organize.');
  }
  const targets = live.filter(e => moving.has(e.id));
  for (const e of targets) {
    if (e.locked || (e.frameId && !moving.has(e.frameId)) || e.angle !== 0 || (e.type === 'text' && e.containerId && !moving.has(e.containerId))) {
      throw Error('Organize unlocked, unrotated items; select the whole frame for items inside one.');
    }
    if ((e.type === 'arrow' || e.type === 'line') && (e.startBinding || e.endBinding) && (!e.startBinding || !e.endBinding || !moving.has(e.startBinding.elementId) || !moving.has(e.endBinding.elementId))) throw Error('Select both ends of every connected arrow.');
    if (e.boundElements?.some(bound => bound.type === 'arrow' && !moving.has(bound.id))) throw Error('Select both ends of every connected arrow.');
  }
  if (live.some(e => (e.type === 'arrow' || e.type === 'line') && !moving.has(e.id) && ((e.startBinding && moving.has(e.startBinding.elementId)) || (e.endBinding && moving.has(e.endBinding.elementId))))) {
    throw Error('Select both ends of every connected arrow.');
  }
  // Union overlapping groups and a shape's label into one rigid unit.
  const parent = new Map(targets.map(e => [e.id,e.id]));
  const find = (id:string):string => { const p=parent.get(id)!; if(p===id)return id; const root=find(p); parent.set(id,root); return root; };
  const union = (a:string,b:string) => { const ra=find(a),rb=find(b); if(ra!==rb)parent.set(ra,rb); };
  const groupOwner = new Map<string,string>();
  for (const e of targets) {
    for (const id of e.groupIds) { const owner=groupOwner.get(id); if(owner)union(e.id,owner); else groupOwner.set(id,e.id); }
    if(e.frameId && parent.has(e.frameId))union(e.id,e.frameId);
    if(e.type==='text' && e.containerId && parent.has(e.containerId))union(e.id,e.containerId);
    if((e.type==='arrow' || e.type==='line') && e.startBinding && e.endBinding){union(e.id,e.startBinding.elementId);union(e.id,e.endBinding.elementId);}
  }
  const units = new Map<string,ExcalidrawElement[]>();
  for(const e of targets){const id=find(e.id); const unit=units.get(id) || []; unit.push(e); units.set(id,unit);}
  if(units.size<2 || units.size>20)throw Error('Select between two and twenty separate items or groups to organize.');
  const boxes:Box[]=[...units.values()].map(items=>{
    const left=Math.min(...items.map(e=>e.x)),top=Math.min(...items.map(e=>e.y));
    return {items,left,top,width:Math.max(...items.map(e=>e.x+e.width))-left,height:Math.max(...items.map(e=>e.y+e.height))-top};
  }).sort((a,b)=>a.top-b.top || a.left-b.left || a.items[0].id.localeCompare(b.items[0].id));
  const left=Math.min(...boxes.map(b=>b.left)),top=Math.min(...boxes.map(b=>b.top));
  const cols=Math.ceil(Math.sqrt(boxes.length));
  const width=Math.max(...boxes.map(b=>b.width)),height=Math.max(...boxes.map(b=>b.height));
  const shifts=new Map<string,{x:number;y:number}>();
  boxes.forEach((box,i)=>{const d={x:left+(i%cols)*(width+40)-box.left,y:top+Math.floor(i/cols)*(height+40)-box.top};for(const e of box.items)shifts.set(e.id,d);});
  const placed=elements.map(e=>{const d=shifts.get(e.id);return d?newElementWith(e,{x:e.x+d.x,y:e.y+d.y}):e;});
  const obstacles=live.filter(e=>!moving.has(e.id));
  if(placed.some(e=>moving.has(e.id) && obstacles.some(o=>e.x<o.x+o.width && e.x+e.width>o.x && e.y<o.y+o.height && e.y+e.height>o.y)))throw Error('There is not enough clear space to organize this selection.');
  return placed;
}
