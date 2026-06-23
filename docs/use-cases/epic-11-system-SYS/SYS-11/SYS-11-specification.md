# SYS-11: Error Recovery & Resilience

**Actor:** System (automatic) or Operator (manual)
**Trigger:** Database failure, LLM rate limit, network error, or corrupted data detection

**Purpose:** Handle failures gracefully without data loss or session corruption.

**Flow:**

1. **Error Detection:**
   - Database connection failures (Neo4j, MongoDB, Qdrant)
   - LLM API rate limits or timeouts
   - Network connectivity issues
   - Data validation failures
   - Corrupted state detection

2. **Automatic Recovery:**
   - **DB Connection:** Exponential backoff retry (3 attempts)
   - **LLM Rate Limit:** Queue requests, notify user of delay
   - **Partial Failure:** Transaction rollback, preserve last-known-good state
   - **Session State:** Auto-save every N turns to prevent data loss

3. **Graceful Degradation:**
   - If Qdrant unavailable → fallback to keyword search
   - If LLM unavailable → offer dice-only resolution mode
   - If Neo4j unavailable → read-only mode from MongoDB cache

4. **Manual Recovery:**
   - Operator can trigger health check
   - Force reconnection to services
   - Restore from last checkpoint
   - Export session for offline recovery

5. **User Notification:**
   - Clear error messages (not stack traces)
   - Recovery options presented
   - Session state preserved

### Implementation

**Layer 1 (Data Layer):**
```python
# Health checks
neo4j_health_check() -> HealthStatus
mongodb_health_check() -> HealthStatus
qdrant_health_check() -> HealthStatus
minio_health_check() -> HealthStatus

# Connection management
neo4j_reconnect(max_attempts=3, backoff=True)
mongodb_reconnect(max_attempts=3, backoff=True)

# Checkpointing
mongodb_create_checkpoint(session_id) -> checkpoint_id
mongodb_restore_checkpoint(checkpoint_id) -> SessionState
mongodb_list_checkpoints(session_id) -> list[Checkpoint]
```

**Layer 2 (Agents):**
- `Orchestrator.handle_error(error, context)` — Route to appropriate recovery
- `Orchestrator.enter_degraded_mode(unavailable_services)` — Graceful degradation
- `Orchestrator.create_session_checkpoint()` — Auto-save

**Layer 3 (CLI):**
```bash
monitor system health                    # Check all services
monitor system reconnect --service neo4j # Force reconnection
monitor system checkpoints --session <UUID>
monitor system restore --checkpoint <UUID>
```

**Error Handling Schema:**
```python
@dataclass
class HealthStatus:
    service: str
    status: ServiceStatus  # healthy, degraded, unavailable
    latency_ms: int
    last_check: datetime
    error: str | None

class ServiceStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"      # Working but slow/limited
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"

@dataclass
class Checkpoint:
    id: UUID
    session_id: UUID
    scene_id: UUID
    turn_number: int
    state_snapshot: dict
    created_at: datetime
    reason: str  # "auto", "manual", "pre_risky_operation"
```

**Auto-Checkpoint Triggers:**
```python
AUTO_CHECKPOINT_TRIGGERS = [
    "every_10_turns",
    "scene_end",
    "before_canonization",
    "before_combat",
    "user_request"
]

async def maybe_checkpoint(trigger: str, session: Session):
    if trigger in session.checkpoint_policy:
        await mongodb_create_checkpoint(session.id)
```

**Degraded Mode Capabilities:**

| Service Unavailable | Capabilities Lost | Fallback |
|---------------------|-------------------|----------|
| Neo4j | Canon writes | Read from cache, queue writes |
| MongoDB | Scene persistence | Local buffer, sync later |
| Qdrant | Semantic search | Keyword search via OpenSearch |
| OpenSearch | Keyword search | Basic string matching |
| LLM API | Narration, NPC dialogue | Dice-only mode, player narrates |
| MinIO | Document storage | Skip media, text-only |

---
