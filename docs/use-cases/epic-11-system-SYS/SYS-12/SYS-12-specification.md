# SYS-12: Logging & Observability

**Actor:** Operator
**Trigger:** Debugging, performance monitoring, audit requirements

**Purpose:** Comprehensive logging for debugging, performance analysis, and compliance.

**Flow:**

1. **Log Levels:**
   - ERROR: Failures requiring attention
   - WARN: Recoverable issues
   - INFO: Normal operations (session start/end, canonization)
   - DEBUG: Detailed operation traces
   - TRACE: Full request/response payloads (dev only)

2. **Log Categories:**
   - `session.*` — User session events
   - `agent.*` — Agent operations
   - `db.*` — Database operations
   - `llm.*` — LLM API calls
   - `error.*` — Error events

3. **Metrics:**
   - Request latency (p50, p95, p99)
   - LLM token usage
   - Database query times
   - Error rates by category
   - Active sessions

4. **Structured Logging:**
   - JSON format for machine parsing
   - Correlation IDs for request tracing
   - User/session context in all logs

### Implementation

**Layer 1 (Data Layer):**
```python
# Logging middleware
def log_operation(operation: str, params: dict, result: Any, duration_ms: int):
    logger.info({
        "operation": operation,
        "params": sanitize(params),  # Remove sensitive data
        "duration_ms": duration_ms,
        "correlation_id": get_correlation_id(),
        "session_id": get_session_id()
    })
```

**Layer 3 (CLI):**
```bash
monitor system logs --level INFO --since "1h"
monitor system logs --category agent.narrator --limit 100
monitor system metrics --service llm
```

---
