export type ChallengeSource = { kind:'csv'|'pdf'; name:string; excerpt:string; ref:Record<string,unknown>; location:string };
import { formatClaim } from './formatClaim';
export type SourceBinding = {documentId:string;datasetId?:string;datasetHash?:string;rowOffset?:number;summaryColumn?:string;summaryMetric?:string;groupColumn?:string;valueColumn?:string;groupName?:string|null;groupMetric?:string;sourceDocumentId?:string;sourceDocumentHash?:string;page?:number};
export type ChallengeAnswer = { summary?:string; interpretation?:string; claims?:{label:string;value:unknown;unit?:string;result_id?:string;path?:string;binding?:{documentId:string;cardId?:string;snapshotId:string;snapshotHash:string};source_binding?:SourceBinding}[] };

function wrap(text:string, width=48):string {
  return text.split('\n').map(line=>{
    const lines:string[]=[];let current='';
    for(const word of line.split(/\s+/).filter(Boolean)){
      if(current && current.length+word.length+1>width){lines.push(current);current='';}
      current+=(current?' ':'')+word;
    }
    if(current)lines.push(current);
    return lines.join('\n');
  }).join('\n');
}

/** A reversible native frame, with source-specific references on each excerpt. */
export function assistantChallenge(answer:ChallengeAnswer, documentId:string, originalIds:string[], originalRef:Record<string,unknown>, sources:ChallengeSource[], x:number, y:number, unique:()=>string):any[] {
  if(!originalIds.length)throw Error('Select a finding to challenge.');
  const elements:any[]=[],children:string[]=[];
  let top=y+24;
  const base={documentId,...originalRef,kind:'assistant-challenge',originalElementIds:originalIds};
  const add=(text:string,meta:Record<string,unknown>,size=16,color='#183149')=>{
    const id=unique(),wrapped=wrap(text);children.push(id);
    elements.push({id,type:'text',x:x+24,y:top,text:wrapped,fontSize:size,fontFamily:2,strokeColor:color,customData:{fireatlas:meta}});
    top+=Math.max(1,wrapped.split('\n').length)*size*1.35+16;
  };
  add('Alternative interpretation',base,20);
  const claims=(answer.claims || []).filter(c=>c && typeof c.label==='string' && c.value!==undefined && c.value!==null).slice(0,8);
  const summary=String(answer.summary || answer.interpretation || '').trim();
  const boundSources=originalRef.sourceBindings;
  const linkedSources=Array.isArray(boundSources) && boundSources.length>0 && boundSources.every(source=>source && source.documentId===documentId && typeof source.snapshotId==='string' && typeof source.snapshotHash==='string');
  const linkedOriginal=linkedSources ||(typeof originalRef.snapshotId==='string' && typeof originalRef.snapshotHash==='string') ||
    (typeof originalRef.datasetId==='string' && typeof originalRef.datasetHash==='string') ||
    (typeof originalRef.sourceDocumentId==='string' && typeof originalRef.sourceDocumentHash==='string');
  if(claims.length || sources.length || linkedOriginal){
    if(summary)add(`${summary.endsWith('?')?'Open question':'AI interpretation'}\n${summary}`,base);
    for(const claim of claims){
      const {binding,source_binding,...checked}=claim;
      add(formatClaim(claim),{documentId,...(binding?.documentId===documentId?binding:{}),...(source_binding?.documentId===documentId?source_binding:{}),kind:'assistant-challenge-claim',originalElementIds:originalIds,claims:[checked]},14);
    }
  }else{
    add(`Open question\n${summary.endsWith('?') ? summary : 'What additional evidence could challenge this finding?'}`,base);
  }
  sources.slice(0,2).forEach(source=>add(`Retrieved source · ${source.name} · ${source.location}\n${source.excerpt.slice(0,400)}`,
    {documentId,...source.ref,kind:'assistant-challenge-source',originalElementIds:originalIds},14));
  elements.push({id:unique(),type:'frame',name:'Challenge',children,customData:{fireatlas:base}});
  return elements;
}
