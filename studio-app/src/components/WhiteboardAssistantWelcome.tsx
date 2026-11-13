import { useRef, useState } from 'react';

/** Keep the companion discoverable before a durable board has been opened. */
export function WhiteboardAssistantWelcome({ ready, boards, status, onStart, onOpen }: {
  ready:boolean; boards:{id:string;title:string}[]; status:string;
  onStart:()=>void; onOpen:(id:string)=>void;
}) {
  const [open,setOpen]=useState(true);
  const launcher=useRef<HTMLButtonElement>(null);
  const close=()=>{setOpen(false);launcher.current?.focus();};
  return <div className="whiteboard-assistant">
    <button ref={launcher} type="button" className="assistant-launcher" aria-expanded={open} aria-controls="investigation-assistant-welcome" onClick={()=>setOpen(value=>!value)}><span className="assistant-orb" aria-hidden="true"><i/><i/></span><span>Ask AI</span></button>
    <span className="assistant-island-hint">Explain · Draw · Challenge</span>
    {open && <section id="investigation-assistant-welcome" className="whiteboard-assistant-panel" aria-label="Meet your investigation companion" onKeyDown={event=>{if(event.key==='Escape'){event.stopPropagation();close();}}}>
      <div className="whiteboard-assistant-heading"><div><span className="assistant-eyebrow">YOUR INVESTIGATION COMPANION</span><strong>Let's make sense of it.</strong></div><button type="button" aria-label="Close assistant" onClick={close}>×</button></div>
      <p>Bring your evidence. Ask a question. Build the explanation together on the board.</p>
      <ol className="assistant-getting-started"><li><strong>Bring evidence in.</strong> Use the Park Fire comparison, or import a CSV or PDF.</li><li><strong>Ask it to draw.</strong> Select evidence and try “Explain and diagram this.”</li><li><strong>Challenge the idea.</strong> Compare another interpretation and open its sources.</li></ol>
      <p>Start or open an investigation to keep your evidence and AI work saved.</p>
      <button type="button" className="assistant-primary" disabled={!ready} onClick={()=>{setOpen(false);onStart();}}>Start an investigation</button>
      {boards.length>0 && <label className="assistant-open-board">Open an investigation<select aria-label="Open an investigation" disabled={!ready} defaultValue="" onChange={event=>{if(event.target.value){setOpen(false);onOpen(event.target.value);}}}><option value="">Choose a saved board</option>{boards.map(board=><option key={board.id} value={board.id}>{board.title}</option>)}</select></label>}
      {!ready && <p role="status">{status || 'Connecting to your local workspace…'}</p>}
    </section>}
  </div>;
}
