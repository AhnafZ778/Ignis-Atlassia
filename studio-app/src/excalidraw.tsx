import {ToolbarMenu} from './components/ToolbarMenu';
import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { CaptureUpdateAction, convertToExcalidrawElements, Excalidraw, exportToBlob, exportToSvg, getCommonBounds, newElementWith, restoreElements, serializeAsJSON } from '@excalidraw/excalidraw';
import type { ExcalidrawImperativeAPI } from '@excalidraw/excalidraw/types';
import { api } from './api';
import type { Card, Snapshot } from './types';
import { useInvestigationBoard } from './lib/useInvestigationBoard';
import { WhiteboardAssistant, wrapEvidenceText, type SourceMatch } from './components/WhiteboardAssistant';
import { WhiteboardAssistantWelcome } from './components/WhiteboardAssistantWelcome';
import { comparisonChart } from './lib/whiteboardChart';
import { figureSelection } from './lib/figureSelection';
import { renderScatter } from './lib/csvScatter';
import { PdfReader, validatePdf, type PdfSource } from './components/PdfReader';
import { parkTimeline } from './lib/parkTimeline';
import { groupIsFocused, type GroupFocus } from './lib/groupFocus';
import { buildReport, sanitizeFigure, type ReportSource } from './lib/investigationReport';
import { challengeComparison, type SeriesName } from './lib/challengeComparison';
import { groupChart } from './lib/groupChart';
import { ScatterValues } from './components/ScatterValues';
import { scatterTable } from './lib/scatterTable';
import { mightContainSources,sourceFileKind } from './lib/importDrop';
import { renderHeatPreview,renderMapPreview } from './lib/mapPreview';
import { mapContextLink } from './lib/mapContextLink';
import { comparisonEvidence } from './lib/comparisonEvidence';
import { challengeOriginals } from './lib/challengeNavigation';
import { externalLinkCard } from './lib/externalLink';
import { mergeDrawing } from './lib/mergeDrawing';
import { selectedSource, sameSelectedSource } from './lib/selectedSource';
import '@excalidraw/excalidraw/index.css';
import './investigation.css';

