export type CardType = 'map' | 'chart' | 'timeline' | 'calendar' | 'finding' | 'observation' | 'table' | 'source-evidence' | 'method-note' | 'note-question' | 'chapter-frame' | 'image' | 'quote' | 'text';

export const CARD_TYPES: { type: CardType; label: string; hint: string }[] = [
  { type: 'chart', label: 'Chart', hint: 'Bars or lines of cited values' },
  { type: 'map', label: 'Map', hint: 'Frozen replay map (up to two live at once)' },
  { type: 'timeline', label: 'Timeline', hint: 'UTC dates and recorded states' },
  { type: 'calendar', label: 'Calendar', hint: 'Daily values on a calendar' },
  { type: 'finding', label: 'Finding', hint: 'Checked result with an interpretation' },
  { type: 'observation', label: 'Observation', hint: 'Selected source row or cell evidence' },
  { type: 'table', label: 'Table', hint: 'Exact cited rows' },
  { type: 'source-evidence', label: 'Source evidence', hint: 'Source and export status' },
  { type: 'method-note', label: 'Method note', hint: 'How a number is calculated' },
  { type: 'note-question', label: 'Note / question', hint: 'User-authored research prompt' },
  { type: 'chapter-frame', label: 'Chapter frame', hint: 'Selected cards for a story chapter' },
  { type: 'image', label: 'Image', hint: 'Licensed image with attribution' },
  { type: 'quote', label: 'Quote', hint: 'Attributed text' },
  { type: 'text', label: 'Text', hint: 'Plain note' }
];

export interface StudyContext { [key: string]: unknown; year?: number; month?: number; bbox?: number[] | string; start?: string; end?: string; region?: string | null; case?: string | null; scale?: string }
export interface Study { context?: StudyContext; ui?: Record<string, string | number | boolean | null> }

