import {PublicReadingPanel} from './PublicReadingPanel';
import {ResearchBriefPanel} from './ResearchBriefPanel';
import type {ResearchAnswer,PublicReadingReport} from '../types';
import {ResearchTeamPanel, type ResearchTeamReport} from './ResearchTeamPanel';
import { useEffect, useRef, useState } from 'react';
import { CaptureUpdateAction, convertToExcalidrawElements, exportToBlob, getCommonBounds, newElementWith } from '@excalidraw/excalidraw';
import type { ExcalidrawImperativeAPI } from '@excalidraw/excalidraw/types';
import { api, uid } from '../api';
import { diagramShapes, type Diagram } from '../lib/whiteboardDiagram';
import { comparisonChart } from '../lib/whiteboardChart';
import { renderScatter } from '../lib/csvScatter';
import { assistantChallenge, type ChallengeSource, type SourceBinding } from '../lib/assistantChallenge';
import { challengeComparison, type SeriesName } from '../lib/challengeComparison';
import { groupChart } from '../lib/groupChart';
import { arrangeSelection } from '../lib/arrangeSelection';
import { explanationElements } from '../lib/assistantExplanation';
import { formatClaim } from '../lib/formatClaim';
import { wrapCardText } from '../lib/wrapCardText';
import { boardNoteIds } from '../lib/boardNoteIds';
import { boardDataset } from '../lib/boardDataset';
import { connectSelection } from '../lib/connectSelection';
import { figureSelection } from '../lib/figureSelection';
import { renderHeatPreview, renderMapPreview } from '../lib/mapPreview';
import { requestsMapLabels, noteText, labelText } from '../lib/boardActionIntent';
import { heatMapLabels } from '../lib/heatMapGeometry';
import { animatePlacement, placementCanvas } from '../lib/assistantPlacement';
import { comparisonBoard, type ComparisonVisual } from '../lib/comparisonBoard';

const POLL_TIMEOUT_MS = 600_000;
const POLL_REQUEST_TIMEOUT_MS = 10_000;

/** Browser speech support is optional; every voice feature degrades to typing. */
type Recognizer = { start():void; stop():void; abort():void; lang:string; interimResults:boolean; continuous:boolean; onresult:((event:any)=>void)|null; onend:(()=>void)|null; onerror:((event:any)=>void)|null };
const recognizerFactory = ():(new()=>Recognizer)|null => typeof window==='undefined' ? null : ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition || null);
const canSpeak = () => typeof window!=='undefined' && 'speechSynthesis' in window && typeof SpeechSynthesisUtterance!=='undefined';
export function spokenText(text:string, limit=420):string {
  const plain=text.replace(/\s+/g,' ').trim();
  if(plain.length<=limit)return plain;
  const cut=plain.slice(0,limit),end=Math.max(cut.lastIndexOf('. '),cut.lastIndexOf('? '),cut.lastIndexOf('! '));
  return end>120?cut.slice(0,end+1):cut.replace(/\s+\S*$/,'')+'…';
}
const SUGGESTIONS:{label:string;question:string;needsSelection?:boolean}[]=[
  {label:'Find sources',question:'Find papers on wildfire thermal remote sensing and fuel moisture.'},
  {label:'Explain this',question:'Explain the main pattern in plain language and suggest the most useful next investigation.'},
  {label:'Diagram it',question:'Create a diagram of this.',needsSelection:false},
  {label:'What is missing?',question:'What is missing or uncertain here, and what should I check next?'},
  {label:'Tidy up',question:'Organize the selected items.',needsSelection:true},
  {label:'Label heatmap',question:'Label the thermal detections on the heatmap.'},
  {label:'Compare maps',question:'Compare the selected saved heatmaps with a shared scale and weather context.',needsSelection:true},
  {label:'Peak days × 3',question:'Compare the busiest day in each of the last three completed years for Rajshahi, Bangladesh, and include weather context.'},
];

type ChartBinding = { documentId: string; cardId?: string; snapshotId: string; snapshotHash: string; title: string };
type ClaimBinding = {documentId:string;cardId?:string;snapshotId:string;snapshotHash:string};
type ScatterBinding = { documentId:string; datasetId:string; datasetHash:string; xColumn:string; yColumn:string };
type GroupBinding = {documentId:string;datasetId:string;datasetHash:string;groupColumn:string;valueColumn:string};
export type SourceMatch = {kind:'csv'|'pdf';name:string;source_id:string;source_sha256:string;excerpt:string;row_offset?:number;column?:string;page?:number};
type ScientificView = {kind:string;result_id:string;binding?:ClaimBinding;title?:string;referenceUrl?:string};
type WebReference = {id?:string;title:string;url:string;snippet:string;provider:string};
type Answer = { public_readings?:PublicReadingReport[]; research_answer?:ResearchAnswer; research_team?:ResearchTeamReport; web_sources?:WebReference[]; question?:string; data_views?:ScientificView[]; view_options?:{label:string;detail:string;question:string;action?:string}[]; provider?:string; model?:string; title?: string; kind?: string; summary?: string; interpretation?: string; ai_wording_unavailable?:boolean; diagram?: Diagram | null; visualizations?: { kind: string; binding?: ChartBinding | ScatterBinding | GroupBinding }[]; claims?: { label: string; value: unknown; unit?: string; result_id?: string; path?: string; binding?:ClaimBinding; source_binding?:SourceBinding }[]; limitations?: string[]; source_matches?:SourceMatch[] };

export function wrapExplanation(text: string, width = 58): string {
  return text.split('\n').map((line) => {
    const words = line.split(/\s+/).filter(Boolean);
    const lines: string[] = [];
    let current = '';
    for (const word of words) {
      if (current && current.length + word.length + 1 > width) { lines.push(current); current = ''; }
      // Long unbroken strings are kept intact, so identifiers are never truncated.
      current += (current ? ' ' : '') + word;
    }
    if (current) lines.push(current);
    return lines.join('\n');
  }).join('\n');
}

/** Evidence cards have a fixed width; break long tokens without dropping characters. */
export function wrapEvidenceText(text:string,width=33):string {
  return wrapCardText(text,width);
}

