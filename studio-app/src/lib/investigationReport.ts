/** Build a standalone, non-executable HTML report from local board content. */
export type ReportSource = { name:string; sha256:string; kind:'csv'|'pdf'|'evidence'; bytes:Uint8Array };
const escapeHtml=(value:string)=>value.replace(/[&<>"']/g,(c)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));

export function sanitizeFigure(svg:SVGSVGElement):string {
  const copy=svg.cloneNode(true) as SVGSVGElement;
  copy.querySelectorAll('script,foreignObject,iframe,object,embed,style').forEach((node)=>node.remove());
  // XMLSerializer supplies the root namespace. An unqualified xmlns written by
  // an SVG exporter can otherwise produce duplicate attributes in strict XML.
  copy.removeAttribute('xmlns');
  const nodes=[copy,...copy.querySelectorAll('*')];
  for(const node of nodes)for(const attr of [...node.attributes]){
    // SVG presentation attributes are unqualified. Normalize exporter-created
    // SVG-namespaced attributes before applying the same safety checks below.
    if(attr.namespaceURI==='http://www.w3.org/2000/svg'){
      node.removeAttributeNS(attr.namespaceURI,attr.localName);
      node.setAttribute(attr.localName,attr.value);
    }
  }
  for(const node of nodes)for(const attr of [...node.attributes]){
    const key=attr.name.toLowerCase(),value=attr.value.trim();
    if(key.startsWith('on') || key==='style' || ((key==='href'||key==='xlink:href') && !/^#/.test(value) && !/^data:image\/(png|jpeg|webp);base64,/i.test(value)) || (/url\s*\(/i.test(value) && !/^url\(#[A-Za-z0-9_-]+\)$/.test(value)))node.removeAttribute(attr.name);
  }
  return new XMLSerializer().serializeToString(copy);
}

/** CSV input has already passed the server's strict UTF-8 and rectangular checks. */
export function parseCsv(text:string):string[][] {
  text=text.replace(/^\uFEFF/,'');const rows:string[][]=[];let row:string[]=[],cell='',quoted=false,closed=false;
  for(let i=0;i<text.length;i++){
    const c=text[i];
    if(quoted){if(c==='"'){if(text[i+1]==='"'){cell+='"';i++;}else{quoted=false;closed=true;}}else cell+=c;continue;}
    if(closed && c!==',' && c!=='\r' && c!=='\n')throw Error('The table could not be read for this report.');
    if(c==='"' && cell===''){quoted=true;continue;}
    if(c===','){row.push(cell);cell='';closed=false;continue;}
    if(c==='\n' || c==='\r'){if(c==='\r' && text[i+1]==='\n')i++;row.push(cell);rows.push(row);row=[];cell='';closed=false;continue;}
    cell+=c;
  }
  if(quoted)throw Error('The table could not be read for this report.');
  if(row.length || cell || closed){row.push(cell);rows.push(row);}
  return rows;
}

function dataUri(bytes:Uint8Array,mime:string):string {
  let binary='';for(let offset=0;offset<bytes.length;offset+=32768)binary+=String.fromCharCode(...bytes.subarray(offset,offset+32768));
  return `data:${mime};base64,${btoa(binary)}`;
}

export function buildReport(title:string,figure:string,notes:string[],sources:ReportSource[]):string {
  const sections=sources.map((source,index)=>{
    const mime=source.kind==='csv'?'text/csv':source.kind==='pdf'?'application/pdf':'application/json';
    const download=`<a download="${escapeHtml(source.name)}" href="${dataUri(source.bytes,mime)}">Download original ${source.kind==='evidence'?'evidence':source.kind.toUpperCase()}</a>`;
    let table='';
    if(source.kind==='csv'){
      const rows=parseCsv(new TextDecoder('utf-8',{fatal:true}).decode(source.bytes));
      const columns=rows[0]?.length || 0;const shown=columns && rows.length*columns>30000 ? rows.slice(0,101) : rows;
      const cells=(row:string[],tag:string)=>'<tr>'+row.map(value=>`<${tag}>${escapeHtml(value)}</${tag}>`).join('')+'</tr>';
      table=`${shown.length<rows.length?'<p>First 100 rows shown; download the original CSV for the complete table.</p>':''}<div class="table-scroll"><table>${shown.length?`<thead>${cells(shown[0],'th')}</thead><tbody>${shown.slice(1).map(row=>cells(row,'td')).join('')}</tbody>`:''}</table></div>`;
    }else if(source.kind==='evidence'){
      const text=new TextDecoder('utf-8',{fatal:true}).decode(source.bytes);
      const preview=text.slice(0,100_000);
      table=`<details><summary>View evidence data</summary>${preview.length<text.length?'<p>Preview shortened; download the evidence for the complete data.</p>':''}<pre>${escapeHtml(preview)}</pre></details>`;
    }
    return `<section><h3>${index+1}. ${escapeHtml(source.name)}</h3><p>SHA-256: <code>${escapeHtml(source.sha256)}</code></p><p>${download}</p>${table}</section>`;
  }).join('');
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline';"><title>${escapeHtml(title)}</title><style>body{font:16px/1.5 system-ui,sans-serif;color:#1a3145;max-width:1100px;padding:24px;margin:auto}h1,h2{line-height:1.2}figure{margin:0;border:1px solid #d8e1e7;padding:12px}figure svg{width:100%;height:auto}section{margin:24px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f6f8;padding:12px}.table-scroll{overflow:auto;max-height:36rem}table{border-collapse:collapse;font-size:14px}th,td{border:1px solid #cbd6df;padding:6px 10px;text-align:left;vertical-align:top}code{overflow-wrap:anywhere}@media print{.table-scroll{max-height:none}}</style></head><body><header><h1>${escapeHtml(title)}</h1><p>Investigation whiteboard export</p></header><h2>Selected figure</h2><figure>${figure}</figure>${notes.length?`<section><h2>Board notes</h2>${notes.map(note=>`<pre>${escapeHtml(note)}</pre>`).join('')}</section>`:''}<section><h2>Sources and exact tables</h2>${sections || '<p>No linked sources in this selection.</p>'}</section></body></html>`;
}
