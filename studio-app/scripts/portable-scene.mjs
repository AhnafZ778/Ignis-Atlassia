/** Conversion shared by the pinned SDK worker and browser acceptance tests. */
const wrap=(text,width)=>String(text||'').split('\n').flatMap(line=>{const rows=[];let current='';for(const word of line.split(/\s+/)){if((current+' '+word).length>width&&current){rows.push(current);current=word;}else current+=(current?' ':'')+word;}rows.push(current);return rows;}).join('\n');
export function sceneSkeletons(ir) {
  const elements=[],files={},mapping={},id=(key,role)=>`${key}-${role}`;
  for(const frame of ir.frames||[])elements.push({type:'frame',children:[],id:frame.id,name:frame.title,x:frame.x,y:frame.y,width:frame.w,height:frame.h});
  for(const object of ir.objects) {
    const ids=[],t=object.transform,angle=(t.rotation||0)*Math.PI/180,groupId=id(object.id,'group'),shape=id(object.id,'shape');ids.push(shape);
    const captionText=wrap(object.caption||object.text||'',Math.max(16,Math.floor((t.w-28)/7))),captionHeight=captionText.split('\n').length*16;
    const imageHeight=object.image?Math.max(48,t.h-captionHeight-72):0,height=Math.max(t.h,captionHeight+72+imageHeight);
    const rotate=(x,y,w,h)=>{const cx=t.x+t.w/2,cy=t.y+height/2,dx=x+w/2-cx,dy=y+h/2-cy;return {x:cx+Math.cos(angle)*dx-Math.sin(angle)*dy-w/2,y:cy+Math.sin(angle)*dx+Math.cos(angle)*dy-h/2,angle};};
    elements.push({type:'rectangle',id:shape,x:t.x,y:t.y,width:t.w,height,angle,backgroundColor:'#fffdf7',strokeColor:'#cbbd9e',fillStyle:'solid',roundness:{type:3},groupIds:[groupId],frameId:object.frame_id||null});
    const title=id(object.id,'title');ids.push(title);
    elements.push({type:'text',id:title,...rotate(t.x+14,t.y+12,t.w-28,24),text:wrap(object.title,Math.max(12,Math.floor((t.w-28)/10))),fontSize:18,fontFamily:2,strokeColor:'#183b42',groupIds:[groupId],frameId:object.frame_id||null});
    if(object.image) {
      const fileId=object.image.sha256,imageId=id(object.id,'image');ids.push(imageId);
      files[fileId]={id:fileId,mimeType:object.image.mime,dataURL:object.image.data_url,created:ir.created_ms,lastRetrieved:ir.created_ms};
      elements.push({type:'image',id:imageId,fileId,...rotate(t.x+12,t.y+48,t.w-24,imageHeight),width:t.w-24,height:imageHeight,status:'saved',scale:[1,1],groupIds:[groupId],frameId:object.frame_id||null});
    }
    const caption=id(object.id,'caption');ids.push(caption);
    elements.push({type:'text',id:caption,...rotate(t.x+14,t.y+48+(object.image?imageHeight+12:0),t.w-28,captionHeight),text:captionText,fontSize:12,fontFamily:2,strokeColor:'#45636b',groupIds:[groupId],frameId:object.frame_id||null});
    if(object.frame_id)elements.find(e=>e.type==='frame'&&e.id===object.frame_id)?.children.push(...ids);
    mapping[object.id]={elements:ids,result_refs:object.result_refs||[],conversion:object.image?'embedded preview with editable caption':'native editable text and shape'};
  }
  const byId=new Map(ir.objects.map(o=>[o.id,o]));
  for(const link of ir.connectors) {
    const a=byId.get(link.source),b=byId.get(link.target);if(!a||!b)continue;
    const x=a.transform.x+a.transform.w/2,y=a.transform.y+a.transform.h/2;
    elements.push({type:'arrow',id:link.id,x,y,points:[[0,0],[b.transform.x+b.transform.w/2-x,b.transform.y+b.transform.h/2-y]],start:{id:id(a.id,'shape')},end:{id:id(b.id,'shape')},strokeColor:'#47758d',endArrowhead:'arrow'});
    mapping[link.id]={elements:[link.id],conversion:'bound arrow'};
  }
  return {elements,files,mapping};
}
