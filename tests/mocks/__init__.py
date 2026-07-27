"""
MONITOR — Unified Mock Mirror.

A 1:1 mocking mirror of the application's external dependencies.
Every fake in this package mirrors a real class's public interface,
providing typed, reusable test doubles.

Structure mirrors the real package layout:

    tests/mocks/
        db/             — Database client fakes (Mongo, Neo4j, Postgres, Qdrant, MinIO, Redis)
        agents/         — Agent-level fakes (LLM client, DSPy, MCP, BaseAgent)
        loops/          — Loop fakes (SceneLoop, StoryLoop)
        routers/        — Router fakes (Chat router DB stubs)
        protocols.py    — typing.Protocol definitions for 1:1 contract enforcement
        factories.py     — Builder functions for common test data
        contract_check.py — CI test verifying fakes match real interfaces
"""
