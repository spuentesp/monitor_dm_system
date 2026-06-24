---
description: "Details the Lain MCP integration for architecture tools."
tags: [infrastructure, mcp, lain]
layer: 0
---

# Lain MCP Proxy

Lain is an external architecture analysis tool integrated into the workspace as an MCP server.

## Configuration
Located in `.vscode/settings.json`, Lain runs via a proxy script: `scripts/lain-mcp-proxy.sh`.
It operates on port `9999`.

## Capabilities
Agents can call Lain tools (via standard MCP clients) for:
- Blast radius analysis (`get_blast_radius`)
- Dependency traces (`trace_dependency`, `get_call_chain`)
- Semantic code search (`semantic_search`)

## Health Checks
You can curl the proxy to verify it's running:
```bash
curl -s -X POST http://localhost:9999/mcp -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"get_health","arguments":{}},"id":1}'
```

## See Also
- [Infrastructure Index](./_index.md)
- [MCP Transport](../2_architecture/mcp_transport.md)
