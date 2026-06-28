// Shared TypeScript types matching the backend Pydantic models

export type SystemMode = "world_architect" | "autonomous_gm" | "gm_assistant";

export interface Session {
  id: string;
  title: string;
  mode: SystemMode;
  multiverse_id: string | null;
  multiverse_label?: string | null;
  universe_id: string | null;
  universe_label?: string | null;
  world_id: string | null;
  character_id: string | null;
  speaker_character_id?: string | null;
  speaker_label?: string | null;
  controlled_character_ids?: string[];
  system_id?: string | null;
  pack_id?: string | null;
  system_source_type?: string | null;
  system_source_id?: string | null;
  system_label?: string | null;
  benchmark_id?: string | null;
  benchmark_label?: string | null;
  tone?: string;
  play_mode?: string;
  scene_id?: string | null;
  story_id?: string | null;
  phase?: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface PlaytestBenchmark {
  benchmark_id: string;
  name: string;
  description: string;
  comparison_group?: string | null;
  mode: string;
  tone: string;
  play_mode: string;
  system_name?: string | null;
  resolved_system_id?: string | null;
  resolved_system_name?: string | null;
  system_available?: boolean;
  requested_system_available?: boolean;
  system_match_type?: "exact" | "fallback" | "missing";
  system_fallback_used?: boolean;
  fallback_reason?: string | null;
  core_mechanic?: string | null;
  session_title?: string | null;
  scripted_turn_count: number;
  scripted_turns?: string[];
  tags: string[];
  focus_areas: string[];
  expected_signals: string[];
  comparison_metrics: string[];
  adversarial_goals: string[];
  starter_questions: string[];
  player_persona?: string;
  llm_player_brief?: string;
  ui_notes?: string;
}

export interface Message {
  id: string;
  session_id: string;
  role: "gm" | "player" | "system";
  content: string;
  timestamp: string;
  metadata: Record<string, unknown>;
  chat_mode?: "ic" | "ooc";
  character_id?: string | null;
}

export interface ChatSessionState {
  session: Session;
  message_count: number;
  latest_gm_message_id?: string | null;
  latest_gm_metadata: Record<string, unknown>;
  recent_phase_sequence: string[];
  recent_success_levels: string[];
  recent_npc_stances?: string[];
  pending_consequence?: Record<string, unknown>;
  last_consequence_choice?: string | null;
  latest_working_state?: Record<string, unknown>;
  latest_scene_checkpoint?: Record<string, unknown>;
  latest_social_read?: Record<string, unknown>;
  latest_relationship_snapshot?: Record<string, unknown>;
}

export interface ModeConfig {
  id: string;
  label: string;
  tagline: string;
  description: string;
  capabilities: string[];
  color: "cyan" | "purple" | "emerald";
  icon: string;
}

export interface ActiveMode {
  mode_id: string;
  world_id: string | null;
  character_id: string | null;
  tone: string;
  context_depth: string;
}

// ─── World Snapshots (M-34 / DL-23) ──────────────────────────

export interface WorldSnapshot {
  snapshot_id: string;
  universe_id: string;
  name: string;
  description: string | null;
  entity_count: number;
  fact_count: number;
  relationship_count: number;
  axiom_count: number;
  created_at: string;
}

export interface SnapshotDiff {
  type: "added" | "removed" | "modified";
  entity_id: string;
  field?: string;
  old_value?: unknown;
  new_value?: unknown;
}

export interface SnapshotComparison {
  snapshot_a: string;
  snapshot_b: string;
  entities_added: number;
  entities_removed: number;
  entities_modified: number;
  facts_added: number;
  facts_removed: number;
  facts_modified: number;
  diff: SnapshotDiff[];
}

export type SourceStatus = "pending" | "processing" | "indexed" | "error";
export type SourceType = "pdf" | "txt" | "epub" | "url" | "manual";

export interface Source {
  id: string;
  title: string;
  filename: string;
  source_type: SourceType;
  status: SourceStatus;
  size_bytes: number;
  page_count: number | null;
  entity_count: number;
  relation_count: number;
  canon_level: string;
  error_message: string | null;
  uploaded_at: string;
  indexed_at: string | null;
  tags: string[];
  metadata: Record<string, unknown>;
}

export interface IngestJob {
  id: string;
  source_id: string;
  source_title: string;
  job_type: string;
  status: string;
  progress: number;
  current_stage: string | null;
  stages_completed: string[];
  processing_checklist: string[];
  activity_log: string[];
  warnings: string[];
  errors: string[];
  snippet_count: number;
  entities_extracted: number;
  axioms_extracted: number;
  proposals_generated: number;
  total_batches?: number;
  succeeded_batches?: number;
  failed_batches?: number;
  retried_batches?: number;
  current_provider?: string | null;
  current_model?: string | null;
  last_error?: string | null;
  next_retry_at?: string | null;
  partial?: boolean;
  kill_reason?: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  error: string | null;
  pack_id: string | null;
}

export interface LLMTaskAttempt {
  id?: string;
  job_id?: string | null;
  source_id?: string | null;
  stage: string;
  batch_id?: string | null;
  provider_id?: string | null;
  model?: string | null;
  role?: string | null;
  attempt_no: number;
  max_attempts: number;
  status: string;
  retryable: boolean;
  error_class?: string | null;
  error_message?: string | null;
  backoff_ms?: number | null;
  started_at?: string | null;
  ended_at?: string | null;
  request_id?: string | null;
  prompt_hash?: string | null;
  input_size?: number | null;
  output_size?: number | null;
  metadata?: Record<string, unknown>;
}

export type LLMProvider =
  | "anthropic"
  | "openai"
  | "github_models"
  | "google_ai_studio"
  | "ollama"
  | "groq"
  | "openrouter"
  | "z_ai"
  | "minimax"
  | "custom";

export interface LLMConnection {
  id: string;
  name: string;
  provider: LLMProvider;
  model: string;
  api_key_masked: string | null;
  base_url: string | null;
  status: "connected" | "error" | "unconfigured";
  latency_ms: number | null;
  is_default: boolean;
  role: "light" | "standard" | "heavy" | "embedding";
}

export interface NodeAssignment {
  node_name: string;
  provider_id: string;
  param_overrides: Record<string, number | string | null>;
  notes: string | null;
  // joined from llm_providers:
  provider_name: string | null;
  model: string | null;
  provider: LLMProvider | null;
}

export interface TestResult {
  ok: boolean;
  latency_ms: number | null;
  model_response: string | null;
  error: string | null;
}

export type DBType =
  | "neo4j"
  | "mongodb"
  | "qdrant"
  | "minio"
  | "opensearch";

export interface DatabaseStatus {
  name: string;
  db_type: DBType;
  url: string;
  status: "online" | "offline" | "degraded";
  latency_ms: number | null;
  version: string | null;
  stats: Record<string, string | number>;
  error: string | null;
}

export interface NPC {
  id: string;
  name: string;
  entity_type: string;
  universe_id: string | null;
  universe_name: string | null;
  description: string | null;
  state_tags: string[];
  properties: Record<string, unknown>;
  memory_count: number;
  canon_level: string;
  is_archetype: boolean;
}

export interface NPCMemory {
  id: string;
  content: string;
  timestamp: string;
  importance: number;
  memory_type: string;
}

export interface NPCDetail extends NPC {
  memories: NPCMemory[];
  stats: Record<string, unknown>;
  relationships: Array<Record<string, unknown>>;
  facts: Array<{ id: string; statement: string; fact_type: string; confidence: number }>;
}

export interface CoreMechanicInfo {
  mechanic_type: string;
  formula: string | null;
  success_type: string | null;
  target_number: number | null;
  description: string | null;
}

export interface AttributeInfo {
  name: string;
  abbreviation: string | null;
  min_value: number | null;
  max_value: number | null;
  description: string | null;
}

export interface SkillInfo {
  name: string;
  linked_attribute: string | null;
  description: string | null;
  untrained_allowed: boolean;
}

export interface ResourceInfo {
  name: string;
  abbreviation: string | null;
  max_value: number | null;
  recovers_on: string | null;
  depleted_effect: string | null;
}

export interface RuleInfo {
  name: string;
  rule_type: string;
  description: string | null;
  formula: string | null;
  examples: string[];
  exceptions: string[];
}

export interface RPGSystem {
  id: string;
  name: string;
  description: string | null;
  version: string | null;
  core_mechanic: CoreMechanicInfo | null;
  attributes: AttributeInfo[];
  skills: SkillInfo[];
  resources: ResourceInfo[];
  rules: RuleInfo[];
  is_builtin: boolean;
  source_document_id: string | null;
  character_count: number;
  session_count: number;
}

export interface Character {
  id: string;
  name: string;
  system_id: string | null;
  system_name: string | null;
  universe_id: string | null;
  description: string | null;
  attributes: Record<string, unknown>;
  state_tags: string[];
  canon_level: string;
}

/** Standalone character (Roleplay UI) — stored in MongoDB, optionally linked to a Neo4j entity. */
export interface StandaloneCharacter {
  id: string;
  name: string;
  description: string;
  avatar_url: string | null;
  personality: string;
  gm_notes: string;
  first_message: string;
  is_ooc_persona: boolean;
  entity_id: string | null;
  // Character Versions: per-universe incarnations. Always present (defaults
  // to [] for legacy docs); see character_storage.add_version.
  default_universe_id: string | null;
  versions: CharacterVersion[];
  memory_count: number;
  created_at: string;
  updated_at: string;
}

export interface PaginatedNPCs {
  items: NPC[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Conversatory (MONITOR-backed chat with a roster character) ───

export interface CharacterExpandResult {
  character_id: string;
  entity_id: string;
  universe_id: string;
}

export interface CharacterCardDraft {
  name: string;
  description: string;
  personality: string;
  first_message: string;
  gm_notes: string;
}

export interface ConversationStart {
  conversation_id: string;
  character_id: string;
  entity_id: string;
  universe_id?: string;
  version_id?: string;
  opening: string;
}

/**
 * One Character Version (per-universe incarnation) of a roster character.
 * Memories, emotional state, and relationship deltas are scoped to the
 * (character, universe_id) pair — see character_versions_api.test.ts.
 */
export interface CharacterVersion {
  version_id: string;
  universe_id: string;
  entity_id: string;
  npc_profile_id: string | null;
  created_at: string;
  last_chatted_at: string | null;
}

export interface CharacterReply {
  text: string;
  emotional_state: string | null;
  relationship_snapshot: Record<string, unknown>;
}

export interface CharacterConversation {
  conversation_id: string | null;
  status: string | null;
  turn_count: number;
  created_at: string;
  updated_at: string;
}

// ─── Source / World profiles ─────────────────────────────────

export interface ProfileEvidenceRef {
  ref: string;
  section_path: string | null;
  page_hint: string | null;
  note: string | null;
}

export interface SourceProfile {
  profile_type: string;
  source_kind: string | null;
  world_kind: string | null;
  system_name: string | null;
  edition: string | null;
  family: string | null;
  genre_tone: string[];
  narrative_frame: string[];
  lore_domains: string[];
  taxonomy_containers: string[];
  institution_model: string[];
  relationship_patterns: string[];
  term_lexicon: Record<string, string[]>;
  aliases: Record<string, string[]>;
  canon_signal_terms: string[];
  important_named_sets: string[];
  coverage_summary: string | null;
  known_open_questions: string[];
  confidence_by_field: Record<string, number>;
  evidence_refs: ProfileEvidenceRef[];
  profile_version: string | null;
  prompt_version: string | null;
  model_used: string | null;
}

// ─── Knowledge Pack extracted item types ─────────────────────

export interface ExtractedAxiom {
  statement: string;
  domain: string;
  confidence: number;
  source_ref: string | null;
  tags: string[];
}

export interface ExtractedEntity {
  name: string;
  entity_type: "character" | "faction" | "location" | "object" | "concept" | "organization";
  sub_type?: string | null;
  description: string;
  properties: Record<string, unknown>;
  entity_roles?: string[];
  is_container?: boolean;
  parent_entity_name?: string | null;
  source_ref: string | null;
  confidence: number;
  tags: string[];
}

export interface ExtractedRelationship {
  from_entity: string;
  rel_type: string;
  to_entity: string;
  description: string;
  confidence: number;
  source_ref: string | null;
}

export interface ExtractedLoreFact {
  statement: string;
  fact_type: string;
  entity_names: string[];
  source_ref: string | null;
  confidence: number;
  tags: string[];
}

export interface ChunkSummaryArtifact {
  chunk_id: string;
  chunk_index: number;
  source_ref: string | null;
  summary: string;
  confidence: number;
  tags: string[];
}

export interface SectionSummaryArtifact {
  section_key: string;
  heading_path: string[];
  chunk_ids: string[];
  summary: string;
  confidence: number;
  semantic_category: string | null;
}

export interface SourceMindscapeArtifact {
  source_name: string;
  summary: string;
  themes: string[];
  taxonomy_hints: string[];
  system_name: string | null;
  confidence: number;
}

export interface KnowledgePack {
  id: string;
  name: string;
  description: string | null;
  pack_type: string;
  status: "draft" | "pending" | "ready" | "review_pending" | "applied" | "archived" | "error" | "canonizing";
  system_name: string | null;
  game_system_id: string | null;
  game_system: Record<string, unknown> | null;
  game_system_data: Record<string, unknown> | null;
  source_profile_data: SourceProfile | null;
  chunk_summaries: ChunkSummaryArtifact[];
  section_summaries: SectionSummaryArtifact[];
  source_mindscape: SourceMindscapeArtifact | null;
  tags: string[];
  axiom_count: number;
  entity_count: number;
  lore_fact_count: number;
  axioms: ExtractedAxiom[];
  entity_archetypes: ExtractedEntity[];
  lore_facts: ExtractedLoreFact[];
  entity_relationships: ExtractedRelationship[];
  created_at: string;
  updated_at: string | null;
  applied_to: string[];
  parent_pack_ids: string[];
  source_document_ids: string[];
}

export interface PackConflict {
  item_type: "entity" | "axiom" | "lore" | "game_system";
  item_name: string;
  pack_value: unknown;
  world_value: unknown;
  resolution: "pack_wins" | "world_wins" | "llm_merged" | "human_picked" | null;
  resolved_value: unknown | null;
  llm_suggestion: string | null;
  resolved_by: "user" | "llm" | "auto" | null;
  auto_committed: boolean;
}

// ─── Proposal Review (I-4) ──────────────────────────────────

export interface ProposalItem {
  proposal_id: string;
  change_type: "fact" | "entity" | "relationship" | "mechanic";
  content: Record<string, unknown>;
  confidence: number;
  authority: string;
  proposer: string;
  status: "pending" | "accepted" | "rejected";
  evidence: Array<{ type: string; ref_id: string }>;
  created_at: string | null;
}

// ─── CanonKeeper Review (CF-8) ────────────────────────────────

export interface SceneReview {
  scene_id: string;
  pending: ProposalItem[];
  accepted: ProposalItem[];
  rejected: ProposalItem[];
  by_change_type: Record<string, number>;
}

export interface CanonQueue {
  story_id: string;
  scenes: SceneReview[];
  total_pending: number;
}

export interface VerdictItem {
  proposal_id: string;
  decision: "accepted" | "rejected";
  reason: string;
}

export interface BatchVerdictResult {
  proposal_id: string;
  status: string;
  decision_metadata: {
    decided_by: string;
    decided_at: string;
    reason: string;
  };
}

// ─── Performance Monitoring ───────────────────────────────────

export interface PerformanceOverview {
  request_count: number;
  avg_latency_ms: number;
  error_rate: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  slow_query_count: number;
  active_alerts: number;
}

export interface SlowQuery {
  query_id: string;
  query_type: string;
  database: string;
  duration_ms: number;
  timestamp: string;
  query_summary: string;
}

export interface PerformanceAlert {
  alert_id: string;
  alert_type: string;
  severity: "info" | "warning" | "critical";
  message: string;
  timestamp: string;
  resolved: boolean;
  resolved_at: string | null;
}

export interface AlertConfig {
  enabled: boolean;
  latency_threshold_ms: number;
  error_rate_threshold: number;
  slow_query_threshold_ms: number;
  cooldown_seconds: number;
}

export interface PerformanceReport {
  overview: PerformanceOverview;
  slow_queries: SlowQuery[];
  recent_alerts: PerformanceAlert[];
  database_health: Array<{
    database: string;
    status: string;
    latency_ms: number;
    connection_count: number;
  }>;
}

export interface ProposalSummary {
  total: number;
  pending: number;
  accepted: number;
  rejected: number;
}

export interface PackApplySession {
  id: string;
  pack_id: string;
  target_universe_id: string;
  mode: "new_world" | "selective" | "full";
  auto_commit_llm: boolean;
  conflicts: PackConflict[];
  status: "pending" | "review" | "committed" | "abandoned";
  applied_at: string | null;
  items_written: number;
}

// ─── Multiverse / Universe ────────────────────────────────────

export interface Multiverse {
  id: string;
  name: string;
  description: string | null;
  tags: string[];
  universe_count: number;
  created_at: string;
}

export interface Universe {
  id: string;
  name: string;
  multiverse_id: string;
  genre: string | null;
  description: string | null;
  tags: string[];
  is_active: boolean;
  entity_count: number;
  session_count: number;
  story_count?: number;
  created_at: string;
}

// ─── World Graph (architect view) ────────────────────────────

export type GraphNodeKind =
  | "multiverse"
  | "universe"
  | "character"
  | "location"
  | "faction"
  | "concept"
  | "axiom"
  | "lore"
  | "rule"
  | "pack";

export interface GraphNodeData extends Record<string, unknown> {
  label: string;
  kind: GraphNodeKind;
  subtitle?: string;
  description?: string;
  tags?: string[];
}

/** A relationship edge between two entities (M-37). */
export interface EntityRelationship {
  relationship_id: string;
  from_entity_id: string;
  to_entity_id: string;
  rel_type: string;
  category: string;
  properties: Record<string, unknown>;
  tags: string[];
}

/** A single canon entity as returned by the entities CRUD endpoints (M-36/M-38). */
export interface EntityDetail {
  id: string;
  universe_id: string;
  name: string;
  entity_type: string;
  description: string;
  properties: Record<string, unknown>;
  state_tags: string[];
  canon_level: string;
  confidence: number;
  authority: string;
  is_archetype: boolean;
}

export interface GraphNode {
  id: string;
  type: "worldNode";
  position: { x: number; y: number };
  data: GraphNodeData;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type?: string;
  label?: string;
  style?: Record<string, unknown>;
}

export interface WorldGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  error?: string;
  entity_types?: string[];
  rel_types?: string[];
}

export interface WorldGraphFilter {
  multiverse_id?: string;
  universe_id?: string;
  entity_types?: string[];
  related_to?: string;
}

// ─── Prompt modules (DSPy) ────────────────────────────────────

export interface PromptFieldInfo {
  name: string;
  desc: string;
}

export interface PromptModuleSummary {
  module_id: string;
  agent: string;
  label: string;
  description: string;
  predictor_type: "Predict" | "ChainOfThought";
  llm_node: string;
  llm_role: "light" | "standard" | "heavy" | "embedding";
  has_override: boolean;
}

export interface PromptModuleDetail extends PromptModuleSummary {
  default_instructions: string;
  current_instructions: string;
  input_fields: PromptFieldInfo[];
  output_fields: PromptFieldInfo[];
  override_updated_at: string | null;
}

export interface PromptTestResult {
  ok: boolean;
  outputs: Record<string, string>;
  raw_prompt: string | null;
  raw_response: string | null;
  latency_ms: number | null;
  error: string | null;
}

// ─── Binary Assets (I-6) ──────────────────────────────────────

export interface BinaryAsset {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  object_key: string;
  asset_type: string;
  label: string;
  source_id: string | null;
  universe_id: string | null;
  presigned_url: string;
  created_at: string;
}

// ─── Stories (Phase 5) ────────────────────────────────────────

export interface StoryResponse {
  story_id: string;
  universe_id: string;
  arc_label: string;
  tension_score: number;
  scenes_completed: number;
  active_threads: string[];
  completed_threads: string[];
  next_scene_type?: string;
  created_at: string;
  updated_at: string;
}

export interface SceneSummary {
  id: string;
  story_id?: string;
  title?: string;
  purpose?: string;
  status: string;
  narrative_order?: number | null;
  summary: string;
  turn_count?: number;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
}

export interface StorySummary {
  id: string;
  universe_id: string;
  title: string;
  story_type: string;
  theme?: string | null;
  premise?: string | null;
  status: string;
  scene_count: number;
  created_at: string;
  completed_at?: string | null;
}

export interface SceneTurn {
  turn_id?: string | null;
  speaker?: string | null;
  entity_id?: string | null;
  text: string;
  timestamp?: string | null;
}

export interface StoryThread {
  id?: string | null;
  title: string;
  thread_type?: string | null;
  status: string;
  urgency?: string | null;
  priority?: string | null;
  source: "graph" | "checkpoint";
}

// ─── Lorebook (Untracked Feature) ──────────────────────────────

export interface LorebookEntry {
  id: string;
  character_id: string;
  keywords: string[];
  content: string;
  priority: number;
  is_active: boolean;
  tags: string[];
  scene_filter: string | null;
  trigger_count: number;
  last_triggered: string | null;
  created_at: string;
}

export interface LorebookStats {
  total_entries: number;
  total_triggers: number;
}

export interface LorebookEntryCreate {
  keywords: string[];
  content: string;
  priority: number;
  is_active?: boolean;
  tags: string[];
  scene_filter?: string | null;
  auto_generate_keywords?: boolean;
}

export interface LorebookIngestRequest {
  source: string;
  content: string;
  chunk_size: number;
  character_id: string;
  auto_keywords: boolean;
  priority_hint: number;
  tags: string[];
}

// ─── GM Assistant Types (CF-4, CF-5, CF-6, CF-7) ─────────────

export interface PlotHook {
  thread_id?: string;
  title: string;
  description: string;
  urgency: "low" | "medium" | "high" | "critical";
  suggested_scene_type: string;
  connected_entities: string[];
}

export interface Contradiction {
  fact_a: string;
  fact_b: string;
  severity: "low" | "medium" | "high";
  explanation: string;
  suggestion: string;
}

export interface SessionPrep {
  recap: string;
  open_threads: string[];
  hooks: PlotHook[];
  npc_reminders: string[];
  world_state_changes: string[];
}

export interface Handout {
  title: string;
  content: string;
  handout_type: "letter" | "map_note" | "prophecy" | "journal_entry" | "notice" | "rumor";
  related_entities: string[];
  tone: "mysterious" | "urgent" | "warm" | "ominous" | "neutral";
  spoiler_level: "safe" | "partial" | "full";
}

// ─── Entity Template Types (M-31, CF-2) ─────────────────────

export interface VariableProperty {
  property_path: string;
  generation_type: "fixed" | "choice" | "range" | "pattern" | "table" | "llm";
  options: unknown[];
  range_min?: number | null;
  range_max?: number | null;
  pattern?: string | null;
  table_id?: string | null;
  llm_hint?: string | null;
}

export interface NamingPattern {
  type: "pattern" | "numbered" | "list" | "llm" | "user";
  pattern?: string | null;
  adjectives?: string[];
  nouns?: string[];
  name_list?: string[];
}

export interface StatGeneration {
  method: string;
  formulas: Record<string, string>;
  constraints: Record<string, unknown>;
  game_system_id?: string | null;
}

export interface DefaultPersonality {
  trait_pool: string[];
  fear_pool: string[];
  desire_pool: string[];
  speech_styles: string[];
  default_disposition?: string | null;
}

export interface EntityTemplate {
  template_id: string;
  universe_id: string;
  name: string;
  description: string;
  entity_type: string;
  base_properties: Record<string, unknown>;
  variable_properties: VariableProperty[];
  naming_pattern: NamingPattern;
  stat_generation: StatGeneration;
  default_state_tags: string[];
  default_detail_level: string;
  default_personality: DefaultPersonality | null;
  parent_template_id: string | null;
  usage_count: number;
  created_at: string;
  updated_at: string | null;
}

export interface EntityTemplateListResponse {
  templates: EntityTemplate[];
  total: number;
  limit: number;
  offset: number;
}

// ─── Random Table Types (M-33, DL-21) ────────────────────────

export type RandomTableType =
  | "encounter" | "loot" | "name" | "trait" | "weather"
  | "rumor" | "npc" | "event" | "location" | "complication" | "custom";

export interface RandomTableEntry {
  min_roll: number;
  max_roll: number;
  weight: number | null;
  value: string;
  subtable_id: string | null;
  conditions: Record<string, unknown> | null;
}

export interface RandomTable {
  table_id: string;
  universe_id: string | null;
  name: string;
  description: string;
  table_type: RandomTableType;
  dice_formula: string;
  weighted: boolean;
  entries: RandomTableEntry[];
  source_id: string | null;
  game_system_id: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface RandomTableListResponse {
  tables: RandomTable[];
  total: number;
  limit: number;
  offset: number;
}

export interface RollResult {
  roll: number;
  entry: RandomTableEntry;
  sub_results?: RollResult[];
}


// ─── Semantic Search (Q-1..Q-5) ──────────────────────────────

export interface SearchResultItem {
  id: string;
  collection: string;
  score: number;
  payload: Record<string, unknown>;
  text: string | null;
  entity_type: string | null;
  universe_id: string | null;
  story_id: string | null;
}

export interface SemanticSearchResponse {
  query: string;
  collections_searched: string[];
  total_results: number;
  results: SearchResultItem[];
}

// ─── Tone system ─────────────────────────────────────────────

export interface ToneProfile {
  profile_id: string;
  name: string;
  description: string;
  instruction: string;
  trigger_tags: string[];
  category: string;
  language: string;
  pack_id: string | null;
  is_builtin: boolean;
  example_output: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface ToneLibrary {
  library_id: string;
  name: string;
  description: string;
  tone_profile_ids: string[];
  pack_id: string | null;
  universe_id: string | null;
  priority: number;
  is_default: boolean;
  created_at: string;
  updated_at: string | null;
}

// ─── Change Log (Q-10 audit trail) ──────────────────────────────
export interface ChangeLogEntry {
  change_id: string;
  subject_type: string;
  subject_id: string;
  change_type: string;
  timestamp: string;
  field_path?: string | null;
  old_value?: unknown;
  new_value?: unknown;
  author: string;
  authority: string;
  evidence_type?: string | null;
  evidence_id?: string | null;
  reason?: string | null;
  transaction_id?: string | null;
}

export interface ChangeLogListResponse {
  entries: ChangeLogEntry[];
  total: number;
  limit: number;
  offset: number;
}