export interface Binding { operation: string; context?: StudyContext; arguments?: Record<string, unknown>; path?: string }
export interface Transform { x: number; y: number; w: number; h: number; rotation?: number }
export interface Card {
  id: string; type: CardType; title: string; text: string; binding: Binding | null; snapshot_id: string | null; asset_id: string | null;
  display: Record<string, unknown>; provenance: Record<string, unknown>; transform: Transform; follow: 'board' | 'pinned' | 'selected'; follow_card_id?: string | null; pinned_study: Study | null; locked?: boolean;
}
export interface Connection { id: string; source: string; target: string; kind: 'context' | 'scale' | 'compare' }
export interface CardGroup { id: string; title: string; card_ids: string[] }
export interface Viewport { x: number; y: number; zoom: number }
export interface DisplaySelection { day?: string; start?: string; end?: string; cell?: string }
export interface DocState {
  schema: string; title: string; study: Study; cards: Record<string, Card>; order: string[]; connections: Record<string, Connection>;
  groups?: Record<string, CardGroup>; viewport?: Viewport;
  story_id: string | null; workflow_id: string | null;
}
export interface Selection { board_id: string; document_revision: number; epoch: number; card_id: string | null }
export interface CapabilityState { available: boolean; reason?: string | null; [key: string]: unknown }
export interface Capabilities {
  story_generation?: CapabilityState & { provider?: string; disclosure?: string };
  canvas: CapabilityState & { engine?: string }; workflow: CapabilityState & { engine?: string }; video: CapabilityState; narration: CapabilityState;
  collaboration: CapabilityState & { adapter?: string }; mcp_apps?: CapabilityState; limits?: Record<string, number>; operations?: string[]; release?: { id: string } | null;
  assistant?: { ai_available: boolean; reason?: string };
  store_version?: number; static_reader?: { available: boolean; authoring?: string };
  context_layers?: Record<string, Record<string, { bounds: number[]; product: string; version: string }>>;
}
export interface DocumentView {
  id: string; title: string; revision: number; context_revision: number; state: DocState; selection: Selection; object_revisions: Record<string, number>;
  role: 'viewer' | 'editor' | 'owner' | null; owner: boolean; snapshots?: Record<string, Snapshot>; release?: { id: string } | null;
  changed?: boolean; touched?: string[]; idempotent_replay?: boolean;
  room?: RoomView | null;
}
export interface Fact { path: string; label: string; value: number | string | null; unit: string; state: 'observed' | 'unknown' | 'unavailable' }
export interface Snapshot {
  id: string; result_id: string; receipt_sha256: string; snapshot_sha256: string; release_id: string; release_frozen: boolean; operation: string;
  method: { id: string; unit: string; [k: string]: unknown }; unit: string; facts: Fact[]; scope: { bbox: number[]; start: string; end: string; day?: string | null };
  context: StudyContext; limitations: string[]; captured_utc: string;
}
export interface SnapshotReport {
  snapshot: Snapshot; verification: { verified: boolean; problems: string[]; receipt_checked: boolean };
  freshness: { fresh: boolean; snapshot_release_id: string; current_release_id: string | null; note: string };
}
export interface NarrationSegment { kind: 'text' | 'checked-field'; text?: string; path?: string; snapshot_id?: string; format?: string; author?: 'user' | 'assistant' }
export interface Chapter {
  id: string; title: string; caption: string; narration: string; narration_segments?: NarrationSegment[]; narration_template?: string | null; card_id: string | null; duration_seconds: number;
  transition: 'cut' | 'fade' | 'slide'; question?: { prompt: string; answer?: string } | null; evidence_cards: string[]; visible_cards?: string[];
  study?: StudyContext | null; selection?: Record<string, unknown> | null; camera?: Record<string, unknown>; layers?: string[]; source_filter?: unknown;
}
export interface StoryBody { title: string; profile: string; chapters: Chapter[]; author_note?: string; audience?: 'public' | 'student' | 'researcher' | 'reviewer' | 'presenter'; target_duration_seconds?: number; style?: Record<string, unknown> }
export interface StoryView {
  id: string; document_id: string; revision: number; latest_revision: number; title: string; body: StoryBody;
  resolved: ResolvedStory | null; profile: { width: number; height: number; fps: number; duration_seconds: number };
}
export interface ScaleContract { mode: string; statistic: string; unit: string; basis: string; observed_values: number; domain: [number, number] | null; warning?: string }
export interface Scene {
  chapter_id: string; title: string; start_seconds: number; duration_seconds: number; transition: string; caption: string; narration_text: string;
  narration_input?: { schema: string; authored_text: string; segments: NarrationSegment[] }; narration_grounding?: { mode: 'authored' | 'structured'; note: string };
  narration_checked: boolean; narration_unmatched_numbers: string[]; question: { prompt: string; answer?: string } | null;
  card: { id: string; type: CardType; title: string; display: Record<string, unknown>; text: string; asset_id: string | null } | null;
  evidence: string[]; scale: ScaleContract | null; study?: StudyContext | null; selection?: Record<string, unknown> | null; camera?: Record<string, unknown>; layers?: string[]; source_filter?: unknown; visible_cards?: string[]; visible_card_views?: { id: string; type: CardType; title: string; text: string; snapshot_id?: string | null; frozen: boolean; visual?: Record<string, unknown> | null }[]; narration_segments?: NarrationSegment[]; audience?: string;
  visual?: { kind?: string; camera_transition?: { from_bbox: number[]; to_bbox: number[]; duration_seconds: number }; [key: string]: unknown } | null;
  visual_svg?: string;
  fallback: { kind: 'bars' | 'table'; unit: string | null; domain?: [number, number]; bars?: { label: string; value: number; state: string }[]; rows?: { label: string; value: number | null; unit: string; state: string }[]; scope: Snapshot['scope'] | null };
}
export interface ResolvedStory {
  schema: string; title: string; profile: { width: number; height: number; fps: number; duration_seconds: number; id: string };
  scenes: Scene[]; snapshots: Record<string, Snapshot>; method: { id: string; unit: string }[]; units: string[]; limitations: string[]; audience?: string; target_duration_seconds?: number; duration_adapted?: boolean;
  warnings: { problem: string; message: string; chapter?: string; card?: string }[]; viewer_states: string[]; sha256: string;
}
export interface RenderJob {
  phase?: 'queued' | 'preparing-assets' | 'rendering' | 'encoding' | 'finalizing' | 'completed' | 'failed' | 'canceled';
  id: string; story_id: string; story_revision: number; created: number; status: 'queued' | 'running' | 'completed' | 'failed' | 'canceled'; progress: number; error: string | null;
  manifest: { narration: { status: string; reason?: string | null; disclosure?: string }; captions_fallback: boolean } | null; artifacts: Record<string, string>;
}
export interface StoryGenerationJob {
  id: string; document_id: string; document_revision: number; status: string; phase: string; progress: number;
  story_id: string | null; render_id: string | null; error: string | null; render?: RenderJob;
  receipt?: { provider: string; model: string } | null; can_resume?: boolean;
}
export type RenderSummary = Pick<RenderJob, 'id' | 'story_id' | 'story_revision' | 'status' | 'phase'> & { created: number };
export interface WorkflowNode { id: string; type: string; label?: string; params?: Record<string, unknown>; inputs?: Record<string, string | string[]>; position?: { x: number; y: number } }
export interface WorkflowDefinition { nodes: WorkflowNode[] }
export interface WorkflowRun { id: string; workflow_id: string; status: string; outputs: Record<string, any>; receipts: { node: string; cache_hit: boolean; output_sha256: string }[]; error: string | null }
export interface RoomView { id: string; document_id: string; adapter: string; members: { principal: string; role: string; you: boolean }[]; adapter_state?: { available: boolean; reason?: string } }
