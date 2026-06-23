"""
Analyzer Agent — extracts structured knowledge from ingested source text.

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1), monitor_agents.prompts

The Analyzer sits between the Indexer and the CanonKeeper in the ingestion
pipeline:

    Indexer → text chunks in Qdrant
    Analyzer → KnowledgePack (MongoDB, status=ready)
                ProposedChanges (ready for CanonKeeper review)
    CanonKeeper → evaluates proposals → Neo4j nodes

This package was split from a single 2717-line module into focused sub-modules:

  _constants.py              — Category lists, config limits, fallback queries
  _models.py                 — AnalysisRunResult, LLMExecutionSummary dataclasses
  _enrichment.py             — Entity evidence enrichment (pure data transform)
  _game_system_persistence.py — Game system save logic + helpers
  _mindscape_projection.py   — Qdrant mindscape projection
  _core.py                   — The Analyzer class (orchestration logic)
"""

# Re-export the main public API — consumers import from monitor_agents.analyzer
from monitor_agents.analyzer._core import Analyzer, AnalysisRunResult

__all__ = ["Analyzer", "AnalysisRunResult"]
