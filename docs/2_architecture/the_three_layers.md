---
description: "Defines the 3-Layer Cake dependency architecture of MONITOR."
tags: [architecture, layers, boundaries]
layer: 0
---

# The Three Layers

MONITOR follows a strict layered architecture pattern known as the **3-Layer Cake**. Dependencies only flow **downward**.

```mermaid
graph TD
    UI["User Interface (CLI / Web UI)"]
    
    subgraph Layer3["Layer 3: Interface Layer"]
        CLI["monitor-cli"]
        WebFrontend["monitor-ui-frontend"]
        WebBackend["monitor-ui-backend"]
    end
    
    subgraph Layer2["Layer 2: Agent Layer"]
        Loops["LangGraph Loops"]
        Agents["Specialized Agents"]
        Logic["GameSystemRuntime"]
    end
    
    subgraph Layer1["Layer 1: Data Layer"]
        Tools["MCP Tools"]
        Clients["DB Clients"]
        Schemas["Pydantic Schemas"]
    end
    
    subgraph Infrastructure
        Neo4j["Neo4j (Canon)"]
        MongoDB["MongoDB (State)"]
        Qdrant["Qdrant (Vectors)"]
        PG["PostgreSQL (Config)"]
        MinIO["MinIO (Files)"]
    end

    UI --> Layer3
    Layer3 --> Layer2
    Layer2 --> Layer1
    Layer1 --> Infrastructure
```

## Layer Summary
1. **[Layer 1: Data Layer](./layer1_data.md)**: Connects to databases. Validates schemas. Exposes MCP Tools. Never imports from Layer 2 or 3.
2. **[Layer 2: Agent Layer](./layer2_agents.md)**: AI logic, LangGraph loops, DSPy reasoning. Imports from Layer 1. Never imports from Layer 3.
3. **[Layer 3: Interface Layer](./layer3_interface.md)**: User surfaces. Imports from Layer 2. Avoids direct Layer 1 imports.

## See Also
- [Architecture Index](./_index.md)
