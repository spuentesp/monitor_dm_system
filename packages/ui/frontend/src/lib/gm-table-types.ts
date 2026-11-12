// Phase 7 Part B — GM assistant at a real table: shared types.
// Kept beside gm-table-api.ts (not lib/types.ts) so the GM-table surface can
// evolve without colliding with the shared type file.

export interface PrepNpcItem {
  name: string;
  description: string;
  want: string;
  existing_entity_id: string | null;
}

export interface PrepLocationItem {
  name: string;
  description: string;
  existing_entity_id: string | null;
}

export interface PrepThreadItem {
  title: string;
  description: string;
  urgency: string;
  thread_id: string | null;
}

export interface PrepExtraction {
  npcs: PrepNpcItem[];
  locations: PrepLocationItem[];
  threads: PrepThreadItem[];
  notes_summary: string;
}

export interface GmPrepBundle {
  universe_id: string;
  story_id: string | null;
  npcs: PrepNpcItem[];
  locations: PrepLocationItem[];
  threads: PrepThreadItem[];
  source: string;
  updated_at: string;
}

export interface PrepCommitResponse {
  bundle: GmPrepBundle;
  committed_thread_ids: string[];
  staged_proposal_ids: string[];
  staging_errors: string[];
}

export interface PrepBundleGetResponse {
  found: boolean;
  bundle: GmPrepBundle | null;
}

export interface DossierEntity {
  id: string;
  name: string;
  entity_type: string;
  description?: string | null;
  properties?: Record<string, unknown> | null;
  state_tags?: string[];
  sub_type?: string | null;
}

export interface DossierAgenda {
  id?: string;
  title?: string;
  description?: string;
  agenda_type?: string;
  status?: string;
  current_segments?: number;
  total_segments?: number;
}

export interface DossierRelationship {
  from_entity_id: string;
  to_entity_id: string;
  rel_type: string;
  category?: string;
  properties?: Record<string, unknown>;
}

export interface DossierFact {
  id: string;
  statement: string;
  fact_type?: string;
  canon_level?: string;
  created_at?: string;
  witnesses?: string[];
}

export interface NpcDossierResponse {
  found: boolean;
  entity: DossierEntity | null;
  agendas: DossierAgenda[];
  relationships: DossierRelationship[];
  recent_facts: DossierFact[];
  note: string;
}

export interface KnownFact {
  statement: string;
  index: number;
}

export interface PartyKnowledgeAnswer {
  topic: string;
  summary: string;
  facts: KnownFact[];
}

export interface TranscriptLine {
  role: string;
  content: string;
  timestamp: string;
}

export interface LedgerStateChange {
  who: string;
  what: string;
  where: string;
}

export interface LedgerEntry {
  entry_id: string;
  sequence: number;
  summary: string;
  state_changes: LedgerStateChange[];
  open_questions: string[];
  world_moves: string[];
  scene_index?: number;
  created_at?: string;
}

export interface LastSessionResponse {
  found: boolean;
  session_id: string | null;
  session_title: string | null;
  ledger_entry: LedgerEntry | null;
  transcript: TranscriptLine[];
  world_time: string;
  time_line: ClockAdvanceRecord[];
  note: string;
}

// World clock (CF-11 Advance World Time)
export type DeadlineStatus = "upcoming" | "due" | "overdue";

export interface WorldClockDeadline {
  id: string;
  title: string;
  due_at: string;
  notes: string;
  status: DeadlineStatus;
}

export interface ClockAdvanceRecord {
  from_at: string | null;
  to_at: string;
  delta: string;
  advanced_at: string;
}

export interface WorldClock {
  universe_id: string;
  story_id: string;
  current_at: string;
  display: string;
  deadlines: WorldClockDeadline[];
  advances: ClockAdvanceRecord[];
  offscreen_summary: string;
  offscreen_summary_at: string | null;
  updated_at: string;
}

export interface ClockGetResponse {
  found: boolean;
  clock: WorldClock | null;
}

export interface ClockAdvanceResponse {
  clock: WorldClock;
  changed: boolean;
  initialized: boolean;
  crossed: WorldClockDeadline[];
  due: WorldClockDeadline[];
  offscreen_summary: string;
  npc_activities: string[];
  staged_proposal_ids: string[];
  staging_errors: string[];
}

export interface ImproviseResponse {
  kind: string;
  suggestions: string[];
  rationale: string;
}

export interface RulesAnswer {
  answer: string;
  source: string;
  covered: boolean;
}

export interface SessionLogFlag {
  kind: "direct" | "implication";
  severity: string;
  explanation: string;
}

export interface SessionLogItem {
  statement: string;
  participants: string[];
  locations: string[];
  proposal_id: string | null;
  flags: SessionLogFlag[];
}

export interface SessionLogProposeResponse {
  batch_id: string;
  items: SessionLogItem[];
  proposal_errors: string[];
}

export interface SessionLogProposalRetractResponse {
  proposal_id: string;
  status: string;
  reason: string;
}

// CF-15 (G09) — what the system believes a character knows.
export interface KnowledgeItem {
  id: string;
  kind: "fact" | "memory" | "proposal";
  statement: string;
  source: "scene" | "witnessed" | "common" | "proposal" | "memory";
  scene_id: string | null;
  importance: number;
  certainty: number;
  confidence: number;
  canon_level: string;
  suspicious: boolean;
  suspicion_reason: string;
}

export interface KnowledgeAudit {
  entity_id: string;
  universe_id: string | null;
  items: KnowledgeItem[];
  fact_count: number;
  memory_count: number;
  proposal_count: number;
  suspicious_count: number;
}
