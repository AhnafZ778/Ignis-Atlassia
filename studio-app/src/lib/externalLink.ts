import { wrapCardText } from './wrapCardText';

/** A user-supplied web reference; creating it never fetches the address. */
export function externalLinkCard(address:string,title:string,documentId:string|null,x:number,y:number) {
  let url:URL;
  try { url=new URL(address.trim()); } catch { throw Error('Enter a complete web address beginning with https:// or http://.'); }
  if(!['http:','https:'].includes(url.protocol) || url.username || url.password) throw Error('Use an http or https address without embedded credentials.');
  if(url.href.length>2048)throw Error('That web address is too long.');
  const name=title.trim().replace(/\s+/g,' ') || url.hostname;
  if(name.length>120)throw Error('Keep the link title under 120 characters.');
  const label=wrapCardText(`${name}\n${url.hostname}`,30);
  return {type:'rectangle' as const,x,y,width:440,height:Math.max(120,44+label.split('\n').length*24),
    backgroundColor:'#edf7f1',fillStyle:'solid' as const,strokeColor:'#4b806e',roundness:{type:3 as const},
    label:{text:label,fontSize:18,fontFamily:2 as const},link:url.href,
    customData:{fireatlas:{...(documentId?{documentId}:{}),kind:'external-link'}}};
}