function Continuation() {
  const [editor, setEditor] = useState<ExcalidrawImperativeAPI | null>(null);
  const board = useInvestigationBoard(editor);
  const [assistantOnboarding,setAssistantOnboarding]=useState(false);
  useEffect(()=>{if(board.document)setAssistantOnboarding(false);},[board.document?.id]);
  const [evidence, setEvidence] = useState<{ documentId: string; card: Card; snapshot: Snapshot }[]>([]);
  const [showEvidence, setShowEvidence] = useState(false);
  const [inspectedEvidence, setInspectedEvidence] = useState<{title:string;snapshot:Snapshot;dates?:string[];mapLink?:string|null;claim?:{label:string;value:string;unit:string};comparison?:ReturnType<typeof comparisonEvidence>;receipt?:unknown;receiptUrl?:string;panelIndex?:number}|null>(null);
  const [evidenceError, setEvidenceError] = useState('');
  const [addingChart, setAddingChart] = useState(false);
  const [challenge, setChallenge] = useState<{ref:{documentId:string;cardId:string;snapshotId:string;snapshotHash:string};pair:any;original:SeriesName;unit:string} | null>(null);
  const [challengeSeries, setChallengeSeries] = useState<SeriesName>('viirs');
  const [dataset, setDataset] = useState<{ id: string; name: string; sha256: string; columns: string[]; row_count: number; preview: string[][]; offset: number } | null>(null);
  const [datasetLoading, setDatasetLoading] = useState(false);
  const [highlightedRecord,setHighlightedRecord]=useState<number|null>(null);
  const [inspectedSummary, setInspectedSummary] = useState<{column:string;metric:string;value:number|string|null}|null>(null);
  const [pdfSource, setPdfSource] = useState<PdfSource | null>(null);
  const [pdfList, setPdfList] = useState<{id:string;name:string;sha256:string;bytes:number}[] | null>(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [scatterX, setScatterX] = useState('');
  const [scatterY, setScatterY] = useState('');
  const [editingScatter,setEditingScatter]=useState<{id:string;serialized:string;datasetId:string;hash:string;x:string;y:string}|null>(null);
  const pendingScatter=useRef<{id:string;x:string;y:string}|null>(null);
  const [groupColumn,setGroupColumn]=useState('');
  const [groupValue,setGroupValue]=useState('');
  const [groups,setGroups]=useState<Awaited<ReturnType<typeof api.datasetGroups>>|null>(null);
  const [groupFocus,setGroupFocus]=useState<GroupFocus|null>(null);
  const pendingGroups=useRef<{id:string;result:Awaited<ReturnType<typeof api.datasetGroups>>}|null>(null);
  const datasetRef = useRef(dataset);
  datasetRef.current = dataset;
  const [datasetList, setDatasetList] = useState<{ id: string; name: string; sha256: string; row_count: number }[] | null>(null);
  const [exporting, setExporting] = useState(false);
  const [nameMode, setNameMode] = useState<'create' | 'rename' | null>(null);
  const [name, setName] = useState('');
  const [selectedDraft, setSelectedDraft] = useState('');
  const [showLink, setShowLink] = useState(false);
  const [sourceAction, setSourceAction] = useState<'table'|'document'|'evidence'|null>(null);
  const [linkAddress, setLinkAddress] = useState('');
  const [linkTitle, setLinkTitle] = useState('');
  const [linkError, setLinkError] = useState('');
  const [recovering, setRecovering] = useState(false);
  const [recoveryToken, setRecoveryToken] = useState('');
  const [recoveryError, setRecoveryError] = useState('');
  const [creatingRecovery, setCreatingRecovery] = useState(false);
  const [issuedRecovery, setIssuedRecovery] = useState('');
  const [issuingRecovery, setIssuingRecovery] = useState(false);
  const currentBoard = useRef<string | null>(null);
  const boardBusy = useRef(false);
  const boardEpoch = useRef(0);
  const interactionBusy=board.busy || board.historyNeedsReload || issuingRecovery;
  if (currentBoard.current !== (board.document?.id || null) || boardBusy.current !== interactionBusy) boardEpoch.current += 1;
  currentBoard.current = board.document?.id || null;
  boardBusy.current = interactionBusy;
  useEffect(()=>{setIssuedRecovery('');setCreatingRecovery(false);},[board.document?.id]);
  useEffect(()=>{setShowLink(false);setLinkAddress('');setLinkTitle('');setLinkError('');},[board.document?.id,board.busy]);
  useEffect(()=>{setSourceAction(null);},[board.document?.id]);
  useEffect(() => { setShowEvidence(false); setEvidence([]); setInspectedEvidence(null); setDataset(null);setHighlightedRecord(null); setEditingScatter(null);pendingScatter.current=null;setInspectedSummary(null);setGroupFocus(null); setDatasetList(null); setPdfSource(null); setPdfList(null); setChallenge(null); }, [board.document?.id, board.busy]);
  useEffect(() => { if (dataset || datasetList || pdfSource || pdfList) document.querySelector('.whiteboard-more')?.removeAttribute('open'); }, [dataset, datasetList, pdfSource, pdfList]);
  useEffect(() => { const scatter=pendingScatter.current;setScatterX(dataset && scatter?.id===dataset.id?scatter.x:'');setScatterY(dataset && scatter?.id===dataset.id?scatter.y:'');pendingScatter.current=null;const pending=pendingGroups.current;if(dataset && pending?.id===dataset.id){setGroupColumn(pending.result.group_column);setGroupValue(pending.result.value_column);setGroups(pending.result);pendingGroups.current=null;}else{setGroupColumn('');setGroupValue('');setGroups(null);} }, [dataset?.id]);
  useEffect(()=>{const close=()=>{setDataset(null);setEditingScatter(null);pendingScatter.current=null;};window.addEventListener('fireatlas-whiteboard-close-table',close);return()=>window.removeEventListener('fireatlas-whiteboard-close-table',close);},[]);
  useEffect(() => {
    if(!board.document)return;
    const onKey=(event:KeyboardEvent)=>{
      const target=event.target as HTMLElement | null;
      if(target && (target.isContentEditable || target.closest('input,textarea,select,[contenteditable="true"],.excalidraw-wysiwyg')))return;
      if(!(event.ctrlKey || event.metaKey) || event.altKey)return;
      const key=event.key.toLowerCase();
      if(key!=='z' && key!=='y')return;
      event.preventDefault();event.stopImmediatePropagation();
      if(!interactionBusy && !event.repeat)void board.historyAction(key==='y' || event.shiftKey?'redo':'undo');
    };
    window.addEventListener('keydown',onKey,true);return()=>window.removeEventListener('keydown',onKey,true);
  },[board.document?.id,interactionBusy,board.historyNeedsReload]);
  if (editor) (window as any).FireAtlasExcalidraw = editor;
  const storageKey = 'fireatlas-investigation-whiteboard-v1';
  const [initial] = useState(() => {
    try { const data = localStorage.getItem(storageKey); return data ? JSON.parse(data) : null; }
    catch { return null; }
  });
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [status, setStatus] = useState('Your whiteboard is saved in this browser. Export a copy to share or back it up.');
  const [notice, setNotice] = useState('');
  useEffect(()=>{if(!notice)return;const timeout=setTimeout(()=>setNotice(''),5000);return()=>clearTimeout(timeout);},[notice]);
  const [ready, setReady] = useState(true);
  const addLink = () => {
    if(!editor || boardBusy.current)return;
    try {
      const existing=editor.getSceneElements();
      const x=existing.length ? Math.max(...existing.map(item=>item.x+item.width))+100 : 100;
      const shape=externalLinkCard(linkAddress,linkTitle,currentBoard.current,x,100);
      const elements=convertToExcalidrawElements([shape]);
      editor.updateScene({elements:[...existing,...elements],captureUpdate:CaptureUpdateAction.IMMEDIATELY});
      editor.scrollToContent(elements,{fitToContent:true});
      setShowLink(false);setLinkAddress('');setLinkTitle('');setLinkError('');setNotice('Link added to the investigation.');
    } catch(error) {setLinkError((error as Error).message);}
  };
  const load = async (file?: File) => {
    if (!file || !editor || boardBusy.current) return;
    const epoch=boardEpoch.current;
    setNotice('');
    try {
      if (file.size > 128 * 1024 ** 2) throw Error('Scene exceeds the 128 MiB editor limit. Export a frame or selection.');
      const scene = JSON.parse(await file.text());
      if(boardEpoch.current!==epoch || boardBusy.current)return;
      if (scene.type !== 'excalidraw' || scene.version !== 2 || !Array.isArray(scene.elements) || scene.elements.length > 8192) throw Error('Choose a valid bounded Excalidraw scene.');
      const files = Object.values(scene.files || {}) as any[];
      if (files.some((f) => !/^data:image\/(png|jpeg|webp|svg\+xml);base64,/.test(f.dataURL) || f.dataURL.length > 44 * 1024 ** 2)) throw Error('Images must be bounded embedded files. External asset URLs are unavailable.');
      if (board.document) {
        if (files.some((f) => !/^data:image\/(png|jpeg|webp);base64,/.test(f.dataURL) || new TextEncoder().encode(JSON.stringify(f)).length > 1_500_000)) throw Error('Saved boards accept PNG, JPEG and WebP images up to 1.5 MB each.');
        if (scene.elements.length + files.length + editor.getSceneElements().length + Object.keys(editor.getFiles()).length + 1 > 500 || new TextEncoder().encode(JSON.stringify(scene)).length > 2_500_000) throw Error('This drawing is too large to add to a saved board.');
      }
      for (const file of files) if (file.dataURL.startsWith('data:image/svg+xml;')) {
        const xml = new DOMParser().parseFromString(atob(file.dataURL.split(',')[1]), 'image/svg+xml');
        if (xml.querySelector('parsererror,script,foreignObject,iframe,object,embed') || [...xml.querySelectorAll('*')].some((e) => [...e.attributes].some((a) => a.name.startsWith('on') || (['href','xlink:href'].includes(a.name) && !a.value.startsWith('#') && !a.value.startsWith('data:image/'))))) throw Error('Embedded SVG must contain a standalone inert figure.');
      }
      const elements = restoreElements(scene.elements, null);
      const ids = new Set(elements.map((e) => e.id));
      for (const element of elements) if ((element as any).startBinding && !ids.has((element as any).startBinding.elementId) || (element as any).endBinding && !ids.has((element as any).endBinding.elementId)) throw Error('A connector references an absent object.');
      const existing=editor.getSceneElements();
      const merged=mergeDrawing(elements,files,existing,()=>crypto.randomUUID());
      let added=merged.elements;
      if(!added.some(item=>item.type==='frame' || item.type==='magicframe')){
        const frameId=crypto.randomUUID(),{x,y,width,height}=merged.bounds;
        const frame=convertToExcalidrawElements([{id:frameId,type:'frame',name:'Imported drawing',children:[],x:x-40,y:y-60,width:width+80,height:height+100}],{regenerateIds:false});
        added=[...added.map(item=>({...item,frameId})),...frame];
      }
      editor.addFiles(merged.files); editor.updateScene({ elements:[...existing,...added], captureUpdate:CaptureUpdateAction.IMMEDIATELY }); editor.scrollToContent(added, { fitToContent: true });
      document.querySelector('.whiteboard-more')?.removeAttribute('open');
      setReady(true); setNotice(`${elements.length} objects added to the investigation.`);
    } catch (e) { setNotice((e as Error).message); }
  };
  const save = () => {
    if (!editor) return;
    const json = serializeAsJSON(editor.getSceneElements(), editor.getAppState(), editor.getFiles(), 'local');
    const href = URL.createObjectURL(new Blob([json], { type: 'application/json' }));
    const anchor = document.createElement('a'); anchor.href = href; anchor.download = 'fireatlas-edited.excalidraw'; anchor.click(); setTimeout(() => URL.revokeObjectURL(href), 1000);
    setStatus('Whiteboard exported.');
  };
  const saveFigure = async (format: 'png' | 'svg') => {
    if (!editor || boardBusy.current) return;
    const requestEpoch = boardEpoch.current;
    const elements = figureSelection(editor.getSceneElements(), editor.getAppState().selectedElementIds);
    if (!elements.length) { setNotice('Add or select something to export.'); return; }
    try {
      const [left, top, right, bottom] = getCommonBounds(elements);
      if (![left, top, right, bottom].every(Number.isFinite) || right - left > 20000 || bottom - top > 20000) throw Error('This figure is too large. Select a smaller area.');
      const options = { elements, files: editor.getFiles(), appState: { exportBackground: true, viewBackgroundColor: editor.getAppState().viewBackgroundColor }, exportPadding: 64 };
      const data = format === 'png' ? await exportToBlob({ ...options, mimeType: 'image/png', maxWidthOrHeight: 4096 }) : new Blob([new XMLSerializer().serializeToString(await exportToSvg(options))], { type: 'image/svg+xml' });
      if (boardEpoch.current !== requestEpoch || boardBusy.current) return;
      const href = URL.createObjectURL(data); const anchor = document.createElement('a');
      anchor.href = href; anchor.download = `investigation-figure.${format}`; anchor.click();
      setTimeout(() => URL.revokeObjectURL(href), 1000); setNotice('Figure exported.');
    } catch (error) { if (boardEpoch.current === requestEpoch) setNotice((error as Error).message); }
  };
  const saveReport = async () => {
    const documentId=currentBoard.current,epoch=boardEpoch.current;
    if(!editor || !documentId || boardBusy.current || exporting)return;
    setExporting(true);setNotice('Preparing report…');
    try{
      if(!(await board.flush()))throw Error('Save the board before preparing a report.');
      if(boardEpoch.current!==epoch || boardBusy.current || currentBoard.current!==documentId)return;
      const scene=JSON.parse(serializeAsJSON(editor.getSceneElements(),editor.getAppState(),editor.getFiles(),'local'));
      const elements=figureSelection(scene.elements,editor.getAppState().selectedElementIds) as any[];
      if(!elements.length)throw Error('Add or select something to include in the report.');
      const [left,top,right,bottom]=getCommonBounds(elements);
      if(![left,top,right,bottom].every(Number.isFinite) || right-left>20000 || bottom-top>20000)throw Error('Select a smaller area for this report.');
      const selectedRefs=elements.map((item)=>(item.customData as any)?.fireatlas).filter(Boolean);
      if(selectedRefs.some((ref)=>ref.documentId && ref.documentId!==documentId && (ref.datasetId || ref.sourceDocumentId || ref.snapshotId)))throw Error('This selection includes a source from another investigation.');
      const unique=(field:string,hash:string)=>{
        const result=new Map<string,string>();
        for(const ref of selectedRefs)if(ref[field]){if(!ref[hash] || (result.has(ref[field]) && result.get(ref[field])!==ref[hash]))throw Error('A selected source reference is inconsistent.');result.set(ref[field],ref[hash]);}
        return result;
      };
      const datasets=unique('datasetId','datasetHash'),pdfs=unique('sourceDocumentId','sourceDocumentHash'),snapshots=unique('snapshotId','snapshotHash');
      if(datasets.size+pdfs.size+snapshots.size>30)throw Error('Select at most 30 linked sources for a report.');
      const sources:ReportSource[]=[];let total=0;
      const addSource=async(name:string,sha256:string,kind:ReportSource['kind'],bytes:Uint8Array)=>{
        total+=bytes.length;if(total>15*1024*1024)throw Error('Selected sources exceed the 15 MiB report limit. Export the investigation package instead.');
        const actual=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new Uint8Array(bytes)))).map(value=>value.toString(16).padStart(2,'0')).join('');
        if(actual!==sha256)throw Error('A selected source no longer matches its saved hash.');
        sources.push({name,sha256,kind,bytes});
      };
      for(const [id,hash] of datasets){
        const info=await api.dataset(documentId,id);if(info.sha256!==hash)throw Error('A selected table has changed.');
        const response=await fetch(api.datasetDownload(documentId,id),{credentials:'same-origin'});if(!response.ok)throw Error('A selected table is unavailable.');
        await addSource(info.name,hash,'csv',new Uint8Array(await response.arrayBuffer()));
      }
      if(pdfs.size){const list=await api.sourceDocuments(documentId);
        for(const [id,hash] of pdfs){const item=list.documents.find(value=>value.id===id && value.sha256===hash);if(!item)throw Error('A selected document is unavailable.');
          const response=await fetch(api.sourceDocumentUrl(documentId,id),{credentials:'same-origin'});if(!response.ok)throw Error('A selected document is unavailable.');
          await addSource(item.name,hash,'pdf',new Uint8Array(await response.arrayBuffer()));}}
      const doc=await api.getDocument(documentId);
      for(const [id,hash] of snapshots){const snapshot=doc.snapshots?.[id];if(!snapshot || snapshot.snapshot_sha256!==hash)throw Error('A selected evidence source has changed.');
        const report=await api.snapshotReport(documentId,id);if(report.snapshot.snapshot_sha256!==hash || !report.verification.verified)throw Error('A selected evidence source could not be verified.');
        const receipt=await api.snapshotReceipt(documentId,id);
        if(receipt.snapshot_id!==id || receipt.result_id!==report.snapshot.result_id)throw Error('A selected evidence receipt no longer matches its snapshot.');
        const value=report.snapshot;const safe={id:value.id,snapshot_sha256:value.snapshot_sha256,result_id:value.result_id,operation:value.operation,scope:value.scope,method:value.method,release_id:value.release_id,facts:value.facts};
        const bytes=new TextEncoder().encode(JSON.stringify({snapshot:safe,receipt:receipt.receipt},null,2));const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(v=>v.toString(16).padStart(2,'0')).join('');
        await addSource(`evidence-${id}.json`,digest,'evidence',bytes);
      }
      const svg=await exportToSvg({elements,files:scene.files,appState:{exportBackground:true,viewBackgroundColor:editor.getAppState().viewBackgroundColor},exportPadding:64});
      if(boardEpoch.current!==epoch || boardBusy.current || currentBoard.current!==documentId)return;
      const notes=elements.filter(item=>item.type==='text' && item.text && !['park-platform-chart','comparison-chart','csv-dataset'].includes(item.customData?.fireatlas?.kind)).map(item=>String(item.text));
      const html=buildReport(doc.title,sanitizeFigure(svg),notes,sources);
      const href=URL.createObjectURL(new Blob([html],{type:'text/html;charset=utf-8'}));const anchor=document.createElement('a');anchor.href=href;anchor.download='investigation-report.html';anchor.click();setTimeout(()=>URL.revokeObjectURL(href),1000);
      setNotice('Report exported.');
    }catch(error){if(boardEpoch.current===epoch)setNotice((error as Error).message);}
    finally{setExporting(false);}
  };
  const savePackage = async () => {
    const documentId = currentBoard.current;
    if (!documentId || exporting || boardBusy.current) return;
    setExporting(true); setNotice('Preparing investigation package…');
    try {
      if (!(await board.flush())) throw Error('Save your drawing before exporting.');
      if (currentBoard.current !== documentId || boardBusy.current) return;
      const requestEpoch = boardEpoch.current;
      const current = () => boardEpoch.current === requestEpoch && currentBoard.current === documentId && !boardBusy.current;
      const latest = await api.getDocument(documentId);
      if (!current()) return;
      const job = await api.prepareExport(documentId, { format: 'native', revision: latest.revision });
      for (let attempts = 0; attempts < 240; attempts++) {
        if (!current()) return;
        const progress = await api.getExport(job.id);
        if (!current()) return;
        if (progress.status === 'completed') {
          const anchor = document.createElement('a'); anchor.href = api.exportDownload(job.id); anchor.download = 'investigation.fireatlas.zip'; anchor.click();
          setNotice('Investigation package ready.'); return;
        }
        if (['failed', 'cancelled'].includes(progress.status)) throw Error(progress.error || 'The package could not be prepared.');
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
      throw Error('Package preparation is taking longer than expected. Try again in Studio.');
    } catch (error) { if (currentBoard.current === documentId) setNotice((error as Error).message); }
    finally { setExporting(false); }
  };
  const placeDataset = (result: {id:string; name:string; sha256:string; columns:string[]; row_count:number; preview:string[][]}, documentId:string) => {
    if (!editor || boardBusy.current || currentBoard.current!==documentId) return;
    const items=editor.getSceneElements(); const x=items.length ? Math.max(...items.map((item)=>item.x+item.width))+100 : 100;
    const customData={fireatlas:{documentId,datasetId:result.id,datasetHash:result.sha256,kind:'csv-dataset'}};
    const elements=convertToExcalidrawElements([{type:'rectangle',x,y:100,width:380,height:150,backgroundColor:'#e5f3eb',fillStyle:'solid',strokeColor:'#37735b',roundness:{type:3},customData},
      {type:'text',x:x+18,y:118,text:`${result.name}\n${result.row_count} rows · ${result.columns.length} columns\nSelect and choose Inspect table`,fontSize:17,strokeColor:'#183149',customData}]);
    editor.updateScene({elements:[...items,...elements],captureUpdate:CaptureUpdateAction.IMMEDIATELY});
    editor.scrollToContent(elements,{fitToContent:true});setEditingScatter(null);setHighlightedRecord(null);pendingScatter.current=null;setDataset({...result,offset:0});setDatasetList(null);setNotice('Table added to the board.');
  };
  const importPdf = async (file:File) => {
    const documentId=currentBoard.current, epoch=boardEpoch.current;
    if(!documentId || !editor || boardBusy.current || pdfLoading)return;
    setPdfLoading(true);setNotice('Opening document…');
    try {
      if(file.size>10*1024*1024)throw Error('Choose a PDF up to 10 MiB.');
      const data=new Uint8Array(await file.arrayBuffer());
      await validatePdf(data);
      if(boardEpoch.current!==epoch || boardBusy.current)return;
      const result=await api.uploadSourceDocument(documentId,file);
      if(boardEpoch.current!==epoch || boardBusy.current || currentBoard.current!==documentId)return;
      setPdfSource({...result,data});setPdfList(null);
    } catch(error) {if(boardEpoch.current===epoch)setNotice((error as Error).message || 'This PDF could not be opened.');}
    finally {setPdfLoading(false);}
  };
  const openPdf = async (source:{id:string;name:string;sha256:string;bytes:number},initialPage=1) => {
    const documentId=currentBoard.current,epoch=boardEpoch.current;
    if(!documentId || boardBusy.current || pdfLoading)return;
    setPdfLoading(true);
    try {
      const response=await fetch(api.sourceDocumentUrl(documentId,source.id),{credentials:'same-origin'});
      if(!response.ok)throw Error('This document is unavailable.');
      const data=new Uint8Array(await response.arrayBuffer());
      const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',data))).map((v)=>v.toString(16).padStart(2,'0')).join('');
      if(digest!==source.sha256)throw Error('The document no longer matches its source.');
      await validatePdf(data);
      if(boardEpoch.current===epoch && !boardBusy.current){setPdfSource({...source,data,initialPage});setPdfList(null);}
    } catch(error){if(boardEpoch.current===epoch)setNotice((error as Error).message || 'This PDF could not be opened.');}
    finally{setPdfLoading(false);}
  };
  const listPdfs = async () => {
    const id=currentBoard.current,epoch=boardEpoch.current;if(!id || boardBusy.current)return;
    try{const result=await api.sourceDocuments(id);if(boardEpoch.current===epoch && !boardBusy.current)setPdfList(result.documents);}
    catch(error){if(boardEpoch.current===epoch)setNotice((error as Error).message);}
  };
  const inspectPdf = async () => {
    if(!editor || !currentBoard.current)return;
    const selected=editor.getAppState().selectedElementIds;
    const ref=editor.getSceneElements().filter((item)=>selected[item.id]).map((item)=>(item.customData as any)?.fireatlas).find((item)=>item?.documentId===currentBoard.current && item.sourceDocumentId && item.sourceDocumentHash);
    if(!ref){setNotice('Select a document page or excerpt first.');return;}
    const epoch=boardEpoch.current;
    try {const result=await api.sourceDocuments(currentBoard.current);if(epoch!==boardEpoch.current || boardBusy.current)return;
      const source=result.documents.find((item)=>item.id===ref.sourceDocumentId && item.sha256===ref.sourceDocumentHash);
      if(!source)throw Error('The selected document is unavailable.');await openPdf(source,Number.isInteger(ref.page)?ref.page:1);
    }catch(error){if(epoch===boardEpoch.current)setNotice((error as Error).message);}
  };
  const placePdf = (page:number,image:string,excerpt?:string,width=1,height=1) => {
    const documentId=currentBoard.current,source=pdfSource;
    if(!editor || !documentId || !source || boardBusy.current)return;
    const items=editor.getSceneElements(),x=items.length?Math.max(...items.map((item)=>item.x+item.width))+100:100;
    const customData={fireatlas:{documentId,sourceDocumentId:source.id,sourceDocumentHash:source.sha256,page,kind:excerpt?'pdf-excerpt':'pdf-page'}};
    if(excerpt){
      const words=excerpt.split(/\s+/),lines:string[]=[];let line='';
      for(const word of words){if(line && line.length+word.length>54){lines.push(line);line='';}line+=(line?' ':'')+word;}if(line)lines.push(line);
      const elements=convertToExcalidrawElements([{type:'text',x,y:100,text:`${source.name} · page ${page}\n\n${lines.join('\n')}`,fontSize:18,strokeColor:'#183149',customData}]);
      editor.updateScene({elements:[...items,...elements],captureUpdate:CaptureUpdateAction.IMMEDIATELY});editor.scrollToContent(elements,{fitToContent:true});
    }else{
      const fileId=crypto.randomUUID(),file={id:fileId,mimeType:'image/png',dataURL:image,created:Date.now()};
      if(new TextEncoder().encode(JSON.stringify(file)).length>1_500_000){setNotice('This page image is too large for the board.');return;}
      const scale=Math.min(600/width,800/height);
      const elements=convertToExcalidrawElements([{type:'image',x,y:100,width:width*scale,height:height*scale,fileId,status:'saved',customData} as any]);
      editor.addFiles([file as any]);editor.updateScene({elements:[...items,...elements],captureUpdate:CaptureUpdateAction.IMMEDIATELY});editor.scrollToContent(elements,{fitToContent:true});
    }
    setNotice('Document added to the board.');
  };
  const importCsv = async (file: File) => {
    const documentId=currentBoard.current, requestEpoch=boardEpoch.current;
    if (!documentId || !editor || boardBusy.current || datasetLoading) return;
    setDatasetLoading(true); setNotice('Importing table…');
    try {
      const result=await api.uploadDataset(documentId,file);
      if (boardEpoch.current!==requestEpoch || boardBusy.current || currentBoard.current!==documentId) return;
      placeDataset(result,documentId);
    } catch(error) { if (boardEpoch.current===requestEpoch) setNotice((error as Error).message); }
    finally {setDatasetLoading(false);}
  };
  const dropSources = (event:React.DragEvent<HTMLDivElement>) => {
    const files=Array.from(event.dataTransfer.files), supported=files.filter(file=>sourceFileKind(file));
    if(!supported.length)return;
    event.preventDefault();event.stopPropagation();
    if(files.length!==1){setNotice('Drop one CSV or PDF at a time.');return;}
    if(!board.document || !editor){setNotice('Create or open an investigation before importing a file.');return;}
    if(interactionBusy || datasetLoading || pdfLoading){setNotice('Wait for the current action to finish before importing.');return;}
    if(sourceFileKind(files[0])==='csv')void importCsv(files[0]);else void importPdf(files[0]);
  };
  const showDatasets = async () => {
    const documentId=currentBoard.current, requestEpoch=boardEpoch.current;
    if (!documentId || boardBusy.current) return;
    try {const result=await api.datasets(documentId);if (boardEpoch.current===requestEpoch && !boardBusy.current) setDatasetList(result.datasets);}
    catch(error) {if(boardEpoch.current===requestEpoch)setNotice((error as Error).message);}
  };
  const placeSavedDataset = async (id:string,hash:string) => {
    const documentId=currentBoard.current,requestEpoch=boardEpoch.current;
    if(!documentId || datasetLoading)return;
    setDatasetLoading(true);
    try {const result=await api.dataset(documentId,id);if(boardEpoch.current!==requestEpoch || boardBusy.current)return;
      if(result.sha256!==hash)throw Error('The table source has changed.');placeDataset(result,documentId);
    } catch(error){if(boardEpoch.current===requestEpoch)setNotice((error as Error).message);}
    finally{setDatasetLoading(false);}
  };
  const inspectDataset = async (id: string, hash: string, offset = 0, highlight = false, stillSelected:()=>boolean = ()=>true) => {
    const documentId=currentBoard.current, requestEpoch=boardEpoch.current;
    if (!documentId || boardBusy.current || datasetLoading) return;
    setDatasetLoading(true);
    try { const result=await api.dataset(documentId,id,offset);
      if (boardEpoch.current!==requestEpoch || boardBusy.current || currentBoard.current!==documentId || !stillSelected()) return;
      if (result.sha256!==hash) throw Error('The selected table no longer matches its source.');
      setDataset(result);setHighlightedRecord(highlight?offset:null);
    } catch(error) { if (boardEpoch.current===requestEpoch) setNotice((error as Error).message); }
    finally {setDatasetLoading(false);}
  };
  const inspectSelectedDataset = async () => {
    if (!editor || !currentBoard.current) return;
    const selected=editor.getAppState().selectedElementIds;
    const item=editor.getSceneElements().find(item=>{const ref=(item.customData as any)?.fireatlas;return selected[item.id] && ref?.documentId===currentBoard.current && ref?.datasetId && ref?.datasetHash;});
    if (!item) {setNotice('Select a table on the board first.');return;}
    const ref=(item.customData as any).fireatlas,epoch=boardEpoch.current,documentId=currentBoard.current;
    const serializedRef=JSON.stringify(ref);
    const stillSelected=()=>sameSelectedSource(editor.getSceneElements(),editor.getAppState().selectedElementIds,item.id,serializedRef);
    if(ref.kind==='dataset-scatter' && item.type==='image' && typeof ref.xColumn==='string' && typeof ref.yColumn==='string'){
      setEditingScatter({id:item.id,serialized:JSON.stringify(item),datasetId:ref.datasetId,hash:ref.datasetHash,x:ref.xColumn,y:ref.yColumn});
      if(datasetRef.current?.id===ref.datasetId){setScatterX(ref.xColumn);setScatterY(ref.yColumn);}
      else pendingScatter.current={id:ref.datasetId,x:ref.xColumn,y:ref.yColumn};
    }else{setEditingScatter(null);pendingScatter.current=null;setScatterX('');setScatterY('');}
    setInspectedSummary(null);
    if(typeof ref.groupColumn==='string' && typeof ref.valueColumn==='string'){
      try{const result=await api.datasetGroups(documentId,ref.datasetId,ref.groupColumn,ref.valueColumn);if(boardEpoch.current!==epoch || boardBusy.current || !stillSelected())return;
        if(result.sha256!==ref.datasetHash)throw Error('The table source changed.');
        const name=ref.groupName;
        setGroupFocus(Object.prototype.hasOwnProperty.call(ref,'groupName') && (typeof name==='string' || name===null) && result.groups.some(item=>item.group===name)
          ? {datasetId:ref.datasetId,groupColumn:result.group_column,valueColumn:result.value_column,name} : null);
        if(datasetRef.current?.id===ref.datasetId){setGroupColumn(result.group_column);setGroupValue(result.value_column);setGroups(result);}
        else pendingGroups.current={id:ref.datasetId,result};
      }catch(error){if(boardEpoch.current===epoch)setNotice((error as Error).message);return;}
    }else{pendingGroups.current=null;setGroups(null);setGroupFocus(null);}
    if(typeof ref.summaryColumn==='string' && ['numeric_count','missing_count','non_numeric_count','minimum','maximum','mean','median'].includes(ref.summaryMetric)){
      try{const summary=await api.datasetSummary(documentId,ref.datasetId,ref.summaryColumn);if(boardEpoch.current!==epoch || boardBusy.current || !stillSelected())return;
        if(summary.sha256!==ref.datasetHash)throw Error('The table source changed.');
        setInspectedSummary({column:ref.summaryColumn,metric:ref.summaryMetric,value:summary.columns[0]?.[ref.summaryMetric] ?? null});
      }catch(error){if(boardEpoch.current===epoch)setNotice((error as Error).message);return;}
    }
    const hasRow=Number.isInteger(ref.rowOffset) && ref.rowOffset>=0;
    void inspectDataset(ref.datasetId,ref.datasetHash,hasRow ? ref.rowOffset : 0,hasRow,stillSelected);
  };
  const openAssistantSource = async (match:SourceMatch) => {
    const documentId=currentBoard.current, epoch=boardEpoch.current;
    if(!documentId || boardBusy.current)return;
    if(match.kind==='csv' && Number.isInteger(match.row_offset) && match.row_offset!>=0){
      setEditingScatter(null);setInspectedSummary(null);setGroups(null);
      await inspectDataset(match.source_id,match.source_sha256,match.row_offset,true);
    } else if(match.kind==='pdf' && Number.isInteger(match.page) && match.page!>0){
      try {const list=await api.sourceDocuments(documentId);
        if(boardEpoch.current!==epoch || boardBusy.current || currentBoard.current!==documentId)return;
        const source=list.documents.find(item=>item.id===match.source_id && item.sha256===match.source_sha256);
        if(!source)throw Error('The document is unavailable. Search again.');
        await openPdf(source,match.page);
      } catch(error){if(boardEpoch.current===epoch)setNotice((error as Error).message);}
    } else setNotice('This source is unavailable. Search again.');
  };
  const addScatter = async () => {
    const documentId = currentBoard.current, selected = dataset, requestEpoch = boardEpoch.current;
    if (!documentId || !editor || !selected || !scatterX || !scatterY || scatterX === scatterY || datasetLoading || boardBusy.current) return;
    setDatasetLoading(true);
    try {
      if(editingScatter && !(await board.flush()))throw Error('Save the current board before updating the chart.');
      const result = await api.datasetScatter(documentId, selected.id, scatterX, scatterY);
      if (boardEpoch.current !== requestEpoch || boardBusy.current || currentBoard.current !== documentId || datasetRef.current?.id !== selected.id || datasetRef.current.sha256 !== selected.sha256) return;
      if (result.dataset_id !== selected.id || result.sha256 !== selected.sha256) throw Error('The table source has changed.');
      const fileId = crypto.randomUUID();
      const file = { id: fileId, mimeType: 'image/png', dataURL: renderScatter(result), created: Date.now() };
      if (new TextEncoder().encode(JSON.stringify(file)).length > 1_500_000) throw Error('The chart image is too large for this board.');
      const items = editor.getSceneElements();
      const original=editingScatter && items.find(item=>item.id===editingScatter.id);
      if(editingScatter && (!original || original.type!=='image' || original.locked || JSON.stringify(original)!==editingScatter.serialized))throw Error('The chart changed or is locked. Select it again before updating.');
      const x = items.length ? Math.max(...items.map((item) => item.x + item.width)) + 100 : 100;
      const customData = { fireatlas: { documentId, datasetId: selected.id, datasetHash: selected.sha256, kind: 'dataset-scatter', xColumn: result.x_column, yColumn: result.y_column, plottedRows: result.points.length, skippedRows: result.skipped_rows } };
      const elements = original && original.type==='image' ? [newElementWith(original,{fileId:fileId as typeof original.fileId,customData:{...original.customData,...customData}})] : convertToExcalidrawElements([{ type: 'image', x, y: 100, width: 960, height: 600, fileId, status: 'saved', customData } as any]);
      editor.addFiles([file as any]);
      editor.updateScene({ elements: original ? items.map(item=>item.id===original.id?elements[0]:item) : [...items, ...elements], captureUpdate: CaptureUpdateAction.IMMEDIATELY });
      editor.scrollToContent(elements, { fitToContent: true });
      setDataset(null);setEditingScatter(null);
      setNotice(`Chart ${original?'updated':'added'}: ${result.points.length} rows plotted, ${result.skipped_rows} skipped.`);
    } catch (error) { if (boardEpoch.current === requestEpoch && currentBoard.current === documentId) setNotice((error as Error).message); }
    finally { setDatasetLoading(false); }
  };
  const addScatterValues = async (data:Awaited<ReturnType<typeof api.datasetScatter>>,page:number) => {
    const documentId=currentBoard.current, epoch=boardEpoch.current, selected=editingScatter;
    if(!editor || !documentId || !selected || boardBusy.current)return;
    try{
      if(!(await board.flush()))throw Error('Save the board before adding values.');
      if(boardEpoch.current!==epoch || boardBusy.current)return;
      const items=editor.getSceneElements(),chart=items.find(item=>item.id===selected.id);
      if(!chart || JSON.stringify(chart)!==selected.serialized || data.dataset_id!==selected.datasetId || data.sha256!==selected.hash || data.x_column!==selected.x || data.y_column!==selected.y)throw Error('The chart changed. Select it again.');
      const x=Math.max(...items.map(item=>item.x+item.width))+80;
      const elements=convertToExcalidrawElements(scatterTable(data,{documentId,datasetId:selected.datasetId,datasetHash:selected.hash},page,x,chart.y));
      editor.updateScene({elements:[...items,...elements],captureUpdate:CaptureUpdateAction.IMMEDIATELY});
      editor.scrollToContent(elements,{fitToContent:true});setDataset(null);setEditingScatter(null);setNotice('Plotted values added.');
    }catch(error){if(boardEpoch.current===epoch)setNotice((error as Error).message);}
  };
  const compareGroups = async () => {
    const documentId=currentBoard.current,selected=dataset,epoch=boardEpoch.current;
    if(!documentId || !selected || !groupColumn || !groupValue || groupColumn===groupValue || datasetLoading)return;
    setDatasetLoading(true);
    try{const result=await api.datasetGroups(documentId,selected.id,groupColumn,groupValue);
      if(boardEpoch.current!==epoch || boardBusy.current || datasetRef.current?.id!==selected.id || datasetRef.current.sha256!==selected.sha256)return;
      if(result.sha256!==selected.sha256)throw Error('The selected table changed.');setGroups(result);
    }catch(error){if(boardEpoch.current===epoch)setNotice((error as Error).message);}
    finally{setDatasetLoading(false);}
  };
  const addGroupTable = () => {
    const documentId=currentBoard.current,selected=dataset,result=groups;
    if(!documentId || !editor || !selected || !result || result.sha256!==selected.sha256 || boardBusy.current)return;
    const items=editor.getSceneElements(),x=items.length?Math.max(...items.map(item=>item.x+item.width))+100:100;
    const lines=[`Grouped table · ${selected.name}`,`${result.group_column} | ${result.value_column} mean | numeric / rows | missing / nonnumeric`,...result.groups.map(item=>`${item.group ?? '(blank group)'} | ${item.mean ?? 'unavailable'} | ${item.numeric_count} / ${item.rows} | ${item.missing_count} / ${item.non_numeric_count}`)];
    const elements=convertToExcalidrawElements([{type:'text',x,y:100,text:lines.join('\n'),fontSize:16,fontFamily:2,strokeColor:'#183149',customData:{fireatlas:{documentId,datasetId:selected.id,datasetHash:selected.sha256,kind:'dataset-group-summary',groupColumn:result.group_column,valueColumn:result.value_column}}}]);
    editor.updateScene({elements:[...items,...elements],captureUpdate:CaptureUpdateAction.IMMEDIATELY});editor.scrollToContent(elements,{fitToContent:true});setNotice('Grouped table added.');
  };
  const addGroupChart = () => {
    const documentId=currentBoard.current,selected=dataset,result=groups;
    if(!documentId || !editor || !selected || !result || result.sha256!==selected.sha256 || boardBusy.current)return;
    try{const items=editor.getSceneElements(),x=items.length?Math.max(...items.map(item=>item.x+item.width))+100:100;
      const ref={documentId,datasetId:selected.id,datasetHash:selected.sha256,kind:'dataset-group-chart',groupColumn:result.group_column,valueColumn:result.value_column};
      const elements=convertToExcalidrawElements(groupChart(result,ref,x,100,()=>`group-${crypto.randomUUID()}`),{regenerateIds:false});
      editor.updateScene({elements:[...items,...elements],captureUpdate:CaptureUpdateAction.IMMEDIATELY});editor.scrollToContent(elements,{fitToContent:true});setDataset(null);setNotice('Grouped chart added.');
    }catch(error){setNotice((error as Error).message);}
  };
  const showSavedEvidence = async () => {
    if (!board.document) return;
    setEvidenceError('');
    const documentId = board.document.id;
    try {
      const doc = await api.getDocument(documentId);
      if (currentBoard.current !== documentId || boardBusy.current) return;
      setEvidence(Object.values(doc.state.cards).flatMap((card) => {
        const snapshot = card.snapshot_id && doc.snapshots?.[card.snapshot_id];
        return snapshot ? [{ documentId, card, snapshot }] : [];
      }));
      setShowEvidence(true);
    } catch (error) { setNotice((error as Error).message); }
  };
  const inspectSelectedEvidence = async () => {
    const documentId=currentBoard.current,epoch=boardEpoch.current;
    if(!editor || !documentId || boardBusy.current)return;
    const selected=editor.getAppState().selectedElementIds;
    const element=editor.getSceneElements().find(item=>selected[item.id] && (item.customData as any)?.fireatlas?.snapshotId);
    const ref=(element?.customData as any)?.fireatlas;
    if(!element || ref?.documentId!==documentId || !ref.snapshotId || !ref.snapshotHash){setNotice('Select a saved evidence item first.');return;}
    try {
      const doc=await api.getDocument(documentId);
      const receipt=await api.snapshotReceipt(documentId,ref.snapshotId);
      if(boardEpoch.current!==epoch || boardBusy.current)return;
      const current=editor.getSceneElements().find(item=>item.id===element.id);
      const now=(current?.customData as any)?.fireatlas;
      const card=ref.cardId ? doc.state.cards[ref.cardId] : null,snapshot=doc.snapshots?.[ref.snapshotId];
      if(!now || !editor.getAppState().selectedElementIds[element.id] || now.comparisonPanel!==ref.comparisonPanel || now.cardId!==ref.cardId || now.snapshotId!==ref.snapshotId || now.snapshotHash!==ref.snapshotHash || (ref.cardId && (!card || card.snapshot_id!==ref.snapshotId)) || !snapshot || snapshot.snapshot_sha256!==ref.snapshotHash)throw Error('The selected evidence changed. Select it again.');
      const dates=receipt.receipt.operation==='archive_search' && Number.isInteger(receipt.receipt.payload?.first_year) && Number.isInteger(receipt.receipt.payload?.last_year) ? [String(receipt.receipt.payload.first_year)+'–'+String(receipt.receipt.payload.last_year)+' · archive query'] : receipt.receipt.operation==='finding_comparison' && Array.isArray(receipt.receipt.payload?.comparison?.dates) ? receipt.receipt.payload.comparison.dates.filter((value:unknown)=>typeof value==='string') : undefined;
      const savedClaim=Array.isArray(now.claims) && now.claims.length===1 ? now.claims[0] : null;
      let value:any=receipt.receipt.payload;
      if(savedClaim && typeof savedClaim.path==='string' && savedClaim.path.startsWith('/')){
        for(const segment of savedClaim.path.slice(1).split('/')){const key=segment.replace(/~1/g,'/').replace(/~0/g,'~');value=value && typeof value==='object' && Object.prototype.hasOwnProperty.call(value,key) ? value[key] : undefined;}
      }else value=undefined;
      const claim=savedClaim && (typeof value==='number' || typeof value==='string') && value===savedClaim.value ? {label:String(savedClaim.label),value:String(value),unit:String(savedClaim.unit || '')}:undefined;
      const mapLink=(['saved-map','saved-heatmap'].includes(now.kind) || (now.kind==='assistant-data-view' && now.viewKind==='heatmap')) ? mapContextLink(snapshot.scope,now.day,now.source,receipt.receipt) : null;
      const comparison=comparisonEvidence(receipt.receipt,now.comparisonPanel);
      setInspectedEvidence({title:comparison?.length===1?comparison[0].title:card?.title || 'Saved assistant evidence',snapshot,dates:comparison?.map(panel=>`${panel.start} – ${panel.end}`) || dates,claim,mapLink,comparison,receipt:receipt.receipt,receiptUrl:api.snapshotReceiptDownload(documentId,ref.snapshotId),panelIndex:now.comparisonPanel});document.querySelector('.whiteboard-more')?.removeAttribute('open');
    }catch(error){if(boardEpoch.current===epoch)setNotice((error as Error).message);}
  };
  const showChallengeOriginal = () => {
    if(!editor || !currentBoard.current || boardBusy.current)return;
    try{
      const {targets,missing}=challengeOriginals(editor.getSceneElements(),editor.getAppState().selectedElementIds,currentBoard.current);
      editor.updateScene({appState:{selectedElementIds:Object.fromEntries(targets.map(item=>[item.id,true]))},captureUpdate:CaptureUpdateAction.NEVER});
      editor.scrollToContent(targets,{fitToContent:true});document.querySelector('.whiteboard-more')?.removeAttribute('open');
      setNotice(missing?'Showing available original items; some are no longer on the board.':'Original material selected.');
    }catch(error){setNotice((error as Error).message);}
  };
  const addParkTimeline = async () => {
    const documentId=currentBoard.current,epoch=boardEpoch.current;
    if(!documentId || !editor || boardBusy.current || addingChart)return;
    setAddingChart(true);setEvidenceError('');
    try{
      const result=await api.parkTimeline(documentId);
      if(boardEpoch.current!==epoch || boardBusy.current || currentBoard.current!==documentId)return;
      const items=editor.getSceneElements();const x=items.length?Math.max(...items.map((item)=>item.x+item.width))+100:100;
      const ref={documentId,datasetId:result.dataset.id,datasetHash:result.dataset.sha256};
      const elements=convertToExcalidrawElements(parkTimeline(result.rows,ref,x,100,()=>`park-${crypto.randomUUID()}`),{regenerateIds:false});
      editor.updateScene({elements:[...items,...elements],captureUpdate:CaptureUpdateAction.IMMEDIATELY});
      editor.scrollToContent(elements,{fitToContent:true});setShowEvidence(false);setNotice('Park satellite comparison added.');
    }catch(error){if(boardEpoch.current===epoch && currentBoard.current===documentId)setEvidenceError((error as Error).message);}
    finally{setAddingChart(false);}
  };
  const startChallenge = async () => {
    const documentId=currentBoard.current,epoch=boardEpoch.current;
    if(!editor || !documentId || boardBusy.current || addingChart)return;
    const selected=editor.getAppState().selectedElementIds;
    const element=editor.getSceneElements().find(item=>selected[item.id] && (item.customData as any)?.fireatlas?.cardId);
    const ref=(element?.customData as any)?.fireatlas;
    if(!element || ref?.documentId!==documentId || !ref.snapshotId || !ref.snapshotHash){setNotice('Select a saved comparison on the board first.');return;}
    setAddingChart(true);
    try{
      if(!(await board.flush()))throw Error('Save the board before comparing.');
      const receipt=await api.snapshotReceipt(documentId,ref.snapshotId);
      const doc=await api.getDocument(documentId);
      if(boardEpoch.current!==epoch || boardBusy.current || currentBoard.current!==documentId)return;
      const current=editor.getSceneElements().find(item=>item.id===element.id);
      const currentRef=(current?.customData as any)?.fireatlas;
      if(!currentRef || currentRef.snapshotId!==ref.snapshotId || currentRef.snapshotHash!==ref.snapshotHash || currentRef.cardId!==ref.cardId || doc.state.cards[ref.cardId]?.snapshot_id!==ref.snapshotId || doc.snapshots?.[ref.snapshotId]?.snapshot_sha256!==ref.snapshotHash)throw Error('This comparison changed. Select its current evidence and try again.');
      const payload=receipt.receipt.payload;
      if(receipt.receipt.operation!=='finding_comparison' || payload?.schema!=='fireatlas-finding-investigation-v1' || !['modis','viirs','adjusted'].includes(payload.selected_series))throw Error('Select a saved two-period finding comparison.');
      const original=payload.selected_series as SeriesName;
      setChallenge({ref:{documentId,cardId:ref.cardId,snapshotId:ref.snapshotId,snapshotHash:ref.snapshotHash},pair:payload.comparison,original,unit:payload.unit});
      setChallengeSeries(original==='viirs'?'modis':'viirs');document.querySelector('.whiteboard-more')?.removeAttribute('open');
    }catch(error){if(boardEpoch.current===epoch)setNotice((error as Error).message);}
    finally{setAddingChart(false);}
  };
  const placeChallenge = async () => {
    const selected=challenge,epoch=boardEpoch.current;
    if(!editor || !selected || boardBusy.current || addingChart || challengeSeries===selected.original)return;
    setAddingChart(true);
    try{
      const doc=await api.getDocument(selected.ref.documentId);
      if(boardEpoch.current!==epoch || boardBusy.current || currentBoard.current!==selected.ref.documentId)return;
      if(doc.state.cards[selected.ref.cardId]?.snapshot_id!==selected.ref.snapshotId || doc.snapshots?.[selected.ref.snapshotId]?.snapshot_sha256!==selected.ref.snapshotHash)throw Error('This comparison changed. Select its current evidence and try again.');
      const items=editor.getSceneElements();const x=items.length?Math.max(...items.map(item=>item.x+item.width))+100:100;
      const elements=convertToExcalidrawElements(challengeComparison(selected.pair,selected.original,challengeSeries,selected.unit,selected.ref,x,100,()=>`cmp-${crypto.randomUUID()}`),{regenerateIds:false});
      editor.updateScene({elements:[...items,...elements],appState:{selectedElementIds:{}},captureUpdate:CaptureUpdateAction.IMMEDIATELY});editor.scrollToContent(elements,{fitToContent:true});
      setChallenge(null);setNotice('Alternative views added.');
    }catch(error){if(boardEpoch.current===epoch)setNotice((error as Error).message);}
    finally{setAddingChart(false);}
  };
  const addChart = async ({ documentId, card, snapshot }: { documentId: string; card: Card; snapshot: Snapshot }) => {
    if (!editor || boardBusy.current || currentBoard.current !== documentId || addingChart) return;
    const requestEpoch = boardEpoch.current;
    setAddingChart(true); setEvidenceError('');
    try {
      const preview = await api.snapshotPreview(documentId, snapshot.id, 'chart');
      const latest = await api.getDocument(documentId);
      if (boardEpoch.current !== requestEpoch || boardBusy.current || currentBoard.current !== documentId) return;
      if (latest.state.cards[card.id]?.snapshot_id !== snapshot.id || preview.snapshot_sha256 !== snapshot.snapshot_sha256) throw Error('This evidence changed. Reopen the evidence list and try again.');
      const items = editor.getSceneElements();
      const x = items.length ? Math.max(...items.map((item) => item.x + item.width)) + 100 : 100;
      const ref = { documentId, cardId: card.id, snapshotId: snapshot.id, snapshotHash: snapshot.snapshot_sha256 };
      const elements = convertToExcalidrawElements(comparisonChart(preview.visual, card.title, ref, x, 100));
      editor.updateScene({ elements: [...items, ...elements], captureUpdate: CaptureUpdateAction.IMMEDIATELY });
      editor.scrollToContent(elements, { fitToContent: true });
      setShowEvidence(false);
    } catch (error) { if (boardEpoch.current === requestEpoch && currentBoard.current === documentId && !boardBusy.current) setEvidenceError((error as Error).message); }
    finally { setAddingChart(false); }
  };
  const addMap = async ({documentId,card,snapshot}:{documentId:string;card:Card;snapshot:Snapshot},heat=false) => {
    if(!editor || boardBusy.current || currentBoard.current!==documentId || addingChart)return;
    const epoch=boardEpoch.current;setAddingChart(true);setEvidenceError('');
    try{
      const day=typeof card.display.day==='string'?card.display.day:undefined;
      const source=['joint','MODIS_SP','VIIRS_SNPP_SP'].includes(String(card.display.source))?String(card.display.source):'joint';
      const preview=heat ? await api.snapshotHeat(documentId,snapshot.id,day,source) : await api.snapshotPreview(documentId,snapshot.id,'map',day,source);
      if(preview.visual?.kind!==(heat?'heat':'map'))throw Error('This saved evidence does not contain the selected map view.');
      if(!heat && !('svg' in preview))throw Error('The saved map preview is unavailable.');
      const rendered=heat ? await renderHeatPreview(preview.visual,documentId,snapshot) : {dataURL:await renderMapPreview((preview as {svg:string;snapshot_sha256:string;visual:any}).svg),background:'Saved map context'};
      const doc=await api.getDocument(documentId);
      if(boardEpoch.current!==epoch || boardBusy.current || currentBoard.current!==documentId)return;
      if(doc.state.cards[card.id]?.snapshot_id!==snapshot.id || preview.snapshot_sha256!==snapshot.snapshot_sha256 || doc.snapshots?.[snapshot.id]?.snapshot_sha256!==snapshot.snapshot_sha256)throw Error('This evidence changed. Reopen the evidence list and try again.');
      const fileId=crypto.randomUUID(),file={id:fileId,mimeType:'image/png',dataURL:rendered.dataURL,created:Date.now()};
      if(new TextEncoder().encode(JSON.stringify(file)).length>1_500_000)throw Error('The map image is too large for this board.');
      const items=editor.getSceneElements(),x=items.length?Math.max(...items.map(item=>item.x+item.width))+100:100;
      const metadata={fireatlas:{documentId,cardId:card.id,snapshotId:snapshot.id,snapshotHash:snapshot.snapshot_sha256,kind:heat?'saved-heatmap':'saved-map',day:preview.visual.day,source:preview.visual.source,bbox:preview.visual.scope.bbox,...(heat?{heatDomain:preview.visual.domain,heatSigmaKm:preview.visual.sigma_km,background:rendered.background}: {})}};
      const elements=convertToExcalidrawElements([{type:'image',x,y:100,width:960,height:540,fileId,status:'saved',customData:metadata} as any]);
      editor.addFiles([file as any]);editor.updateScene({elements:[...items,...elements],captureUpdate:CaptureUpdateAction.IMMEDIATELY});editor.scrollToContent(elements,{fitToContent:true});setShowEvidence(false);setNotice(heat?'Heatmap added to the board.':'Map added to the board.');
    }catch(error){if(boardEpoch.current===epoch && currentBoard.current===documentId)setEvidenceError((error as Error).message);}
    finally{setAddingChart(false);}
  };
  const addEvidence = ({ documentId, card, snapshot }: { documentId: string; card: Card; snapshot: Snapshot }) => {
    if (!editor || !board.document || board.busy || board.document.id !== documentId) return;
    const items = editor.getSceneElements();
    const x = items.length ? Math.max(...items.map((item) => item.x + item.width)) + 80 : 80;
    const facts = snapshot.facts.slice(0, 3).map((fact) => `${fact.label}: ${fact.value ?? 'unavailable'} ${fact.unit}`);
    const text = wrapEvidenceText([card.title, `${snapshot.scope.start} – ${snapshot.scope.end}`, ...facts].join('\n'),20);
    const cardHeight=Math.max(190,40+text.split('\n').length*25);
    const link = new URL(`./studio.html?board=${encodeURIComponent(board.document.id)}`, document.baseURI).href;
    const elements = convertToExcalidrawElements([
      { type: 'rectangle', x, y: 80, width: 420, height: cardHeight, backgroundColor: '#eef4ff', fillStyle: 'solid', strokeColor: '#315fc6', roundness: { type: 3 },
        customData: { fireatlas: { documentId: board.document.id, cardId: card.id, snapshotId: snapshot.id, snapshotHash: snapshot.snapshot_sha256 } } },
      { type: 'text', x: x + 20, y: 100, text, fontSize: 18, fontFamily:2, strokeColor: '#183149', link,
        customData: { fireatlas: { documentId: board.document.id, cardId: card.id, snapshotId: snapshot.id, snapshotHash: snapshot.snapshot_sha256 } } }
    ]);
    editor.updateScene({ elements: [...items, ...elements], captureUpdate: CaptureUpdateAction.IMMEDIATELY });
    editor.scrollToContent(elements, { fitToContent: true });
    setShowEvidence(false);
  };
  return <div className={`whiteboard-shell${board.document ? ' whiteboard-saved' : ''}`}><div className="whiteboard-bar"><div><details className="whiteboard-site-menu" onKeyDown={event=>{if(event.key==='Escape' && event.currentTarget.open){event.currentTarget.open=false;event.currentTarget.querySelector('summary')?.focus();event.stopPropagation();}}}><summary aria-label="Project navigation" title="Project navigation"><svg aria-hidden="true" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M4 6h16M4 12h16M4 18h16"/></svg></summary><nav aria-label="Project navigation"><a href="./">Ignis-Atlassia</a><a href="./atlas.html">Explore</a><a href="./research.html?tab=comparison">Compare</a><a href="./investigate.html?split=true">Maps</a><a href="./studio-excalidraw.html" aria-current="page">Investigation</a><a href="./evidence.html">Data &amp; methods</a><a href="./studio.html">Studio</a></nav></details><strong>Investigation</strong><span role="status">{notice || board.status || status}</span></div>
    <div className="whiteboard-actions">
    {board.document && <><button disabled={interactionBusy} onClick={()=>void board.historyAction('undo')}>Undo</button><button disabled={interactionBusy} onClick={()=>void board.historyAction('redo')}>Redo</button>{sourceAction && <button disabled={interactionBusy || datasetLoading || pdfLoading} onClick={()=>{if(sourceAction==='table')void inspectSelectedDataset();else if(sourceAction==='document')void inspectPdf();else void inspectSelectedEvidence();}}>Open source</button>}{board.historyNeedsReload && <button onClick={()=>void board.retryHistoryReload()}>Reload board</button>}</>}
    {board.available && <><select aria-label="Investigation" disabled={interactionBusy} value={board.document?.id || ''} onChange={(e) => { if (e.target.value) void board.open(e.target.value); }}><option value="">Choose a board</option>{board.boards.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select><button disabled={interactionBusy} onClick={() => { setName(''); setNameMode('create'); }}>New</button>{board.document && <button disabled={interactionBusy} onClick={() => { void showSavedEvidence(); }}>Add evidence</button>}{board.recoveryDrafts.length > 0 && <>{board.recoveryDrafts.length > 1 && <select aria-label="Recoverable draft" value={board.recoveryDrafts.some((item) => item.key === selectedDraft) ? selectedDraft : board.recoveryDrafts[0].key} onChange={(e) => setSelectedDraft(e.target.value)}>{board.recoveryDrafts.map((item, index) => <option key={item.key} value={item.key}>Draft {index + 1}{item.savedAt ? ` · ${new Date(item.savedAt).toLocaleString()}` : ''}</option>)}</select>}<button title="Older drafts are recovered to a new drawing-only board." onClick={() => board.restoreDraft(board.recoveryDrafts.some((item) => item.key === selectedDraft) ? selectedDraft : board.recoveryDrafts[0].key)}>{(board.recoveryDrafts.find((item) => item.key === selectedDraft) || board.recoveryDrafts[0]).baseRevision === board.document?.revision ? 'Restore draft' : 'Recover as new board'}</button></>}{board.conflict ? <button disabled={interactionBusy} onClick={() => { void board.saveCopy(); }}>Save drawing as new board</button> : board.document && board.status && board.status !== 'Saved' && board.status !== 'Saving…' && <button onClick={() => { void board.flush(); }}>Retry save</button>}</>}
    <button disabled={!ready || !editor} onClick={save}>Export</button><ToolbarMenu><button disabled={!editor || interactionBusy} onClick={()=>{setLinkError('');setShowLink(true);document.querySelector('.whiteboard-more')?.removeAttribute('open');}}>Add web link</button>{board.document && <><button disabled={interactionBusy} onClick={() => { setName(board.document?.title || ''); setNameMode('rename'); }}>Rename</button><button disabled={interactionBusy} onClick={board.copyPreviousDraft}>Copy previous drawing</button><label className="whiteboard-button">Import CSV<input aria-label="Import CSV" type="file" accept=".csv,text/csv" disabled={!editor || interactionBusy || datasetLoading} onChange={(e) => { const file=e.target.files?.[0]; e.currentTarget.value=''; if(file) void importCsv(file); }} /></label><label className="whiteboard-button">Import PDF<input aria-label="Import PDF" type="file" accept=".pdf,application/pdf" disabled={!editor || interactionBusy || pdfLoading} onChange={(e) => { const file=e.target.files?.[0]; e.currentTarget.value=''; if(file) void importPdf(file); }} /></label><button disabled={interactionBusy || pdfLoading} onClick={() => void inspectPdf()}>Inspect selected document</button><button disabled={interactionBusy || pdfLoading} onClick={() => void listPdfs()}>Saved documents</button><button disabled={interactionBusy || addingChart} onClick={() => void startChallenge()}>Challenge selected comparison</button><button disabled={interactionBusy} onClick={() => void inspectSelectedEvidence()}>Inspect selected evidence</button><button disabled={interactionBusy} onClick={showChallengeOriginal}>Find original material</button><button disabled={interactionBusy || datasetLoading} onClick={inspectSelectedDataset}>Inspect selected table</button><button disabled={interactionBusy || datasetLoading} onClick={() => void showDatasets()}>Saved tables</button><button disabled={interactionBusy || exporting} onClick={() => void saveReport()}>Export HTML report</button><button disabled={interactionBusy || exporting} onClick={() => void savePackage()}>{exporting ? 'Preparing package…' : 'Export investigation package (includes AI conversation)'}</button></>}<button disabled={!editor || interactionBusy} onClick={() => void saveFigure('png')}>Export figure as PNG</button><button disabled={!editor || interactionBusy} onClick={() => void saveFigure('svg')}>Export figure as SVG</button><label className="whiteboard-button">Add drawing<input aria-label="Add Excalidraw drawing" type="file" accept=".excalidraw,.json" disabled={!editor || interactionBusy} onChange={(e) => { void load(e.target.files?.[0]); e.currentTarget.value = ''; }} /></label>{board.available && <><label className="whiteboard-button">Restore investigation package<input aria-label="Restore investigation package" type="file" accept=".zip" disabled={!editor || interactionBusy} onChange={(e) => { const file = e.target.files?.[0]; e.currentTarget.value = ''; if (file) { document.querySelector('.whiteboard-more')?.removeAttribute('open'); void board.restorePackage(file).then(() => setNotice('Investigation restored as a new board.')).catch((error) => setNotice((error as Error).message)); } }} /></label><button disabled={interactionBusy || issuingRecovery} onClick={() => { setRecoveryError(''); setIssuedRecovery(''); setCreatingRecovery(true); document.querySelector('.whiteboard-more')?.removeAttribute('open'); }}>Create recovery token</button><button disabled={issuingRecovery} onClick={() => { setRecoveryError(''); setRecoveryToken(''); setRecovering(true); document.querySelector('.whiteboard-more')?.removeAttribute('open'); }}>Recover Studio access</button></>}<a href="./park-example.html">Open Park example</a><a href={board.document ? `./studio.html?board=${encodeURIComponent(board.document.id)}` : './studio.html'}>Evidence boards</a></ToolbarMenu></div></div>
    <div className="whiteboard-companion-dock" aria-label="AI companion">
      {board.document && editor ? <WhiteboardAssistant key={board.document.id} editor={editor} documentId={board.document.id} initialOpen={assistantOnboarding} flush={board.flush} busy={interactionBusy} onOpenSource={match=>void openAssistantSource(match)} onAddEvidence={()=>void showSavedEvidence()} />
        : <WhiteboardAssistantWelcome ready={Boolean(board.available && editor && !interactionBusy)} boards={board.boards} status={board.status || status} onStart={()=>{setAssistantOnboarding(true);setName('');setNameMode('create');}} onOpen={id=>{setAssistantOnboarding(true);void board.open(id);}} />}
    </div>
    {showLink && <form className="whiteboard-evidence" aria-label="Add web link" onSubmit={event=>{event.preventDefault();addLink();}}><strong>Add a web link</strong><label htmlFor="link-address">Web address</label><input id="link-address" type="url" required autoFocus maxLength={2048} placeholder="https://…" value={linkAddress} onChange={event=>setLinkAddress(event.target.value)}/><label htmlFor="link-title">Title <span>(optional)</span></label><input id="link-title" maxLength={120} value={linkTitle} onChange={event=>setLinkTitle(event.target.value)} placeholder="Name this source"/>{linkError && <p role="alert">{linkError}</p>}<button type="submit" disabled={interactionBusy}>Add to board</button><button type="button" onClick={()=>setShowLink(false)}>Cancel</button></form>}
    {nameMode && <form className="whiteboard-evidence" aria-label={nameMode === 'create' ? 'New investigation' : 'Rename investigation'} onSubmit={(event) => { event.preventDefault(); const title = name.trim(); if (!title) return; if (nameMode === 'create') void board.create(title); else void board.rename(title); setNameMode(null); }}><label htmlFor="investigation-name">{nameMode === 'create' ? 'Name your investigation' : 'Rename investigation'}</label><input id="investigation-name" autoFocus maxLength={120} value={name} onChange={(event) => setName(event.target.value)} /><button type="submit">Save</button><button type="button" onClick={() => setNameMode(null)}>Cancel</button></form>}
    {creatingRecovery && <section className="whiteboard-evidence" role="dialog" aria-label="Create recovery token"><strong>Save access to your boards</strong>{issuedRecovery ? <><p>Save this token somewhere private. It can restore access to your boards on this server.</p><label htmlFor="issued-recovery">Recovery token</label><input id="issued-recovery" type="text" readOnly value={issuedRecovery} onFocus={event=>event.currentTarget.select()} /><button onClick={()=>{setIssuedRecovery('');setCreatingRecovery(false);}}>Done</button></> : <><p>Creating a token replaces any previous recovery token for this account.</p>{recoveryError && <p role="alert">{recoveryError}</p>}<button disabled={issuingRecovery} onClick={()=>{setIssuingRecovery(true);setRecoveryError('');void api.recovery().then(result=>setIssuedRecovery(result.recovery)).catch(error=>setRecoveryError((error as Error).message)).finally(()=>setIssuingRecovery(false));}}>{issuingRecovery?'Creating…':'Create token'}</button><button disabled={issuingRecovery} onClick={()=>setCreatingRecovery(false)}>Cancel</button></>}</section>}
    {recovering && <form className="whiteboard-evidence" aria-label="Recover Studio access" onSubmit={(event) => { event.preventDefault(); setRecoveryError(''); void board.recoverAccess(recoveryToken).then(() => { setRecoveryToken(''); setRecovering(false); setNotice('Access restored. Choose an investigation.'); }).catch((error) => setRecoveryError((error as Error).message)); }}><label htmlFor="studio-recovery">Studio recovery token</label><input id="studio-recovery" type="password" autoComplete="off" value={recoveryToken} onChange={(event) => setRecoveryToken(event.target.value)} />{recoveryError && <p role="alert">{recoveryError}</p>}<button type="submit" disabled={!recoveryToken || interactionBusy}>Recover access</button><button type="button" onClick={() => { setRecoveryToken(''); setRecovering(false); }}>Cancel</button></form>}
    {showEvidence && <div className="whiteboard-evidence" role="dialog" aria-label="Add saved evidence"><strong>Saved evidence</strong><button aria-label="Close saved evidence" onClick={() => setShowEvidence(false)}>Close</button>{evidenceError && <p role="alert">{evidenceError}</p>}<button disabled={addingChart} onClick={()=>void addParkTimeline()}>Add Park Fire satellite comparison</button>{evidence.length ? evidence.map((item) => <div key={item.card.id}><button disabled={addingChart} onClick={() => addEvidence(item)}>{item.card.title}</button>{item.card.type === 'chart' && ['finding_comparison', 'comparability'].includes(item.snapshot.operation) && <button disabled={addingChart} onClick={() => void addChart(item)}>Add chart</button>}{item.card.type === 'map' && <button disabled={addingChart} onClick={() => void addMap(item)}>Add cell map</button>}{item.card.type === 'map' && item.snapshot.operation === 'replay' && <button disabled={addingChart} onClick={() => void addMap(item,true)}>Add heatmap</button>}</div>) : <p>Save a chart or map to this investigation in Studio to add it here.</p>}</div>}
    {challenge && <section className="whiteboard-evidence" role="dialog" aria-label="Compare alternative views"><strong>Challenge this comparison</strong><p>Compare the saved interpretation with another sensor or estimate, using the same two periods.</p><label htmlFor="challenge-series">Alternative view</label><select id="challenge-series" value={challengeSeries} onChange={(event)=>setChallengeSeries(event.target.value as SeriesName)}>{challenge.original!=='modis' && <option value="modis">MODIS observed</option>}{challenge.original!=='viirs' && <option value="viirs">S-NPP observed</option>}{challenge.original!=='adjusted' && <option value="adjusted">Adjusted MODIS estimate</option>}</select><button disabled={addingChart} onClick={()=>void placeChallenge()}>Add side-by-side views</button><button onClick={()=>setChallenge(null)}>Cancel</button></section>}
    {inspectedEvidence && <section className="whiteboard-dataset" aria-label="Evidence details"><div><strong>{inspectedEvidence.title}</strong><button aria-label="Close evidence details" onClick={()=>setInspectedEvidence(null)}>Close</button></div><p>{inspectedEvidence.dates?.length ? inspectedEvidence.dates.join(" · ") : inspectedEvidence.snapshot.scope.periods?.length ? inspectedEvidence.snapshot.scope.periods.map(period=>`${period.start} – ${period.end}`).join(" · ") : `${inspectedEvidence.snapshot.scope.start} – ${inspectedEvidence.snapshot.scope.end}`}</p><p>{inspectedEvidence.snapshot.method.id} · {inspectedEvidence.snapshot.unit}</p>{inspectedEvidence.claim && <p><strong>{inspectedEvidence.claim.label}:</strong> {inspectedEvidence.claim.value} {inspectedEvidence.claim.unit}</p>}{inspectedEvidence.mapLink && <p><a href={inspectedEvidence.mapLink} target="_blank" rel="noopener noreferrer">Open current interactive map ↗</a></p>}{inspectedEvidence.comparison?.map((panel,index)=><div key={index}><p><strong>{panel.title}</strong> · {panel.product}{panel.rank ? ` · rank ${panel.rank}` : ''}{panel.rankMetric ? ` · ranked by ${panel.rankMetric}` : ''}</p><p>Search: {panel.searchStart} – {panel.searchEnd} UTC. {panel.cells} occupied 1 km cells · {panel.records} detection records · {panel.delta===null?'difference unavailable':`${panel.delta>0?'+':''}${panel.delta} cells vs reference`}.</p>{panel.tiedDates.length>1 && <p>Tied dates: {panel.tiedDates.join(' · ')}</p>}{panel.weather ? <><p>{panel.weather.source} · {panel.weather.start} – {panel.weather.end} UTC · point {panel.weather.latitude}, {panel.weather.longitude}</p><p>{panel.weather.note}</p>{panel.weather.url && <p><a href={panel.weather.url} target="_blank" rel="noopener noreferrer">Open weather query ↗</a></p>}</>:<p>Verified weather context unavailable or not requested.</p>}</div>)}{inspectedEvidence.receiptUrl && <a href={inspectedEvidence.receiptUrl} download="comparison-evidence.json">Download full evidence</a>}<div className="whiteboard-dataset-scroll"><table><thead><tr><th>Measure</th><th>Value</th></tr></thead><tbody>{inspectedEvidence.snapshot.facts.filter(fact=>inspectedEvidence.panelIndex===undefined || fact.path.startsWith(`/panels/${inspectedEvidence.panelIndex}/`)).map((fact,index)=><tr key={index}><td>{fact.label}</td><td>{fact.value ?? "Unavailable"} {fact.unit}</td></tr>)}</tbody></table></div></section>}
    {pdfSource && board.document && <PdfReader source={pdfSource} downloadUrl={api.sourceDocumentUrl(board.document.id,pdfSource.id)} onClose={()=>setPdfSource(null)} onPlace={placePdf} />}
    {pdfList && <section className="whiteboard-evidence" aria-label="Saved documents"><strong>Saved documents</strong><button onClick={()=>setPdfList(null)}>Close</button>{pdfList.length ? pdfList.map((item)=><button key={item.id} disabled={pdfLoading} onClick={()=>void openPdf(item)}>{item.name}</button>) : <p>No documents saved yet.</p>}</section>}
    {datasetList && <section className="whiteboard-evidence" aria-label="Saved tables"><strong>Saved tables</strong><button onClick={() => setDatasetList(null)}>Close</button>{datasetList.length ? datasetList.map((item) => <button key={item.id} disabled={datasetLoading} onClick={() => void placeSavedDataset(item.id,item.sha256)}>{item.name} · {item.row_count} rows</button>) : <p>No tables saved yet.</p>}</section>}
    {dataset && board.document && <section className="whiteboard-dataset" aria-label="Table inspector"><div><strong>{dataset.name}</strong><button aria-label="Close table inspector" onClick={()=>{setDataset(null);setEditingScatter(null);}}>Close</button></div><p>{dataset.row_count} rows · {dataset.columns.length} columns</p>{inspectedSummary && <p><strong>{inspectedSummary.column} · {inspectedSummary.metric.replaceAll("_"," ")}:</strong> {inspectedSummary.value ?? "Unavailable"}</p>}<div className="whiteboard-dataset-scroll"><table><thead><tr>{dataset.columns.map((column,index)=><th key={index}>{column}</th>)}</tr></thead><tbody>{dataset.preview.map((row,index)=><tr key={index} aria-label={highlightedRecord===dataset.offset+index ? `Selected CSV record ${highlightedRecord+2}` : undefined} style={highlightedRecord===dataset.offset+index ? {backgroundColor:"#fff0bd"} : undefined}>{row.map((value,column)=><td key={column}>{value}</td>)}</tr>)}</tbody></table></div><div><button disabled={datasetLoading || dataset.offset===0} onClick={()=>void inspectDataset(dataset.id,dataset.sha256,Math.max(0,dataset.offset-10))}>Previous</button><span> Rows {dataset.row_count ? dataset.offset+1 : 0}–{Math.min(dataset.offset+dataset.preview.length,dataset.row_count)} </span><button disabled={datasetLoading || dataset.offset+dataset.preview.length>=dataset.row_count} onClick={()=>void inspectDataset(dataset.id,dataset.sha256,dataset.offset+10)}>Next</button><a href={api.datasetDownload(board.document.id,dataset.id)}>Download CSV</a></div>{editingScatter && editingScatter.datasetId===dataset.id && <ScatterValues documentId={board.document.id} datasetId={editingScatter.datasetId} hash={editingScatter.hash} x={editingScatter.x} y={editingScatter.y} onShowRecord={offset=>void inspectDataset(dataset.id,dataset.sha256,offset,true)} onAddPage={(data,page)=>void addScatterValues(data,page)} />}<div className="whiteboard-scatter"><strong>{editingScatter ? "Edit scatter plot" : "Plot two columns"}</strong><label>X axis <select value={scatterX} onChange={(event)=>setScatterX(event.target.value)}><option value="">Choose column</option>{dataset.columns.map((column)=><option key={column} value={column}>{column}</option>)}</select></label><label>Y axis <select value={scatterY} onChange={(event)=>setScatterY(event.target.value)}><option value="">Choose column</option>{dataset.columns.map((column)=><option key={column} value={column}>{column}</option>)}</select></label><button disabled={datasetLoading || !scatterX || !scatterY || scatterX===scatterY} onClick={()=>void addScatter()}>{editingScatter ? "Update scatter plot" : "Add scatter plot"}</button></div><div className="whiteboard-scatter"><strong>Compare groups</strong><label>Group by <select disabled={datasetLoading} value={groupColumn} onChange={event=>{setGroupColumn(event.target.value);setGroups(null);}}><option value="">Choose column</option>{dataset.columns.map(column=><option key={column} value={column}>{column}</option>)}</select></label><label>Average <select disabled={datasetLoading} value={groupValue} onChange={event=>{setGroupValue(event.target.value);setGroups(null);}}><option value="">Choose column</option>{dataset.columns.map(column=><option key={column} value={column}>{column}</option>)}</select></label><button disabled={datasetLoading || !groupColumn || !groupValue || groupColumn===groupValue} onClick={()=>void compareGroups()}>Compare</button></div>{groups && <div className="whiteboard-dataset-scroll"><table><thead><tr><th>Group</th><th>Mean</th><th>Numeric / rows</th><th>Missing / nonnumeric</th></tr></thead><tbody>{groups.groups.map((item,index)=>{const focused=groupIsFocused(groupFocus,dataset.id,groups.group_column,groups.value_column,item.group);return <tr key={index} aria-label={focused ? `Selected group ${item.group ?? "blank"}` : undefined} style={focused ? {backgroundColor:"#fff0bd"} : undefined}><td>{item.group ?? "(blank group)"}</td><td>{item.mean ?? "Unavailable"}</td><td>{item.numeric_count} / {item.rows}</td><td>{item.missing_count} / {item.non_numeric_count}</td></tr>;})}</tbody></table><button onClick={addGroupTable}>Add grouped table</button><button onClick={addGroupChart}>Add grouped chart</button></div>}</section>}
    <div className="whiteboard-canvas" aria-busy={interactionBusy} inert={interactionBusy || undefined} onDragOverCapture={event=>{if(mightContainSources(event.dataTransfer.items)){event.preventDefault();event.dataTransfer.dropEffect='copy';}}} onDropCapture={dropSources}><Excalidraw excalidrawAPI={setEditor} initialData={initial || undefined} onPointerDown={board.onPointerDown} onPointerUp={board.onPointerUp} onChange={(elements, appState, files) => {
    if (!editor) return;
    if (board.loading.current) return;
    setSourceAction(selectedSource(elements,appState.selectedElementIds,board.document?.id || null));
    if (board.document) { board.onScene(JSON.parse(serializeAsJSON(elements, appState, files, 'local')),Boolean(appState.editingTextElement),{scrollX:appState.scrollX,scrollY:appState.scrollY,zoom:appState.zoom}); return; }
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => { try { localStorage.setItem(storageKey, serializeAsJSON(elements, appState, files, 'local')); setStatus('Saved in this browser'); } catch { setStatus('Could not save in this browser. Export your board to keep a copy.'); } }, 800);
  }} UIOptions={{ canvasActions: { loadScene: false } }} /></div></div>;
}
createRoot(document.getElementById('excalidraw-root')!).render(<Continuation />);