export function requestsGroupedChart(text:string):boolean {
  return ((/\b(create|make|draw|add|plot|build)\b/i.test(text) && /\b(chart|graph|plot)\b/i.test(text)) || /\b(?:and|then)\s+chart\b/i.test(text)) && !/\b(don't|do not|never|without|avoid|not)\b/i.test(text);
}
export function requestsDiagram(text:string):boolean {
  return ((/\b(create|make|draw|add|build)\b/i.test(text) && /\b(diagram|flowchart|flow chart)\b/i.test(text)) || /\b(?:and|then)\s+diagram\b/i.test(text) || /^\s*(?:please\s+)?diagram\b/i.test(text)) && !/\b(don't|do not|never|without|avoid|not)\b/i.test(text);
}
export function requestsOrganize(text:string):boolean {
  return /^\s*(?:please\s+)?(?:organize|organise|arrange|tidy)\b/i.test(text) && /\b(selection|selected|these|items|objects|shapes|notes|board|everything)\b/i.test(text) && !/\b(don't|do not|never|without|avoid|not)\b/i.test(text);
}
export function requestsWholeBoardOrganization(text:string):boolean {
  return requestsOrganize(text) && /^\s*(?:please\s+)?(?:organize|organise|arrange|tidy)\s+(?:(?:(?:the|this)\s+)?(?:entire\s+|whole\s+)?board|everything|all\s+(?:items|objects))\b/i.test(text);
}
export function requestsConnectSelection(text:string):boolean {
  return /^\s*(?:please\s+)?(?:connect|link)\s+(?:these|the selected|selected)\b/i.test(text) && !/\b(don't|do not|never|without|avoid|not)\b/i.test(text);
}
export function requestsVisualInspection(text:string):boolean {
  return /\b(?:look at|inspect|describe|examine|read|explain)\s+(?:(?:this|the|selected|these|my|board)\s+){0,3}(?:image|picture|drawing|sketch|visual|diagram|chart)\b/i.test(text) ||
    /\bwhat\b[^.!?]*\b(?:image|picture|drawing|sketch|visual|diagram|chart)\b[^.!?]*\b(?:show|shows|mean|means)\b/i.test(text);
}

function sourceContent(item:any):string {
  return JSON.stringify({id:item.id,type:item.type,text:item.text,originalText:item.originalText,
    containerId:item.containerId,frameId:item.frameId,customData:item.customData,link:item.link,fileId:item.fileId,isDeleted:item.isDeleted});
}

/** Assistant results remain attached to the document and selection captured at submission. */
export function WhiteboardAssistant({ editor, documentId, flush, busy, onOpenSource, onAddEvidence, initialOpen=false }: {
  editor: ExcalidrawImperativeAPI; documentId: string; flush: () => Promise<boolean>; busy: boolean;
  onOpenSource?: (match:SourceMatch) => void;
  onAddEvidence?: () => void; initialOpen?: boolean;
}) {
  const [message, setMessage] = useState('');
  const lastQuestion=useRef('');
  const [result, setResult] = useState<Answer | null>(null);
  const [status, setStatus] = useState('');
  const [working, setWorking] = useState(false);
  const [researchTeam,setResearchTeam]=useState(false);
  const [activity,setActivity]=useState<{id:number;name:string;message:string}[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [placing, setPlacing] = useState(false);
  const [open, setOpen] = useState(initialOpen);
  const [watching, setWatching] = useState(false);
  const [listening, setListening] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [voiceReply, setVoiceReply] = useState(()=>{try{return window.localStorage.getItem('fireatlas-assistant-voice')==='on';}catch{return false;}});
  const [selectedCount, setSelectedCount] = useState(0);
  const [interim, setInterim] = useState('');
  const [conversation, setConversation] = useState<{question:string;title:string;summary:string;public_readings?:PublicReadingReport[];research_answer?:ResearchAnswer;research_team?:ResearchTeamReport;web_sources?:WebReference[];claims?:{label:string;value:string|number;unit:string}[]}[]>([]);
  const [conversationError, setConversationError] = useState(false);
  const [conversationRevision, setConversationRevision] = useState(0);
  const [automaticChart, setAutomaticChart] = useState(false);
  const [automaticDiagram, setAutomaticDiagram] = useState(false);
  const [automaticExplanation, setAutomaticExplanation] = useState(false);
  const [cue, setCue] = useState<{ids:string[]; phase:'reading'|'placed'|'moved'|'connected'|'pointing'} | null>(null);
  const recognizer = useRef<Recognizer|null>(null);
  const voiceRef = useRef(false);
  const askRef = useRef<(challenge?:boolean,spoken?:string)=>Promise<void>>(async()=>undefined);
  const cueNode = useRef<HTMLDivElement>(null);
  const launcherNode = useRef<HTMLButtonElement>(null);
  const instance = useRef(uid('whiteboard'));
  const generation = useRef(0);
  const run = useRef<{ documentId: string; id: string } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollController = useRef<AbortController | null>(null);
  const selection = useRef<string[]>([]);
  const selectedElements = useRef<string[]>([]);
  const sourceFingerprint = useRef<Map<string,string>>(new Map());
  const sourceContainers = useRef<Set<string>>(new Set());
  const wholeBoardNotes = useRef(false);
  const boardSourceIds = useRef<string[]>([]);
  const visualFiles = useRef<Map<string,string>>(new Map());
  const visualElements = useRef<Map<string,string>>(new Map());
  const diagramElementIds = useRef<string[]>([]);
  const dataViewElements = useRef<{id:string;kind:string;snapshotHash?:string}[]>([]);
  const datasetSelection = useRef<{datasetId:string;datasetHash:string} | null>(null);
  const boardDatasetSelection = useRef<{datasetId:string;datasetHash:string} | null>(null);
  const sourceSelection = useRef<{sourceDocumentId:string;sourceDocumentHash:string;page:number} | null>(null);
  const switching = useRef(busy);
  switching.current = busy;

  useEffect(() => {
    if (!cue || !cueNode.current) return;
    let frame = 0;
    const update = () => {
      const node=cueNode.current, canvas=document.querySelector('.whiteboard-canvas');
      const item=editor.getSceneElements().find(element=>cue.ids.includes(element.id) && !element.isDeleted);
      if (node && canvas && item) {
        const rect=canvas.getBoundingClientRect(), state=editor.getAppState(), zoom=state.zoom?.value || 1;
        const x=rect.left+(item.x+item.width/2+state.scrollX)*zoom;
        const y=rect.top+(item.y+item.height/2+state.scrollY)*zoom;
        const visible=x>=rect.left && x<=rect.right && y>=rect.top && y<=rect.bottom;
        node.style.opacity=visible?'1':'0';
        node.classList.toggle('near-bottom',y>rect.bottom-42);
        node.classList.toggle('near-right',x>rect.right-130);
        node.style.transform=`translate3d(${x}px,${y}px,0)`;
      } else if(node) node.style.opacity='0';
      frame=requestAnimationFrame(update);
    };
    frame=requestAnimationFrame(update);
    const expiry=cue.phase!=='reading'?window.setTimeout(()=>setCue(null),3500):null;
    return ()=>{cancelAnimationFrame(frame);if(expiry!==null)window.clearTimeout(expiry);};
  },[cue,editor]);

  useEffect(() => {
    if (!open) return;
    let active = true;
    setConversationError(false);
    api.jarvisConversation(documentId).then(data => {if(active)setConversation(data.turns);})
      .catch(() => {if(active)setConversationError(true);});
    return () => {active=false;};
  }, [documentId,open,conversationRevision]);

  useEffect(() => {
    generation.current += 1;
    setResult(null); setStatus(''); setWorking(false); setChartLoading(false);setResearchTeam(false);setActivity([]);
    setCue(null); setWatching(false); setPlacing(false);
    diagramElementIds.current = [];dataViewElements.current=[];
    return () => {
      generation.current += 1;
      if (timer.current) clearTimeout(timer.current);
      pollController.current?.abort();pollController.current=null;
      const active = run.current; run.current = null;
      if (active) void api.jarvisCancel(active.documentId, active.id).catch(() => undefined);
    };
  }, [documentId]);

  type Scene = NonNullable<Parameters<ExcalidrawImperativeAPI['updateScene']>[0]['elements']>;
  const place = async (before:Scene, next:Scene, focus:Scene, options:{
    phase?:'placed'|'moved'|'connected';
    clearSelection?:boolean;
    viewportZoomFactor?:number;
    fit?:Scene;
    files?:Parameters<ExcalidrawImperativeAPI['addFiles']>[0];
  }={}) => {
    if(!focus.length)return true;
    const request=generation.current;
    const current=()=>generation.current===request && !switching.current;
    const canvas=placementCanvas(launcherNode.current);
    if(canvas){
      const original=JSON.stringify(before);
      const origin=(cueNode.current?.getBoundingClientRect() || launcherNode.current!.getBoundingClientRect());
      const files={...editor.getFiles(),...Object.fromEntries((options.files || []).map(file=>[file.id,file]))};
      setCue(null);setOpen(false);setWatching(true);setPlacing(true);
      launcherNode.current?.focus({preventScroll:true});
      try {
        await animatePlacement({editor,canvas,focus,files,origin:{x:origin.left,y:origin.top},
          label:options.phase==='connected'?'Connecting':options.phase==='moved'?'Arranging':'Drawing',
          current,viewportZoomFactor:options.viewportZoomFactor,preview:options.phase!=='moved'});
      } finally {setPlacing(false);}
      if(!current())return false;
      if(JSON.stringify(editor.getSceneElements())!==original){
        setOpen(true);
        throw Error('The board changed while drawing. Ask again to place the result.');
      }
    }
    if(!current())return false;
    if(options.files?.length)editor.addFiles(options.files);
    editor.updateScene({elements:next,...(options.clearSelection?{appState:{selectedElementIds:{}}}:{}),captureUpdate:CaptureUpdateAction.IMMEDIATELY});
    if(!canvas && options.phase!=='moved' && options.phase!=='connected'){
      editor.scrollToContent(options.fit || focus,{fitToContent:true,viewportZoomFactor:options.viewportZoomFactor});
    }
    setCue({ids:[focus[0].id],phase:options.phase || 'placed'});
    return true;
  };

  const pinWebSources = async (sources:WebReference[]) => {
    const scene=editor.getSceneElements();
    const startX=Math.max(16,...scene.map(item=>item.x+item.width))+84;
    const references=sources.slice(0,6).flatMap((source,index)=>{
      let url:URL;
      try { url=new URL(source.url); } catch { return []; }
      if(url.protocol!=='https:' || url.username || url.password)return [];
      return [{type:'rectangle' as const,x:startX+(index%2)*405,y:100+Math.floor(index/2)*190,width:380,height:164,
        roundness:{type:3 as const},backgroundColor:'#edf7f3',fillStyle:'solid' as const,strokeColor:'#426e60',link:url.href,
        label:{text:wrapCardText(source.provider+' · Public reference\n'+source.title,39),fontSize:16,fontFamily:2}}];
    });
    const objects=convertToExcalidrawElements(references);
    if(objects.length && await place(scene,[...scene,...objects],objects))setStatus('Public references pinned. Use Undo to remove them.');
  };

  const applyBoardAction = async (question:string,selected:Record<string,boolean>,current:()=>boolean) => {
    const scene=editor.getSceneElements();
    const label=labelText(question),text=label || noteText(question);
    if(text){
      const anchors=scene.filter(item=>selected[item.id] && !item.isDeleted);
      if(label && anchors.length!==1)throw Error('Select one board object to label.');
      const anchor=anchors[0];
      if(label && anchor){
        const caption=convertToExcalidrawElements([{type:'text',x:anchor.x,y:anchor.y-29,text,fontSize:17,fontFamily:2,strokeColor:'#143832'}]);
        if(await place(scene,[...scene,...caption],caption,{fit:[anchor,...caption]}))setStatus('Label added. Use Undo to remove it.');
        return;
      }
      const x=anchor ? anchor.x+anchor.width+48 : Math.max(52,...scene.map(item=>item.x+item.width))+48;
      const wrapped=wrapCardText(text,37);
      const note=convertToExcalidrawElements([{type:'rectangle',x,y:anchor?.y ?? 100,width:350,height:Math.max(100,42+wrapped.split('\n').length*23),
        roundness:{type:3},backgroundColor:'#fff3c9',fillStyle:'solid',strokeColor:'#b68f44',label:{text:wrapped,fontSize:17,fontFamily:2}}]);
      if(await place(scene,[...scene,...note],note))setStatus('Note added. Use Undo to remove it.');
      return;
    }
    const maps=scene.filter(item=>{
      const ref=item.customData?.fireatlas as any;
      return item.type==='image' && !item.isDeleted && ref?.documentId===documentId && ref.snapshotId && ref.snapshotHash &&
        (ref.kind==='saved-heatmap' || (ref.kind==='assistant-data-view' && ['heatmap','firms-region-heatmap','firms-country-heatmap'].includes(ref.viewKind)));
    });
    const chosen=maps.filter(item=>selected[item.id]);
    const recent=maps.filter(item=>dataViewElements.current.some(view=>view.id===item.id));
    const target=chosen.length===1?chosen[0]:chosen.length===0 && !Object.keys(selected).some(id=>selected[id])
      ? recent.length===1?recent[0]:maps.length===1?maps[0]:undefined : undefined;
    if(!target)throw Error(maps.length?'Select one heatmap to label.':'Add a source-linked heatmap first, then ask to label its detections.');
    if(target.type!=='image' || target.angle || target.scale.some(value=>value!==1))throw Error('Use an unrotated, unflipped heatmap to place geographic labels.');
    const ref=target.customData!.fireatlas as any;
    if(scene.some(item=>!item.isDeleted && (item.customData?.fireatlas as any)?.mapLabelFor===target.id)){
      setStatus('This heatmap already has editable location labels.');return;
    }
    setStatus('Checking the saved heatmap locations…');
    const [report,heat]=await Promise.all([
      api.snapshotReport(documentId,ref.snapshotId),
      api.snapshotHeat(documentId,ref.snapshotId,ref.day || undefined,ref.source || 'joint'),
    ]);
    if(!current())return;
    if(!report.verification.verified || report.snapshot.snapshot_sha256!==ref.snapshotHash || heat.snapshot_sha256!==ref.snapshotHash)
      throw Error('The saved heatmap source changed. Select the heatmap again.');
    if(JSON.stringify(editor.getSceneElements())!==JSON.stringify(scene))throw Error('The board changed while checking locations. Ask again.');
    const labels=heatMapLabels(heat.visual.scope.bbox,heat.visual.points || []);
    if(!labels.length){setStatus('The saved heatmap has no occupied cells to label.');return;}
    const customData={fireatlas:{documentId,snapshotId:ref.snapshotId,snapshotHash:ref.snapshotHash,
      kind:'heatmap-location-label',mapLabelFor:target.id,originalElementIds:[target.id]}};
    const mapGroup=uid('labelled-heatmap');
    const objects=labels.flatMap(label=>{
      const x=target.x+label.x*target.width/960,y=target.y+label.y*target.height/540;
      const groupIds=[uid('heat-label'),mapGroup],size=Math.max(9,13*target.width/960);
      return [{type:'ellipse' as const,x:x-4,y:y-4,width:8,height:8,strokeColor:'#ffffff',backgroundColor:'#854700',fillStyle:'solid' as const,groupIds,customData},
        {type:'rectangle' as const,x:x+6,y:y-15,width:size*9.5,height:size+10,strokeColor:'#225549',backgroundColor:'#fff9dc',fillStyle:'solid' as const,
         groupIds,customData,label:{text:label.text,fontFamily:2,fontSize:size,strokeColor:'#103831'}}];
    });
    const placed=convertToExcalidrawElements(objects);
    const grouped=scene.map(item=>item.id===target.id?newElementWith(item,{groupIds:[...item.groupIds,mapGroup]}):item);
    if(await place(scene,[...grouped,...placed],placed,{fit:[target]})){
      setStatus('Added '+labels.length+' editable occupied-cell labels across the heatmap. Use Undo to remove them.');
    }
  };

  const ask = async (challenge = false, spoken?: string) => {
    stopSpeaking();
    const typed=(spoken ?? message).trim();
    const typedChallenge=/^\s*(?:please\s+)?(?:challenge|critique)\b/i.test(typed);
    challenge=challenge || typedChallenge;
    const question=challenge ? (typed && (typedChallenge || typed!==lastQuestion.current) ? typed : 'Challenge the selected finding. Offer an alternative interpretation based on its saved evidence and a concrete test using the available fields.') : typed;
    if (!question || busy || working || chartLoading) return;
    if (spoken) setMessage(spoken);
    lastQuestion.current=question;
    const request = ++generation.current;
    const current = () => generation.current === request && !switching.current;
    setWorking(true);setActivity([]); setResult(null); setAutomaticChart(false); setAutomaticDiagram(false); setAutomaticExplanation(false); setStatus('Reading the investigation…');
    try {
      const organize = !challenge && requestsOrganize(question);
      const connect = !challenge && requestsConnectSelection(question);
      visualFiles.current=new Map();
      visualElements.current=new Map();
      wholeBoardNotes.current = false;
      const initialSelection = {...editor.getAppState().selectedElementIds};
      const initialItems=editor.getSceneElements().filter(item=>initialSelection[item.id]);
      setCue(initialItems.length ? {ids:initialItems.map(item=>item.id),phase:'reading'} : null);
      sourceContainers.current=new Set(initialItems.map(item=>item.id));
      sourceFingerprint.current=new Map(editor.getSceneElements().filter(item=>initialSelection[item.id] || (item.frameId && sourceContainers.current.has(item.frameId)) || (item.type==='text' && item.containerId && sourceContainers.current.has(item.containerId))).map(item=>[item.id,sourceContent(item)]));
      const initialScene = organize || connect ? JSON.stringify(editor.getSceneElements()) : '';
      if (!(await flush())) throw Error('Save your drawing before asking the assistant.');
      if (!current()) return;
      const selected = editor.getAppState().selectedElementIds;
      if (JSON.stringify(initialSelection) !== JSON.stringify(selected)) throw Error('The selection changed. Select the items and try again.');
      if(!sourceUnchanged())throw Error('The selected source changed. Select it and ask again.');
      if (organize) {
        if (JSON.stringify(initialSelection) !== JSON.stringify(selected) || initialScene !== JSON.stringify(editor.getSceneElements())) throw Error('The selection changed. Select the items and try again.');
        const scene=editor.getSceneElements();
        const targets=requestsWholeBoardOrganization(question)
          ? Object.fromEntries(scene.filter(item=>!item.isDeleted && !item.locked && !item.frameId).map(item=>[item.id,true]))
          : selected;
        const arranged = arrangeSelection(scene, targets);
        if (!current()) return;
        const previous=new Map(scene.map(item=>[item.id,item]));
        const moved=arranged.filter(item=>{const before=previous.get(item.id);return before && (before.x!==item.x || before.y!==item.y);});
        if(!(await place(scene,arranged,moved,{phase:'moved'})))return;
        setWorking(false); setStatus(`${requestsWholeBoardOrganization(question) ? 'Board' : 'Selection'} organized. Use Undo to reverse the move.`);
        return;
      }
      if (connect) {
        if (initialScene !== JSON.stringify(editor.getSceneElements())) throw Error('The selected objects changed. Select them and try again.');
        const scene=editor.getSceneElements();
        const connected=connectSelection(scene,selected,documentId,uid('link'));
        if(!current())return;
        const previous=new Set(scene.map(item=>item.id));
        const added=connected.filter(item=>!previous.has(item.id));
        if(!(await place(scene,connected,added,{phase:'connected'})))return;
        setWorking(false);setStatus('Objects connected. Use Undo to remove the connection.');
        return;
      }
      if(!challenge && (requestsMapLabels(question) || noteText(question) || labelText(question))){
        await applyBoardAction(question,selected,current);
        if(current())setWorking(false);
        return;
      }
      const selectedItems = editor.getSceneElements().filter((item) => selected[item.id]);
      wholeBoardNotes.current = !challenge && !selectedItems.length;
      boardSourceIds.current = wholeBoardNotes.current ? boardNoteIds(editor.getSceneElements(),documentId) : [];
      selectedElements.current = selectedItems.map(item=>item.id);
      if (challenge && !selectedItems.length) throw Error('Select a saved finding, table or document page first.');
      const selectedFrameIds=new Set(selectedItems.filter(item=>item.type==='frame').map(item=>item.id));
      const selectedIds=new Set(selectedItems.map(item=>item.id));
      const capturedItems=editor.getSceneElements().filter(item=>selected[item.id] || (item.frameId && selectedFrameIds.has(item.frameId)) || (item.type==='text' && item.containerId && selectedIds.has(item.containerId)));
      const captured=new Map(capturedItems.map(item=>[item.id,sourceContent(item)]));
      if(wholeBoardNotes.current)for(const item of editor.getSceneElements())if(item.type==='text')captured.set(item.id,sourceContent(item));
      sourceFingerprint.current=captured;sourceContainers.current=selectedIds;
      const references = selectedItems.flatMap((item) => {
        const ref = (item.customData as { fireatlas?: { documentId?: string; cardId?: string; snapshotId?: string; snapshotHash?: string } } | undefined)?.fireatlas;
        return ref?.documentId === documentId && ref.cardId ? [ref] : [];
      });
      const standaloneItems = selectedItems.filter(item=>{const ref=(item.customData as any)?.fireatlas;return ref?.documentId===documentId && !ref.cardId && ((ref.snapshotId && ref.snapshotHash) || (Array.isArray(ref.sourceBindings) && ref.sourceBindings.length>0));});
      const standaloneRefs = standaloneItems.flatMap(item=>{const ref=(item.customData as any).fireatlas;return ref.snapshotId && ref.snapshotHash ? [ref as ClaimBinding] : ref.sourceBindings as ClaimBinding[];});
      const datasetItems = selectedItems.filter((item) => {
        const ref = (item.customData as any)?.fireatlas;
        return ref?.documentId === documentId && ref.datasetId && ref.datasetHash;
      });
      const boardTable=wholeBoardNotes.current ? boardDataset(editor.getSceneElements(),documentId) : null;
      const boardRef=(boardTable?.customData as any)?.fireatlas;
      boardDatasetSelection.current=boardRef ? {datasetId:boardRef.datasetId,datasetHash:boardRef.datasetHash} : null;
      if(boardRef){
        const source=await api.dataset(documentId,boardRef.datasetId);
        if(!current())return;
        if(source.sha256!==boardRef.datasetHash || !sourceUnchanged())throw Error('The board table changed. Open its source and ask again.');
      }
      const sourceItems = selectedItems.filter((item) => {
        const ref=(item.customData as any)?.fireatlas;
        return ref?.documentId===documentId && ref.sourceDocumentId && ref.sourceDocumentHash && Number.isInteger(ref.page);
      });
      const sceneItems = editor.getSceneElements();
      const noteItems = selectedItems.filter((item) => item.type === 'text' || sceneItems.some(child => child.type === 'text' && (child.containerId === item.id || child.frameId === item.id))).slice(0, 20);
      // A frame and its children share a series reference. Send one saved
      // element per view; the server resolves and verifies it independently.
      const comparisonItems = selectedItems.filter((item, index, all) => {
        const ref = (item.customData as any)?.fireatlas;
        return ref?.documentId === documentId && ref.kind === 'finding-alternative' &&
          all.findIndex((other) => { const candidate = (other.customData as any)?.fireatlas; return candidate?.snapshotId === ref.snapshotId && candidate?.comparisonSeries === ref.comparisonSeries; }) === index;
      });
      const visualOnly=selectedItems.length>0 && !references.length && !standaloneItems.length && !datasetItems.length && !sourceItems.length && !noteItems.length;
      let visualCapture:{element_ids:string[];png:string}|undefined;
      if(visualOnly || (selectedItems.length>0 && requestsVisualInspection(question))){
        if(selectedItems.length>20)throw Error('Select up to twenty objects to inspect.');
        const visual=figureSelection(editor.getSceneElements(),selected);
        visualElements.current=new Map(visual.map(item=>[item.id,JSON.stringify(item)]));
        const files=editor.getFiles();
        for(const item of visual)if(item.type==='image' && item.fileId){
          const file=files[item.fileId];if(!file)throw Error('The selected image is unavailable.');
          visualFiles.current.set(item.fileId,file.dataURL);
        }
        const [left,top,right,bottom]=getCommonBounds(visual);
        if(![left,top,right,bottom].every(Number.isFinite) || right-left>20000 || bottom-top>20000)throw Error('Select a smaller visual to inspect.');
        const blob=await exportToBlob({elements:visual,files,appState:{exportBackground:true,viewBackgroundColor:editor.getAppState().viewBackgroundColor},exportPadding:32,mimeType:'image/png',maxWidthOrHeight:1536});
        if(blob.size>1_500_000)throw Error('The selected visual is too large. Select a smaller area.');
        const data=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>typeof reader.result==='string'?resolve(reader.result):reject(Error('The visual could not be read.'));reader.onerror=()=>reject(Error('The visual could not be read.'));reader.readAsDataURL(blob);});
        if(!current() || !sourceUnchanged())throw Error('The selected visual changed. Select it and ask again.');
        visualCapture={element_ids:selectedItems.map(item=>item.id),png:data.split(',')[1]};
      }
      selection.current = [...new Set(references.map((ref) => ref.cardId!))];
      const dataRef = (datasetItems[0]?.customData as any)?.fireatlas || boardRef;
      datasetSelection.current = dataRef ? { datasetId: dataRef.datasetId, datasetHash: dataRef.datasetHash } : null;
      const sourceRef = (sourceItems[0]?.customData as any)?.fireatlas;
      sourceSelection.current = sourceRef ? { sourceDocumentId:sourceRef.sourceDocumentId, sourceDocumentHash:sourceRef.sourceDocumentHash, page:sourceRef.page } : null;
      const document = await api.getDocument(documentId);
      if (!current()) return;
      for (const ref of references) {
        const card = document.state.cards[ref.cardId!];
        const snapshot = ref.snapshotId && document.snapshots?.[ref.snapshotId];
        if (!card || card.snapshot_id !== ref.snapshotId || !snapshot || snapshot.snapshot_sha256 !== ref.snapshotHash) {
          throw Error('This evidence preview no longer matches its saved card. Add the current evidence to the board and try again.');
        }
      }
      for(const ref of standaloneRefs)if(document.snapshots?.[ref.snapshotId]?.snapshot_sha256!==ref.snapshotHash)throw Error('The saved evidence changed. Select it again.');
      const job = await api.jarvisStart(documentId, { base_revision: document.revision, instance_id: instance.current, message: question, selected_cards: selection.current, selected_snapshot_elements:standaloneItems.map(item=>item.id), selected_dataset_elements: datasetItems.map((item) => item.id), selected_source_elements: sourceItems.map((item)=>item.id), selected_comparison_elements: comparisonItems.map((item)=>item.id), selected_note_elements: noteItems.map(item=>item.id), visual_capture:visualCapture, whiteboard: true, whiteboard_challenge:challenge, research_team:researchTeam && !challenge });
      if (!current()) { void api.jarvisCancel(documentId, job.id).catch(() => undefined); return; }
      run.current = { documentId, id: job.id };
      const startedAt = Date.now();
      let attempt = 0;
      const poll = async () => {
        try {
          if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
            run.current = null; generation.current += 1;
            void api.jarvisCancel(documentId, job.id).catch(() => undefined);
            setWorking(false); setStatus('The assistant took too long and was stopped. Try again.');
            return;
          }
          let next;
          const controller=new AbortController();pollController.current=controller;
          const requestTimeout=setTimeout(()=>controller.abort(),Math.min(POLL_REQUEST_TIMEOUT_MS,Math.max(1,POLL_TIMEOUT_MS-(Date.now()-startedAt))));
          try { next = await api.jarvisRun(documentId, job.id,controller.signal); }
          catch (error) {
            if (!current()) return;
            const status=(error as {status?:number})?.status;
            // Only retry the read of this same run, never the model request.
            if ([0,502,503,504].includes(status ?? -1)) {
              setStatus('Reconnecting to the assistant…');
              timer.current = setTimeout(() => void poll(), Math.min(700 * 1.25 ** attempt++, 3000));
              return;
            }
            throw error;
          } finally {clearTimeout(requestTimeout);if(pollController.current===controller)pollController.current=null;}
          if (!current()) return;
          if(Array.isArray(next.activity))setActivity(next.activity);
          if (['queued', 'running'].includes(next.status)) {
            setStatus(next.activity?.at(-1)?.message || 'Reading the investigation…');
            timer.current = setTimeout(() => void poll(), Math.min(700 * 1.25 ** attempt++, 3000));
            return;
          }
          run.current = null;
          if (next.status !== 'completed') { setWorking(false); setStatus(next.body?.error || `Assistant ${next.status}.`); return; }
          if (!next.body?.title) { setWorking(false); setStatus('The assistant did not return an explanation. Try another question.'); return; }
          const answer=next.body as Answer;
          if(!sourceUnchanged())throw Error(challenge?'The selected finding changed. Select it and try again.':wholeBoardNotes.current?'The board text changed. Ask again to use the latest notes.':'The selected source changed. Select it and ask again.');
          setConversationRevision(value=>value+1);
          if(answer.data_views?.length || (!(challenge && answer.ai_wording_unavailable) && (answer.claims || []).some(claim=>claim.result_id && claim.path && !claim.binding && !claim.source_binding))){
            const preserved=await api.jarvisPreserveClaims(documentId,job.id);
            if(!current())return;
            for(const claim of answer.claims || [])if(!claim.binding && !claim.source_binding && claim.result_id && preserved.bindings[claim.result_id]){const {resultId,...binding}=preserved.bindings[claim.result_id];claim.binding=binding;claim.result_id=resultId;}
            for(const view of answer.data_views || []){const binding=preserved.bindings[view.result_id];if(!binding)throw Error('The requested view could not preserve its source.');const {resultId,...ref}=binding;view.binding=ref;}
          }
          if(answer.data_views?.length && !challenge){setResult(answer);await addDataViews(answer.data_views,sourceUnchanged,/\b(connect|link|similar|analogu)/i.test(question),answer.data_views.some(view=>view.kind==='regional-comparison') || /\b(note|sticky|pinned|pin)\b/i.test(question)?answer:undefined);if(current())setWorking(false);return;}
          if(answer.web_sources?.length && /\b(?:and|then)\s+(?:pin|add|put)\b/i.test(question)){
            setResult(answer);await pinWebSources(answer.web_sources);
            if(current())setWorking(false);
            return;
          }
          let displayAnswer:Answer=answer;
          if(challenge){
            const unchanged=()=>sourceUnchanged();
            if(!unchanged())throw Error('The selected finding changed. Select it and try again.');
            const latest=await api.getDocument(documentId);
            if(!current())return;
            for(const ref of references){
              if(latest.state.cards[ref.cardId!]?.snapshot_id!==ref.snapshotId || !ref.snapshotId || latest.snapshots?.[ref.snapshotId]?.snapshot_sha256!==ref.snapshotHash)throw Error('The selected evidence changed. Select it and try again.');
            }
            for(const ref of standaloneRefs)if(latest.snapshots?.[ref.snapshotId]?.snapshot_sha256!==ref.snapshotHash)throw Error('The saved evidence changed. Select it again.');
            if(dataRef){const info=await api.dataset(documentId,dataRef.datasetId);if(!current())return;if(info.sha256!==dataRef.datasetHash)throw Error('The selected table changed.');}
            if(sourceRef){const info=await api.sourceDocuments(documentId);if(!current())return;if(!info.documents.some(item=>item.id===sourceRef.sourceDocumentId && item.sha256===sourceRef.sourceDocumentHash))throw Error('The selected document changed.');}
            const sources:ChallengeSource[]=[];
            for(const match of (answer.source_matches || []).slice(0,2)){sources.push(await resolveSourceMatch(match));if(!current())return;}
            const firstRef=references[0] || standaloneRefs[0];
            const receipt=firstRef?.snapshotId ? await api.snapshotReceipt(documentId,firstRef.snapshotId) : null;
            if(!current())return;
            if(!(await flush()))throw Error('Save the current drawing before adding the challenge.');
            if(!current())return;
            const finalDocument=await api.getDocument(documentId);
            if(!current())return;
            for(const ref of references){
              if(finalDocument.state.cards[ref.cardId!]?.snapshot_id!==ref.snapshotId || !ref.snapshotId || finalDocument.snapshots?.[ref.snapshotId]?.snapshot_sha256!==ref.snapshotHash)throw Error('The selected evidence changed. Select it and try again.');
            }
            for(const ref of standaloneRefs)if(finalDocument.snapshots?.[ref.snapshotId]?.snapshot_sha256!==ref.snapshotHash)throw Error('The saved evidence changed. Select it again.');
            for(const claim of answer.claims || []){const ref=claim.binding;if(ref && (ref.documentId!==documentId || (ref.cardId && finalDocument.state.cards[ref.cardId]?.snapshot_id!==ref.snapshotId) || finalDocument.snapshots?.[ref.snapshotId]?.snapshot_sha256!==ref.snapshotHash))throw Error('A claim source changed. Select the evidence and try again.');}
            for(const claim of answer.claims || []){
              const ref=claim.source_binding;if(!ref)continue;
              if(ref.documentId!==documentId)throw Error('A claim source is unavailable.');
              if(ref.datasetId && ref.datasetHash && ref.groupColumn && ref.valueColumn && (typeof ref.groupName==='string' || ref.groupName===null) && ref.groupMetric && ['group','rows','numeric_count','missing_count','non_numeric_count','mean'].includes(ref.groupMetric)){const result=await api.datasetGroups(documentId,ref.datasetId,ref.groupColumn,ref.valueColumn);if(!current())return;const row=result.groups.find(item=>item.group===ref.groupName);if(result.sha256!==ref.datasetHash || !row || row[ref.groupMetric as keyof typeof row]!==claim.value)throw Error('The grouped summary changed.');}
              else if(ref.datasetId && ref.datasetHash && ref.summaryColumn && ref.summaryMetric && ['numeric_count','missing_count','non_numeric_count','minimum','maximum','mean','median'].includes(ref.summaryMetric)){const summary=await api.datasetSummary(documentId,ref.datasetId,ref.summaryColumn);if(!current())return;if(summary.sha256!==ref.datasetHash || summary.columns[0]?.[ref.summaryMetric]!==claim.value)throw Error('The table summary changed.');}
              else if(ref.datasetId && ref.datasetHash && Number.isInteger(ref.rowOffset) && ref.rowOffset!>=0){const table=await api.dataset(documentId,ref.datasetId,ref.rowOffset);if(!current())return;if(table.sha256!==ref.datasetHash)throw Error('A claim table changed.');}
              else if(ref.sourceDocumentId && ref.sourceDocumentHash && Number.isInteger(ref.page) && ref.page!>=1){const docs=await api.sourceDocuments(documentId);if(!current())return;if(!docs.documents.some(item=>item.id===ref.sourceDocumentId && item.sha256===ref.sourceDocumentHash))throw Error('A claim document changed.');}
              else throw Error('A claim source is unavailable.');
            }
            if(!unchanged())throw Error('The selected finding changed. Select it and try again.');
            const originalSources=[...new Map([...references,...standaloneRefs].filter(ref=>ref.snapshotId && ref.snapshotHash).map(ref=>[ref.snapshotId,{documentId,snapshotId:ref.snapshotId!,snapshotHash:ref.snapshotHash!}])).values()];
            const originalRef:Record<string,unknown>=originalSources.length>1?{sourceBindings:originalSources}:firstRef?{cardId:firstRef.cardId,snapshotId:firstRef.snapshotId,snapshotHash:firstRef.snapshotHash}:dataRef?{datasetId:dataRef.datasetId,datasetHash:dataRef.datasetHash}:sourceRef?{sourceDocumentId:sourceRef.sourceDocumentId,sourceDocumentHash:sourceRef.sourceDocumentHash,page:sourceRef.page}:{};
            const items=editor.getSceneElements(),x=items.length?Math.max(...items.map(item=>item.x+item.width))+100:100;
            const payload=receipt?.receipt?.payload;
            const selectedSeries=(comparisonItems[0]?.customData as any)?.fireatlas?.comparisonSeries || payload?.selected_series;
            const supported=['modis','viirs','adjusted'].includes(selectedSeries);
            const comparison=receipt?.receipt?.operation==='finding_comparison' && payload?.schema==='fireatlas-finding-investigation-v1' && supported && firstRef?.cardId && firstRef.snapshotId && firstRef.snapshotHash
              ? challengeComparison(payload.comparison,selectedSeries as SeriesName,selectedSeries==='viirs'?'modis':'viirs',payload.unit,{documentId,cardId:firstRef.cardId,snapshotId:firstRef.snapshotId,snapshotHash:firstRef.snapshotHash},x,100,()=>uid('comparison')) : [];
            const firstDirection=payload?.comparison?.series?.[selectedSeries]?.direction;
            const otherDirection=payload?.comparison?.series?.[selectedSeries==='viirs'?'modis':'viirs']?.direction;
            const hasDirections=[firstDirection,otherDirection].every(value=>['increase','decrease','unchanged'].includes(value));
            const comparisonQuestion=hasDirections
              ? (firstDirection===otherDirection?'How does the size of the change depend on the selected sensor or estimate?':'How should the conclusion change when the two views show different directions?')
              : 'What can the available sensor records show about change between these periods?';
            const parkTimelineSelected=selectedItems.length>0 && !firstRef && selectedItems.every(item=>{
              const ref=(item.customData as any)?.fireatlas;
              return ref?.kind==='park-platform-chart' && ref.documentId===documentId && ref.datasetId===dataRef?.datasetId && ref.datasetHash===dataRef?.datasetHash;
            });
            const checkedTableClaims=(answer.claims || []).filter(claim=>claim.source_binding?.documentId===documentId && claim.source_binding?.datasetId===dataRef?.datasetId && claim.source_binding?.datasetHash===dataRef?.datasetHash);
            const groupVisuals=(answer.visualizations || []).filter(item=>item.kind==='csv-groups' && item.binding);
            let groupShapes:any[]=[];
            if(dataRef && groupVisuals.length===1){
              const binding=groupVisuals[0].binding as GroupBinding;
              if(binding.documentId!==documentId || binding.datasetId!==dataRef.datasetId || binding.datasetHash!==dataRef.datasetHash)throw Error('The challenge chart source changed.');
              const grouped=await api.datasetGroups(documentId,binding.datasetId,binding.groupColumn,binding.valueColumn);
              if(!current())return;
              if(grouped.dataset_id!==binding.datasetId || grouped.sha256!==binding.datasetHash || grouped.group_column!==binding.groupColumn || grouped.value_column!==binding.valueColumn)throw Error('The challenge chart source changed.');
              if(!unchanged())throw Error('The selected finding changed. Select it and try again.');
              groupShapes=groupChart(grouped,{...binding,kind:'dataset-group-chart'},x+(comparison.length?1040:0)+720,100,()=>uid('group'));
            }
            const safeAnswer=(answer.ai_wording_unavailable || (!(answer.claims || []).length && !sources.length)) && comparison.length
              ? {summary:comparisonQuestion} : answer.ai_wording_unavailable && parkTimelineSelected
                ? {summary:'How do the satellite observations compare, and which source records are unavailable?',claims:checkedTableClaims}
                : answer.ai_wording_unavailable && dataRef && checkedTableClaims.length
                  ? {summary:'What additional evidence could challenge this finding?',claims:checkedTableClaims}
                  : answer.ai_wording_unavailable?{summary:'What additional evidence could challenge this finding?'}:answer;
            if(answer.ai_wording_unavailable)displayAnswer={title:answer.title,...safeAnswer};
            const elements=convertToExcalidrawElements([...comparison,...assistantChallenge(safeAnswer,documentId,selectedItems.map(item=>item.id),originalRef,sources,x+(comparison.length?1040:0),100,()=>uid('challenge')),...groupShapes],{regenerateIds:false});
            if(!(await place(items,[...items,...elements],elements,{clearSelection:true,viewportZoomFactor:.8})))return;
            if(groupShapes.length)setAutomaticChart(true);
          }
          if(!sourceUnchanged())throw Error('The selected source changed. Select it and ask again.');
          setResult(displayAnswer);
          if(selectedElements.current.length && !challenge)setCue({ids:selectedElements.current,phase:'pointing'});
          if(voiceRef.current && displayAnswer.kind!=='Assistant unavailable')speak(displayAnswer.summary || displayAnswer.interpretation || displayAnswer.title || '');
          const requestedTableVisuals=(answer.visualizations || []).filter(item=>['csv-groups','csv-scatter'].includes(item.kind) && item.binding);
          const hasRequestedTableChart=Boolean(dataRef && requestsGroupedChart(question) && requestedTableVisuals.length===1 && (requestedTableVisuals[0].binding as GroupBinding | ScatterBinding).datasetId===dataRef.datasetId && (requestedTableVisuals[0].binding as GroupBinding | ScatterBinding).datasetHash===dataRef.datasetHash);
          if(!challenge && answer.diagram && requestsDiagram(question) && !hasRequestedTableChart){
            const unchanged=()=>sourceUnchanged();
            if(!unchanged())throw Error('The selected evidence changed. Select it and try again.');
            const explain=/\b(explain|explanation)\b/i.test(question);
            const charts=(answer.visualizations || []).filter(item=>item.kind==='monthly-comparison' && item.binding);
            const chart=requestsGroupedChart(question) && charts.length===1 ? charts[0].binding as ChartBinding : undefined;
            const added=await addDiagram(answer.diagram,unchanged,explain?answer:undefined,chart);
            if(!current())return;
            setAutomaticDiagram(added);setAutomaticExplanation(added && explain);setWorking(false);return;
          }
          const comparisons=(answer.visualizations || []).filter(item=>item.kind==='monthly-comparison' && item.binding);
          if(!challenge && !hasRequestedTableChart && requestsGroupedChart(question) && comparisons.length===1){
            const explain=/\b(explain|explanation)\b/i.test(question);
            const added=await addChart(comparisons[0].binding as ChartBinding,explain?answer:undefined);
            if(!current())return;
            setAutomaticChart(added);setAutomaticExplanation(added && explain);setWorking(false);
            if(added && requestsDiagram(question) && !answer.diagram)setStatus('Chart added. The diagram is unavailable.');
            return;
          }
          const tableVisuals=requestedTableVisuals;
          const visual=dataRef && tableVisuals.length===1 ? tableVisuals[0] : null;
          const selectedTable=visual?.binding as GroupBinding | ScatterBinding | undefined;
          if(!challenge && requestsGroupedChart(question) && selectedTable && selectedTable.datasetId===dataRef.datasetId && selectedTable.datasetHash===dataRef.datasetHash){
            const unchanged=()=>sourceUnchanged();
            if(!unchanged())throw Error('The selected table changed. Select it and try again.');
            const explain=/\b(explain|explanation)\b/i.test(question);
            const requestedDiagram=requestsDiagram(question);
            const nodes=answer.diagram?.nodes || [];
            const evidenceNodes=nodes.filter(node=>node.kind==='evidence');
            const matched=Boolean(evidenceNodes.length && evidenceNodes.every(node=>{
              const ref=node.binding;
              if(ref?.documentId!==documentId || ref.datasetId!==selectedTable.datasetId || ref.datasetHash!==selectedTable.datasetHash)return false;
              return 'xColumn' in selectedTable ? ref.xColumn===selectedTable.xColumn && ref.yColumn===selectedTable.yColumn : ref.groupColumn===selectedTable.groupColumn && ref.valueColumn===selectedTable.valueColumn;
            }));
            const diagram=requestedDiagram ? (matched ? answer.diagram! : true) : false;
            const added=visual?.kind==='csv-scatter' ? await addScatter(selectedTable as ScatterBinding,unchanged,explain?answer:undefined,diagram) : await addGroupChart(selectedTable as GroupBinding,unchanged,explain?answer:undefined,diagram);
            if(!current())return;
            setAutomaticChart(added);setAutomaticExplanation(added && explain);setAutomaticDiagram(Boolean(added && diagram));setWorking(false);
            return;
          }
          setWorking(false);setStatus(challenge?'Challenge added to the board.':requestsDiagram(question) && !answer.diagram?'The diagram is unavailable. You can still add the explanation.':'');
        } catch (error) { if (current()) { const active=run.current;run.current=null;if(active)void api.jarvisCancel(active.documentId,active.id).catch(()=>undefined);setWorking(false); setStatus((error as Error).message); } }
      };
      void poll();
    } catch (error) { if (current()) { setWorking(false); setStatus((error as Error).message); } }
  };

  const cancel = () => {
    generation.current += 1;
    if (timer.current) clearTimeout(timer.current);
    pollController.current?.abort();pollController.current=null;
    const active = run.current; run.current = null;
    if (active) void api.jarvisCancel(active.documentId, active.id).catch(() => undefined);
    stopSpeaking();setWorking(false); setChartLoading(false); setStatus('Stopped.');
    if(placing){setWatching(false);launcherNode.current?.focus({preventScroll:true});}
  };

  function stopSpeaking() { if(canSpeak())window.speechSynthesis.cancel(); setSpeaking(false); }
  function speak(text:string) {
    const line=spokenText(text);
    if(!line || !canSpeak())return;
    window.speechSynthesis.cancel();
    const utterance=new SpeechSynthesisUtterance(line);
    utterance.rate=1.02; utterance.onstart=()=>setSpeaking(true); utterance.onend=()=>setSpeaking(false); utterance.onerror=()=>setSpeaking(false);
    window.speechSynthesis.speak(utterance);
  }
  const toggleVoiceReply = () => {
    const next=!voiceReply; setVoiceReply(next); voiceRef.current=next;
    try{window.localStorage.setItem('fireatlas-assistant-voice',next?'on':'off');}catch{/* private mode */}
    if(!next)stopSpeaking();
  };
  const stopListening = () => { recognizer.current?.stop(); };
  const startListening = () => {
    const Factory=recognizerFactory();
    if(!Factory){setStatus('Voice input is not supported in this browser. Type your question instead.');return;}
    if(recognizer.current || working || busy || chartLoading)return;
    stopSpeaking();
    const recognition=new Factory();
    recognition.lang=navigator.language || 'en-US'; recognition.interimResults=true; recognition.continuous=false;
    let finalText='';
    recognition.onresult=(event:any)=>{
      let partial='';
      for(let i=event.resultIndex;i<event.results.length;i++){const part=event.results[i];if(part.isFinal)finalText+=part[0].transcript;else partial+=part[0].transcript;}
      setInterim((finalText+partial).trim());
    };
    recognition.onerror=(event:any)=>{setStatus(event?.error==='not-allowed'?'Microphone permission was denied.':event?.error==='no-speech'?'I did not hear anything. Try again.':'Voice input stopped.');};
    recognition.onend=()=>{
      recognizer.current=null; setListening(false); setInterim('');
      const text=finalText.trim();
      if(text){ if(!voiceRef.current){voiceRef.current=true;setVoiceReply(true);} void askRef.current(false,text); }
    };
    recognizer.current=recognition; setListening(true); setOpen(true);
    try{recognition.start();}catch{recognizer.current=null;setListening(false);}
  };
  const startListeningRef=useRef(startListening); startListeningRef.current=startListening;
  const stopListeningRef=useRef(stopListening); stopListeningRef.current=stopListening;
  askRef.current=ask; voiceRef.current=voiceRef.current || voiceReply;

  // Hold Ctrl+Alt to talk, release to send. Typing fields are left alone.
  useEffect(()=>{
    const down=(event:KeyboardEvent)=>{
      const target=event.target as HTMLElement|null;
      if(target && (target.isContentEditable || ['INPUT','TEXTAREA','SELECT'].includes(target.tagName)))return;
      if(event.ctrlKey && event.altKey && !event.repeat)startListeningRef.current();
    };
    const up=(event:KeyboardEvent)=>{if(event.key==='Control' || event.key==='Alt')stopListeningRef.current();};
    window.addEventListener('keydown',down);window.addEventListener('keyup',up);
    return ()=>{window.removeEventListener('keydown',down);window.removeEventListener('keyup',up);recognizer.current?.abort();recognizer.current=null;if(canSpeak())window.speechSynthesis.cancel();};
  },[]);

  // Suggestions adapt to what is selected.
  useEffect(()=>{
    if(!open)return;
    const read=()=>setSelectedCount(Object.values(editor.getAppState?.().selectedElementIds||{}).filter(Boolean).length);
    read();const id=window.setInterval(read,500);return ()=>window.clearInterval(id);
  },[open,editor]);

  useEffect(() => {
    if (busy && working) cancel();
    else if (busy) { generation.current += 1; setChartLoading(false); }
  }, [busy]); // eslint-disable-line react-hooks/exhaustive-deps

  const add = async () => {
    if (!result || busy || working || chartLoading) return;
    if(!sourceUnchanged()){setStatus('The selected source changed. Select it and ask again.');return;}
    const items = editor.getSceneElements();
    const x = items.length ? Math.max(...items.map((item) => item.x + item.width)) + 100 : 100;
    const link = new URL(`./studio.html?board=${encodeURIComponent(documentId)}`, document.baseURI).href;
    const originalIds=wholeBoardNotes.current ? boardSourceIds.current : selectedElements.current;
    const elements = convertToExcalidrawElements(explanationElements(result,documentId,selection.current,{...(datasetSelection.current || {}),...(sourceSelection.current || {})},x,100,link,originalIds));
    const request=generation.current;
    setChartLoading(true);
    try {
      if(!(await place(items,[...items,...elements],elements,{viewportZoomFactor:.8})))return;
      if(wholeBoardNotes.current)for(const item of elements)if(item.type==='text')sourceFingerprint.current.set(item.id,sourceContent(item));
      setStatus('Added to the board.');
    } catch(error){if(generation.current===request)setStatus((error as Error).message);}
    finally{if(generation.current===request)setChartLoading(false);}
  };

  const sourceUnchanged = () => {
    const scene=editor.getSceneElements(),current=new Map(scene.map(item=>[item.id,sourceContent(item)]));
    if(wholeBoardNotes.current){
      const ref=(boardDataset(scene,documentId)?.customData as any)?.fireatlas;
      const expected=boardDatasetSelection.current;
      if((ref?.datasetId || null)!==(expected?.datasetId || null) || (ref?.datasetHash || null)!==(expected?.datasetHash || null))return false;
    }
    if(visualFiles.current.size && [...visualFiles.current].some(([id,value])=>editor.getFiles()[id]?.dataURL!==value))return false;
    if(visualElements.current.size){
      const selected=Object.fromEntries(selectedElements.current.map(id=>[id,true]));
      const now=figureSelection(scene,selected);
      if(now.length!==visualElements.current.size || now.some(item=>visualElements.current.get(item.id)!==JSON.stringify(item)))return false;
    }
    return [...sourceFingerprint.current].every(([id,value])=>current.get(id)===value) && !scene.some(item=>((wholeBoardNotes.current && item.type==='text') || (item.frameId && sourceContainers.current.has(item.frameId)) || (item.type==='text' && item.containerId && sourceContainers.current.has(item.containerId))) && !sourceFingerprint.current.has(item.id));
  };

  const showSource = () => {
    if(!sourceUnchanged()){setStatus('The selected source changed. Select it and ask again.');return;}
    const ids=new Set(selectedElements.current);
    const targets=editor.getSceneElements().filter(item=>ids.has(item.id) && !item.isDeleted);
    if(!targets.length){setStatus('The selected source is no longer on this board.');return;}
    editor.updateScene({appState:{selectedElementIds:Object.fromEntries(targets.map(item=>[item.id,true]))},captureUpdate:CaptureUpdateAction.NEVER});
    const request=generation.current;
    setOpen(false);
    // The assistant changes the canvas dimensions, especially on phones. Fit
    // after the panel has closed, so the selected source uses the full canvas.
    requestAnimationFrame(()=>requestAnimationFrame(()=>{
      if(generation.current!==request || switching.current || !sourceUnchanged())return;
      const current=editor.getSceneElements().filter(item=>ids.has(item.id) && !item.isDeleted);
      if(current.length)editor.scrollToContent(current,{fitToContent:true});
    }));
  };

  const showDataView = (id:string) => {
    const request=generation.current;
    const saved=dataViewElements.current.find(item=>item.id===id);
    if(!saved)return;
    setOpen(false);setWatching(false);
    requestAnimationFrame(()=>requestAnimationFrame(()=>{
      if(generation.current!==request || switching.current)return;
      const item=editor.getSceneElements().find(item=>{
        const ref=(item.customData as any)?.fireatlas;
        return item.id===saved.id && !item.isDeleted && ref?.documentId===documentId && ref.snapshotHash===saved.snapshotHash;
      });
      if(!item){setStatus('This view is no longer on the board.');return;}
      editor.scrollToContent([item],{fitToContent:true,viewportZoomFactor:.85});
      setCue({ids:[item.id],phase:'pointing'});
    }));
  };

  const addDataViews = async (views:ScientificView[],stillValid=sourceUnchanged,connect=/\b(connect|link|similar|analogu)/i.test(result?.question || ''),annotation?:Answer):Promise<boolean> => {
    if(busy || chartLoading || !views.length)return false;
    if(views.some(view=>view.kind==='regional-comparison')){
      if(views.length!==1){setStatus('Add a comparison as its own board composition. Ask for the comparison separately.');return false;}
      return addRegionalComparison(views[0],stillValid,annotation);
    }
    const request=generation.current,current=()=>generation.current===request && !switching.current && stillValid();
    setChartLoading(true);
    try {
      if(!(await flush()))throw Error('Save the board before adding scientific views.');
      const items=editor.getSceneElements(),startX=items.length?Math.max(...items.map(item=>item.x+item.width))+100:100;
      const shapes:any[]=[],files:any[]=[];
      for(let index=0;index<views.length;index++){
        const view=views[index],ref=view.binding;
        if(!ref || ref.documentId!==documentId)throw Error('The scientific view has no saved source.');
        const report=await api.snapshotReport(documentId,ref.snapshotId);
        if(!current())return false;
        if(!report.verification.verified || report.snapshot.snapshot_sha256!==ref.snapshotHash)throw Error('The scientific view source changed.');
        const snapshot=report.snapshot;
        const source=snapshot.scope.source || 'joint',day=snapshot.scope.day || undefined;
        let dataURL:string,title:string,viewStart=snapshot.scope.start,viewEnd=snapshot.scope.end,viewSource:string|null=source;
        const areaHeat=view.kind==='firms-region-heatmap' || view.kind==='firms-country-heatmap';
        if(view.kind==='heatmap' || areaHeat){
          const heat=areaHeat ? await api.snapshotHeat(documentId,ref.snapshotId) : await api.snapshotHeat(documentId,ref.snapshotId,day,source);
          if(!current())return false;
          if(heat.snapshot_sha256!==ref.snapshotHash)throw Error('The heatmap source changed.');
          title=view.title || heat.visual.title || 'Thermal concentration · '+heat.visual.day+' UTC';
          dataURL=(await renderHeatPreview(heat.visual,documentId,snapshot,title)).dataURL;
          if(areaHeat && heat.visual.interval){
            viewStart=heat.visual.interval.start;viewEnd=heat.visual.interval.end;viewSource=heat.visual.source ?? null;
          }
        }else{
          const preview=await api.snapshotPreview(documentId,ref.snapshotId,view.kind==='calendar'?'calendar':view.kind,day,source);
          if(!current())return false;
          if(preview.snapshot_sha256!==ref.snapshotHash || !preview.visual)throw Error('The requested scientific visualization is unavailable.');
          if(typeof preview.visual.scope?.start==='string' && typeof preview.visual.scope?.end==='string'){viewStart=preview.visual.scope.start;viewEnd=preview.visual.scope.end;}
          dataURL=await renderMapPreview(preview.svg);
          title=preview.visual.title || ({coordinates:'Original thermal coordinates',satellites:'Satellite detection comparison','park-satellites':'Park four-platform comparison',calendar:'Observed-cell calendar',archive:'Historical observation windows',similar:'Candidate historical thermal profiles',factors:'Measured environmental context',analogues:'Measured environmental analogues'} as Record<string,string>)[view.kind] || 'Scientific view';
        }
        if(!current())return false;
        const x=startX+(index%2)*1040,y=100+Math.floor(index/2)*640,fileId=uid('science-image'),id=uid('science-view');
        files.push({id:fileId,dataURL,mimeType:'image/png',created:Date.now()});
        const metadata={fireatlas:{...ref,kind:'assistant-data-view',viewKind:view.kind,viewStart,viewEnd,day:areaHeat ? null : day || null,source:viewSource,title,originalElementIds:selectedElements.current}};
        const incidentLink=view.referenceUrl?.startsWith('https://') ? {link:view.referenceUrl} : {};
        shapes.push({id,type:'image',x,y,width:960,height:540,fileId,status:'saved',scale:[1,1],customData:metadata,...incidentLink});
      }
      const note=annotation || (/\b(note|sticky|pinned|pin)\b/i.test(result?.question || '')?result:null);
      let noteId:string|undefined;
      if(note?.summary || note?.interpretation){
        const text=wrapCardText('AI note\n'+(note.summary || note.interpretation || ''),43);
        noteId=uid('analysis-note');
        const x=startX+(views.length===1?1040:2130),y=100;
        const originalElementIds=[...selectedElements.current,...shapes.filter(shape=>shape.type==='image').map(shape=>shape.id)];
        const customData={fireatlas:{documentId,kind:'assistant-analysis-note',originalElementIds,sourceBindings:views.map(view=>view.binding)}};
        shapes.push({id:noteId,type:'rectangle',x,y,width:440,height:Math.max(160,48+text.split('\n').length*24),roundness:{type:3},backgroundColor:'#fff3c9',fillStyle:'solid',strokeColor:'#c59b45',label:{text,fontSize:17,fontFamily:2},customData});
      }
      if(!current())return false;
      const latest=editor.getSceneElements();
      const latestStart=latest.length?Math.max(...latest.map(item=>item.x+item.width))+100:100;
      const shift=latestStart-startX;
      const elements=convertToExcalidrawElements(shapes.map(shape=>({...shape,x:shape.x+shift})),{regenerateIds:false});
      let next:ReturnType<typeof connectSelection>=[...latest,...elements];
      if(connect){
        let previous=latest.find(item=>selectedElements.current.includes(item.id) && ['rectangle','ellipse','diamond','text','image'].includes(item.type) && !item.locked && !item.angle) || latest.find(item=>item.frameId && selectedElements.current.includes(item.frameId) && ['rectangle','ellipse','diamond','text','image'].includes(item.type) && !item.locked && !item.angle);
        for(const image of elements.filter(item=>item.type==='image')){
          if(previous){next=connectSelection(next,{[previous.id]:true,[image.id]:true},documentId,uid('related'));}
          previous=image;
        }
      }
      if(noteId){
        const anchors=elements.filter(item=>item.type==='image');
        const anchor=anchors[Math.min(1,anchors.length-1)];
        if(anchor)next=connectSelection(next,{[anchor.id]:true,[noteId]:true},documentId,uid('note-link'));
      }
      if(!current())return false;
      const images=elements.filter(item=>item.type==='image');
      const focus=elements.length && noteId && images.length===1 ? next.filter(item=>!latest.some(existing=>existing.id===item.id)) : images;
      if(!(await place(latest,next,focus,{clearSelection:true,files,viewportZoomFactor:.85,fit:images.slice(0,2)})))return false;
      dataViewElements.current=images.map(item=>({id:item.id,kind:(item.customData as any).fireatlas.viewKind,snapshotHash:(item.customData as any).fireatlas.snapshotHash}));
      if(noteId)dataViewElements.current.push({id:noteId,kind:'note'});
      setOpen(false);setWatching(true);setAutomaticChart(true);
      setStatus(views.length===1?'Scientific view added. Select it and choose Open source.':views.length+' scientific views added. Select a view to open its source.');
      return true;
    }catch(error){if(current())setStatus((error as Error).message);return false;}
    finally{setChartLoading(false);}
  };

  const addRegionalComparison = async (view:ScientificView,stillValid:()=>boolean,answer?:Answer):Promise<boolean> => {
    const ref=view.binding,request=generation.current,current=()=>generation.current===request && !switching.current && stillValid();
    if(!ref || ref.documentId!==documentId){setStatus('The comparison has no saved evidence source.');return false;}
    setChartLoading(true);
    try {
      if(!(await flush()))throw Error('Save the board before adding the comparison.');
      const report=await api.snapshotReport(documentId,ref.snapshotId);
      if(!current())return false;
      if(!report.verification.verified || report.snapshot.snapshot_sha256!==ref.snapshotHash)throw Error('The comparison source changed.');
      const preview=await api.snapshotPreview(documentId,ref.snapshotId,'regional-comparison');
      if(!current())return false;
      if(preview.snapshot_sha256!==ref.snapshotHash || preview.visual?.kind!=='regional-comparison')throw Error('The comparison could not be verified.');
      const visual=preview.visual as ComparisonVisual,files:any[]=[];
      for(const panel of visual.panels){
        const {dataURL}=await renderHeatPreview(panel.heat,documentId,report.snapshot,panel.label);
        if(!current())return false;
        files.push({id:uid('comparison-image'),dataURL,mimeType:'image/png',created:Date.now()});
      }
      // Read the latest scene after every asynchronous fetch/rasterization.
      const latest=editor.getSceneElements(),left=latest.length?Math.max(...latest.map(item=>item.x+item.width))+140:100;
      const composition=comparisonBoard(visual,ref,files.map(file=>file.id),left,100,()=>uid('comparison'),answer?.ai_wording_unavailable?undefined:answer?.summary || answer?.interpretation);
      const added=convertToExcalidrawElements(composition.shapes,{regenerateIds:false});
      if(!current())return false;
      if(!(await place(latest,[...latest,...added],added,{clearSelection:true,files,viewportZoomFactor:.88})))return false;
      dataViewElements.current=[{id:composition.frameId,kind:'Comparison overview',snapshotHash:ref.snapshotHash},...composition.imageIds.map((id,index)=>({id,kind:visual.panels[index].label+' · '+(visual.panels[index].day || visual.panels[index].year),snapshotHash:ref.snapshotHash}))];
      setOpen(false);setWatching(true);setAutomaticChart(true);
      setStatus('Comparison added with a shared heat scale, editable callouts and source-linked weather. Open a panel for a closer view.');
      return true;
    }catch(error){if(current())setStatus((error as Error).message);return false;}
    finally{setChartLoading(false);}
  };

  const addDiagram = async (diagram:Diagram,stillValid=sourceUnchanged,explanation?:Answer,chart?:ChartBinding):Promise<boolean> => {
    if (busy || chartLoading) return false;
    const request=generation.current,current=()=>generation.current===request && !switching.current;
    setChartLoading(true);
    try {
      if(!(await flush()))throw Error('Save the board before adding the diagram.');
      let chartPreview:Awaited<ReturnType<typeof api.snapshotPreview>> | undefined;
      let chartFailed=false;
      if(chart){
        try {
          if(chart.documentId!==documentId)throw Error('Chart source is unavailable.');
          chartPreview=await api.snapshotPreview(documentId,chart.snapshotId,'chart');
          if(chartPreview.snapshot_sha256!==chart.snapshotHash)throw Error('Chart source changed.');
        } catch { chartPreview=undefined; chartFailed=true; }
      }
      const doc=await api.getDocument(documentId);
      if(!current())return false;
      if(!stillValid())throw Error('The selected evidence changed. Select it and try again.');
      for(const node of diagram.nodes){
        const ref=node.binding;if(!ref)continue;
        if(ref.documentId!==documentId)throw Error('A diagram source is unavailable.');
        if(ref.datasetId && ref.datasetHash){const data=await api.dataset(documentId,ref.datasetId);if(!current())return false;if(data.sha256!==ref.datasetHash)throw Error('A diagram table changed.');}
        else if(!ref.snapshotId || (ref.cardId && doc.state.cards[ref.cardId]?.snapshot_id!==ref.snapshotId) || doc.snapshots?.[ref.snapshotId]?.snapshot_sha256!==ref.snapshotHash)throw Error('A diagram source changed. Ask again using the current evidence.');
      }
      if(chart && chartPreview && ((chart.cardId && doc.state.cards[chart.cardId]?.snapshot_id!==chart.snapshotId) || doc.snapshots?.[chart.snapshotId]?.snapshot_sha256!==chart.snapshotHash)){chartPreview=undefined;chartFailed=true;}
      if(explanation && !(await verifyTableExplanation(explanation,current,doc)))return false;
      if(!stillValid())throw Error('The selected evidence changed. Select it and try again.');
      const items = editor.getSceneElements();
      const x = items.length ? Math.max(...items.map((item) => item.x + item.width)) + 100 : 100;
      const originalIds=wholeBoardNotes.current
        ? boardSourceIds.current
        : selectedElements.current;
      const shapes=diagramShapes(diagram, documentId, selection.current, x, 100, () => uid('node'), originalIds);
      if(explanation){
        const link=new URL(`./studio.html?board=${encodeURIComponent(documentId)}`,document.baseURI).href;
        const bottom=Math.max(...shapes.filter(shape=>shape.type==='rectangle').map(shape=>shape.y+shape.height));
        shapes.push(...explanationElements(explanation,documentId,selection.current,{...(datasetSelection.current || {}),...(sourceSelection.current || {})},x,bottom+75,link,originalIds));
      }
      if(chart && chartPreview){
        try { shapes.push(...comparisonChart(chartPreview.visual,chart.title,chart,x+800,100)); }
        catch { chartFailed=true; }
      }
      const elements = convertToExcalidrawElements(shapes, { regenerateIds: false });
      const originals=items.filter(item=>selectedElements.current.includes(item.id));
      if(!(await place(items,[...items,...elements],elements,{clearSelection:true,fit:explanation?[...originals,...elements]:elements})))return false;
      diagramElementIds.current = elements.map(item=>item.id);
      if(wholeBoardNotes.current)for(const item of elements)if(item.type==='text')sourceFingerprint.current.set(item.id,sourceContent(item));
      const chartAdded=Boolean(chart && chartPreview && !chartFailed);
      if(chartAdded)setAutomaticChart(true);
      setStatus(chartFailed?'Diagram added. The chart could not be added; try the chart button.':chartAdded?'Diagram and chart added to the board.':explanation?'Explanation and diagram added to the board.':'Diagram added to the board.');return true;
    } catch (error) { if(current())setStatus((error as Error).message);return false; }
    finally{if(current())setChartLoading(false);}
  };

  const showDiagram = (part:'diagram'|'explanation'|'idea'='diagram') => {
    const ids=new Set(diagramElementIds.current);
    const items=editor.getSceneElements().filter(item=>ids.has(item.id) && !item.isDeleted);
    if(!items.length){setStatus('The diagram is no longer on this board.');return;}
    const request=generation.current;
    setOpen(false);
    requestAnimationFrame(()=>requestAnimationFrame(()=>{
      if(generation.current!==request || switching.current)return;
      const current=editor.getSceneElements().filter(item=>ids.has(item.id) && !item.isDeleted);
      if(!current.length)return;
      const nodes=current.filter(item=>item.type==='rectangle' && (item.customData as any)?.fireatlas?.kind==='assistant-diagram');
      const explanation=current.find(item=>item.type==='text' && (item.customData as any)?.fireatlas?.kind==='assistant-explanation');
      const idea=nodes.find(item=>(item.customData as any)?.fireatlas?.nodeKind==='interpretation');
      const target=part==='explanation' ? (explanation?[explanation]:[]) : part==='idea' ? (idea?[idea]:[]) : window.innerWidth<600 ? nodes.slice(0,1) : nodes;
      if(target.length)editor.scrollToContent(target,{fitToContent:true,...(part==='diagram'?{viewportZoomFactor:.95}:part==='idea'?{minZoom:window.innerWidth<360?.7:.8,maxZoom:1}:{})});
    }));
  };

  const addChart = async (binding: ChartBinding,explanation?:Answer):Promise<boolean> => {
    if (busy || chartLoading || binding.documentId !== documentId) return false;
    const request = generation.current;
    const current = () => generation.current === request && !switching.current;
    setChartLoading(true); setStatus('Preparing chart…');
    try {
      const preview = await api.snapshotPreview(documentId, binding.snapshotId, 'chart');
      if (!current()) return false;
      if (!(await flush())) throw Error('Save the board before adding the chart.');
      if (!current()) return false;
      const document = await api.getDocument(documentId);
      if (!current()) return false;
      if(!sourceUnchanged())throw Error('The selected source changed. Select it and ask again.');
      if ((binding.cardId && document.state.cards[binding.cardId]?.snapshot_id !== binding.snapshotId) || preview.snapshot_sha256 !== binding.snapshotHash || document.snapshots?.[binding.snapshotId]?.snapshot_sha256!==binding.snapshotHash) throw Error('The source changed. Ask again using the current evidence.');
      if(explanation && !(await verifyTableExplanation(explanation,current,document)))return false;
      if(!sourceUnchanged())throw Error('The selected source changed. Select it and ask again.');
      const items = editor.getSceneElements();
      const x = items.length ? Math.max(...items.map((item) => item.x + item.width)) + 100 : 100;
      const shapes=comparisonChart(preview.visual, binding.title, binding, x, 100);
      if(explanation){const link=new URL(`./studio.html?board=${encodeURIComponent(documentId)}`,window.document.baseURI).href;shapes.push(...explanationElements(explanation,documentId,selection.current,{...(datasetSelection.current || {}),...(sourceSelection.current || {})},x+850,100,link,selectedElements.current));}
      const elements = convertToExcalidrawElements(shapes);
      if(!(await place(items,[...items,...elements],elements)))return false;
      setStatus(explanation?'Explanation and chart added to the board.':'Chart added to the board.'); return true;
    } catch (error) { if (current()) setStatus((error as Error).message); return false; }
    finally { if(current())setChartLoading(false); }
  };
  const verifyTableExplanation = async (explanation:Answer,current:()=>boolean,loaded?:Awaited<ReturnType<typeof api.getDocument>>):Promise<boolean> => {
    const doc=loaded ?? await api.getDocument(documentId);
    if(!current())return false;
    for(const claim of explanation.claims || []){
      const ref=claim.binding;
      if(ref && (ref.documentId!==documentId || (ref.cardId && doc.state.cards[ref.cardId]?.snapshot_id!==ref.snapshotId) || doc.snapshots?.[ref.snapshotId]?.snapshot_sha256!==ref.snapshotHash))throw Error('An explanation source changed. Ask again.');
      const source=claim.source_binding;
      if(source && source.documentId!==documentId)throw Error('An explanation source is unavailable.');
      if(source?.datasetId && source.datasetHash){const data=await api.dataset(documentId,source.datasetId);if(!current())return false;if(data.sha256!==source.datasetHash)throw Error('An explanation table changed.');}
      if(source?.sourceDocumentId && source.sourceDocumentHash){const data=await api.sourceDocuments(documentId);if(!current())return false;if(!data.documents.some(item=>item.id===source.sourceDocumentId && item.sha256===source.sourceDocumentHash))throw Error('An explanation document changed.');}
    }
    return current();
  };
  const tableExplanation = (answer:Answer,x:number) => {
    const link=new URL(`./studio.html?board=${encodeURIComponent(documentId)}`,window.document.baseURI).href;
    return explanationElements(answer,documentId,selection.current,{...(datasetSelection.current || {}),...(sourceSelection.current || {})},x,100,link,selectedElements.current);
  };
  const tableDiagram = (binding:ScatterBinding | GroupBinding,x:number,modelDiagram?:Diagram) => {
    const chartLabel='groupColumn' in binding ? `Mean ${binding.valueColumn} by ${binding.groupColumn}` : `${binding.yColumn} versus ${binding.xColumn}`;
    const shapes=diagramShapes(modelDiagram || {nodes:[{id:'source',kind:'evidence',label:'Selected table'},{id:'chart',kind:'evidence',label:chartLabel},{id:'question',kind:'question',label:'What does this comparison show?'}],edges:[{source:'source',target:'chart',relation:'context'},{source:'chart',target:'question',relation:'question'}]},documentId,selection.current,x,100,()=>uid('node'));
    for(const shape of shapes){if(shape.customData?.fireatlas)Object.assign(shape.customData.fireatlas,binding);}
    return shapes;
  };
  const addScatter = async (binding:ScatterBinding,stillValid=sourceUnchanged,explanation?:Answer,diagram: boolean | Diagram=false):Promise<boolean> => {
    if(busy || chartLoading || binding.documentId!==documentId)return false;
    const request=generation.current,current=()=>generation.current===request && !switching.current;
    setChartLoading(true);setStatus('Preparing chart…');
    try {
      const data=await api.datasetScatter(documentId,binding.datasetId,binding.xColumn,binding.yColumn);
      if(!current())return false;
      if(data.dataset_id!==binding.datasetId || data.sha256!==binding.datasetHash || data.x_column!==binding.xColumn || data.y_column!==binding.yColumn)throw Error('The table source changed. Ask again using the current table.');
      if(!(await flush()))throw Error('Save the board before adding the chart.');
      if(!current())return false;
      if(explanation && !(await verifyTableExplanation(explanation,current)))return false;
      if(!stillValid())throw Error('The selected table changed. Select it and try again.');
      const fileId=crypto.randomUUID(),file={id:fileId,mimeType:'image/png',dataURL:renderScatter(data),created:Date.now()};
      if(new TextEncoder().encode(JSON.stringify(file)).length>1_500_000)throw Error('The chart image is too large for this board.');
      const items=editor.getSceneElements(),x=items.length?Math.max(...items.map((item)=>item.x+item.width))+100:100;
      const customData={fireatlas:{...binding,kind:'dataset-scatter',plottedRows:data.points.length,skippedRows:data.skipped_rows}};
      const chartX=x+(diagram?800:0);
      const shapes:any[]=diagram?tableDiagram(binding,x,typeof diagram==='object'?diagram:undefined):[];
      shapes.push({type:'image',x:chartX,y:100,width:960,height:600,fileId,status:'saved',customData});
      if(explanation)shapes.push(...tableExplanation(explanation,chartX+1060));
      const elements=convertToExcalidrawElements(shapes,{regenerateIds:false});
      if(!(await place(items,[...items,...elements],elements,{clearSelection:true,files:[file as any]})))return false;
      window.dispatchEvent(new Event('fireatlas-whiteboard-close-table'));setStatus(diagram?'Diagram and chart added to the board.':explanation?'Explanation and chart added to the board.':'Chart added to the board.');return true;
    } catch(error){if(current())setStatus((error as Error).message);return false;}
    finally{if(current())setChartLoading(false);}
  };
  const addGroupChart = async (binding:GroupBinding,stillValid=sourceUnchanged,explanation?:Answer,diagram: boolean | Diagram=false):Promise<boolean> => {
    if(busy || chartLoading || binding.documentId!==documentId)return false;
    const request=generation.current,current=()=>generation.current===request && !switching.current;
    setChartLoading(true);setStatus('Preparing grouped chart…');
    try{
      const data=await api.datasetGroups(documentId,binding.datasetId,binding.groupColumn,binding.valueColumn);
      if(!current())return false;
      if(data.dataset_id!==binding.datasetId || data.sha256!==binding.datasetHash || data.group_column!==binding.groupColumn || data.value_column!==binding.valueColumn)throw Error('The table source changed. Ask again.');
      if(!(await flush()))throw Error('Save the board before adding the chart.');
      if(!current())return false;
      if(explanation && !(await verifyTableExplanation(explanation,current)))return false;
      if(!stillValid())throw Error('The selected table changed. Select it and try again.');
      const items=editor.getSceneElements(),x=items.length?Math.max(...items.map(item=>item.x+item.width))+100:100;
      const chartX=x+(diagram?800:0);
      const shapes=diagram?tableDiagram(binding,x,typeof diagram==='object'?diagram:undefined):[];
      shapes.push(...groupChart(data,{...binding,kind:'dataset-group-chart'},chartX,100,()=>uid('group')));
      if(explanation)shapes.push(...tableExplanation(explanation,chartX+850));
      const elements=convertToExcalidrawElements(shapes,{regenerateIds:false});
      if(!(await place(items,[...items,...elements],elements,{clearSelection:true})))return false;
      window.dispatchEvent(new Event('fireatlas-whiteboard-close-table'));setStatus(diagram?'Diagram and chart added to the board.':explanation?'Explanation and grouped chart added to the board.':'Grouped chart added to the board.');return true;
    }catch(error){if(current())setStatus((error as Error).message);return false;}
    finally{if(current())setChartLoading(false);}
  };

  const resolveSourceMatch = async (match:SourceMatch):Promise<ChallengeSource> => {
      let ref:Record<string,unknown>;
      if(!match || typeof match.name!=='string' || typeof match.excerpt!=='string' || !match.excerpt || match.excerpt.length>1000)throw Error('This source match is unavailable.');
      if(match.kind==='csv' && Number.isInteger(match.row_offset) && (match.row_offset as number)>=0){
        const table=await api.dataset(documentId,match.source_id,match.row_offset);
        const index=table.columns.indexOf(match.column || '');
        if(table.sha256!==match.source_sha256 || index<0 || !table.preview[0]?.[index]?.includes(match.excerpt))throw Error('The source row is unavailable. Search again.');
        ref={datasetId:match.source_id,datasetHash:match.source_sha256,rowOffset:match.row_offset};
      } else if(match.kind==='pdf' && Number.isInteger(match.page) && (match.page as number)>0){
        const documents=await api.sourceDocuments(documentId);
        if(!documents.documents.some(item=>item.id===match.source_id && item.sha256===match.source_sha256))throw Error('The source document is unavailable. Search again.');
        ref={sourceDocumentId:match.source_id,sourceDocumentHash:match.source_sha256,page:match.page};
      } else throw Error('This source match is unavailable.');
      const location=match.kind==='pdf'?`Page ${match.page}`:`CSV record ${(match.row_offset as number)+2} · ${match.column}`;
      return {kind:match.kind,name:match.name,excerpt:match.excerpt,location,ref};
  };

  const addSourceMatch = async (match:SourceMatch) => {
    if(busy || chartLoading)return;
    const request=generation.current, current=()=>generation.current===request && !switching.current;
    setChartLoading(true);setStatus('Preparing source…');
    try {
      const {ref,location}=await resolveSourceMatch(match);
      if(!current())return;
      if(!sourceUnchanged())throw Error('The selected source changed. Select it and ask again.');
      const items=editor.getSceneElements(),x=items.length?Math.max(...items.map(item=>item.x+item.width))+100:100;
      const text=wrapExplanation(`${match.name} · ${location}\n\n${match.excerpt}`);
      const elements=convertToExcalidrawElements([{type:'text',x,y:100,text,fontSize:18,strokeColor:'#183149',customData:{fireatlas:{documentId,...ref,kind:'source-search-match'}}}]);
      if(!(await place(items,[...items,...elements],elements)))return;
      setStatus('Source excerpt added to the board.');
    } catch(error){if(current())setStatus((error as Error).message);}
    finally{setChartLoading(false);}
  };

  useEffect(()=>{if(!working)setCue(current=>current?.phase==='reading'?null:current);},[working]);

  return <div className="whiteboard-assistant">
    {cue && <div ref={cueNode} className={`assistant-canvas-cue assistant-canvas-cue--${cue.phase}`} aria-hidden="true"><svg viewBox="0 0 20 24" width="18" height="22"><path d="M2 1 17 12l-7 1-3 8z" fill="#173f39" stroke="white" strokeWidth="1.5" strokeLinejoin="round"/></svg><span className="assistant-cue-label"><span className="assistant-cue-dot"/>{({reading:'Reading',placed:'Added',moved:'Moved',connected:'Connected',pointing:'Look here'})[cue.phase]}</span></div>}
    <button ref={launcherNode} type="button" className="assistant-launcher" aria-disabled={placing || undefined} onClick={() => {if(placing)return;setOpen(!open);setWatching(false);}} aria-expanded={open} aria-controls="investigation-assistant-panel"><span className={`assistant-orb${(working || placing)?' is-working':''}${listening?' is-listening':''}${speaking?' is-speaking':''}`} aria-hidden="true"><i/><i/></span><span aria-live="polite">{listening?'Listening…':placing?'Drawing on board…':working?'Working…':watching?'View update':'Ask AI'}</span></button>
    {placing ? <button type="button" className="assistant-placement-stop" onClick={cancel}>Stop</button> : <span className="assistant-island-hint">Explain · Draw · Challenge</span>}
    {open && <section id="investigation-assistant-panel" className="whiteboard-assistant-panel" aria-label="Investigation assistant" onKeyDown={(event)=>{if(event.key==='Escape'){event.stopPropagation();setOpen(false);launcherNode.current?.focus();}}}>
      <div className="whiteboard-assistant-heading research-lab-heading"><div><span className="assistant-eyebrow">IGNIS / SCIENTIFIC FIELD LAB</span><strong>Follow the evidence.</strong><p>Compare observations. Find the missing context.</p><div className="research-domains"><span>NASA FIRMS</span><span>Earthdata</span><span>Literature</span></div></div><button type="button" aria-label="Close assistant" onClick={() => {setOpen(false);launcherNode.current?.focus();}}>×</button></div>
      <div className="research-mode" role="group" aria-label="Investigation mode"><button type="button" aria-pressed={!researchTeam} disabled={working || busy || chartLoading} onClick={()=>setResearchTeam(false)}>Solo investigation</button><button type="button" aria-pressed={researchTeam} disabled={working || busy || chartLoading} onClick={()=>setResearchTeam(true)}>Research team <span>3 specialists</span></button></div>
      {researchTeam && <p className="research-budget-note">Up to $0.02 extra per review. Requires a verified low-cost model. Your main investigation uses its normal allowance.</p>}
      <label htmlFor="whiteboard-question">Question</label>
      <textarea id="whiteboard-question" autoFocus onKeyDown={event=>{if(event.key==='Enter' && (event.ctrlKey || event.metaKey)){event.preventDefault();void ask();}}} value={listening && interim ? interim : message} maxLength={3000} onChange={(event) => setMessage(event.target.value)} placeholder="What does this evidence show?" />
      <div className="assistant-actions"><button type="button" disabled={working || busy || chartLoading || !message.trim()} onClick={() => void ask()}>Ask</button><button type="button" className={`assistant-mic${listening?' is-listening':''}`} aria-pressed={listening} aria-label={listening?'Stop listening and send':'Talk to the assistant (or hold Ctrl+Alt)'} disabled={working || busy || chartLoading} onClick={()=>listening?stopListening():startListening()}>{listening?'Send':'Talk'}</button><button type="button" className="assistant-voice" aria-pressed={voiceReply} aria-label="Read answers aloud" onClick={toggleVoiceReply}>{voiceReply?'Voice on':'Voice off'}</button>{speaking && <button type="button" onClick={stopSpeaking}>Hush</button>}<button type="button" disabled={working || busy || chartLoading} onClick={() => void ask(true)}>Challenge selection</button>{working && <><button type="button" onClick={cancel}>Stop</button><button type="button" onClick={()=>{setWatching(true);setOpen(false);launcherNode.current?.focus();}}>Watch on board</button></>}</div>
      {!result && !working && <div className="assistant-quick-guide"><p>Add evidence, select it, then try <strong>“Explain and diagram this.”</strong> Use <strong>Challenge selection</strong> for another interpretation.</p>{onAddEvidence && <button type="button" onClick={()=>{setOpen(false);onAddEvidence();}}>Add evidence</button>}</div>}
      {conversation.length>0 && <details className="whiteboard-conversation"><summary>Recent conversation</summary>{conversation.map((turn,index)=><div key={index}><p><strong>You:</strong> {turn.question}</p><p><strong>AI:</strong> {turn.research_answer ? turn.title : turn.summary || turn.title}</p>{(turn.claims || []).map((claim,i)=><p key={i}>{formatClaim(claim)}</p>)}{turn.research_answer && <ResearchBriefPanel brief={turn.research_answer} sources={turn.web_sources || []} readings={turn.public_readings}/>}{turn.public_readings?.length ? <PublicReadingPanel reports={turn.public_readings}/> : null} {turn.web_sources?.filter(source=>source.url.startsWith("https://")).map(source=><p key={source.url}><a href={source.url} target="_blank" rel="noopener noreferrer">{source.title} ↗</a></p>)}{turn.research_team && <ResearchTeamPanel report={turn.research_team}/>}</div>)}</details>}
      {conversationError && <p role="status">Recent conversation couldn’t load. <button type="button" onClick={()=>setConversationRevision(value=>value+1)}>Retry</button></p>}
      {working && activity.length>0 && <ol className="research-activity" aria-label="Live research activity">{activity.slice(-4).map(step=><li key={step.id}><span aria-hidden="true"/><div>{step.message}</div></li>)}</ol>}
      {status && <p role="status" className="assistant-status">{working && <span className="assistant-status-orbit" aria-hidden="true"/>}{status}</p>}
      {dataViewElements.current.map(item=><button type="button" key={item.id} disabled={busy || working || chartLoading} onClick={()=>showDataView(item.id)}>View {({'firms-region-heatmap':'regional heatmap','firms-region-calendar':'reading calendar','firms-country-calendar':'reading calendar','firms-region-readings':'reading table','firms-country-readings':'reading table','firms-region-satellites':'satellite comparison','firms-country-satellites':'satellite comparison','firms-region-coordinates':'coordinate map','archived-readings':'reading table','export-status':'export status','persistence-summary':'persistence','monthly-comparability-summary':'comparability','harmonized-summary':'harmonization','inventory-summary':'source inventory','overlap-summary':'sensor overlap','coverage-summary':'coverage','validation-summary':'validation','firms-country':'country readings','firms-country-heatmap':'country heatmap',heatmap:'heatmap',coordinates:'coordinate map',satellites:'satellite chart','park-satellites':'satellite chart',calendar:'calendar',similar:'candidate profiles',archive:'archive',factors:'measured factors',analogues:'environmental matches',note:'note'} as Record<string,string>)[item.kind] || item.kind}</button>)}
      {automaticDiagram && diagramElementIds.current.length>0 && <button type="button" disabled={busy || working || chartLoading} onClick={()=>showDiagram('diagram')}>View diagram</button>}
      {automaticDiagram && result?.diagram?.nodes.some(node=>node.kind==='interpretation') && <button type="button" disabled={busy || working || chartLoading} onClick={()=>showDiagram('idea')}>Read key idea</button>}
      {automaticDiagram && automaticExplanation && <button type="button" disabled={busy || working || chartLoading} onClick={()=>showDiagram('explanation')}>View explanation</button>}
      {result?.data_views?.length && !automaticChart && <button type="button" disabled={busy || working || chartLoading} onClick={()=>void addDataViews(result.data_views!,sourceUnchanged,undefined,result)}>Add scientific views</button>}
      {result?.research_answer && <ResearchBriefPanel brief={result.research_answer} sources={result.web_sources || []} readings={result.public_readings}/>}
      {!!result?.public_readings?.length && <PublicReadingPanel reports={result.public_readings}/>}
      {!!result?.web_sources?.length && <section aria-label="Public references"><ul className="assistant-view-options">{result.web_sources.filter(source=>source.url.startsWith('https://')).map(source=><li key={source.url}><a href={source.url} target="_blank" rel="noopener noreferrer">{source.id && <span className="research-reference-id">{source.id}</span>} {source.title}</a><small>{source.provider}{source.snippet ? ' · '+source.snippet : ''}</small>{source.id && <button type="button" disabled={busy || working || placing} onClick={()=>void ask(false,`Read the original methods passages for ${source.id}. Explain what was actually read and what remains unavailable. Source URL: ${source.url}`)}>Read original methods</button>}</li>)}</ul><button type="button" disabled={busy || working || placing} onClick={()=>void pinWebSources(result.web_sources!).catch(error=>setStatus(error.message))}>Pin references to board</button></section>}
      {result?.research_team && <ResearchTeamPanel report={result.research_team}/>}
      {result && <article><strong>{result.title}</strong><p className="assistant-answer-origin">{result.ai_wording_unavailable?'Source results · model explanation unavailable':result.kind==='Live NASA FIRMS'?'Live data · NASA FIRMS':result.kind==='View catalog'?'Saved view catalog':result.kind==='Saved scientific view'?'Saved data · checked source':result.model ? 'AI · '+result.model : null}</p><p>{!result.research_answer && (result.summary || result.interpretation)}</p>{Boolean(result.view_options?.length) && <ul className="assistant-view-options">{result.view_options!.map(option=><li key={option.question}><div><strong>{option.label}</strong><small>{option.detail}</small></div><button type="button" aria-label={option.action?`Add ${option.label}`:`Add ${option.label} heatmap`} disabled={busy || working || chartLoading} onClick={()=>void ask(false,option.question)}>{option.action || 'Add heatmap'}</button></li>)}</ul>}{Boolean(result.claims?.length) && <details className="assistant-source-values"><summary>{result.claims!.length} checked source values</summary>{result.claims!.map((claim,index)=><p key={index}>{formatClaim(claim)}</p>)}</details>}{Boolean(result.limitations?.length) && <details className="assistant-source-notes"><summary>Source notes</summary>{result.limitations!.map((line,index)=><p key={index}>{line}</p>)}</details>}{selectedElements.current.length>0 && <button type="button" disabled={busy} onClick={showSource}>Show selected source</button>}{!automaticExplanation && !result.view_options?.length && result.kind!=='Assistant unavailable' && <button type="button" disabled={busy || working || chartLoading} onClick={add}>Add explanation to board</button>}{result.diagram && !automaticDiagram && <button type="button" disabled={busy || chartLoading} onClick={()=>void addDiagram(result.diagram!)}>Add diagram to board</button>}{(result.visualizations || []).filter((item) => !automaticChart && item.kind === 'monthly-comparison' && item.binding).map((item,index) => <button type="button" key={`comparison-${index}`} disabled={busy || working || chartLoading} onClick={() => void addChart(item.binding as ChartBinding)}>Add comparison chart</button>)}{(result.visualizations || []).filter((item)=>!automaticChart && item.kind==='csv-scatter' && item.binding).map((item,index)=><button type="button" key={`scatter-${index}`} disabled={busy || chartLoading} onClick={()=>void addScatter(item.binding as ScatterBinding)}>Add scatter plot</button>)}{(result.visualizations || []).filter(item=>!automaticChart && item.kind==='csv-groups' && item.binding).map((item,index)=><button type="button" key={`groups-${index}`} disabled={busy || chartLoading} onClick={()=>void addGroupChart(item.binding as GroupBinding)}>Add grouped chart</button>)}{(result.source_matches || []).map((match,index)=><div key={`source-${index}`}><p>{match.name} · {match.kind==='pdf'?`page ${match.page}`:`CSV record ${(match.row_offset ?? 0)+2}`}</p><p>{match.excerpt}</p>{onOpenSource && <button type="button" disabled={busy || working || chartLoading} onClick={()=>{setOpen(false);onOpenSource(match);}}>Open original</button>}<button type="button" disabled={busy || chartLoading} onClick={()=>void addSourceMatch(match)}>Add source excerpt</button></div>)}</article>}
      <p>{selectedCount>0?`${selectedCount} selected. Ask about ${selectedCount===1?'it':'them'}, or pick a quick start.`:'Select a note, image, drawing or evidence, or ask about the whole investigation.'}</p>
      <div className="assistant-chips" role="group" aria-label="Quick starts">{SUGGESTIONS.filter(item=>item.needsSelection===undefined || item.needsSelection===(selectedCount>0)).map(item=><button type="button" key={item.label} className="assistant-chip" disabled={working || busy || chartLoading} onClick={()=>void ask(false,item.question)}>{item.label}</button>)}</div>
      <details className="assistant-data-starters" open><summary>Bring in a real data view</summary><div className="assistant-chips">{[
        {label:'Park heatmap',question:'Show a heatmap of Park Fire on 2024-07-27, using the July 25–28 study, and add a short interpretation note.'},
        {label:'Park coordinates',question:'Show an original-coordinate map of Park Fire thermal records on 2024-07-27.'},
        {label:'Park satellites',question:'Show the published four-platform satellite comparison for Park Fire, July 25–28, 2024.'},
        {label:'Park calendar',question:'Show a MODIS raw observed-cell calendar for Park Fire, July 25–28, 2024.'},
        {label:'Find similar profiles',question:'Find candidate thermal-observation profiles similar to Park Fire over 2024-07-25 to 2024-07-28 using MODIS and the available imported archive. Bring a real coordinate view for a returned candidate and connect the views. Explain why the candidate is worth comparing.'},
        {label:'Measured factors',question:'Show the measured NDVI and elevation maps for the Park Fire July 25–28, 2024 pilot. Explain the main differences and a useful question to investigate.'}
      ].map(item=><button type="button" className="assistant-chip" key={item.label} disabled={working || busy || chartLoading} onClick={()=>void ask(false,item.question)}>{item.label}</button>)}</div><p>Try “What readings can you bring?” or “Show a heatmap and reading calendar for Rajshahi.”</p></details>
      <details className="assistant-data-starters"><summary>Board tools and web search</summary><p>Label map detections, label a selected object, add a note, arrange objects, connect selections or pin public references.</p><p>Try “Label the heatmap”, “Add a note saying Check the April pass”, or “Find papers on VIIRS fire detection and pin the results”.</p></details>
    </section>}
  </div>;
}
