export type Scatter = { name:string; x_column:string; y_column:string; points:{row:number;x:number;y:number}[]; skipped_rows:number; total_rows:number };

/** Normalize before subtracting to keep very large finite values from overflowing. */
export function scatterPosition(values: number[]): number[] {
  const scale=Math.max(...values.map((v)=>Math.abs(v))) || 1;
  const normalized=values.map((v)=>v/scale);
  const low=Math.min(...normalized),high=Math.max(...normalized);
  return normalized.map((v)=>high===low ? 0.5 : (v-low)/(high-low));
}

export function renderScatter(data:Scatter): string {
  if (!data.points.length || data.points.length>5000 || data.points.some((p)=>!Number.isFinite(p.x)||!Number.isFinite(p.y))) throw Error('The plot has invalid data.');
  const canvas=document.createElement('canvas');canvas.width=960;canvas.height=600;
  const ctx=canvas.getContext('2d');if(!ctx)throw Error('Chart drawing is unavailable in this browser.');
  ctx.fillStyle='#ffffff';ctx.fillRect(0,0,960,600);ctx.fillStyle='#183149';ctx.font='bold 24px sans-serif';
  const label=(value:string)=>value.length>48 ? value.slice(0,45)+'…' : value;
  ctx.fillText(label(data.name),70,44);ctx.font='16px sans-serif';ctx.fillText(`${data.points.length} plotted · ${data.skipped_rows} rows skipped`,70,70);
  const left=100,top=100,width=790,height=390;
  ctx.strokeStyle='#dbe3e9';ctx.lineWidth=1;
  for(let i=0;i<=4;i++){const px=left+width*i/4,py=top+height*i/4;ctx.beginPath();ctx.moveTo(px,top);ctx.lineTo(px,top+height);ctx.moveTo(left,py);ctx.lineTo(left+width,py);ctx.stroke();}
  ctx.strokeStyle='#435a6d';ctx.lineWidth=2;ctx.beginPath();ctx.moveTo(left,top);ctx.lineTo(left,top+height);ctx.lineTo(left+width,top+height);ctx.stroke();
  const xs=data.points.map((p)=>p.x),ys=data.points.map((p)=>p.y),xp=scatterPosition(xs),yp=scatterPosition(ys);
  ctx.fillStyle='rgba(36,102,183,0.65)';data.points.forEach((_,i)=>{ctx.beginPath();ctx.arc(left+xp[i]*width,top+(1-yp[i])*height,3.5,0,Math.PI*2);ctx.fill();});
  const number=(n:number)=>Number(n.toPrecision(5)).toString();
  ctx.fillStyle='#40566a';ctx.font='14px sans-serif';ctx.textAlign='center';ctx.fillText(number(Math.min(...xs)),left,top+height+22);ctx.fillText(number(Math.max(...xs)),left+width,top+height+22);
  ctx.textAlign='right';ctx.fillText(number(Math.min(...ys)),left-10,top+height);ctx.fillText(number(Math.max(...ys)),left-10,top+5);
  ctx.fillStyle='#183149';ctx.font='16px sans-serif';ctx.textAlign='center';ctx.fillText(label(data.x_column),left+width/2,top+height+55);
  ctx.save();ctx.translate(25,top+height/2);ctx.rotate(-Math.PI/2);ctx.fillText(label(data.y_column),0,0);ctx.restore();
  ctx.font='13px sans-serif';ctx.fillText('Source: imported CSV · select the table to inspect exact rows',480,585);
  return canvas.toDataURL('image/png');
}
