---
description: "Logging standards and tracing."
tags: [infrastructure, logging, structlog]
layer: 0
---

# Observability

## Logging with Structlog
MONITOR forbids the use of `print()` for system logs. All modules must use `structlog` to ensure logs are structured, parseable (JSON in production), and context-aware.

```python
import structlog

log = structlog.get_logger()
log.info("scene_resolved", scene_id="123", outcome="success")
```

## Traceability
Every LLM call and MCP tool execution is logged. LangGraph also provides native trace states that are persisted via the `MongoDBSaver`.

## See Also
- [Infrastructure Index](./_index.md)
