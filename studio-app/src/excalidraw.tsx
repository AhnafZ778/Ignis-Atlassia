import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Excalidraw, restoreElements, serializeAsJSON } from '@excalidraw/excalidraw';
import type { ExcalidrawImperativeAPI } from '@excalidraw/excalidraw/types';
import '@excalidraw/excalidraw/index.css';

function Continuation() {
  const [editor, setEditor] = useState<ExcalidrawImperativeAPI | null>(null);
  if (editor) (window as any).FireAtlasExcalidraw = editor;
  const [status, setStatus] = useState('Choose an exported .excalidraw scene. Edits here change the portable diagram; FireAtlas scientific receipts remain frozen.');
  const [ready, setReady] = useState(false);
  const load = async (file?: File) => {
    if (!file || !editor) return;
    try {
      if (file.size > 128 * 1024 ** 2) throw Error('Scene exceeds the 128 MiB editor limit. Export a frame or selection.');
      const scene = JSON.parse(await file.text());
      if (scene.type !== 'excalidraw' || scene.version !== 2 || !Array.isArray(scene.elements) || scene.elements.length > 8192) throw Error('Choose a valid bounded Excalidraw scene.');
      const files = Object.values(scene.files || {}) as any[];
      if (files.some((f) => !/^data:image\/(png|jpeg|webp|svg\+xml);base64,/.test(f.dataURL) || f.dataURL.length > 44 * 1024 ** 2)) throw Error('Images must be bounded embedded files. External asset URLs are unavailable.');
      for (const file of files) if (file.dataURL.startsWith('data:image/svg+xml;')) {
        const xml = new DOMParser().parseFromString(atob(file.dataURL.split(',')[1]), 'image/svg+xml');
        if (xml.querySelector('parsererror,script,foreignObject,iframe,object,embed') || [...xml.querySelectorAll('*')].some((e) => [...e.attributes].some((a) => a.name.startsWith('on') || (['href','xlink:href'].includes(a.name) && !a.value.startsWith('#') && !a.value.startsWith('data:image/'))))) throw Error('Embedded SVG must contain a standalone inert figure.');
      }
      const elements = restoreElements(scene.elements, null);
      const ids = new Set(elements.map((e) => e.id));
      for (const element of elements) if ((element as any).startBinding && !ids.has((element as any).startBinding.elementId) || (element as any).endBinding && !ids.has((element as any).endBinding.elementId)) throw Error('A connector references an absent object.');
      editor.resetScene(); editor.addFiles(files); editor.updateScene({ elements, appState: { viewBackgroundColor: '#fbf7ef' } }); editor.scrollToContent(elements, { fitToContent: true });
      setReady(true); setStatus(`${elements.length} editable objects loaded. Move a map, edit its caption, reconnect an arrow or add an annotation, then save and reopen.`);
    } catch (e) { setStatus((e as Error).message); }
  };
  const save = () => {
    if (!editor) return;
    const json = serializeAsJSON(editor.getSceneElements(), editor.getAppState(), editor.getFiles(), 'local');
    const href = URL.createObjectURL(new Blob([json], { type: 'application/json' }));
    const anchor = document.createElement('a'); anchor.href = href; anchor.download = 'fireatlas-edited.excalidraw'; anchor.click(); setTimeout(() => URL.revokeObjectURL(href), 1000);
    setStatus('Editable scene saved. Reopen this file to continue editing.');
  };
  return <><header style={{ padding: 16, fontFamily: 'sans-serif', background: '#fbf7ef', color: '#183b42' }}><a href="./studio.html">Return to Research Studio</a><h1>Editable whiteboard continuation</h1><label>Open Excalidraw scene <input aria-label="Open Excalidraw scene" type="file" accept=".excalidraw,.json" disabled={!editor} onChange={(e) => void load(e.target.files?.[0])} /></label><button disabled={!ready} onClick={save}>Save edited scene</button><p role="status">{status}</p></header><div style={{ height: 'calc(100vh - 205px)', minHeight: 400 }}><Excalidraw excalidrawAPI={setEditor} UIOptions={{ canvasActions: { loadScene: false } }} /></div></>;
}
createRoot(document.getElementById('excalidraw-root')!).render(<Continuation />);
