import type { SourceBinding } from './assistantChallenge';
import { formatClaim } from './formatClaim';

type CardBinding = {documentId:string;cardId?:string;snapshotId:string;snapshotHash:string};
type Claim = {label:string;value:unknown;unit?:string;result_id?:string;path?:string;binding?:CardBinding;source_binding?:SourceBinding};
type Answer = {title?:string;summary?:string;interpretation?:string;claims?:Claim[];limitations?:string[]};

function wrap(text:string,width=58):string {
  return text.split('\n').map(line=>{let current='';const lines:string[]=[];for(const original of line.split(/\s+/).filter(Boolean)){let word=original;while(word.length>width){if(current){lines.push(current);current='';}lines.push(word.slice(0,width));word=word.slice(width);}if(current && current.length+word.length+1>width){lines.push(current);current='';}current+=(current?' ':'')+word;}if(current)lines.push(current);return lines.join('\n');}).join('\n');
}

/** Editable explanation with separately selectable, source-linked claim objects. */
export function explanationElements(answer:Answer,documentId:string,sourceCardIds:string[],base:Record<string,unknown>,x:number,y:number,link:string,originalElementIds:string[]=[]):any[] {
  const elements:any[]=[];let top=y+36;
  const add=(text:string,metadata:Record<string,unknown>,color='#183149',size=18,width=58,gap=16)=>{
    const wrapped=wrap(text,width).trim();if(!wrapped)return;
    elements.push({type:'text',x:x+36,y:top,text:wrapped,fontSize:size,fontFamily:2,strokeColor:color,link,customData:{fireatlas:metadata}});
    top+=Math.max(1,wrapped.split('\n').length)*size*1.4+gap;
  };
  const common={documentId,sourceCardIds,...base,...(originalElementIds.length?{originalElementIds}:{})};
  if(answer.title)add(answer.title,{...common,kind:'assistant-explanation-heading'},'#174f45',24,40,12);
  if(answer.summary || answer.interpretation)add(answer.summary || answer.interpretation || '',{...common,kind:'assistant-explanation'},'#183149',18,58,24);
  const hasClaims=(answer.claims || []).some(claim=>claim && typeof claim.label==='string' && claim.value!==undefined && claim.value!==null);
  if(hasClaims){
    elements.push({type:'text',x:x+36,y:top,text:'SOURCE VALUES',fontSize:13,fontFamily:2,strokeColor:'#52796d',locked:true,customData:{fireatlas:{documentId,kind:'assistant-explanation-decoration'}}});
    top+=30;
  }
  for(const claim of answer.claims || []){
    if(!claim || typeof claim.label!=='string' || claim.value===undefined || claim.value===null)continue;
    const {binding,source_binding,...checked}=claim;
    const linked = binding?.documentId===documentId ? binding : source_binding?.documentId===documentId ? source_binding : base;
    add(formatClaim(claim),{
      ...linked,documentId,sourceCardIds,...(originalElementIds.length?{originalElementIds}:{}),
      kind:'assistant-explanation-claim',claims:[checked],
    },'#286f62',18,58,12);
  }
  if(answer.limitations?.length)add(answer.limitations.join('\n\n'),{...common,kind:'assistant-explanation'});
  if(!elements.length)return elements;
  return [{type:'rectangle',x,y,width:740,height:top-y+18,backgroundColor:'#f4faf6',fillStyle:'solid',strokeColor:'#bbd9cd',strokeWidth:1,roundness:{type:3},locked:true,customData:{fireatlas:{documentId,kind:'assistant-explanation-decoration'}}},...elements];
}
