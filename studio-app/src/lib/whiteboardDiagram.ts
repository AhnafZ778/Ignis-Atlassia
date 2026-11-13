import { wrapCardText } from './wrapCardText';
export type Diagram = { nodes: { id: string; label: string; kind: 'evidence' | 'interpretation' | 'context' | 'question'; evidence_id?: string | null; binding?: { documentId: string; cardId?: string; snapshotId?: string; snapshotHash?: string; datasetId?:string; datasetHash?:string; xColumn?:string; yColumn?:string; groupColumn?:string; valueColumn?:string } }[]; edges: { source: string; target: string; relation: 'context' | 'question' }[] };

/** Convert a bounded diagram intent to editable native shapes and bound arrows. */
export function diagramShapes(diagram: Diagram, documentId: string, sourceCardIds: string[], x: number, y: number, unique: () => string, originalElementIds:string[]=[]): any[] {
  if (!diagram || !Array.isArray(diagram.nodes) || !Array.isArray(diagram.edges) || !diagram.nodes.length || diagram.nodes.length > 6 || diagram.edges.length > 8) throw Error('The assistant diagram is unavailable.');
  const ids = new Map<string, string>();
  const shapes: any[] = [];
  const colors = { evidence: '#dceefa', interpretation: '#e9e5fa', context: '#e8f1ec', question: '#fff0d8' };
  // Give long interpretations a full row so their complete text remains legible
  // without forcing the entire diagram into a very tall, narrow column.
  const wide=diagram.nodes.map(node=>node.kind==='interpretation' && node.label.length>120);
  const labels=diagram.nodes.map((node,index)=>wrapCardText(node.kind==='interpretation'?`AI interpretation\n${node.label}`:node.kind==='context'?`AI context\n${node.label}`:node.label,wide[index]?40:18));
  const heights=labels.map(label=>Math.max(105,36+label.split('\n').length*23));
  const positions:{row:number;column:number}[]=[];
  let row=0,column=0;
  wide.forEach(isWide=>{
    if(isWide && column){row++;column=0;}
    positions.push({row,column});
    if(isWide || column===1){row++;column=0;}else column=1;
  });
  const rows:number[]=[];
  positions.forEach((position,index)=>{rows[position.row]=Math.max(rows[position.row] || 0,heights[index]);});
  const rowTop=rows.map((_,index)=>y+rows.slice(0,index).reduce((sum,height)=>sum+height+75,0));
  diagram.nodes.forEach((node, index) => {
    if (!node.id || ids.has(node.id) || !node.label || !(node.kind in colors)) throw Error('The assistant diagram contains an invalid node.');
    const id = unique(); ids.set(node.id, id);
    const metadata = { fireatlas: { documentId, sourceCardIds, kind: 'assistant-diagram', nodeKind: node.kind, evidenceId: node.evidence_id || null, ...(originalElementIds.length ? {originalElementIds} : {}), ...(node.binding || {}) } };
    const link = node.binding ? new URL(`./studio.html?board=${encodeURIComponent(documentId)}`, document.baseURI).href : null;
    shapes.push({ id, type: 'rectangle', x: x + positions[index].column * 435, y: rowTop[positions[index].row],
      width: wide[index] ? 775 : 340, height: heights[index], backgroundColor: colors[node.kind], fillStyle: 'solid', strokeColor: '#486884',
      roundness: { type: 3 }, label: { text: labels[index], fontSize: 18, fontFamily:2 }, link, customData: metadata });
  });
  diagram.edges.forEach((edge, edgeIndex) => {
    const start = ids.get(edge.source), end = ids.get(edge.target);
    if (!start || !end || start === end || !['context', 'question'].includes(edge.relation)) throw Error('The assistant diagram contains an invalid connection.');
    const a = shapes.find((shape) => shape.id === start);
    const b = shapes.find((shape) => shape.id === end);
    const dx=(b.x+b.width/2)-(a.x+a.width/2),dy=(b.y+b.height/2)-(a.y+a.height/2);
    const horizontal=a.y===b.y;
    const sx=horizontal ? a.x+(dx>0?a.width:0) : a.x+a.width/2;
    const sy=horizontal ? a.y+a.height/2 : a.y+(dy>0?a.height:0);
    const ex=horizontal ? b.x+(dx>0?0:b.width) : b.x+b.width/2;
    const ey=horizontal ? b.y+b.height/2 : b.y+(dy>0?0:b.height);
    // A connection spanning rows must not pass through a card in between.
    // Route around the right edge of the diagram, using a small lane per edge.
    const cards=shapes.filter(shape=>shape.type==='rectangle');
    const blocked=!horizontal && cards.some(card=>card.id!==start && card.id!==end &&
      card.y<Math.max(sy,ey) && card.y+card.height>Math.min(sy,ey) &&
      card.x<Math.max(sx,ex)+1 && card.x+card.width>Math.min(sx,ex)-1);
    const lane=blocked ? Math.max(...cards.map(card=>card.x+card.width))+60+edgeIndex*18 : 0;
    const points=blocked ? [[0,0],[lane-sx,0],[lane-sx,ey-sy],[ex-sx,ey-sy]] : [[0,0],[ex-sx,ey-sy]];
    shapes.push({ type: 'arrow', x:sx, y:sy, points,
      start: { id: start }, end: { id: end }, label: { text: edge.relation, fontSize: 14, fontFamily:2 },
      strokeColor: '#486884', customData: { fireatlas: { documentId, sourceCardIds, kind: 'assistant-diagram-link', relation: edge.relation } } });
  });
  return shapes;
}
