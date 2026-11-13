import { useEffect, useRef, useState } from 'react';
import type { ExcalidrawImperativeAPI } from '@excalidraw/excalidraw/types';
import { restoreElements, serializeAsJSON } from '@excalidraw/excalidraw';
import { api } from '../api';
import type { DocumentView } from '../types';
import { sceneChanges, sceneObjects, type Scene, type SceneObject } from './whiteboard';
import { readBoardViewport, saveBoardViewport, type BoardViewport } from './boardViewport';

type BoardSummary = { id: string; title: string };
const draftPrefix = (id: string) => `fireatlas-whiteboard-draft:${id}`;
const selectedKey = 'fireatlas-investigation-active-board';
const draftFullWarning = 'Browser draft is full; keep this tab open until saved.';

/** Keeps the existing freehand editor intact while attaching it to a Studio document. */
export function useInvestigationBoard(editor: ExcalidrawImperativeAPI | null) {
  const [boards, setBoards] = useState<BoardSummary[]>([]);
  const [document, setDocument] = useState<DocumentView | null>(null);
  const [available, setAvailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState('');
  const [recoveryDrafts, setRecoveryDrafts] = useState<{ key: string; savedAt: number; baseRevision: number | null }[]>([]);
  const [conflict, setConflict] = useState(false);
  const [historyNeedsReload, setHistoryNeedsReload] = useState(false);
  const instance = useRef(crypto.randomUUID());
  const current = useRef<DocumentView | null>(null);
  const saved = useRef<Map<string, SceneObject>>(new Map());
  const pending = useRef<Scene | null>(null);
  const sealed = useRef<Scene[]>([]);
  const pointerActive = useRef(false);
  const editingText = useRef(false);
  const pointerEpoch = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inFlight = useRef<Promise<boolean> | null>(null);
  const loading = useRef(false);
  const epoch = useRef(0);
  const historyLocked = useRef(false);

  const storeDraft = (id: string, scene: Scene) => {
    try { localStorage.setItem(`${draftPrefix(id)}:${instance.current}`, JSON.stringify({ savedAt: Date.now(), baseRevision: current.current?.revision ?? null, scene })); return true; }
    catch { return false; }
  };

  const flush = async (force = true): Promise<boolean> => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null; }
    if (inFlight.current) {
      if (!(await inFlight.current)) return false;
      return flush(force);
    }
    const doc = current.current;
    if (!doc) return true;
    if (!sealed.current.length && (pointerActive.current || editingText.current)) return !force;
    const snapshot = sealed.current.shift() || pending.current;
    if (!snapshot) {
      if (!conflict && !historyNeedsReload) setStatus(previous => previous === draftFullWarning ? 'Saved' : previous);
      return true;
    }
    const next = sceneObjects(snapshot);
    const changes = sceneChanges(saved.current, next);
    if (!changes.length) {
      if (pending.current === snapshot) pending.current = null;
      if (sealed.current.length || pending.current) return flush(force);
      try { localStorage.removeItem(`${draftPrefix(doc.id)}:${instance.current}`); } catch { /* The server is authoritative. */ }
      setStatus('Saved');return true;
    }
    if (changes.length > 500) { if(pending.current!==snapshot)sealed.current.unshift(snapshot);setStatus('Too many changes at once. Export your board to keep a copy.'); return false; }
    if (pending.current === snapshot) pending.current = null;
    setStatus('Saving…');
    const run = (async () => {
      try {
        // A disjoint server merge would advance our revision without updating the
        // canvas with the other tab's changes. Fail closed until we can reconcile.
        const result = await api.transact(doc.id, doc.revision, [{ op: 'patch_whiteboard', changes }]);
        if (current.current?.id !== doc.id) return false;
        current.current = result;
        setConflict(false);
        setDocument(result);
        saved.current = next;
        if (!pending.current && !sealed.current.length) {
          try { localStorage.removeItem(`${draftPrefix(doc.id)}:${instance.current}`); } catch { /* Keep a recoverable draft. */ }
          setStatus('Saved');
        } else {
          setStatus('Saving…');
        }
        return true;
      } catch (error) {
        sealed.current.unshift(snapshot);
        const stale = (error as { status?: number }).status === 409;
        setConflict(stale);
        setStatus(stale ? 'This board changed elsewhere. Save your drawing as a new board; its evidence stays in the original.' : (error as Error).message + ' Your draft is kept in this browser when space permits.');
        return false;
      }
    })();
    inFlight.current = run;
    const ok = await run;
    if (inFlight.current === run) inFlight.current = null;
    if (ok && (sealed.current.length || pending.current)) return flush(force);
    return ok;
  };

  const open = async (id: string): Promise<boolean> => {
    if (!editor || !id || !(await flush())) return false;
    const request = ++epoch.current;
    loading.current = true;
    setBusy(true);
    try {
      const result = await api.getWhiteboard(id);
      if (request !== epoch.current) return false;
      const scene: Scene = { elements: result.elements, files: result.files };
      saved.current = sceneObjects(scene);
      sealed.current=[];pending.current=null;pointerActive.current=false;editingText.current=false;pointerEpoch.current++;
      current.current = result.document;
      setConflict(false);
      setHistoryNeedsReload(false);
      setDocument(result.document);
      editor.resetScene();
      editor.addFiles(Object.values(result.files));
      const viewport=readBoardViewport(id);
      editor.updateScene({ elements: restoreElements(result.elements, null), appState: { viewBackgroundColor: '#fbf7ef' } });
      if(viewport){const zoom=editor.getAppState().zoom;editor.updateScene({appState:{scrollX:viewport.scrollX,scrollY:viewport.scrollY,zoom:{...zoom,value:viewport.zoom.value as typeof zoom.value}}});}
      if (result.elements.length && !viewport) editor.scrollToContent(undefined, { fitToContent: true, minZoom: .4 });
      try {
        localStorage.setItem(selectedKey, id);
        const prefix = draftPrefix(id);
        const keys = Object.keys(localStorage).filter((key) => key === prefix || key.startsWith(prefix + ':'));
        const drafts = keys.flatMap((key) => {
          try {
            const draft = JSON.parse(localStorage.getItem(key) || '{}');
            const scene = draft.scene || draft;
            if (!Array.isArray(scene.elements) || !scene.files || !sceneChanges(saved.current, sceneObjects(scene)).length) return [];
            return [{ key, savedAt: Number(draft.savedAt) || 0, baseRevision: Number.isInteger(draft.baseRevision) ? draft.baseRevision : null }];
          } catch { return []; }
        }).sort((a, b) => b.savedAt - a.savedAt);
        setRecoveryDrafts(drafts);
        sessionStorage.setItem('fireatlas-studio-board', id);
      } catch { setRecoveryDrafts([]); }
      const url = new URL(location.href); url.searchParams.set('board', id); history.replaceState(null, '', url);
      // Excalidraw normalizes restored shapes and frame ordering. Capture that
      // rendered baseline before enabling saves, so opening a board never
      // creates a phantom transaction that consumes the next Undo.
      await new Promise<void>((resolve)=>setTimeout(resolve,150));
      if(request!==epoch.current)return false;
      const normalized=JSON.parse(serializeAsJSON(editor.getSceneElements(),editor.getAppState(),editor.getFiles(),'local')) as Scene;
      saved.current=sceneObjects(normalized);editor.history.clear();
      setStatus('Saved');
      return true;
    } catch (error) {
      setStatus((error as Error).message);
      return false;
    } finally {
      if (request === epoch.current) setTimeout(() => { loading.current = false; setBusy(false); }, 0);
    }
  };

  useEffect(() => {
    if (!editor) return;
    let active = true;
    void (async () => {
      try {
        await api.ensurePrincipal();
        const listed = await api.listDocuments();
        if (!active) return;
        setAvailable(true); setBoards(listed.documents);
        let id = new URL(location.href).searchParams.get('board');
        try { id ||= localStorage.getItem(selectedKey); } catch { /* Browser storage is optional. */ }
        if (id && listed.documents.some((item) => item.id === id)) await open(id);
      } catch { if (active) setAvailable(false); }
    })();
    return () => { active = false; epoch.current += 1; if (timer.current) clearTimeout(timer.current); };
  }, [editor]);

  const onScene = (scene: Scene, textEditing = false, viewport?:BoardViewport) => {
    if (loading.current || historyLocked.current || !current.current) return;
    if(viewport)saveBoardViewport(current.current.id,viewport);
    const wasEditing=editingText.current;
    // Camera/focus updates do not need a second copy of the entire drawing.
    // Retain queued edits and text-edit transitions even if their final scene
    // currently matches the saved baseline.
    if (!wasEditing && !textEditing && !pending.current && !sealed.current.length && !inFlight.current &&
        !sceneChanges(saved.current,sceneObjects(scene)).length) {
      setStatus(previous => previous === draftFullWarning ? 'Saved' : previous);
      return;
    }
    if(!wasEditing && textEditing && pending.current){sealed.current.push(pending.current);pending.current=null;}
    editingText.current=textEditing;
    pending.current = scene;
    if (!storeDraft(current.current.id, scene)) setStatus(draftFullWarning);
    if (timer.current) clearTimeout(timer.current);
    if(wasEditing && !textEditing){sealed.current.push(scene);pending.current=null;void flush(false);}
    else if (!pointerActive.current && !textEditing) timer.current = setTimeout(() => { void flush(false); }, 800);
  };

  const sealGesture = () => {
    if (pending.current && !editingText.current) { sealed.current.push(pending.current); pending.current=null; }
    if (sealed.current.length) void flush(false);
  };
  const onPointerDown = () => {
    if (!current.current || loading.current || historyLocked.current) return;
    // Close any previous gesture before this one can modify the scene.
    sealGesture();pointerActive.current=true;pointerEpoch.current++;
    if(timer.current){clearTimeout(timer.current);timer.current=null;}
  };
  const onPointerUp = () => {
    if (!current.current || loading.current || historyLocked.current)return;
    pointerActive.current=false;const sequence=pointerEpoch.current;
    // Excalidraw reports the final scene asynchronously after pointer release.
    setTimeout(()=>{if(!pointerActive.current && pointerEpoch.current===sequence)sealGesture();},0);
  };

  const refreshAfterHistory = async (id:string) => {
    if (!editor || current.current?.id !== id) throw Error('The investigation changed.');
    const result=await api.getWhiteboard(id);
    if (current.current?.id!==id) throw Error('The investigation changed.');
    const scene:Scene={elements:result.elements,files:result.files};
    const {scrollX,scrollY,zoom}=editor.getAppState();
    loading.current=true;
    editor.resetScene();editor.addFiles(Object.values(result.files));
    editor.updateScene({elements:restoreElements(result.elements,null),appState:{viewBackgroundColor:'#fbf7ef',scrollX,scrollY,zoom}});
    saved.current=sceneObjects(scene);pending.current=null;sealed.current=[];current.current=result.document;
    setDocument(result.document);setBoards((list)=>list.map((item)=>item.id===id?{...item,title:result.document.title}:item));
    setHistoryNeedsReload(false);setConflict(false);
    // Ignore Excalidraw's asynchronous onChange until its replacement scene settles.
    await new Promise<void>((resolve)=>setTimeout(resolve,150));
    // Excalidraw normalizes restored elements. Treat its rendered scene as the
    // local baseline so that normalization does not create a new undo step.
    const normalized=JSON.parse(serializeAsJSON(editor.getSceneElements(),editor.getAppState(),editor.getFiles(),'local')) as Scene;
    saved.current=sceneObjects(normalized);
    editor.history.clear();
    loading.current=false;
  };

  const historyAction = async (direction:'undo'|'redo') => {
    const id=current.current?.id;
    if(!id || historyLocked.current || historyNeedsReload)return;
    historyLocked.current=true;setBusy(true);
    let requested=false,committed=false;
    try {
      if(!(await flush()))return;
      if(current.current?.id!==id)throw Error('The investigation changed.');
      requested=true;await api[direction](id);committed=true;
      await refreshAfterHistory(id);
      setStatus(direction==='undo'?'Undone':'Redone');
    } catch(error) {
      const status=(error as {status?:number}).status;
      if(committed || (requested && (status===undefined || status===0 || status>=500))){setHistoryNeedsReload(true);setStatus('The history result is uncertain. Reload the board to continue.');}
      else setStatus((error as Error).message);
    } finally {loading.current=false;historyLocked.current=false;setBusy(false);}
  };

  const retryHistoryReload = async () => {
    const id=current.current?.id;if(!id || historyLocked.current)return;
    historyLocked.current=true;setBusy(true);
    try{await refreshAfterHistory(id);setStatus('Saved');}
    catch(error){setStatus((error as Error).message);}
    finally{loading.current=false;historyLocked.current=false;setBusy(false);}
  };

  const create = async (title: string) => {
    if (!(await flush())) return;
    setBusy(true);
    try {
      const created = await api.createDocument(title);
      setBoards((list) => [{ id: created.id, title: created.title }, ...list]);
      await open(created.id);
    } catch (error) { setStatus((error as Error).message); setBusy(false); }
  };

  const rename = async (title: string) => {
    if (!(await flush()) || !current.current) return;
    try {
      const updated = await api.transact(current.current.id, current.current.revision, [{ op: 'set_title', title }]);
      current.current = updated; setDocument(updated);
      setBoards((list) => list.map((item) => item.id === updated.id ? { ...item, title: updated.title } : item));
      setStatus('Saved');
    } catch (error) { setStatus((error as Error).message); }
  };

  const restorePackage = async (file: File) => {
    if (!(await flush())) throw Error('Save the current drawing before restoring a package.');
    setBusy(true);
    let opened = false;
    try {
      const restored = await api.restoreArchive(file);
      setBoards((list) => [{ id: restored.document.id, title: restored.document.title }, ...list]);
      opened = await open(restored.document.id);
      if (!opened) throw Error('The package was restored, but the board could not be opened. Choose it from the board list.');
    } finally { if (!opened) setBusy(false); }
  };

  const recoverAccess = async (token: string) => {
    if (timer.current) { clearTimeout(timer.current); timer.current = null; }
    if (inFlight.current) await inFlight.current;
    const latestDraft=pending.current || sealed.current[sealed.current.length-1];
    if (current.current && latestDraft && !storeDraft(current.current.id, latestDraft)) {
      throw Error('The browser cannot store this draft. Export the drawing, then reload before recovering access.');
    }
    setBusy(true);
    try {
      await api.recover(token);
      // The previous principal's drawing must not remain on a blank canvas
      // after the browser switches to a different Studio identity.
      loading.current = true;
      epoch.current += 1;
      editor?.resetScene();
      editor?.history.clear();
      pointerActive.current=false;editingText.current=false;pointerEpoch.current++;
      current.current = null; saved.current = new Map(); pending.current = null; sealed.current=[];
      setDocument(null); setBoards([]); setRecoveryDrafts([]); setConflict(false);
      try { localStorage.removeItem(selectedKey); sessionStorage.removeItem('fireatlas-studio-board'); } catch { /* Access is restored. */ }
      const url = new URL(location.href); url.searchParams.delete('board'); history.replaceState(null, '', url);
      const listed = await api.listDocuments();
      setBoards(listed.documents);
      setStatus('Access restored. Choose an investigation.');
    } catch (error) {
      if (pending.current && current.current) timer.current = setTimeout(() => { void flush(); }, 800);
      throw error;
    } finally { loading.current=false;setBusy(false); }
  };

  const saveCopy = async (recoveredScene?: Scene) => {
    if (!current.current || (!pending.current && !sealed.current.length && !recoveredScene) || inFlight.current) return;
    const source = current.current;
    const snapshot = recoveredScene || pending.current || sealed.current[sealed.current.length-1];
    const next = sceneObjects(snapshot);
    const changes = sceneChanges(new Map(), next);
    if (!changes.length || changes.length > 500) { setStatus('Export your drawing to keep a copy.'); return; }
    setBusy(true);
    try {
      const created = await api.createDocument((source.title.slice(0, 112) + ' copy').trim());
      const result = await api.transact(created.id, created.revision, [{ op: 'patch_whiteboard', changes }]);
      current.current = result; saved.current = next; pending.current = null; sealed.current=[];
      setDocument(result); setBoards((list) => [{ id: result.id, title: result.title }, ...list]);
      setConflict(false); setRecoveryDrafts([]);
      if (recoveredScene && editor) {
        loading.current = true;
        editor.resetScene(); editor.addFiles(Object.values(recoveredScene.files || {}));
        editor.updateScene({ elements: restoreElements(recoveredScene.elements, null) });
      }
      try { localStorage.setItem(selectedKey, result.id); sessionStorage.setItem('fireatlas-studio-board', result.id); } catch { /* The board is already saved. */ }
      const url = new URL(location.href); url.searchParams.set('board', result.id); history.replaceState(null, '', url);
      setStatus('Saved');
    } catch (error) { setStatus((error as Error).message + ' Your original draft is still available.'); }
    finally { loading.current = false; setBusy(false); }
  };

  const restoreDraft = (key: string) => {
    if (!editor || !current.current) return;
    if (pending.current || sealed.current.length || inFlight.current) { setStatus('Save current changes before restoring the earlier draft.'); return; }
    try {
      if (!recoveryDrafts.some((draft) => draft.key === key)) throw Error('Draft is unavailable.');
      const data = JSON.parse(localStorage.getItem(key) || 'null');
      const scene = (data?.scene || data) as Scene | null;
      if (!scene || !Array.isArray(scene.elements) || !scene.files) throw Error('Draft is unavailable.');
      if (!Number.isInteger(data?.baseRevision) || data.baseRevision !== current.current.revision) {
        void saveCopy(scene); return;
      }
      editor.resetScene(); editor.addFiles(Object.values(scene.files));
      editor.updateScene({ elements: restoreElements(scene.elements, null) });
      setRecoveryDrafts((drafts) => drafts.filter((draft) => draft.key !== key)); onScene(scene);
    } catch (error) { setStatus((error as Error).message); }
  };

  const copyPreviousDraft = () => {
    if (!editor || !current.current) return;
    if (editor.getSceneElements().length) {
      setStatus('Choose an empty investigation to copy the previous drawing.'); return;
    }
    try {
      const scene = JSON.parse(localStorage.getItem('fireatlas-investigation-whiteboard-v1') || 'null') as Scene | null;
      if (!scene || !Array.isArray(scene.elements) || !scene.elements.length) throw Error('No previous drawing is available.');
      editor.addFiles(Object.values(scene.files || {}));
      editor.updateScene({ elements: restoreElements(scene.elements, null) });
      onScene({ elements: scene.elements, files: scene.files || {} });
      setStatus('Previous drawing copied. Saving…');
    } catch (error) { setStatus((error as Error).message); }
  };

  return { boards, document, available, busy, status, recoveryDrafts, conflict, historyNeedsReload, historyAction, retryHistoryReload, loading, onScene, onPointerDown, onPointerUp, open, create, rename, restorePackage, recoverAccess, flush, saveCopy, restoreDraft, copyPreviousDraft };
}
