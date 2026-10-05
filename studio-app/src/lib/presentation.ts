import { api } from '../api';
import { adaptAudience } from './audience';
import type { DocumentView, StoryBody, WorkflowDefinition } from '../types';

export const PRESENTATIONS = [
  { id: 'park-2024', title: 'Park · two sensors, one study', eyebrow: 'SENSOR COMPARISON', description: 'Paired heat maps → daily activity → source states → original rows. A guided historical comparison with the July processing gap visible.', duration: 90, tone: 'ember' },
  { id: 'camp-2018', title: 'Camp · read the archive honestly', eyebrow: 'HISTORICAL EVIDENCE', description: 'Paired heat maps and recorded activity connected to the partial-export ledger. See what the archive supports without filling its gaps.', duration: 90, tone: 'forest' },
  { id: 'grove-2025', title: 'Grove · a small, inspectable example', eyebrow: 'QUICK WALKTHROUGH', description: 'A short three-scene study: paired maps, the seven recorded detections, and the evidence boundary. Ideal for demonstrating the workflow clearly.', duration: 45, tone: 'cobalt' }
] as const;

/** Every branch retains the full result. Only display outputs are arranged here. */
export function presentationWorkflow(): WorkflowDefinition {
  return { nodes: [
    { id: 'replay', type: 'operation', label: 'Frozen study observations', params: { operation: 'replay', arguments: {} }, position: { x: 0, y: 100 } },
    { id: 'map', type: 'card_output', label: 'Sensor map', params: { card_type: 'map', title: 'Recorded common-cell map' }, inputs: { content: 'replay' }, position: { x: 300, y: 0 } },
    { id: 'chart', type: 'card_output', label: 'Daily activity', params: { card_type: 'chart', title: 'Daily occupied cells' }, inputs: { content: 'replay' }, position: { x: 300, y: 200 } },
    { id: 'states', type: 'operation', label: 'Export and processing states', params: { operation: 'missingness', arguments: {} }, position: { x: 0, y: 400 } },
    { id: 'timeline', type: 'card_output', label: 'Every UTC date', params: { card_type: 'timeline', title: 'Availability timeline' }, inputs: { content: 'states' }, position: { x: 300, y: 400 } },
    { id: 'story', type: 'story_output', label: 'Editable evidence briefing', params: { title: 'Curated study briefing' }, inputs: { items: ['map', 'chart', 'timeline'] }, position: { x: 650, y: 100 } },
    { id: 'export', type: 'export_prep', label: 'Reproducible evidence inventory', inputs: { items: ['map', 'chart', 'timeline'] }, position: { x: 650, y: 400 } }
  ] };
}

export async function buildPresentation(id: typeof PRESENTATIONS[number]['id'], hooks: { open: (doc: DocumentView) => void; current: (id: string, revision?: number) => boolean; progress: (text: string) => void }): Promise<DocumentView> {
  const preset = PRESENTATIONS.find((p) => p.id === id)!;
  let board = await api.createDocument(preset.title, { context: { case: id } });
  hooks.open(board);
  const check = () => { if (!hooks.current(board.id, board.context_revision)) throw new Error('Presentation preparation stopped because the applied board changed. The saved draft is retained.'); };
  hooks.progress('Arranging the investigation…');
  const built = await api.studioAction(board.id, { action: 'build_investigation', base_revision: board.revision });
  check(); board = built.document!; hooks.open(board);
  const evidence = new Map<string, string>();
  const patches: any[] = [];
  for (const cid of board.state.order) {
    const card = board.state.cards[cid]; if (!card.binding) continue;
    check(); hooks.progress(`Freezing ${card.title}…`);
    const signature = JSON.stringify(card.binding);
    if (!evidence.has(signature)) { const result = await api.resolveBinding(board.id, card.binding); check(); evidence.set(signature, result.snapshot.id); }
    patches.push({ op: 'update_card', id: cid, patch: { snapshot_id: evidence.get(signature) } });
  }
  board = await api.transact(board.id, board.revision, patches, { group_id: 'presentation-evidence' }); check(); hooks.open(board);
  const map = board.state.cards['starter-1'];
  const receipt = await api.snapshotReceipt(board.id, map.snapshot_id!); check();
  const frames = receipt.receipt.payload.frames;
  const paired = frames.filter((frame: any) => frame.products.MODIS_SP.cell_days > 0 && frame.products.VIIRS_SNPP_SP.cell_days > 0);
  const peak = (paired.length ? paired : frames).reduce((best: any, frame: any) => frame.joint_cell_days > best.joint_cell_days ? frame : best).date_utc;
  const modis = { ...map, title: 'MODIS · occupied-cell heat', display: { preview: 'heat', source: 'MODIS_SP', day: peak }, transform: { x: 40, y: 40, w: 460, h: 400 } };
  const viirs = { ...map, id: 'presentation-viirs', title: 'S-NPP VIIRS · occupied-cell heat', display: { preview: 'heat', source: 'VIIRS_SNPP_SP', day: peak }, transform: { x: 540, y: 40, w: 460, h: 400 } };
  const positions = [[40, 40, 460, 400], [1040, 40, 420, 400], [40, 500, 460, 320], [540, 500, 460, 320], [1040, 500, 420, 320], [40, 880, 960, 160], [1040, 880, 420, 160]];
  const ops: any[] = board.state.order.map((cid, index) => ({ op: 'update_card', id: cid, patch: cid === map.id ? { title: modis.title, display: modis.display, transform: modis.transform } : { transform: Object.fromEntries(['x', 'y', 'w', 'h'].map((k, j) => [k, positions[index][j]])) } }));
  ops.push({ op: 'add_card', card: viirs });
  for (const [source, target, kind] of [[map.id, viirs.id, 'compare'], [map.id, 'starter-2', 'context'], ['starter-2', 'starter-3', 'context'], ['starter-2', 'starter-4', 'context'], [map.id, 'starter-5', 'context']]) ops.push({ op: 'connect', connection: { id: `presentation-${source}-${target}`, source, target, kind } });
  ops.push({ op: 'set_group', group: { id: 'presentation-sensors', title: '01 / Two sensor views · shared scale', card_ids: [map.id, viirs.id] } });
  hooks.progress('Connecting the presentation…');
  board = await api.transact(board.id, board.revision, ops, { group_id: 'presentation-layout' }); check();
  board = await api.getDocument(board.id); check(); hooks.open(board);
  await api.saveWorkflow(board.id, presentationWorkflow()); check();
  const created = await api.createStory(board.id); check();
  let body: StoryBody = adaptAudience(created.body, 'presenter');
  body = { ...body, title: preset.title, target_duration_seconds: preset.duration, chapters: (id === 'grove-2025' ? [body.chapters[0], body.chapters[1], body.chapters[4]] : body.chapters).map((chapter) => ({ ...chapter, duration_seconds: 15, visible_cards: chapter.card_id === map.id ? [map.id, viirs.id] : chapter.visible_cards, ...(chapter.card_id === map.id ? { selection: { day: peak } } : {}) })) };
  const saved = await api.updateStory(created.id, created.revision, body); check();
  await api.resolveStory(saved.id); check();
  hooks.progress(`Ready · heat maps show ${peak} UTC, ${paired.length ? 'the highest recorded joint-cell date with detections in both sensors' : 'the highest recorded joint-cell date; a paired positive date is unavailable'}. The full study and its gaps remain in the timeline.`);
  return board;
}
