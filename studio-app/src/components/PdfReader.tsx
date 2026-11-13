import { useEffect, useRef, useState } from 'react';
import { GlobalWorkerOptions, getDocument, type PDFDocumentProxy } from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

GlobalWorkerOptions.workerSrc = workerUrl;
export type PdfSource = { id:string; name:string; sha256:string; bytes:number; data:Uint8Array; initialPage?:number };

export async function validatePdf(bytes: Uint8Array): Promise<number> {
  if (!bytes.length || bytes.length > 10 * 1024 * 1024) throw Error('Choose a PDF up to 10 MiB.');
  const task = getDocument({ data: bytes.slice(), isEvalSupported: false, useSystemFonts: true });
  try {
    const pdf = await task.promise;
    if (pdf.numPages > 20) throw Error('Choose a PDF with at most 20 pages.');
    return pdf.numPages;
  } finally { await task.destroy(); }
}

export function PdfReader({ source, downloadUrl, onClose, onPlace }: { source:PdfSource; downloadUrl:string; onClose:()=>void; onPlace:(page:number, image:string, excerpt?:string, width?:number, height?:number)=>void }) {
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(0);
  const [text, setText] = useState('');
  const [error, setError] = useState('');
  const [image, setImage] = useState('');
  const [dimensions, setDimensions] = useState({width:1,height:1});
  const [pdf, setPdf] = useState<PDFDocumentProxy|null>(null);
  const textRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let active = true;
    setPage(source.initialPage || 1); setPdf(null); setError(''); setText(''); setImage('');
    const task = getDocument({data:source.data.slice(),isEvalSupported:false,useSystemFonts:true});
    task.promise.then((doc)=>{if (!active) return; if(doc.numPages>20) {setError('This PDF exceeds the 20-page limit.');return;} setPage(Math.max(1,Math.min(source.initialPage || 1,doc.numPages))); setPages(doc.numPages); setPdf(doc);}).catch(()=>{if(active)setError('This PDF could not be opened.');});
    return ()=>{active=false;void task.destroy();};
  },[source]);
  useEffect(()=>{
    if(!pdf)return;
    let active=true;setImage('');setText('');setError('');
    void (async()=>{
      try {
        const item=await pdf.getPage(page);const view=item.getViewport({scale:1});
        const scale=Math.min(1.2,1200/Math.max(view.width,view.height));
        const viewport=item.getViewport({scale});const canvas=document.createElement('canvas');
        canvas.width=Math.ceil(viewport.width);canvas.height=Math.ceil(viewport.height);
        const context=canvas.getContext('2d');if(!context)throw Error('Cannot render this page.');
        await item.render({canvasContext:context,viewport}).promise;
        const content=await item.getTextContent();
        if(!active)return;
        setImage(canvas.toDataURL('image/png'));
        setDimensions({width:canvas.width,height:canvas.height});
        setText(content.items.map((entry)=>'str' in entry ? entry.str : '').join(' ').trim());
      } catch {if(active)setError('This page could not be displayed.');}
    })();
    return ()=>{active=false;};
  },[pdf,page]);
  const addExcerpt=()=>{
    const selected=window.getSelection();
    if(!selected || !textRef.current?.contains(selected.anchorNode) || !textRef.current.contains(selected.focusNode)) {setError('Select text from this page first.');return;}
    const excerpt=selected.toString().trim();
    if(!excerpt || excerpt.length>1200){setError('Select an excerpt of up to 1,200 characters.');return;}
    onPlace(page,image,excerpt);
  };
  const changePage=(next:number)=>{setImage('');setText('');setError('');setPage(next);};
  return <section className="whiteboard-pdf" aria-label="Document reader">
    <div className="whiteboard-pdf-heading"><strong>{source.name}</strong><button onClick={onClose}>Close</button></div>
    <div><button disabled={page<=1} onClick={()=>changePage(page-1)}>Previous page</button> <span>Page {page} of {pages || '…'}</span> <button disabled={!pages || page>=pages} onClick={()=>changePage(page+1)}>Next page</button> <a href={downloadUrl}>Download PDF</a></div>
    {error && <p role="alert">{error}</p>}
    {image ? <img src={image} alt={`Page ${page} of ${source.name}`} /> : <p>Opening page…</p>}
    <button disabled={!image} onClick={()=>onPlace(page,image,undefined,dimensions.width,dimensions.height)}>Add page to board</button>
    <button disabled={!text} onClick={addExcerpt}>Add selected excerpt</button>
    <h3>Page text</h3><div ref={textRef} className="whiteboard-pdf-text">{text || 'No selectable text on this page.'}</div>
  </section>;
}
