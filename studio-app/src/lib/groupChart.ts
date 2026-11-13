import { wrapCardText } from './wrapCardText';
type Group = {group:string|null;rows:number;numeric_count:number;mean:number|null};
type GroupData = {group_column:string;value_column:string;groups:Group[]};
/** Editable horizontal bars share a zero baseline and retain the saved source reference. */
export function groupChart(data:GroupData,ref:Record<string,unknown>,x:number,y:number,unique:()=>string):any[]{
 if(!data || !Array.isArray(data.groups) || !data.groups.length || data.groups.length>30 || data.groups.some(g=>g.mean!==null && !Number.isFinite(g.mean)))throw Error('The grouped chart is unavailable.');
 const values=data.groups.map(g=>g.mean).filter((n):n is number=>n!==null), scale=Math.max(1,...values.map(Math.abs));
 const elements:any[]=[],children:string[]=[];
 const add=(item:any,groupName?:string|null)=>{const id=unique();children.push(id);elements.push({...item,id,customData:{fireatlas:groupName===undefined?ref:{...ref,groupName,groupMetric:'mean'}}});};
 const title=wrapCardText(`Mean ${data.value_column} by ${data.group_column}`,60);
 const subtitleY=y+20+title.split('\n').length*26+4,axisTop=subtitleY+30;
 add({type:'text',x:x+20,y:y+20,text:title,fontSize:20,fontFamily:2});
 add({type:'text',x:x+20,y:subtitleY,text:'Source units unspecified · numeric / all rows',fontSize:14,fontFamily:2});
 const axis=x+500;
 // Keep full category names visible: distinct groups must not collapse to the
 // same shortened label. Wrap words naturally, splitting long identifiers only
 // when necessary to keep them within the label gutter.
 const labels=data.groups.map(g=>wrapCardText(g.group===null?'(blank group)':g.group,20));
 const heights=labels.map(label=>Math.max(36,label.split('\n').length*19+12));
 add({type:'rectangle',x:axis,y:axisTop,width:1,height:heights.reduce((a,b)=>a+b,0),strokeColor:'#9caebc',backgroundColor:'#9caebc',fillStyle:'solid'});
 let offset=0;
 data.groups.forEach((g,i)=>{const yy=axisTop+10+offset;offset+=heights[i];
  add({type:'text',x:x+20,y:yy,text:labels[i],fontSize:14,fontFamily:2},g.group);
  if(g.mean!==null && g.mean!==0){const width=Math.max(1,Math.abs(g.mean/scale)*180);add({type:'rectangle',x:g.mean<0?axis-width:axis,y:yy,width,height:17,strokeColor:'#087b99',backgroundColor:'#087b99',fillStyle:'solid'},g.group);}
  add({type:'text',x:x+710,y:yy,text:`${g.mean===null?'unavailable':String(g.mean)}  (${g.numeric_count}/${g.rows})`,fontSize:14,fontFamily:2},g.group);
 });
 elements.push({id:unique(),type:'frame',name:'Grouped comparison',children,customData:{fireatlas:ref}});return elements;
}
