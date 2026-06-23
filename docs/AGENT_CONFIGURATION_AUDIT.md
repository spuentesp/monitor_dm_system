# MONITOR Agent Configuration Audit

> Complete inventory of ALL configurable parameters across the agents system.
> Generated: 2026-06-03

---

## Table of Contents

1. [Data-Layer Settings (env vars)](#1-data-layer-settings)
2. [BaseAgent Configuration](#2-baseagent-configuration)
3. [LLM Registry & Provider Configuration](#3-llm-registry--provider-configuration)
4. [Token Budgets by Model Role](#4-token-budgets-by-model-role)
5. [DSPy Runtime / Model Role Assignments](#5-dspy-runtime--model-role-assignments)
6. [Agent-Specific Parameters](#6-agent-specific-parameters)
7. [DSPy Prompt Modules](#7-dspy-prompt-modules)
8. [Loop State Configuration](#8-loop-state-configuration)
9. [Tone System Configuration](#9-tone-system-configuration)
10. [GM Profile Configuration](#10-gm-profile-configuration)
11. [NPC Profile Configuration](#11-npc-profile-configuration)
12. [Game System Schema Configuration](#12-game-system-schema-configuration)
13. [Entity Schema Configuration](#13-entity-schema-configuration)
14. [Modes Configuration](#14-modes-configuration)
15. [Performance Monitoring](#15-performance-monitoring)
16. [Play Session Configuration](#16-play-session-configuration)
17. [Environment Variables (Complete)](#17-environment-variables-complete)

---

## 1. Data-Layer Settings

**File:** `packages/data-layer/src/monitor_data/config.py`

| Parameter | Type | Default | Env Var | Frontend Exposed | UI Control |
|-----------|------|---------|---------|-----------------|------------|
| `neo4j_uri` | `str` | `bolt://localhost:7687` | `NEO4J_URI` | No | Text input |
| `neo4j_user` | `str` | `neo4j` | `NEO4J_USER` | No | Text input |
| `neo4j_password` | `str` | `monitor-dev-neo4j` | `NEO4J_PASSWORD` | No | Password input |
| `mongodb_uri` | `str` | `mongodb://localhost:27017` | `MONGODB_URI` | No | Text input |
| `mongodb_database` | `str` | `monitor` | `MONGODB_DATABASE` | No | Text input |
| `mongodb_server_selection_timeout_ms` | `int` | `3000` | `MONGODB_SERVER_SELECTION_TIMEOUT_MS` | No | Number input |
| `mongodb_connect_timeout_ms` | `int` | `3000` | `MONGODB_CONNECT_TIMEOUT_MS` | No | Number input |
| `qdrant_url` | `Optional[str]` | `None` | `QDRANT_URL` | No | Text input |
| `qdrant_api_key` | `Optional[str]` | `None` | `QDRANT_API_KEY` | No | Password input |
| `qdrant_path` | `Optional[str]` | `None` | `QDRANT_PATH` | No | Text input |
| `storage_backend` | `str` | `minio` | `STORAGE_BACKEND` | No | Dropdown (minio/s3/folder) |
| `storage_endpoint` | `Optional[str]` | `None` | `STORAGE_ENDPOINT` | No | Text input |
| `storage_fallback_to_local` | `bool` | `True` | `STORAGE_FALLBACK_TO_LOCAL` | No | Toggle |
| `local_storage_path` | `str` | `.local_storage` | `LOCAL_STORAGE_PATH` | No | Text input |
| `minio_endpoint` | `str` | `localhost:9000` | `MINIO_ENDPOINT` | No | Text input |
| `minio_access_key` | `str` | `minioadmin` | `MINIO_ACCESS_KEY` | No | Text input |
| `minio_secret_key` | `str` | `monitor-dev-minio` | `MINIO_SECRET_KEY` | No | Password input |
| `minio_bucket` | `str` | `monitor` | `MINIO_BUCKET` | No | Text input |
| `minio_secure` | `bool` | `False` | `MINIO_SECURE` | No | Toggle |
| `minio_region` | `str` | `us-east-1` | `MINIO_REGION` | No | Text input |
| `opensearch_url` | `str` | `http://localhost:9200` | `OPENSEARCH_URL` | No | Text input |
| `opensearch_user` | `Optional[str]` | `None` | `OPENSEARCH_USER` | No | Text input |
| `opensearch_password` | `Optional[str]` | `None` | `OPENSEARCH_PASSWORD` | No | Password input |
| `redis_url` | `Optional[str]` | `redis://localhost:6379/0` | `REDIS_URL` | No | Text input |
| `redis_enabled` | `bool` | `True` | `REDIS_ENABLED` | No | Toggle |
| `redis_key_prefix` | `str` | `monitor` | `REDIS_KEY_PREFIX` | No | Text input |
| `redis_cache_ttl_seconds` | `int` | `30` | `REDIS_CACHE_TTL_SECONDS` | No | Slider (1-300) |
| `redis_solo_play_ttl_seconds` | `int` | `15` | `REDIS_SOLO_PLAY_TTL_SECONDS` | No | Slider (1-120) |
| `redis_socket_timeout` | `float` | `0.15` | `REDIS_SOCKET_TIMEOUT` | No | Number input |
| `redis_connect_timeout` | `float` | `0.15` | `REDIS_CONNECT_TIMEOUT` | No | Number input |
| `embedding_model` | `str` | `text-embedding-3-small` | `EMBEDDING_MODEL` | No | Dropdown |
| `embedding_dimension` | `int` | `1536` | `EMBEDDING_DIMENSION` | No | Dropdown |
| `openai_api_key` | `Optional[str]` | `None` | `OPENAI_API_KEY` | No | Password input |
| `anthropic_api_key` | `Optional[str]` | `None` | `ANTHROPIC_API_KEY` | No | Password input |
| `llm_model` | `str` | `claude-sonnet-4-20250514` | `LLM_MODEL` | Partial (via LLM mgmt) | Dropdown |
| `vision_model` | `str` | `gpt-4o-mini` | `VISION_MODEL` | No | Dropdown |
| `postgres_host` | `str` | `localhost` | `POSTGRES_HOST` | No | Text input |
| `postgres_port` | `int` | `5432` | `POSTGRES_PORT` | No | Number input |
| `postgres_user` | `str` | `monitor` | `POSTGRES_USER` | No | Text input |
| `postgres_password` | `str` | `monitor-dev-postgres` | `POSTGRES_PASSWORD` | No | Password input |
| `postgres_db` | `str` | `monitor` | `POSTGRES_DB` | No | Text input |
| `db_retry_attempts` | `int` | `3` | `DB_RETRY_ATTEMPTS` | No | Slider (1-10) |
| `db_retry_min_wait` | `float` | `1.0` | `DB_RETRY_MIN_WAIT` | No | Number input |
| `db_retry_max_wait` | `float` | `10.0` | `DB_RETRY_MAX_WAIT` | No | Number input |
| `llm_retry_attempts` | `int` | `3` | `LLM_RETRY_ATTEMPTS` | No | Slider (1-10) |
| `llm_retry_min_wait` | `float` | `2.0` | `LLM_RETRY_MIN_WAIT` | No | Number input |
| `llm_retry_max_wait` | `float` | `30.0` | `LLM_RETRY_MAX_WAIT` | No | Number input |
| `nlp_enabled` | `bool` | `True` | `NLP_ENABLED` | No | Toggle |
| `nlp_backend` | `str` | `gliner` | `NLP_BACKEND` | No | Dropdown |
| `gliner_url` | `str` | `http://localhost:8082` | `GLINER_URL` | No | Text input |
| `gliner_model` | `str` | `knowledgator/gliner-base-v0.1` | `GLINER_MODEL` | No | Text input |
| `gliner_max_length` | `int` | `384` | `GLINER_MAX_LENGTH` | No | Slider (64-1024) |
| `gliner_batch_size` | `int` | `8` | `GLINER_BATCH_SIZE` | No | Slider (1-32) |
| `entity_extraction_enabled` | `bool` | `True` | `ENTITY_EXTRACTION_ENABLED` | No | Toggle |
| `entity_types` | `str` | (long comma-separated list) | `ENTITY_TYPES` | No | Multi-select / text |

---

## 2. BaseAgent Configuration

**File:** `packages/agents/src/monitor_agents/base.py`

| Parameter | Type | Default | Where Defined | Frontend Exposed | UI Control |
|-----------|------|---------|---------------|-----------------|------------|
| `agent_type` | `str` | (required) | `__init__` param | No | — (internal) |
| `agent_id` | `str` | (required) | `__init__` param | No | — (internal) |
| `model` | `str | None` | `settings.llm_model` | `__init__` param | Partial (via LLM mgmt) | Dropdown |
| `max_tokens` | `int` | `2048` | `call_llm_structured` param | No | Slider (256-8192) |

**Retry policy (hardcoded from settings):**

| Parameter | Type | Default | Where Defined | Frontend Exposed | UI Control |
|-----------|------|---------|---------------|-----------------|------------|
| `stop_after_attempt` | `int` | `settings.llm_retry_attempts` (3) | `_LLM_RETRY` dict | No | Slider |
| `wait_multiplier` | `int` | `1` | `_LLM_RETRY` dict | No | Number input |
| `wait_min` | `float` | `settings.llm_retry_min_wait` (2.0) | `_LLM_RETRY` dict | No | Number input |
| `wait_max` | `float` | `settings.llm_retry_max_wait` (30.0) | `_LLM_RETRY` dict | No | Number input |

---

## 3. LLM Registry & Provider Configuration

**File:** `packages/data-layer/src/monitor_data/schemas/llm_config.py`
**Router:** `packages/ui/backend/src/monitor_ui/routers/llm_mgmt.py`

### LLMProviderConfig (PostgreSQL table: `llm_providers`)

| Parameter | Type | Default | Frontend Exposed | UI Control |
|-----------|------|---------|-----------------|------------|
| `id` | `str` | (required slug) | Yes | Text input |
| `name` | `str` | (required) | Yes | Text input |
| `provider` | `LLMProviderType` | (required) | Yes | Dropdown (anthropic/openai/github_models/google_ai_studio/azure_openai/groq/ollama/openrouter/z_ai/minimax/custom) |
| `model` | `str` | (required) | Yes | Dropdown (dynamic per provider) |
| `api_key` | `str` | `""` | Yes (masked) | Password input |
| `base_url` | `Optional[str]` | `None` | Yes | Text input |
| `model_params` | `dict[str, Any]` | `{}` | Partial | JSON editor / individual controls |
| `role` | `ModelRole` | `standard` | Yes | Dropdown (light/standard/heavy/embedding) |
| `status` | `str` | `unconfigured` | Yes | Badge (read-only) |
| `latency_ms` | `Optional[int]` | `None` | Yes | Badge (read-only) |
| `is_default` | `bool` | `False` | Yes | Toggle |

### ModelParams (sampling parameters)

| Parameter | Type | Default | Frontend Exposed | UI Control |
|-----------|------|---------|-----------------|------------|
| `temperature` | `Optional[float]` | `None` | Yes | Slider (0.0-2.0) |
| `max_tokens` | `Optional[int]` | `None` | Yes | Slider (1-16384) |
| `top_p` | `Optional[float]` | `None` | Yes | Slider (0.0-1.0) |
| `frequency_penalty` | `Optional[float]` | `None` | Yes | Slider (-2.0-2.0) |
| `presence_penalty` | `Optional[float]` | `None` | Yes | Slider (-2.0-2.0) |

### LLMNodeAssignment (PostgreSQL table: `llm_node_assignments`)

| Parameter | Type | Default | Frontend Exposed | UI Control |
|-----------|------|---------|-----------------|------------|
| `node_name` | `str` | (required) | Yes | Dropdown (agent node names) |
| `provider_id` | `str` | (required) | Yes | Dropdown (provider slugs) |
| `param_overrides` | `dict[str, Any]` | `{}` | Yes | JSON editor |
| `notes` | `Optional[str]` | `None` | Yes | Text area |

---

## 4. Token Budgets by Model Role

**File:** `packages/agents/src/monitor_agents/token_budget.py`

| Role | `max_output` | `context_window` | `query_budget` | `summary_budget` | Frontend Exposed | UI Control |
|------|-------------|-----------------|----------------|-----------------|-----------------|------------|
| `LIGHT` | 1024 | 128,000 | 128 | 512 | No | Number inputs |
| `STANDARD` | 2048 | 128,000 | 256 | 1024 | No | Number inputs |
| `HEAVY` | 4096 | 200,000 | 256 | 1536 | No | Number inputs |

> **Note:** These are hardcoded class-level defaults. No PostgreSQL override mechanism exists yet.

---

## 5. DSPy Runtime / Model Role Assignments

**File:** `packages/agents/src/monitor_agents/dspy_runtime.py`

### Default Node → Role Mapping

| Node Name | Default Role | Frontend Exposed | UI Control |
|-----------|-------------|-----------------|------------|
| `narrator` | `HEAVY` | Partial (via LLM mgmt) | Dropdown |
| `canon_keeper` | `HEAVY` | Partial | Dropdown |
| `canonkeeper` | `HEAVY` | Partial | Dropdown |
| `context_assembly` | `LIGHT` | Partial | Dropdown |
| `query_formulation` | `LIGHT` | Partial | Dropdown |
| `turn_intent` | `LIGHT` | Partial | Dropdown |
| `indexer` | `LIGHT` | Partial | Dropdown |
| *(all others)* | `STANDARD` | Partial | Dropdown |

### Dynamic Model Routing (Intensity Escalation)

**File:** `packages/agents/src/monitor_agents/dspy_runtime.py`

The system escalates from STANDARD → HEAVY for the narrator when high-intensity keywords are detected. The keyword set is hardcoded:

`attack, kill, death, die, fight, combat, critical, betray, sacrifice, explosion, collapse, scream, flee`

| Parameter | Type | Default | Frontend Exposed | UI Control |
|-----------|------|---------|-----------------|------------|
| `_HIGH_INTENSITY_KEYWORDS` | `set[str]` | (13 keywords) | No | Multi-select / tag editor |
| Dynamic escalation enabled | `bool` | `True` (implicit) | No | Toggle |

### LLM Call Logging

| Parameter | Type | Default | Env Var | Frontend Exposed | UI Control |
|-----------|------|---------|---------|-----------------|------------|
| `MONITOR_LLM_LOG` | `str` | `""` (disabled) | `MONITOR_LLM_LOG` | No | Toggle |
| `MONITOR_LLM_LOG_FILE` | `str` | `llm_calls.log` | `MONITOR_LLM_LOG_FILE` | No | Text input |

---

## 6. Agent-Specific Parameters

### 6.1 Narrator (`narrator.py`)

| Parameter | Type | Default | Where Defined | Frontend Exposed | UI Control |
|-----------|------|---------|---------------|-----------------|------------|
| `session_tone` | `str` | `"dramatic"` | `narrate_turn()` param | Yes | Dropdown (dramatic/grim/horror/heroic/mystery/adventure) |
| `gm_profile` | `Optional[Dict]` | `None` | `narrate_turn()` param | Yes | Profile picker |
| `lorebook_context` | `Optional[List[str]]` | `None` | `narrate_turn()` param | No | — (auto-injected) |
| `story_state` | `Optional[StoryState]` | `None` | `narrate_turn()` param | No | — (auto-injected) |
| `_TONE_PROFILES` | `Dict[str, str]` | 6 built-in profiles | Class attribute | Partial (via Tone system) | — (deprecated, use ToneResolver) |

### 6.2 CanonKeeper (`canonkeeper.py`)

| Parameter | Type | Default | Where Defined | Frontend Exposed | UI Control |
|-----------|------|---------|---------------|-----------------|------------|
| `_COMMIT_ORDER` | `Dict[str, int]` | 7 proposal types | Class attribute | No | — (internal ordering) |
| `_STATE_TAG_ALIASES` | `Dict[str, str]` | 15 aliases | Module-level | No | — (normalization map) |

### 6.3 Resolver (`resolver.py`)

| Parameter | Type | Default | Where Defined | Frontend Exposed | UI Control |
|-----------|------|---------|---------------|-----------------|------------|
| `_ACTION_PROFILE_MAP` | `list[tuple]` | 4 action profiles | Module-level | No | — (keyword routing) |
| `_DEFAULT_MODIFIER_FORMULA` | `str` | `"(VALUE - 10) // 2"` | Module-level | No | Text input |
| `_FORCED_NARRATIVE_RE` | `Pattern` | (regex) | Module-level | No | — (detection pattern) |
| `_ATTEMPT_RE` | `Pattern` | (regex) | Module-level | No | — (detection pattern) |
| `_OOC_BLOCK_RE` | `Pattern` | (regex) | Module-level | No | — (detection pattern) |
| `_META_COMMAND_RE` | `Pattern` | (regex) | Module-level | No | — (detection pattern) |
| `_QUERY_OPEN_RE` | `Pattern` | (regex) | Module-level | No | — (detection pattern) |
| `_DIALOGUE_RE` | `Pattern` | (regex) | Module-level | No | — (detection pattern) |
| `_COMBAT_RE` | `Pattern` | (regex) | Module-level | No | — (detection pattern) |
| `_STEALTH_RE` | `Pattern` | (regex) | Module-level | No | — (detection pattern) |
| `_EXPLORE_RE` | `Pattern` | (regex) | Module-level | No | — (detection pattern) |
| `_SOCIAL_RE` | `Pattern` | (regex) | Module-level | No | — (detection pattern) |

### 6.4 Oracle (`oracle.py`)

| Parameter | Type | Default | Where Defined | Frontend Exposed | UI Control |
|-----------|------|---------|---------------|-----------------|------------|
| `likelihood` | `Likelihood` | `FIFTY_FIFTY` | `resolve_question()` param | Yes | Dropdown (certain/nearly_certain/very_likely/likely/50_50/unlikely/very_unlikely/nearly_impossible/impossible) |
| `tension_score` | `float` | `0.5` | `resolve_question()` param | Yes | Slider (0.0-1.0) |
| DC map | `Dict[Likelihood, int]` | 7 entries (2-19) | Hardcoded | No | — (game design) |
| Tension skew formula | `int` | `(tension_score - 0.5) * 4` | Hardcoded | No | — (game design) |

### 6.5 WorldArchitect (`world_architect.py`)

| Parameter | Type | Default | Where Defined | Frontend Exposed | UI Control |
|-----------|------|---------|---------------|-----------------|------------|
| `multiverse_id` | `Optional[UUID]` | `None` | Instance attribute | No | — (auto-set) |

### 6.6 ContextAssembly (`context_assembly.py`)

| Parameter | Type | Default | Where Defined | Frontend Exposed | UI Control |
|-----------|------|---------|---------------|-----------------|------------|
| `_token_budget` | `TokenBudget` | `TokenBudget(STANDARD)` | `__init__` | No | — (derived from role) |
| Action overlap weight | `float` | `0.7` | `_score_item()` | No | Slider (0.0-1.0) |
| Profile overlap weight | `float` | `0.3` | `_score_item()` | No | Slider (0.0-1.0) |
| Cache TTL (short) | `int` | `settings.redis_solo_play_ttl_seconds` | `_ttl()` | No | Slider |
| Cache TTL (long) | `int` | `settings.redis_cache_ttl_seconds` | `_ttl()` | No | Slider |

### 6.7 NPCVoice (`npc_voice.py`)

| Parameter | Type | Default | Where Defined | Frontend Exposed | UI Control |
|-----------|------|---------|---------------|-----------------|------------|
| `conversation_id` | `UUID` | (required) | `respond_direct()` param | No | — (session-bound) |
| `npc_id` | `UUID` | (required) | `respond_direct()` param | No | — (entity-bound) |
| `player_said` | `str` | (required) | `respond_direct()` param | No | — (user input) |
| `player_entity_id` | `Optional[UUID]` | `None` | `respond_direct()` param | No | — (session-bound) |
| `scene_id` | `Optional[UUID]` | `None` | `respond_direct()` param | No | — (session-bound) |
| `story_id` | `Optional[UUID]` | `None` | `respond_direct()` param | No | — (session-bound) |
| `source_profile` | `Optional[Dict]` | `None` | `respond_direct()` param | No | — (auto-injected) |
| `npc_data` | `Optional[Dict]` | `None` | `respond_direct()` param | No | — (auto-loaded) |

### 6.8 SimulacrumAgent (`simulacrum.py`)

| Parameter | Type | Default | Where Defined | Frontend Exposed | UI Control |
|-----------|------|---------|---------------|-----------------|------------|
| `world_tone` | `str` | `"dramatic"` | `run_world_tick()` param | Yes | Dropdown |
| `clock_tick range` | `int` | `-2 to +2` | CouncilReconcilerSignature output | No | — (LLM output) |

### 6.9 CharacterCreator (`character_creator.py`)

| Parameter | Type | Default | Where Defined | Frontend Exposed | UI Control |
|-----------|------|---------|---------------|-----------------|------------|
| `DEFAULT_STATS` | `list[str]` | `["STR","DEX","CON","INT","WIS","CHA"]` | Module-level | No | Multi-select / tag editor |
| `valid_roles` | `set[str]` | 7 roles | `validate_character_params()` | No | Dropdown |
| Stat value range | `int` | `1-30` | `validate_character_params()` | No | Slider |
| Name length range | `int` | `1-200` | `validate_character_params()` | No | — (validation) |

---

## 7. DSPy Prompt Modules

### 7.1 NarratorModule (`prompts/narrator.py`)

**Signature:** `NarratorSignature` (ChainOfThought)

| Input Field | Type | Description | Frontend Exposed | UI Control |
|-------------|------|-------------|-----------------|------------|
| `tone_context` | `str` | GM persona/voice guidance | Yes (via GMProfile) | Text area |
| `game_system_context` | `str` | JSON game system description | Yes (via game system) | — (auto-injected) |
| `profile_context` | `str` | Source profile hints | No | — (auto-injected) |
| `scene_context` | `str` | JSON entities/location/conditions | No | — (auto-injected) |
| `memory_context` | `str` | Character memories | No | — (auto-injected) |
| `prior_turns` | `str` | Recent turn history | No | — (auto-injected) |
| `player_action` | `str` | Player's declared action | No | — (user input) |
| `resolution_summary` | `str` | Mechanical outcome | No | — (auto-injected) |

| Output Field | Type | Description | Frontend Exposed | UI Control |
|-------------|------|-------------|-----------------|------------|
| `narrative_text` | `str` | GM prose | Yes | — (LLM output) |
| `proposed_changes` | `str` | JSON array of proposals | No | — (LLM output) |
| `narrative_time_elapsed` | `str` | In-game minutes | No | — (LLM output) |

**Module role:** `ModelRole.HEAVY`

### 7.2 CanonKeeperReasoningModule (`prompts/canonkeeper.py`)

**Signature:** `CanonKeeperReasoningSignature` (ChainOfThought)

| Input Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `proposal_summary` | Human-readable change description | No | — (auto-injected) |
| `proposal_content` | JSON change details | No | — (auto-injected) |
| `existing_canon` | JSON excerpt of Neo4j entities/facts | No | — (auto-injected) |
| `story_arcs` | Active story arcs | No | — (auto-injected) |

| Output Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `reasoning` | Step-by-step analysis + ACCEPT/REJECT | No | — (LLM output) |

**Module role:** `ModelRole.HEAVY`

### 7.3 PolicyCheckModule (`prompts/canonkeeper.py`)

**Signature:** `PolicyCheckSignature` (Predict — no CoT)

| Input Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `proposal_content` | JSON change details | No | — (auto-injected) |
| `protected_entities` | JSON list of protected entity IDs | No | — (auto-injected) |
| `world_rules` | Bullet list of world rules | No | — (auto-injected) |

| Output Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `violation_found` | `'YES'` or `'NO'` | No | — (LLM output) |
| `violation_detail` | Description or `'none'` | No | — (LLM output) |

**Module role:** `ModelRole.LIGHT`

### 7.4 QueryFormulationModule (`prompts/context_assembly.py`)

**Signature:** `QueryFormulationSignature` (Predict — no CoT)

| Input Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `player_action` | Player's declared action | No | — (user input) |
| `scene_summary` | Current scene summary | No | — (auto-injected) |
| `character_name` | Player character name | No | — (auto-injected) |
| `character_tags` | Comma-separated character tags | No | — (auto-injected) |

| Output Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `memory_query` | Qdrant memories query | No | — (LLM output) |
| `snippet_query` | Qdrant snippets query | No | — (LLM output) |
| `entity_filter` | Neo4j entity filter | No | — (LLM output) |

**Module role:** `ModelRole.LIGHT`

### 7.5 NPCDirectVoiceModule (`prompts/npc_voice.py`)

**Signature:** `NPCDirectVoiceSignature` (Predict — no CoT)

| Input Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `npc_name` | NPC's name | No | — (auto-injected) |
| `npc_role` | NPC's role/occupation | No | — (auto-injected) |
| `personality_summary` | Personality profile | No | — (auto-injected) |
| `current_emotional_state` | Current emotion | No | — (auto-injected) |
| `relevant_memories` | JSON memories | No | — (auto-injected) |
| `known_facts` | JSON canonical facts | No | — (auto-injected) |
| `active_triggers` | JSON behavioral triggers | No | — (auto-injected) |
| `conversation_history` | Recent turns | No | — (auto-injected) |
| `profile_context` | Source profile hints | No | — (auto-injected) |
| `player_said` | Player's input | No | — (user input) |

| Output Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `npc_response` | NPC's direct response | Yes | — (LLM output) |
| `emotional_state_after` | Post-exchange emotion | No | — (LLM output) |
| `relationship_delta` | e.g., `'trust:+0.1'` | No | — (LLM output) |

**Module role:** `ModelRole.LIGHT`

### 7.6 NPCActorModule (`prompts/npc_voice.py`)

**Signature:** `NPCActorSignature` (Predict — no CoT)

| Input Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `npc_name` | Character name | No | — (auto-injected) |
| `full_profile` | Complete NPC profile | No | — (auto-injected) |
| `story_context` | Current story state | No | — (auto-injected) |
| `profile_context` | Source profile hints | No | — (auto-injected) |
| `conversation_history` | Prior turns | No | — (auto-injected) |
| `gm_question` | GM's question | No | — (user input) |

| Output Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `actor_response` | Actor's reflective response | Yes | — (LLM output) |
| `canon_insight` | Profile update suggestion | No | — (LLM output) |

**Module role:** `ModelRole.LIGHT`

### 7.7 WorldArchitectModule (`prompts/world_architect.py`)

**Signature:** `WorldArchitectSignature` (ChainOfThought)

| Input Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `user_message` | User's latest input | No | — (user input) |
| `conversation_history` | Prior messages | No | — (auto-injected) |
| `world_state_summary` | JSON of existing world | No | — (auto-injected) |
| `world_profile_context` | Structured world profile | No | — (auto-injected) |
| `coverage_summary` | What's already defined | No | — (auto-injected) |
| `known_open_questions` | JSON list of open questions | No | — (auto-injected) |

| Output Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `response` | Conversational reply | Yes | — (LLM output) |
| `extracted_proposals` | JSON array of world elements | No | — (LLM output) |

**Module role:** `ModelRole.STANDARD`

### 7.8 WorldGapAnalysisModule (`prompts/world_architect.py`)

**Signature:** `WorldGapAnalysisSignature` (ChainOfThought)

| Input Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `world_state_summary` | JSON of existing world | No | — (auto-injected) |
| `world_profile_context` | Structured world profile | No | — (auto-injected) |
| `coverage_summary` | What's already defined | No | — (auto-injected) |
| `known_open_questions` | JSON list of open questions | No | — (auto-injected) |

| Output Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `gaps` | JSON array of gap recommendations | Yes | — (LLM output) |

**Module role:** `ModelRole.STANDARD`

### 7.9 Simulacrum Council (`prompts/simulacrum.py`)

Three signatures, all ChainOfThought:

| Module | Signature | Role | Inputs | Outputs |
|--------|-----------|------|--------|---------|
| Opportunist | `OpportunistSimulacrumSignature` | HEAVY | `current_time`, `high_impact_events`, `faction_name`, `faction_agenda` | `proposed_move`, `reasoning` |
| Realist | `RealistSimulacrumSignature` | HEAVY | `current_time`, `high_impact_events`, `faction_name`, `faction_agenda` | `proposed_move`, `reasoning` |
| Reconciler | `CouncilReconcilerSignature` | HEAVY | `opportunist_move`, `realist_move`, `world_tone` | `final_decision`, `change_type`, `clock_tick`, `summary` |

### 7.10 StoryPlannerModule (`prompts/story.py`)

**Signature:** `StoryPlannerSignature` (ChainOfThought)

| Input Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `arc_label` | Current arc phase | No | — (auto-injected) |
| `active_threads` | Open plot threads | No | — (auto-injected) |
| `recent_scenes` | Recent scene summaries | No | — (auto-injected) |

| Output Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `next_scene_type` | e.g., combat, social, exploration | No | — (LLM output) |
| `plot_hook` | One-sentence hook | No | — (LLM output) |

### 7.11 RecapModule (`prompts/recap.py`)

**Signature:** `RecapSignature` (ChainOfThought)

| Input Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `story_outline` | JSON story outline/beats | No | — (auto-injected) |
| `scene_summaries` | Completed scene summaries | No | — (auto-injected) |
| `significant_facts` | Key events/facts | No | — (auto-injected) |
| `tone_context` | Narrative tone guidance | Yes (via GMProfile) | — (auto-injected) |

| Output Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `recap_markdown` | Compelling markdown summary | Yes | — (LLM output) |

**Module role:** `ModelRole.STANDARD`

### 7.12 MemoryExtractor (`prompts/memory_extraction.py`)

**Signature:** `MemoryExtractionSignature` (ChainOfThought)

| Input Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `narrative_text` | Scene turn prose | No | — (auto-injected) |
| `resolution` | Mechanic resolution summary | No | — (auto-injected) |
| `actor_name` | Acting character name | No | — (auto-injected) |

| Output Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `memories` | JSON list of memory dicts | No | — (LLM output) |

**Module role:** `ModelRole.STANDARD`

### 7.13 NarrativeEntityExtractionModule (`prompts/narrative_entity_extraction.py`)

**Signature:** `NarrativeEntityExtractionSignature` (ChainOfThought)

| Input Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `narration` | GM narrative text | No | — (auto-injected) |
| `known_entities` | Comma-separated known entity names | No | — (auto-injected) |
| `universe_context` | Brief universe description | No | — (auto-injected) |

| Output Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `new_entities` | JSON array of new entities | No | — (LLM output) |

### 7.14 ContradictionModule (`prompts/verification.py`)

**Signature:** `ContradictionSignature` (ChainOfThought)

| Input Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `context` | Established canon facts | No | — (auto-injected) |
| `new_fact` | New fact to verify | No | — (auto-injected) |

| Output Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `has_contradiction` | Boolean | No | — (LLM output) |
| `explanation` | Why consistent/contradictory | No | — (LLM output) |

### 7.15 Analyzer Signatures (`prompts/analyzer.py`)

| Module | Signature | Role | Key Inputs | Key Outputs |
|--------|-----------|------|------------|-------------|
| AxiomExtraction | `AxiomExtractionSignature` | HEAVY | `section_context`, `source_name` | `axioms_reasoning` |
| EntityExtraction | `EntityExtractionSignature` | HEAVY | `section_context`, `source_name` | `entities_reasoning` |
| SourceProfileSynthesis | `SourceProfileSynthesisSignature` | HEAVY | `representative_sections`, `heading_paths`, `reference_signals`, `source_name`, `draft_profile_context` | `profile_json` |
| LoreFactExtraction | `LoreFactExtractionSignature` | HEAVY | `section_context`, `source_name` | `lore_facts_reasoning` |

### 7.16 NPCSceneGeneratorModule (`prompts/npc_scene_generator.py`)

| Module | Signature | Role | Max Tokens |
|--------|-----------|------|-----------|
| `NPCSceneGeneratorModule` | `NPCSceneGeneratorSignature` | HEAVY | 16384 |
| `ScenePromptModule` | `ScenePromptSignature` | STANDARD | 4096 |

### 7.17 MapExtractorModule (`prompts/vision.py`)

**Signature:** `MapExtractorSignature` (Predict)

| Input Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `image_description` | Textual map description/OCR | No | — (auto-injected) |
| `context` | World/system context | No | — (auto-injected) |

| Output Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `extraction` | `MapExtraction` (locations, scale, lore) | No | — (LLM output) |

### 7.18 SessionListenerModule (`prompts/session_ingest.py`)

**Signature:** `SessionListenerSignature` (Predict)

| Input Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `turns` | Sequence of gameplay turns | No | — (auto-injected) |
| `context` | Existing world context | No | — (auto-injected) |

| Output Field | Description | Frontend Exposed | UI Control |
|-------------|-------------|-----------------|------------|
| `extraction` | `SessionExtraction` (events, lore, threads) | No | — (LLM output) |

### 7.19 Lorebook Modules (`prompts/lorebook.py`)

| Module | Type | Key Params |
|--------|------|-----------|
| `LorebookKeywordExtractor` | Predict | `content` → 3-8 keywords |
| `LorebookIngestionModule` | Predict | `chunk`, `existing_keywords`, `priority_hint` (0-100), `tags` → `LorebookEntryDraft` |

---

## 8. Loop State Configuration

### 8.1 SceneLoop (`loops/scene_loop.py`) — `SceneState`

| Parameter | Type | Default | Frontend Exposed | UI Control |
|-----------|------|---------|-----------------|------------|
| `scene_id` | `UUID` | (required) | No | — (session-bound) |
| `story_id` | `UUID` | (required) | No | — (session-bound) |
| `universe_id` | `Optional[UUID]` | `None` | No | — (session-bound) |
| `gm_profile_id` | `Optional[UUID]` | `None` | Yes | Profile picker |
| `gm_profile` | `Optional[Dict]` | `None` | Yes | Profile picker |
| `play_mode` | `str` | `"dice_game_system"` | Yes | Dropdown (narrative/dice_standard/dice_game_system) |
| `system_id` | `Optional[str]` | `None` | Yes | Dropdown (game systems) |
| `pack_id` | `Optional[str]` | `None` | Yes | Dropdown (packs) |
| `system_source_type` | `Optional[str]` | `None` | No | — (auto-detected) |
| `system_source_id` | `Optional[str]` | `None` | No | — (auto-detected) |
| `session_tone` | `str` | `"dramatic"` | Yes | Dropdown |
| `tension_score` | `float` | `0.5` | Yes | Slider (0.0-1.0) |
| `roll_mode` | `str` | `"normal"` | Yes | Dropdown (normal/advantage/disadvantage) |
| `max_turns` | `int` | `50` | No | Slider (10-200) |
| `temporal_mode` | `str` | `"present"` | No | Dropdown (present/flashback/flashforward) |
| `time_ref` | `Optional[datetime]` | `None` | No | Date/time picker |

### 8.2 StoryLoop (`loops/story_loop.py`) — `StoryState`

| Parameter | Type | Default | Frontend Exposed | UI Control |
|-----------|------|---------|-----------------|------------|
| `story_id` | `UUID` | (required) | No | — (session-bound) |
| `universe_id` | `UUID` | (required) | No | — (session-bound) |
| `in_game_time` | `datetime` | `1000-01-01T12:00:00Z` | No | Date/time display |
| `world_ticks` | `int` | `0` | No | Counter |
| `last_scene_duration_minutes` | `int` | `0` | No | Counter |
| `world_tone` | `str` | `"dramatic"` | Yes | Dropdown |
| `arc_label` | `str` | `"rising_action"` | Yes | Dropdown (rising_action/climax/falling_action/resolution/new_thread) |
| `tension_score` | `float` | `0.3` | Yes | Slider (0.0-1.0) |
| `active_threads` | `List[str]` | `[]` | Yes | Tag list |
| `completed_threads` | `List[str]` | `[]` | Yes | Tag list (read-only) |
| `next_scene_type` | `Optional[str]` | `None` | Yes | Badge (LLM suggestion) |
| `scene_hook` | `Optional[str]` | `None` | Yes | Text display (LLM suggestion) |

### 8.3 CombatLoop (`loops/combat_loop.py`) — `CombatState`

| Parameter | Type | Default | Frontend Exposed | UI Control |
|-----------|------|---------|-----------------|------------|
| `scene_id` | `UUID` | (required) | No | — (session-bound) |
| `story_id` | `UUID` | (required) | No | — (session-bound) |
| `combatants` | `List[CombatantState]` | `[]` | Yes | Entity list |
| `initiative_order` | `List[UUID]` | `[]` | Yes | Ordered list (read-only) |
| `current_index` | `int` | `0` | No | — (internal) |
| `round_number` | `int` | `1` | Yes | Counter |
| `combat_active` | `bool` | `True` | Yes | Badge |
| `victory_side` | `Optional[str]` | `None` | Yes | Badge (pc/enemy) |
| `session_tone` | `str` | `"dramatic"` | Yes | Dropdown |
| `gm_profile` | `Optional[Dict]` | `None` | Yes | Profile picker |

### 8.4 ConversationLoop (`loops/conversation_loop.py`) — `ConversationState`

| Parameter | Type | Default | Frontend Exposed | UI Control |
|-----------|------|---------|-----------------|------------|
| `conversation_id` | `UUID` | (required) | No | — (session-bound) |
| `universe_id` | `UUID` | (required) | No | — (session-bound) |
| `mode` | `ConversationMode` | (required) | Yes | Dropdown (DIRECT/ACTOR) |
| `npc_ids` | `List[UUID]` | `[]` | Yes | Entity picker (multi) |
| `scene_id` | `Optional[UUID]` | `None` | No | — (optional context) |
| `story_id` | `Optional[UUID]` | `None` | No | — (optional context) |
| `player_entity_id` | `Optional[UUID]` | `None` | No | — (optional context) |
| `max_turns` | `int` | `100` | No | Slider (10-500) |

### 8.5 WorldBuildingLoop (`loops/world_building_loop.py`) — `WorldBuildingState`

| Parameter | Type | Default | Frontend Exposed | UI Control |
|-----------|------|---------|-----------------|------------|
| `session_id` | `str` | (required) | No | — (session-bound) |
| `universe_id` | `Optional[UUID]` | `None` | Yes | Universe picker |
| `multiverse_id` | `Optional[UUID]` | `None` | Yes | Multiverse picker |

### 8.6 CharacterCreationLoop (`loops/character_creation_loop.py`) — `CharacterCreationState`

| Parameter | Type | Default | Frontend Exposed | UI Control |
|-----------|------|---------|-----------------|------------|
| `scene_id` | `Optional[UUID]` | `None` | No | — (session-bound) |
| `story_id` | `Optional[UUID]` | `None` | No | — (session-bound) |
| `universe_id` | `Optional[UUID]` | `None` | No | — (session-bound) |
| `game_context` | `Dict[str, Any]` | `{}` | Yes | Game system picker |
| `current_step_index` | `int` | `0` | Yes | Progress indicator |
| `total_steps` | `int` | `0` | Yes | Progress indicator |
| `creation_complete` | `bool` | `False` | Yes | Badge |

### 8.7 ProgressionLoop (`loops/progression_loop.py`) — `ProgressionState`

| Parameter | Type | Default | Frontend Exposed | UI Control |
|-----------|------|---------|-----------------|------------|
| `entity_id` | `UUID` | (required) | No | — (entity-bound) |
| `universe_id` | `UUID` | (required) | No | — (entity-bound) |
| `available_xp` | `int` | `0` | Yes | Counter |
| `available_upgrades` | `List[Dict]` | `[]` | Yes | Upgrade list |
| `selected_upgrades` | `List[Dict]` | `[]` | Yes | Multi-select |

---

## 9. Tone System Configuration

### 9.1 ToneProfile (`schemas/tone_profiles.py`)

| Parameter | Type | Default | Frontend Exposed | UI Control |
|-----------|------|---------|-----------------|------------|
| `name` | `str` | (required, 1-200 chars) | Yes | Text input |
| `description` | `str` | (required, max 500) | Yes | Text area |
| `instruction` | `str` | (required, max 2000) | Yes | Text area (large) |
| `trigger_tags` | `List[str]` | `[]` | Yes | Tag editor |
| `category` | `str` | `"narrative"` | Yes | Dropdown (narrative/genre/mood/pacing) |
| `language` | `str` | `"en"` | Yes | Dropdown (language codes) |
| `pack_id` | `Optional[UUID]` | `None` | Yes | Pack picker |
| `is_builtin` | `bool` | `False` | Yes | Badge (read-only) |
| `example_output` | `Optional[str]` | `None` (max 1000) | Yes | Text area |

### 9.2 ToneLibrary (`schemas/tone_libraries.py`)

| Parameter | Type | Default | Frontend Exposed | UI Control |
|-----------|------|---------|-----------------|------------|
| `name` | `str` | (required, 1-200) | Yes | Text input |
| `description` | `str` | `""` (max 1000) | Yes | Text area |
| `tone_profile_ids` | `List[UUID]` | `[]` | Yes | Multi-select |
| `pack_id` | `Optional[UUID]` | `None` | Yes | Pack picker |
| `universe_id` | `Optional[UUID]` | `None` | Yes | Universe picker |
| `priority` | `int` | `100` (0-1000) | Yes | Slider |
| `is_default` | `bool` | `False` | Yes | Toggle |

### 9.3 Built-in Tone Profiles (Fallback)

**File:** `packages/agents/src/monitor_agents/utils/tone_resolver.py`

| Tone Key | Instruction (summary) | Frontend Exposed | UI Control |
|----------|----------------------|-----------------|------------|
| `dramatic` | Baroque, weighty, emotionally charged | Yes | Dropdown |
| `grim` | Terse, industrial, cosmic-dread | Yes | Dropdown |
| `horror` | Dread through omission, very short sentences | Yes | Dropdown |
| `heroic` | Elevated, mythic register | Yes | Dropdown |
| `mystery` | Careful and layered, information rationed | Yes | Dropdown |
| `adventure` | Kinetic and immediate, momentum | Yes | Dropdown |

---

## 10. GM Profile Configuration

**File:** `packages/data-layer/src/monitor_data/schemas/gm_profiles.py`

| Parameter | Type | Default | Frontend Exposed | UI Control |
|-----------|------|---------|-----------------|------------|
| `name` | `str` | (required, 1-200) | Yes | Text input |
| `description` | `str` | `""` (max 1000) | Yes | Text area |
| `tone_tags` | `List[str]` | `[]` | Yes | Tag editor |
| `theme_tags` | `List[str]` | `[]` | Yes | Tag editor |
| `style_tags` | `List[str]` | `[]` | Yes | Tag editor |
| `concept_tags` | `List[str]` | `[]` | Yes | Tag editor |
| `tone_instructions` | `Optional[str]` | `None` (max 2000) | Yes | Text area (large) |
| `narrator_constraints` | `Optional[str]` | `None` (max 1000) | Yes | Text area |
| `tone_library_id` | `Optional[UUID]` | `None` | Yes | Library picker |
| `merge_with_default_library` | `bool` | `True` | Yes | Toggle |
| `universe_id` | `Optional[UUID]` | `None` | Yes | Universe picker |
| `game_system_id` | `Optional[UUID]` | `None` | Yes | Game system picker |
| `is_builtin` | `bool` | `False` | Yes | Badge (read-only) |

---

## 11. NPC Profile Configuration

**File:** `packages/data-layer/src/monitor_data/schemas/npc_profiles.py`

| Parameter | Type | Default | Frontend Exposed | UI Control |
|-----------|------|---------|-----------------|------------|
| `entity_id` | `UUID` | (required) | No | — (entity-bound) |
| `traits` | `Dict[str, float]` | `{}` | Yes | Key-value editor (0.0-1.0) |
| `values` | `List[str]` | `[]` | Yes | Tag editor |
| `fears` | `List[str]` | `[]` | Yes | Tag editor |
| `desires` | `List[str]` | `[]` | Yes | Tag editor |
| `speech_style` | `Optional[str]` | `None` (max 200) | Yes | Text input |
| `catchphrases` | `List[str]` | `[]` | Yes | Tag editor |
| `mannerisms` | `List[str]` | `[]` | Yes | Tag editor |
| `emotional_tendencies` | `List[EmotionalTendency]` | `[]` | Yes | Structured list |
| `preferences` | `List[CharacterPreference]` | `[]` | Yes | Structured list |
| `triggers` | `List[BehavioralTrigger]` | `[]` | Yes | Structured list |
| `secrets` | `List[str]` | `[]` | Yes (GM only) | Tag editor |
| `gm_notes` | `Optional[str]` | `None` (max 5000) | Yes (GM only) | Text area |
| `current_emotional_state` | `Optional[str]` | `None` (max 200) | Yes | Text input |
| `relationship_states` | `Dict[str, Dict]` | `{}` | Yes | Structured editor |

### EmotionalTendency Sub-Model

| Parameter | Type | Default | Range | Frontend Exposed | UI Control |
|-----------|------|---------|-------|-----------------|------------|
| `emotion` | `str` | (required) | — | Yes | Dropdown |
| `baseline` | `float` | (required) | -1.0 to 1.0 | Yes | Slider |
| `volatility` | `float` | `0.5` | 0.0 to 1.0 | Yes | Slider |

### CharacterPreference Sub-Model

| Parameter | Type | Default | Range | Frontend Exposed | UI Control |
|-----------|------|---------|-------|-----------------|------------|
| `category` | `str` | (required) | — | Yes | Dropdown |
| `item` | `str` | (required) | — | Yes | Text input |
| `valence` | `float` | (required) | -1.0 to 1.0 | Yes | Slider |
| `reason` | `Optional[str]` | `None` | — | Yes | Text input |

### BehavioralTrigger Sub-Model

| Parameter | Type | Default | Range | Frontend Exposed | UI Control |
|-----------|------|---------|-------|-----------------|------------|
| `condition` | `str` | (required) | — | Yes | Text input |
| `reaction` | `str` | (required) | — | Yes | Text input |
| `intensity` | `float` | `0.7` | 0.0 to 1.0 | Yes | Slider |
| `is_hidden` | `bool` | `True` | — | Yes | Toggle |

---

## 12. Game System Schema Configuration

**File:** `packages/data-layer/src/monitor_data/schemas/game_systems.py`

### Core Enums

| Enum | Values | Frontend Exposed | UI Control |
|------|--------|-----------------|------------|
| `CoreMechanicType` | d20, dice_pool, percentile, card, narrative | Yes | Dropdown |
| `SuccessType` | meet_or_beat, count_successes, highest_wins, degrees_of_success | Yes | Dropdown |
| `GameRuleType` | core, combat, social, power, lore, custom | Yes | Dropdown |
| `AbilityScoreMethod` | random_roll, point_buy, standard_array, fixed, free_assign | Yes | Dropdown |
| `CreationStepType` | choose_archetype, generate_stats, assign_stats, choose_background, choose_powers, choose_equipment, calculate_derived, write_backstory, custom | Yes | Dropdown |
| `LogicStepType` | choice, roll, calculation, text, narrative | Yes | Dropdown |
| `NPCTier` | minion, standard, elite, boss, brute, villain | Yes | Dropdown |
| `RuleOverrideScope` | story, scene | Yes | Dropdown |

### Component Schemas (all configurable via game system definition)

| Schema | Key Configurable Fields | Frontend Exposed |
|--------|------------------------|-----------------|
| `AttributeDefinition` | name, abbreviation, min/max/default_value, modifier_formula | Yes |
| `SkillDefinition` | name, abbreviation, linked_attribute, description | Yes |
| `TrackDefinition` | name, min/max/default_value, track_type, gain/loss/spend_conditions, recovery_rules, threshold_effects, depleted/maxed_effect | Yes |
| `ThresholdEffect` | value, direction, effect | Yes |
| `TieredAbilitySystem` | name, parent_category, tiers, max_tier, acquisition_rule, linked_track, access_restriction | Yes |
| `AbilityTier` | tier, name, cost, effect, prerequisites, duration, roll | Yes |
| `AdvantageDefinition` | name, cost, category, effect, prerequisites, mutually_exclusive, tags | Yes |
| `ResolutionMechanic` | dice_formula, mechanic_type, difficulty_model, difficulty_range, success_degrees, success_type, critical_success/failure, consequence_on_failure, complication_mechanic | Yes |
| `SuccessDegree` | threshold, label, effect | Yes |
| `DamageModel` | damage_types, damage_track, incapacitated_at, death_condition | Yes |
| `DamageType` | name, healing_rate, healing_requires, resisted_by, lethality, bypasses | Yes |
| `ConditionDefinition` | name, trigger, mechanical_effects, ends_when, stackable | Yes |
| `ActionEconomy` | action_types, turn_structure, initiative_model, surprise_rules | Yes |
| `ActionType` | name, count_per_turn, can_be_used_for, triggers_on | Yes |
| `AdvancementModel` | currencies, targets, uses_levels, max_level, progression_table | Yes |
| `AdvancementCurrency` | name, earn_conditions | Yes |
| `AdvancementTarget` | target_type, target_name, cost_formula, prerequisites, max_purchases | Yes |
| `RecoveryModel` | events | Yes |
| `RecoveryEvent` | name, duration, restores, requires, available_when | Yes |

---

## 13. Entity Schema Configuration

**File:** `packages/data-layer/src/monitor_data/schemas/entities.py`

| Parameter | Type | Default | Frontend Exposed | UI Control |
|-----------|------|---------|-----------------|------------|
| `name` | `str` | (required, 1-200) | Yes | Text input |
| `entity_type` | `EntityType` | (required) | Yes | Dropdown (character/faction/location/object/concept/organization) |
| `sub_type` | `Optional[str]` | `None` (max 100) | Yes | Text input |
| `is_archetype` | `bool` | `False` | Yes | Toggle |
| `description` | `str` | `""` (max 2000) | Yes | Text area |
| `properties` | `Dict[str, Any]` | `{}` | Yes | JSON editor |
| `state_tags` | `List[str]` | `[]` | Yes | Tag editor |
| `archetype_id` | `Optional[UUID]` | `None` | Yes | Entity picker |
| `authority` | `Authority` | `SYSTEM` | No | Dropdown (source/gm/system/player) |
| `canon_level` | `CanonLevel` | `CANON` | No | Dropdown (proposed/canon/rumor/character_belief/player_knowledge/retconned/superseded) |
| `confidence` | `float` | `1.0` (0.0-1.0) | No | Slider |
| `detail_level` | `DetailLevel` | `STUB` | No | Dropdown (stub/sketched/detailed/elaborated) |

---

## 14. Modes Configuration

**File:** `packages/ui/backend/src/monitor_ui/routers/modes.py`, `modes_schemas.py`

### Available Modes

| Mode ID | Label | Frontend Exposed | UI Control |
|---------|-------|-----------------|------------|
| `world_architect` | World Architect | Yes | Card selector |
| `autonomous_gm` | Autonomous GM | Yes | Card selector |
| `gm_assistant` | GM Assistant | Yes | Card selector |

### ActiveMode Parameters

| Parameter | Type | Default | Frontend Exposed | UI Control |
|-----------|------|---------|-----------------|------------|
| `mode_id` | `str` | `"autonomous_gm"` | Yes | Dropdown |
| `world_id` | `str | None` | `None` | Yes | Entity picker |
| `character_id` | `str | None` | `None` | Yes | Entity picker |
| `tone` | `str` | `"dramatic"` | Yes | Dropdown |
| `context_depth` | `str` | `"standard"` | Yes | Dropdown (shallow/standard/deep) |

---

## 15. Performance Monitoring

**File:** `packages/ui/backend/src/monitor_ui/routers/performance.py`

### PerformanceOverview

| Metric | Type | Description | Frontend Exposed | UI Control |
|--------|------|-------------|-----------------|------------|
| `total_queries` | `int` | Total Neo4j queries | Yes | Counter (read-only) |
| `total_time_ms` | `float` | Total execution time | Yes | Counter (read-only) |
| `avg_time_ms` | `float` | Average query time | Yes | Gauge (read-only) |
| `slow_queries` | `int` | Queries >150ms | Yes | Counter (read-only) |
| `slow_query_rate` | `float` | % slow queries | Yes | Gauge (read-only) |
| `unique_patterns` | `int` | Unique query patterns | Yes | Counter (read-only) |
| `uptime_seconds` | `Optional[float]` | Tracker uptime | Yes | Counter (read-only) |

### Query Pattern Metrics

| Metric | Type | Frontend Exposed | UI Control |
|--------|------|-----------------|------------|
| `pattern` | `str` | Yes | Text (read-only) |
| `count` | `int` | Yes | Counter (read-only) |
| `total_time_ms` | `float` | Yes | Counter (read-only) |
| `avg_time_ms` | `float` | Yes | Gauge (read-only) |
| `min_time_ms` | `float` | Yes | Gauge (read-only) |
| `max_time_ms` | `float` | Yes | Gauge (read-only) |
| `p95_time_ms` | `Optional[float]` | Yes | Gauge (read-only) |
| `p99_time_ms` | `Optional[float]` | Yes | Gauge (read-only) |
| `slow_count` | `int` | Yes | Counter (read-only) |

### Query Pattern Filters

| Parameter | Type | Default | Frontend Exposed | UI Control |
|-----------|------|---------|-----------------|------------|
| `limit` | `int` | `20` (1-100) | Yes | Slider |
| `sort_by` | `str` | `"count"` | Yes | Dropdown (count/avg_time/max_time/slow_count) |
| `min_count` | `int` | `1` | Yes | Number input |

---

## 16. Play Session Configuration

**File:** `packages/data-layer/src/monitor_data/schemas/play_sessions.py`

| Parameter | Type | Default | Frontend Exposed | UI Control |
|-----------|------|---------|-----------------|------------|
| `story_id` | `UUID` | (required) | No | — (session-bound) |
| `universe_id` | `UUID` | (required) | No | — (session-bound) |
| `session_number` | `int` | (required, ≥1) | Yes | Counter |
| `player_ids` | `List[UUID]` | `[]` | Yes | Entity picker (multi) |
| `gm_notes` | `Optional[str]` | `None` (max 5000) | Yes (GM only) | Text area |
| `player_notes` | `Optional[str]` | `None` (max 5000) | Yes | Text area |
| `summary` | `Optional[str]` | `None` (max 5000) | Yes | Text area |
| `xp_awarded` | `Optional[int]` | `None` (≥0) | Yes | Number input |
| `status` | `SessionStatus` | (auto) | Yes | Badge |

---

## 17. Environment Variables (Complete)

**File:** `env.example`

### UI Backend

| Env Var | Default | Frontend Exposed | UI Control |
|---------|---------|-----------------|------------|
| `UI_HOST` | `0.0.0.0` | No | Text input |
| `UI_PORT` | `8000` | No | Number input |
| `UI_CORS_ORIGINS` | `http://localhost:3000` | No | Text input |

### Database Performance Tuning

| Env Var | Default | Frontend Exposed | UI Control |
|---------|---------|-----------------|------------|
| `NEO4J_HEAP_INITIAL` | `512m` | No | Text input |
| `NEO4J_HEAP_MAX` | `2G` | No | Text input |
| `NEO4J_PAGECACHE` | `1G` | No | Text input |
| `MONGODB_CACHE_SIZE` | `1024` | No | Number input |
| `QDRANT_M` | `16` | No | Number input |
| `QDRANT_EF_CONSTRUCT` | `100` | No | Number input |

### LLM Configuration

| Env Var | Default | Frontend Exposed | UI Control |
|---------|---------|-----------------|------------|
| `LLM_PROVIDER` | `anthropic` | No | Dropdown |
| `LLM_MODEL` | `claude-sonnet-4-5-20250929` | Partial (via LLM mgmt) | Dropdown |
| `LLM_TEMPERATURE` | `0.7` | No | Slider (0.0-2.0) |
| `LLM_MAX_TOKENS` | `4096` | No | Slider (1-16384) |
| `GITHUB_MODELS_TOKEN` | (empty) | No | Password input |
| `GITHUB_MODELS_BASE_URL` | `https://models.github.ai/inference` | No | Text input |
| `GITHUB_MODELS_MODEL` | `gpt-4.1-mini` | No | Dropdown |
| `GOOGLE_API_KEY` | (empty) | No | Password input |
| `GOOGLE_MODEL` | `gemini-2.5-flash` | No | Dropdown |
| `Z_AI_API_KEY` | (set) | No | Password input |
| `Z_AI_MODEL` | `glm-5.1` | No | Dropdown |
| `Z_AI_BASE_URL` | `https://api.z.ai/api/coding/paas/v4` | No | Text input |
| `MINIMAX_TOKEN` | (empty) | No | Password input |
| `MINIMAX_BASE_URL` | `https://api.minimax.io/anthropic` | No | Text input |
| `OLLAMA_ENDPOINT` | `http://localhost:11434` | No | Text input |
| `OLLAMA_MODEL` | `qwen2.5:latest` | No | Dropdown |

### Ingestion Tuning

| Env Var | Default | Frontend Exposed | UI Control |
|---------|---------|-----------------|------------|
| `MONITOR_INGEST_MAX_WORKERS` | `1` | No | Slider (1-8) |
| `MONITOR_INGEST_TIMEOUT` | `2700` | No | Number input |
| `MONITOR_MAX_INGEST_FILE_BYTES` | `209715200` | No | Number input |

### Observability

| Env Var | Default | Frontend Exposed | UI Control |
|---------|---------|-----------------|------------|
| `LOG_LEVEL` | `INFO` | No | Dropdown (DEBUG/INFO/WARNING/ERROR) |
| `ENABLE_METRICS` | `true` | No | Toggle |
| `METRICS_ENDPOINT` | `http://prometheus:9090` | No | Text input |
| `ENVIRONMENT` | `development` | No | Dropdown |
| `DEBUG` | `false` | No | Toggle |
| `ENABLE_CORS` | `true` | No | Toggle |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:5173` | No | Text input |

### MCP Server

| Env Var | Default | Frontend Exposed | UI Control |
|---------|---------|-----------------|------------|
| `MCP_SERVER_PORT` | `8080` | No | Number input |
| `MCP_AUTH_SECRET` | (required) | No | Password input |

---

## Summary Statistics

| Category | Total Parameters | Frontend Exposed | Not Exposed |
|----------|-----------------|-----------------|-------------|
| Data-Layer Settings | 42 | 0 | 42 |
| BaseAgent | 6 | 1 | 5 |
| LLM Provider Config | 11 | 10 | 1 |
| Model Params | 5 | 5 | 0 |
| Node Assignments | 4 | 4 | 0 |
| Token Budgets | 12 | 0 | 12 |
| DSPy Runtime | 9 | 2 | 7 |
| Agent-Specific | ~40 | ~8 | ~32 |
| DSPy Prompt Modules | ~80 input/output fields | ~15 | ~65 |
| Loop States | ~60 | ~30 | ~30 |
| Tone System | 17 | 17 | 0 |
| GM Profiles | 13 | 13 | 0 |
| NPC Profiles | 16+sub | 16+sub | 0 |
| Game System Schemas | ~100+ | ~100+ | 0 |
| Entity Schemas | 12 | 8 | 4 |
| Modes | 5 | 5 | 0 |
| Performance | 12 | 12 | 0 |
| Play Sessions | 9 | 6 | 3 |
| Environment Vars | ~50 | ~5 | ~45 |
| **TOTAL** | **~500+** | **~260** | **~240** |

### Key Gaps (Not Frontend-Exposed)

1. **Token budgets** — hardcoded per role, no UI override
2. **Retry policies** — env-var only, no UI
3. **Context scoring weights** (0.7/0.3 action/profile) — hardcoded
4. **Dynamic escalation keywords** — hardcoded set
5. **Oracle DC map** — hardcoded game design values
6. **Resolver regex patterns** — hardcoded detection patterns
7. **Scene max_turns** — hardcoded at 50
8. **Conversation max_turns** — hardcoded at 100
9. **All database connection settings** — env-var only
10. **Ingestion tuning** — env-var only
11. **NLP/GLiNER settings** — env-var only
12. **Redis cache TTLs** — env-var only