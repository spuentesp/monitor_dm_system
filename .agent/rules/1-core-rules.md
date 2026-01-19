# Critical Invariants (MUST FOLLOW)

## What You MUST Do
1. **Evidence for All Facts**: Every canonical fact MUST have evidence (`evidence_refs`).
2. **Agent Identity**: Every MCP request MUST include agent identity.
3. **Validate All Boundaries**: Use Pydantic for cross-layer data.
4. **UUIDs Only**: Neo4j IDs must be UUIDs (no MongoDB IDs).
5. **Bottom-Up Implementation**: L1 (Data) → L2 (Agents) → L3 (CLI).
6. **Single Use Case**: One PR per use case.
7. **Test All Changes**: No code without tests.

## What You MUST NEVER Do
1. **Delete Canonical Facts**: Mark as `retconned` instead.
2. **Direct DB Access**: Use MCP tools only.
3. **Reference External Keys**: No Mongo IDs in Neo4j.
4. **Qdrant as Authority**: It is a derived index only.
5. **Per-Turn Canonization**: Canonize at scene end (batch).
6. **Reverse Data Flow**: Neo4j → MongoDB is forbidden.
7. **Upward Imports**: L1 cannot import L2/L3.

## The 7 Golden Rules
1. **Layer boundaries are sacred**.
2. **CanonKeeper owns Neo4j writes** (exclusive).
3. **Use case IDs are mandatory**.
4. **Tests are required**.
5. **Evidence is mandatory**.
6. **Canonization at scene end**.
7. **Follow existing patterns**.
