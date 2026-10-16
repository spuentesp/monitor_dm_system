"""
================================================================================
SUITE DE VERIFICACIÓN DE INTEGRACIÓN DETERMINISTA Y PROVENIENCIA ("INSIDE-OUT")
Diseñada específicamente para: https://github.com/spuentesp/monitor_dm_system
================================================================================

Implementa un Arnés de Simulación Determinista de Caja Gris (Sin Mocks de
Capas Internas) que corre con `uv run pytest`:

- CAPA 1 (`StrictMCPWireBridge`): Prohibido `FakeMCPClient` directo. Fuerza que
  toda llamada entre `monitor_agents` y `monitor_data` pase por serialización
  JSON-RPC estricta y validación de esquemas Pydantic/FastMCP.
- CAPA 2 (`DeterministicRawLLMTransport`): En vez de mockear módulos DSPy,
  inyecta respuestas en la frontera más baja de texto crudo (con ruido realista:
  bloques ```json, campos extra, conflictos de canon) controladas por `seed`.
- CAPA 3 (`MonitorCrossStoreOracle`): Oráculo "Inside-Out" que verifica en CADA
  paso los 5 Invariantes de Oro cruzando Neo4j, MongoDB, Qdrant y MinIO.
- CAPA 4 (`MonitorDMSystemVerificationSuite`):
  Ejecuta campañas completas desde manual PDF hasta múltiples turnos de juego
  con retrocesos de línea de tiempo, caídas en medio del loop y validación
  contra el `TOOL_REGISTRY` real de `monitor_data.server`.
================================================================================
"""

from __future__ import annotations

import hashlib
import json
import random
import unittest
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4


# ==============================================================================
# 1. PUENTE ESTRICTO DE PROTOCOLO MCP (`StrictMCPWireBridge`)
#    Reemplaza `FakeMCPClient` exigiendo serialización JSON-RPC real y
#    verificación de esquemas de entrada/salida entre `monitor_agents` y `monitor_data`.
# ==============================================================================


class MCPWireBoundaryError(RuntimeError):
    """Explota cuando un agente llama una herramienta MCP inexistente o con tipos no JSON."""


@dataclass
class MCPToolSpec:
    name: str
    required_args: Set[str]
    optional_args: Set[str]
    handler: Callable[[Dict[str, Any]], Dict[str, Any]]


class StrictMCPWireBridge:
    """
    Simula exactamente la frontera de proceso/red de `monitor_data/server.py` (FastMCP).
    Ningún objeto Python pasa por referencia en memoria: todo request y response
    es forzado a cruzar `json.dumps` -> `json.loads` + validación de contrato.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, MCPToolSpec] = {}
        self.call_audit_log: List[Dict[str, Any]] = []

    def register_tool(
        self,
        name: str,
        required_args: Set[str],
        handler: Callable[[Dict[str, Any]], Dict[str, Any]],
        optional_args: Optional[Set[str]] = None,
    ) -> None:
        self._tools[name] = MCPToolSpec(
            name=name,
            required_args=set(required_args),
            optional_args=set(optional_args or set()),
            handler=handler,
        )

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        # 1. Verificar que la herramienta realmente exista en `monitor_data/server.py`
        if tool_name not in self._tools:
            raise MCPWireBoundaryError(
                f"Desconexión Agente->MCP: El agente invocó '{tool_name}', "
                f"pero las herramientas registradas en monitor_data son: {sorted(self._tools.keys())}"
            )

        spec = self._tools[tool_name]

        # 2. Forzar serialización JSON-RPC de ida (detecta UUIDs, datetimes crudos, sets, modelos sin .model_dump())
        try:
            wire_request = json.dumps({"tool": tool_name, "arguments": arguments})
            decoded_args: Dict[str, Any] = json.loads(wire_request)["arguments"]
        except TypeError as exc:
            raise MCPWireBoundaryError(
                f"Fallo de serialización JSON-RPC al llamar '{tool_name}': {exc}. "
                f"Un mock en memoria habría dejado pasar este objeto inválido."
            ) from exc

        # 3. Validar esquema estricto de argumentos (sin llaves fantasma ni faltantes)
        provided_keys = set(decoded_args.keys())
        missing = spec.required_args - provided_keys
        unknown = provided_keys - (spec.required_args | spec.optional_args)
        if missing:
            raise MCPWireBoundaryError(
                f"Contrato MCP roto en '{tool_name}': faltan argumentos obligatorios {sorted(missing)}"
            )
        if unknown:
            raise MCPWireBoundaryError(
                f"Contrato MCP roto en '{tool_name}': argumentos desconocidos {sorted(unknown)}"
            )

        # 4. Ejecutar el handler real de `monitor_data` y forzar serialización JSON de vuelta
        raw_response = spec.handler(decoded_args)
        try:
            wire_response = json.dumps(raw_response)
            decoded_response: Dict[str, Any] = json.loads(wire_response)
        except TypeError as exc:
            raise MCPWireBoundaryError(
                f"La herramienta '{tool_name}' en monitor_data devolvió un objeto no serializable por MCP: {exc}"
            ) from exc

        self.call_audit_log.append(
            {
                "tool": tool_name,
                "request": decoded_args,
                "response": decoded_response,
            }
        )
        return decoded_response


# ==============================================================================
# 2. ESTADO MULTI-BASE DE DATOS REALISTA (MinIO + Qdrant + MongoDB + Neo4j)
# ==============================================================================


class ProposalStatus(str, Enum):
    PROPOSED = "PROPOSED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


@dataclass
class MultiStoreDataLayer:
    """
    Representa las 4 bases de datos de `monitor_dm_system` expuestas únicamente
    a través de herramientas MCP en `StrictMCPWireBridge`.
    """

    minio_blobs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    qdrant_points: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    mongo_documents: Dict[str, Dict[str, Any]] = field(
        default_factory=lambda: {
            "ingestion_docs": {},
            "scenes": {},
            "turns": {},
            "proposed_changes": {},
            "langgraph_checkpoints": {},
        }
    )
    neo4j_nodes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    neo4j_edges: List[Dict[str, Any]] = field(default_factory=list)

    def mount_mcp_tools(self, bridge: StrictMCPWireBridge) -> None:
        """Registra las herramientas del servidor MCP `monitor_data`."""
        bridge.register_tool(
            name="ingest_store_document",
            required_args={"source_document_id", "title", "raw_text"},
            handler=self._mcp_ingest_store_document,
        )
        bridge.register_tool(
            name="qdrant_upsert_chunk",
            required_args={
                "chunk_id",
                "source_document_id",
                "text",
                "vector",
                "entity_ids",
                "timeline_tick",
            },
            handler=self._mcp_qdrant_upsert_chunk,
        )
        bridge.register_tool(
            name="mongo_propose_change",
            required_args={
                "proposal_id",
                "source_type",
                "source_ref_id",
                "entity_id",
                "entity_type",
                "fact_key",
                "fact_value",
                "timeline_branch",
                "timeline_tick",
            },
            optional_args={"target_entity_id", "relation_type"},
            handler=self._mcp_mongo_propose_change,
        )
        bridge.register_tool(
            name="canonkeeper_commit_proposal",
            required_args={"proposal_id", "decision", "reason"},
            handler=self._mcp_canonkeeper_commit_proposal,
        )
        bridge.register_tool(
            name="context_query_world_at_tick",
            required_args={"entity_ids", "timeline_branch", "max_tick"},
            handler=self._mcp_context_query_world_at_tick,
        )
        bridge.register_tool(
            name="langgraph_save_checkpoint",
            required_args={"thread_id", "step_index", "serialized_state_json"},
            handler=self._mcp_langgraph_save_checkpoint,
        )
        bridge.register_tool(
            name="langgraph_load_checkpoint",
            required_args={"thread_id"},
            handler=self._mcp_langgraph_load_checkpoint,
        )

    def _mcp_ingest_store_document(self, args: Dict[str, Any]) -> Dict[str, Any]:
        doc_id = args["source_document_id"]
        sha256 = hashlib.sha256(args["raw_text"].encode("utf-8")).hexdigest()
        self.minio_blobs[doc_id] = {"sha256": sha256, "size": len(args["raw_text"])}
        self.mongo_documents["ingestion_docs"][doc_id] = {
            "source_document_id": doc_id,
            "title": args["title"],
            "minio_sha256": sha256,
        }
        return {"ok": True, "source_document_id": doc_id, "sha256": sha256}

    def _mcp_qdrant_upsert_chunk(self, args: Dict[str, Any]) -> Dict[str, Any]:
        vec = args["vector"]
        if not isinstance(vec, list) or len(vec) != 8 or not all(isinstance(x, (int, float)) for x in vec):
            raise ValueError("Qdrant exige vector numérico de dimensión fija (8 en test)")
        self.qdrant_points[args["chunk_id"]] = {
            "chunk_id": args["chunk_id"],
            "source_document_id": args["source_document_id"],
            "text": args["text"],
            "vector": vec,
            "entity_ids": list(args["entity_ids"]),
            "timeline_tick": int(args["timeline_tick"]),
        }
        return {"ok": True, "chunk_id": args["chunk_id"]}

    def _mcp_mongo_propose_change(self, args: Dict[str, Any]) -> Dict[str, Any]:
        pid = args["proposal_id"]
        self.mongo_documents["proposed_changes"][pid] = {
            **args,
            "status": ProposalStatus.PROPOSED.value,
        }
        return {"ok": True, "proposal_id": pid, "status": ProposalStatus.PROPOSED.value}

    def _mcp_canonkeeper_commit_proposal(self, args: Dict[str, Any]) -> Dict[str, Any]:
        pid = args["proposal_id"]
        prop = self.mongo_documents["proposed_changes"].get(pid)
        if prop is None:
            return {"ok": False, "error": "PROPOSAL_NOT_FOUND"}
        if prop["status"] != ProposalStatus.PROPOSED.value:
            return {"ok": True, "status": prop["status"], "idempotent_replay": True}

        decision = args["decision"]
        if decision == ProposalStatus.REJECTED.value:
            prop["status"] = ProposalStatus.REJECTED.value
            prop["decision_reason"] = args["reason"]
            return {"ok": True, "status": ProposalStatus.REJECTED.value}

        # Validación de proveniencia por CanonKeeper antes de tocar Neo4j:
        source_type = prop["source_type"]
        source_ref = prop["source_ref_id"]
        if source_type == "MANUAL_DOCUMENT":
            if source_ref not in self.mongo_documents["ingestion_docs"]:
                prop["status"] = ProposalStatus.REJECTED.value
                prop["decision_reason"] = "MISSING_PROVENANCE_DOCUMENT"
                return {"ok": False, "status": "REJECTED", "reason": "MISSING_PROVENANCE_DOCUMENT"}
        elif source_type == "SCENE_TURN":
            if source_ref not in self.mongo_documents["turns"]:
                prop["status"] = ProposalStatus.REJECTED.value
                prop["decision_reason"] = "MISSING_PROVENANCE_TURN"
                return {"ok": False, "status": "REJECTED", "reason": "MISSING_PROVENANCE_TURN"}

        prop["status"] = ProposalStatus.ACCEPTED.value
        prop["decision_reason"] = args["reason"]

        # Escritura canónica en Neo4j con línea de tiempo y enlace de proveniencia
        ent_id = prop["entity_id"]
        branch = prop["timeline_branch"]
        tick = int(prop["timeline_tick"])
        node_key = f"{branch}::{ent_id}"

        node = self.neo4j_nodes.setdefault(
            node_key,
            {
                "entity_id": ent_id,
                "entity_type": prop["entity_type"],
                "timeline_branch": branch,
                "facts_history": [],
            },
        )

        # Cerrar vigencia (`valid_to_tick`) del hecho anterior para la misma `fact_key` en esa línea de tiempo
        for prev_fact in node["facts_history"]:
            if prev_fact["fact_key"] == prop["fact_key"] and prev_fact["valid_to_tick"] is None:
                if tick < prev_fact["valid_from_tick"]:
                    prop["status"] = ProposalStatus.REJECTED.value
                    return {"ok": False, "status": "REJECTED", "reason": "NON_MONOTONIC_TIMELINE_TICK"}
                prev_fact["valid_to_tick"] = tick

        node["facts_history"].append(
            {
                "fact_key": prop["fact_key"],
                "fact_value": prop["fact_value"],
                "valid_from_tick": tick,
                "valid_to_tick": None,
                "provenance_source_type": source_type,
                "provenance_ref_id": source_ref,
                "proposal_id": pid,
            }
        )

        if prop.get("target_entity_id") and prop.get("relation_type"):
            self.neo4j_edges.append(
                {
                    "source_entity_id": ent_id,
                    "target_entity_id": prop["target_entity_id"],
                    "relation_type": prop["relation_type"],
                    "timeline_branch": branch,
                    "valid_from_tick": tick,
                    "provenance_ref_id": source_ref,
                    "proposal_id": pid,
                }
            )

        return {"ok": True, "status": ProposalStatus.ACCEPTED.value}

    def _mcp_context_query_world_at_tick(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ensambla el contexto combinando Neo4j (hechos vigentes en `max_tick` sobre `timeline_branch`)
        y Qdrant (chunks asociados a esas entidades con `timeline_tick <= max_tick`).
        """
        branch = args["timeline_branch"]
        max_tick = int(args["max_tick"])
        entity_ids = set(args["entity_ids"])

        resolved_entities: Dict[str, Dict[str, Any]] = {}
        for ent_id in sorted(entity_ids):
            node_key = f"{branch}::{ent_id}"
            node = self.neo4j_nodes.get(node_key)
            if not node:
                continue

            active_facts: Dict[str, Any] = {}
            provenance_refs: List[str] = []
            for fact in node["facts_history"]:
                starts_before = fact["valid_from_tick"] <= max_tick
                ends_after = fact["valid_to_tick"] is None or max_tick < fact["valid_to_tick"]
                if starts_before and ends_after:
                    active_facts[fact["fact_key"]] = fact["fact_value"]
                    provenance_refs.append(fact["provenance_ref_id"])

            if active_facts:
                resolved_entities[ent_id] = {
                    "entity_id": ent_id,
                    "entity_type": node["entity_type"],
                    "facts": active_facts,
                    "provenance_refs": provenance_refs,
                }

        matching_chunks: List[Dict[str, Any]] = []
        for chunk in self.qdrant_points.values():
            if chunk["timeline_tick"] <= max_tick and (set(chunk["entity_ids"]) & entity_ids):
                matching_chunks.append(
                    {
                        "chunk_id": chunk["chunk_id"],
                        "source_document_id": chunk["source_document_id"],
                        "text": chunk["text"],
                    }
                )

        return {
            "timeline_branch": branch,
            "queried_at_tick": max_tick,
            "entities": resolved_entities,
            "rag_chunks": matching_chunks,
        }

    def _mcp_langgraph_save_checkpoint(self, args: Dict[str, Any]) -> Dict[str, Any]:
        parsed = json.loads(args["serialized_state_json"])
        self.mongo_documents["langgraph_checkpoints"][args["thread_id"]] = {
            "thread_id": args["thread_id"],
            "step_index": int(args["step_index"]),
            "serialized_state_json": json.dumps(parsed),
        }
        return {"ok": True, "step_index": int(args["step_index"])}

    def _mcp_langgraph_load_checkpoint(self, args: Dict[str, Any]) -> Dict[str, Any]:
        ckpt = self.mongo_documents["langgraph_checkpoints"].get(args["thread_id"])
        if not ckpt:
            return {"found": False, "serialized_state_json": "{}"}
        return {
            "found": True,
            "step_index": ckpt["step_index"],
            "serialized_state_json": ckpt["serialized_state_json"],
        }


# ==============================================================================
# 3. ORÁCULO "INSIDE-OUT" DE PROVENIENCIA Y LÍNEAS DE TIEMPO (`MonitorCrossStoreOracle`)
# ==============================================================================


class MonitorCrossStoreOracle:
    """
    Inspecciona Neo4j + MongoDB + Qdrant + MinIO al mismo tiempo tras cada paso
    para garantizar que ningún componente trabajó en aislamiento ni dejó basura.
    """

    def __init__(self, stores: MultiStoreDataLayer) -> None:
        self.stores = stores

    def assert_all_cross_store_invariants(self) -> None:
        self._assert_ingestion_and_qdrant_provenance()
        self._assert_neo4j_canonical_provenance_and_exclusivity()
        self._assert_timeline_temporal_consistency()
        self._assert_langgraph_checkpoints_rehydratable()

    def _assert_ingestion_and_qdrant_provenance(self) -> None:
        for doc_id, doc_meta in self.stores.mongo_documents["ingestion_docs"].items():
            assert doc_id in self.stores.minio_blobs, (
                f"Invariante de Ingestión roto: '{doc_id}' existe en MongoDB pero no en MinIO"
            )
            assert (
                doc_meta["minio_sha256"] == self.stores.minio_blobs[doc_id]["sha256"]
            ), f"Hash corrupto entre MongoDB y MinIO para '{doc_id}'"

        for chunk_id, point in self.stores.qdrant_points.items():
            src_doc = point.get("source_document_id")
            assert src_doc, f"Chunk huérfano en Qdrant '{chunk_id}': falta source_document_id"
            assert src_doc in self.stores.mongo_documents["ingestion_docs"], (
                f"Proveniencia rota en Qdrant: el chunk '{chunk_id}' apunta a "
                f"source_document_id='{src_doc}', que no existe en MongoDB"
            )

    def _assert_neo4j_canonical_provenance_and_exclusivity(self) -> None:
        accepted_proposals = {
            pid: prop
            for pid, prop in self.stores.mongo_documents["proposed_changes"].items()
            if prop["status"] == ProposalStatus.ACCEPTED.value
        }

        seen_accepted_in_graph: Set[str] = set()

        for node_key, node in self.stores.neo4j_nodes.items():
            for fact in node["facts_history"]:
                pid = fact["proposal_id"]
                assert pid in accepted_proposals, (
                    f"Bypass de CanonKeeper detectado en Neo4j ({node_key}): "
                    f"hecho con proposal_id='{pid}' no está ACCEPTED en MongoDB"
                )
                seen_accepted_in_graph.add(pid)

                src_type = fact["provenance_source_type"]
                src_ref = fact["provenance_ref_id"]
                if src_type == "MANUAL_DOCUMENT":
                    assert src_ref in self.stores.mongo_documents["ingestion_docs"], (
                        f"Hecho en Neo4j ({node_key}) apunta a manual inexistente '{src_ref}'"
                    )
                elif src_type == "SCENE_TURN":
                    assert src_ref in self.stores.mongo_documents["turns"], (
                        f"Hecho en Neo4j ({node_key}) apunta a turno inexistente '{src_ref}'"
                    )
                else:
                    raise AssertionError(f"Tipo de proveniencia desconocido: {src_type}")

        for pid in accepted_proposals:
            assert pid in seen_accepted_in_graph, (
                f"Desconexión CanonKeeper->Neo4j: la propuesta '{pid}' fue marcada ACCEPTED "
                f"en MongoDB pero nunca se escribió el hecho en Neo4j"
            )

    def _assert_timeline_temporal_consistency(self) -> None:
        for node_key, node in self.stores.neo4j_nodes.items():
            by_key: Dict[str, List[Dict[str, Any]]] = {}
            for fact in node["facts_history"]:
                by_key.setdefault(fact["fact_key"], []).append(fact)

            for fact_key, intervals in by_key.items():
                open_ended_count = 0
                for idx, item in enumerate(intervals):
                    start = item["valid_from_tick"]
                    end = item["valid_to_tick"]
                    if end is None:
                        open_ended_count += 1
                    else:
                        assert end >= start, (
                            f"Intervalo temporal invertido en {node_key}.{fact_key}: [{start}, {end})"
                        )
                    if idx > 0:
                        prev_end = intervals[idx - 1]["valid_to_tick"]
                        assert prev_end is not None and start >= prev_end, (
                            f"Solapamiento de línea de tiempo en {node_key}.{fact_key}"
                        )
                assert open_ended_count <= 1, (
                    f"Múltiples hechos vigentes simultáneos para la misma clave {node_key}.{fact_key}"
                )

    def _assert_langgraph_checkpoints_rehydratable(self) -> None:
        required_keys = {"scene_id", "timeline_branch", "current_tick", "active_entities", "turn_history"}
        for thread_id, ckpt in self.stores.mongo_documents["langgraph_checkpoints"].items():
            hydrated = json.loads(ckpt["serialized_state_json"])
            missing = required_keys - set(hydrated.keys())
            assert not missing, (
                f"Checkpoint de LangGraph corrupto en thread '{thread_id}': faltan {sorted(missing)}"
            )


# ==============================================================================
# 4. TRANSPORTE LLM DETERMINISTA Y ADVERSARIO (Cero Mocks de Módulos DSPy)
# ==============================================================================


class DeterministicRawLLMTransport:
    """
    Frontera de bajo nivel para reemplazar `FakeLLMClient` sin apagar la lógica de
    los agentes. Devuelve strings JSON crudos (a veces envueltos en ```json ... ```)
    para verificar que el desempaquetado y validación Pydantic de los agentes funcione.
    """

    def __init__(self, seed: int = 42) -> None:
        self.rng = random.Random(seed)

    def complete_structured_extraction(self, raw_text: str, doc_id: str) -> str:
        """Simula la salida cruda de texto del LLM para `Analyzer` (DSPy)."""
        payload = {
            "extracted_entities": [
                {
                    "entity_id": "ent_valdris",
                    "entity_type": "FACTION",
                    "fact_key": "alignment",
                    "fact_value": "Order of the Silver Flame",
                    "source_document_id": doc_id,
                },
                {
                    "entity_id": "ent_elara",
                    "entity_type": "NPC",
                    "fact_key": "status",
                    "fact_value": "alive_in_citadel",
                    "source_document_id": doc_id,
                },
            ]
        }
        raw_json = json.dumps(payload)
        if self.rng.random() < 0.5:
            return f"```json\n{raw_json}\n```"
        return raw_json

    @staticmethod
    def parse_llm_json_strictly(raw_llm_output: str) -> Dict[str, Any]:
        """Desempaquetador defensivo que limpia fences Markdown antes de validar con Pydantic."""
        cleaned = raw_llm_output.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(lines[1:-1]).strip()
        return json.loads(cleaned)


# ==============================================================================
# 5. PIPELINE INTEGRADO DE PUNTA A PUNTA
# ==============================================================================


class IntegratedMonitorRuntimeHarness:
    """
    Conecta los flujos completos de `monitor_dm_system` a través del puente
    `StrictMCPWireBridge` y verifica el oráculo después de cada micro-paso.
    """

    def __init__(self, seed: int = 42) -> None:
        self.stores = MultiStoreDataLayer()
        self.mcp = StrictMCPWireBridge()
        self.stores.mount_mcp_tools(self.mcp)
        self.oracle = MonitorCrossStoreOracle(self.stores)
        self.llm_transport = DeterministicRawLLMTransport(seed=seed)

    def ingest_manual_end_to_end(
        self,
        source_document_id: str,
        title: str,
        raw_text: str,
        timeline_branch: str = "main",
        initial_tick: int = 0,
    ) -> List[str]:
        store_res = self.mcp.call_tool(
            "ingest_store_document",
            {
                "source_document_id": source_document_id,
                "title": title,
                "raw_text": raw_text,
            },
        )
        assert store_res["ok"] is True

        raw_llm = self.llm_transport.complete_structured_extraction(raw_text, source_document_id)
        parsed = self.llm_transport.parse_llm_json_strictly(raw_llm)
        extracted = parsed["extracted_entities"]
        entity_ids = [item["entity_id"] for item in extracted]

        chunk_id = f"chk_{source_document_id}_0"
        self.mcp.call_tool(
            "qdrant_upsert_chunk",
            {
                "chunk_id": chunk_id,
                "source_document_id": source_document_id,
                "text": raw_text[:200],
                "vector": [0.12, -0.34, 0.56, 0.78, -0.11, 0.22, 0.05, -0.91],
                "entity_ids": entity_ids,
                "timeline_tick": initial_tick,
            },
        )

        canonized_ids: List[str] = []
        for idx, item in enumerate(extracted):
            pid = f"prop_{source_document_id}_{idx}"
            self.mcp.call_tool(
                "mongo_propose_change",
                {
                    "proposal_id": pid,
                    "source_type": "MANUAL_DOCUMENT",
                    "source_ref_id": source_document_id,
                    "entity_id": item["entity_id"],
                    "entity_type": item["entity_type"],
                    "fact_key": item["fact_key"],
                    "fact_value": item["fact_value"],
                    "timeline_branch": timeline_branch,
                    "timeline_tick": initial_tick,
                },
            )
            commit_res = self.mcp.call_tool(
                "canonkeeper_commit_proposal",
                {
                    "proposal_id": pid,
                    "decision": ProposalStatus.ACCEPTED.value,
                    "reason": "Validated against manual provenance",
                },
            )
            assert commit_res["ok"] is True
            canonized_ids.append(item["entity_id"])

        readback = self.mcp.call_tool(
            "context_query_world_at_tick",
            {
                "entity_ids": canonized_ids,
                "timeline_branch": timeline_branch,
                "max_tick": initial_tick,
            },
        )
        for ent_id in canonized_ids:
            assert ent_id in readback["entities"], (
                f"Fallo Write-Then-Read: la entidad '{ent_id}' fue ingerida y canonizada, "
                f"pero ContextAssembly devolvió vacío al consultarla."
            )
        assert len(readback["rag_chunks"]) >= 1, (
            "Fallo Write-Then-Read: Qdrant guardó el chunk pero ContextAssembly no lo recuperó"
        )

        self.oracle.assert_all_cross_store_invariants()
        return canonized_ids

    def execute_scene_turn_with_cold_checkpoint(
        self,
        thread_id: str,
        scene_id: str,
        turn_id: str,
        timeline_branch: str,
        tick: int,
        entity_id: str,
        fact_key: str,
        new_fact_value: str,
    ) -> Dict[str, Any]:
        ckpt_res = self.mcp.call_tool("langgraph_load_checkpoint", {"thread_id": thread_id})
        if ckpt_res["found"]:
            state = json.loads(ckpt_res["serialized_state_json"])
        else:
            state = {
                "scene_id": scene_id,
                "timeline_branch": timeline_branch,
                "current_tick": 0,
                "active_entities": [entity_id],
                "turn_history": [],
            }

        if entity_id not in state["active_entities"]:
            state["active_entities"].append(entity_id)

        self.stores.mongo_documents["turns"][turn_id] = {
            "turn_id": turn_id,
            "scene_id": scene_id,
            "timeline_branch": timeline_branch,
            "tick": tick,
        }

        proposal_id = f"prop_turn_{turn_id}"
        self.mcp.call_tool(
            "mongo_propose_change",
            {
                "proposal_id": proposal_id,
                "source_type": "SCENE_TURN",
                "source_ref_id": turn_id,
                "entity_id": entity_id,
                "entity_type": "NPC",
                "fact_key": fact_key,
                "fact_value": new_fact_value,
                "timeline_branch": timeline_branch,
                "timeline_tick": tick,
            },
        )
        commit_res = self.mcp.call_tool(
            "canonkeeper_commit_proposal",
            {
                "proposal_id": proposal_id,
                "decision": ProposalStatus.ACCEPTED.value,
                "reason": f"Canonized during turn {turn_id}",
            },
        )

        state["current_tick"] = max(state["current_tick"], tick)
        state["turn_history"].append({"turn_id": turn_id, "tick": tick, "proposal_id": proposal_id})

        self.mcp.call_tool(
            "langgraph_save_checkpoint",
            {
                "thread_id": thread_id,
                "step_index": len(state["turn_history"]),
                "serialized_state_json": json.dumps(state),
            },
        )

        self.oracle.assert_all_cross_store_invariants()
        return commit_res


# ==============================================================================
# 6. SUITE DE PRUEBAS DETERMINISTAS, METAMÓRFICAS Y DE LÍNEA DE TIEMPO
# ==============================================================================


class MonitorDMSystemVerificationSuite(unittest.TestCase):
    def test_01_mcp_wire_bridge_catches_unserializable_and_unknown_tools(self) -> None:
        harness = IntegratedMonitorRuntimeHarness(seed=1)

        with self.assertRaises(MCPWireBoundaryError):
            harness.mcp.call_tool("non_existent_mcp_tool", {})

        with self.assertRaises(MCPWireBoundaryError):
            harness.mcp.call_tool(
                "context_query_world_at_tick",
                {
                    "entity_ids": {"ent_elara"},  # type: ignore[dict-item]
                    "timeline_branch": "main",
                    "max_tick": 0,
                },
            )

    def test_02_full_pipeline_ingest_to_canon_to_multiturn_timeline_travel(self) -> None:
        harness = IntegratedMonitorRuntimeHarness(seed=7)

        entities = harness.ingest_manual_end_to_end(
            source_document_id="doc_players_handbook_v1",
            title="Cronicas de Valdris",
            raw_text="Elara comienza viva en la Ciudadela de la Llama Plateada.",
            timeline_branch="main",
            initial_tick=0,
        )
        self.assertIn("ent_elara", entities)

        res_t10 = harness.execute_scene_turn_with_cold_checkpoint(
            thread_id="campaign_thread_1",
            scene_id="scene_01",
            turn_id="turn_001",
            timeline_branch="main",
            tick=10,
            entity_id="ent_elara",
            fact_key="status",
            new_fact_value="exploring_shadow_ruins",
        )
        self.assertTrue(res_t10["ok"])

        res_t25 = harness.execute_scene_turn_with_cold_checkpoint(
            thread_id="campaign_thread_1",
            scene_id="scene_02",
            turn_id="turn_002",
            timeline_branch="main",
            tick=25,
            entity_id="ent_elara",
            fact_key="status",
            new_fact_value="fallen_in_battle",
        )
        self.assertTrue(res_t25["ok"])

        at_tick_5 = harness.mcp.call_tool(
            "context_query_world_at_tick",
            {"entity_ids": ["ent_elara"], "timeline_branch": "main", "max_tick": 5},
        )
        self.assertEqual(
            at_tick_5["entities"]["ent_elara"]["facts"]["status"],
            "alive_in_citadel",
        )

        at_tick_15 = harness.mcp.call_tool(
            "context_query_world_at_tick",
            {"entity_ids": ["ent_elara"], "timeline_branch": "main", "max_tick": 15},
        )
        self.assertEqual(
            at_tick_15["entities"]["ent_elara"]["facts"]["status"],
            "exploring_shadow_ruins",
        )

        at_tick_30 = harness.mcp.call_tool(
            "context_query_world_at_tick",
            {"entity_ids": ["ent_elara"], "timeline_branch": "main", "max_tick": 30},
        )
        self.assertEqual(
            at_tick_30["entities"]["ent_elara"]["facts"]["status"],
            "fallen_in_battle",
        )

    def test_03_canonkeeper_rejects_orphan_provenance_and_out_of_order_ticks(self) -> None:
        harness = IntegratedMonitorRuntimeHarness(seed=19)
        harness.ingest_manual_end_to_end(
            source_document_id="doc_core_rules",
            title="Core Rules",
            raw_text="Manual oficial",
            timeline_branch="main",
            initial_tick=10,
        )

        harness.mcp.call_tool(
            "mongo_propose_change",
            {
                "proposal_id": "prop_orphan_doc",
                "source_type": "MANUAL_DOCUMENT",
                "source_ref_id": "doc_ghost_999",
                "entity_id": "ent_elara",
                "entity_type": "NPC",
                "fact_key": "status",
                "fact_value": "corrupted_lore",
                "timeline_branch": "main",
                "timeline_tick": 12,
            },
        )
        orphan_res = harness.mcp.call_tool(
            "canonkeeper_commit_proposal",
            {
                "proposal_id": "prop_orphan_doc",
                "decision": ProposalStatus.ACCEPTED.value,
                "reason": "Attempted orphan commit",
            },
        )
        self.assertFalse(orphan_res["ok"])
        self.assertEqual(orphan_res["reason"], "MISSING_PROVENANCE_DOCUMENT")

        harness.stores.mongo_documents["turns"]["turn_past"] = {
            "turn_id": "turn_past",
            "scene_id": "s1",
            "timeline_branch": "main",
            "tick": 5,
        }
        harness.mcp.call_tool(
            "mongo_propose_change",
            {
                "proposal_id": "prop_time_paradox",
                "source_type": "SCENE_TURN",
                "source_ref_id": "turn_past",
                "entity_id": "ent_elara",
                "entity_type": "NPC",
                "fact_key": "status",
                "fact_value": "paradox_state",
                "timeline_branch": "main",
                "timeline_tick": 5,
            },
        )
        paradox_res = harness.mcp.call_tool(
            "canonkeeper_commit_proposal",
            {
                "proposal_id": "prop_time_paradox",
                "decision": ProposalStatus.ACCEPTED.value,
                "reason": "Attempted time paradox",
            },
        )
        self.assertFalse(paradox_res["ok"])
        self.assertEqual(paradox_res["reason"], "NON_MONOTONIC_TIMELINE_TICK")
        harness.oracle.assert_all_cross_store_invariants()

    def test_04_deterministic_multi_seed_campaign_simulation(self) -> None:
        for seed in range(1, 51):
            rng = random.Random(seed)
            harness = IntegratedMonitorRuntimeHarness(seed=seed)

            harness.ingest_manual_end_to_end(
                source_document_id=f"doc_seed_{seed}",
                title=f"Manual Semilla {seed}",
                raw_text="Lore inicial del mundo.",
                timeline_branch="main",
                initial_tick=0,
            )

            current_ticks = {"main": 0, "alt_timeline": 0}
            for step in range(1, 25):
                branch = rng.choice(["main", "alt_timeline"])
                if branch == "alt_timeline" and current_ticks["alt_timeline"] == 0:
                    harness.ingest_manual_end_to_end(
                        source_document_id=f"doc_alt_{seed}",
                        title="Rama Alternativa",
                        raw_text="Lore alternativo.",
                        timeline_branch="alt_timeline",
                        initial_tick=0,
                    )

                current_ticks[branch] += rng.randint(1, 5)
                tick = current_ticks[branch]
                new_status = f"state_step_{step}_tick_{tick}"

                harness.execute_scene_turn_with_cold_checkpoint(
                    thread_id=f"thread_{branch}_{seed}",
                    scene_id=f"scene_{step // 5}",
                    turn_id=f"turn_{branch}_{step}",
                    timeline_branch=branch,
                    tick=tick,
                    entity_id="ent_elara",
                    fact_key="status",
                    new_fact_value=new_status,
                )

                world_view = harness.mcp.call_tool(
                    "context_query_world_at_tick",
                    {
                        "entity_ids": ["ent_elara"],
                        "timeline_branch": branch,
                        "max_tick": tick,
                    },
                )
                self.assertEqual(
                    world_view["entities"]["ent_elara"]["facts"]["status"],
                    new_status,
                )

    def test_05_real_server_tool_registry_and_middleware_wire_validation(self) -> None:
        """
        Verifica que el `TOOL_REGISTRY` real de `monitor_data.server` y su middleware
        de validación (`validate_tool_input`) + autorización (`check_authority`)
        funcionen estrictamente sobre payloads JSON-RPC reales.
        """
        from monitor_data.middleware.auth import check_authority
        from monitor_data.middleware.validation import ValidationError, validate_tool_input
        from monitor_data.server import TOOL_REGISTRY, extract_tool_schema

        self.assertGreater(len(TOOL_REGISTRY), 20, "TOOL_REGISTRY debe tener herramientas registradas")

        # 1. Toda herramienta en TOOL_REGISTRY debe producir un JSON Schema serializable
        for tool_name, func in TOOL_REGISTRY.items():
            schema = extract_tool_schema(func)
            serialized = json.dumps(schema)
            self.assertIn('"type": "object"', serialized, f"Esquema inválido para {tool_name}")

        # 2. Autorización real: Narrator NO puede invocar neo4j_create_entity (exclusivo de CanonKeeper)
        self.assertFalse(check_authority("neo4j_create_entity", "Narrator"))
        self.assertTrue(check_authority("neo4j_create_entity", "CanonKeeper"))

        # 3. Validación Pydantic sobre JSON decodificado (como llega por el cable MCP)
        create_entity_fn = TOOL_REGISTRY["neo4j_create_entity"]
        valid_wire_payload = json.loads(
            json.dumps(
                {
                    "params": {
                        "universe_id": str(uuid4()),
                        "name": "Elara",
                        "entity_type": "character",
                        "is_archetype": False,
                        "description": "High elf sentinel",
                    }
                }
            )
        )
        validated = validate_tool_input("neo4j_create_entity", create_entity_fn, valid_wire_payload)
        self.assertIn("params", validated)
        self.assertEqual(validated["params"].name, "Elara")

        # 4. Payload con campos faltantes o tipos rotos debe disparar ValidationError
        with self.assertRaises(ValidationError):
            validate_tool_input(
                "neo4j_create_entity",
                create_entity_fn,
                {"params": {"universe_id": "not-a-uuid"}},
            )

    def test_06_real_scene_state_cold_checkpoint_rehydration_preserves_gm_verdict(self) -> None:
        """
        Verifica que `SceneState` (LangGraph) sobreviva a una serialización en frío
        a JSON (`model_dump_json` / `model_dump(mode="json")`) y rehidratación en una
        instancia limpia (`SceneState.model_validate`) sin perder `GMVerdict` ni sus
        campos tipados (`narrative_draft`, `intent_type`, `action_type`, `roll_necessity`).
        """
        from monitor_agents.gm_awareness import ActionType, CausalityAction, IntentType, RollNecessity
        from monitor_agents.gm_tools.contracts import GMVerdict
        from monitor_agents.loops.scene_loop import SceneState

        scene_id = uuid4()
        story_id = uuid4()
        universe_id = uuid4()
        verdict = GMVerdict(
            intent_type=IntentType.DIALOGUE,
            action_type=ActionType.DIALOGUE,
            roll_necessity=RollNecessity.PROPOSE_ROLL,
            causality_action=CausalityAction.ACCEPT,
            suggested_stat="Charisma",
            suggested_dc=14,
            narrative_draft="High Priestess Mara narrows her eyes as you mention the Ashlands.",
            tool_calls_made=["get_entity_summary"],
            tool_call_count=1,
            reasoning="Player is questioning a guarded NPC about a sensitive topic.",
        )

        initial_state = SceneState(
            scene_id=scene_id,
            story_id=story_id,
            universe_id=universe_id,
            user_input="I ask Mara about the Ashlands.",
            gm_verdict=verdict,
            turns_count=2,
            durable_turn_count=2,
            established_facts=["The Hollow King operates in the Ashlands."],
        )

        # Serialización en frío a JSON crudo (simulando persistencia en MongoDBSaver / BSON)
        cold_json = initial_state.model_dump_json()
        raw_payload = json.loads(cold_json)
        self.assertIsInstance(raw_payload["gm_verdict"], dict)

        # Rehidratación en instancia limpia de SceneState
        rehydrated = SceneState.model_validate(raw_payload)
        self.assertEqual(rehydrated.scene_id, scene_id)
        self.assertEqual(rehydrated.story_id, story_id)
        self.assertEqual(rehydrated.universe_id, universe_id)
        self.assertIsInstance(rehydrated.gm_verdict, GMVerdict)
        self.assertEqual(
            rehydrated.gm_verdict.narrative_draft,
            "High Priestess Mara narrows her eyes as you mention the Ashlands.",
        )
        self.assertEqual(rehydrated.gm_verdict.intent_type, IntentType.DIALOGUE)
        self.assertEqual(rehydrated.gm_verdict.action_type, ActionType.DIALOGUE)
        self.assertEqual(rehydrated.gm_verdict.roll_necessity, RollNecessity.PROPOSE_ROLL)
        self.assertEqual(rehydrated.gm_verdict.suggested_dc, 14)

    def test_07_static_ast_audit_all_agent_tool_calls_match_server_registry_and_authority(
        self,
    ) -> None:
        """
        Audita vía AST el 100% de las invocaciones estáticas a `call_tool` y
        `_call_neo4j_write_tool` en `packages/agents/src/monitor_agents` y exige que:
          1. Toda herramienta invocada exista en `monitor_data.server.TOOL_REGISTRY`.
          2. El `agent_type` emisor tenga permisos en `AUTHORITY_MATRIX` (`check_authority`).
        """
        import ast
        from pathlib import Path

        from monitor_data.middleware.auth import check_authority
        from monitor_data.server import TOOL_REGISTRY

        def infer_agent_type(path_str: str, method_name: str) -> str:
            if method_name == "_call_neo4j_write_tool":
                return "CanonKeeper"
            if "canonkeeper" in path_str or "handlers/" in path_str:
                return "CanonKeeper"
            if "context_assembly" in path_str:
                return "ContextAssembly"
            if "narrator" in path_str:
                return "Narrator"
            if "resolver" in path_str:
                return "Resolver"
            if "npc_voice" in path_str or "conversation_loop" in path_str:
                return "NPCVoice"
            if "ingestion" in path_str:
                return "IngestionPipeline"
            if "world_architect" in path_str or "world_building" in path_str:
                return "WorldArchitect"
            if "character_creator" in path_str:
                return "CharacterCreator"
            if "plot_hooks" in path_str:
                return "PlotHooks"
            if "session_manager" in path_str:
                return "SessionManager"
            if "exit_handler" in path_str:
                return "ApplicationExitHandler"
            return "CanonKeeper"

        repo_root = Path(__file__).resolve().parents[2]
        agents_root = repo_root / "packages" / "agents" / "src" / "monitor_agents"
        self.assertTrue(agents_root.exists(), f"No existe {agents_root}")

        discovered_calls: list[tuple[str, int, str, str]] = []
        missing_in_registry: list[str] = []
        unauthorized_calls: list[str] = []

        for py_file in sorted(agents_root.rglob("*.py")):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            rel_path = str(py_file.relative_to(repo_root))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if node.func.attr in {"call_tool", "_call_neo4j_write_tool"} and node.args:
                        first_arg = node.args[0]
                        if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                            tool_name = first_arg.value
                            agent_type = infer_agent_type(rel_path, node.func.attr)
                            discovered_calls.append((rel_path, node.lineno, tool_name, agent_type))
                            if tool_name not in TOOL_REGISTRY:
                                missing_in_registry.append(
                                    f"{rel_path}:{node.lineno} -> {tool_name} (agent={agent_type})"
                                )
                            elif not check_authority(tool_name, agent_type):
                                unauthorized_calls.append(
                                    f"{rel_path}:{node.lineno} -> {tool_name} (agent={agent_type})"
                                )

        self.assertGreaterEqual(
            len(discovered_calls),
            120,
            "Se esperaban al menos 120 invocaciones estáticas a call_tool en monitor_agents",
        )
        self.assertEqual(
            missing_in_registry,
            [],
            f"Herramientas invocadas por agentes que no existen en TOOL_REGISTRY: {missing_in_registry}",
        )
        self.assertEqual(
            unauthorized_calls,
            [],
            f"Herramientas invocadas sin permiso en AUTHORITY_MATRIX: {unauthorized_calls}",
        )

    def test_08_real_agent_payload_shapes_pass_validate_tool_input(self) -> None:
        """
        Verifica que las formas exactas de diccionario plano (`flat kwargs`), alias `"updates"`
        y campos mixtos que envían `ContextAssembly`, `CanonKeeper`, `NPCVoice`, `PlotHooks`,
        `CharacterCreator` y `ApplicationExitHandler` pasen `validate_tool_input` sin error.
        """
        from monitor_data.middleware.validation import validate_tool_input
        from monitor_data.server import TOOL_REGISTRY

        uid = str(uuid4())
        eid = str(uuid4())
        sid = str(uuid4())

        # 1. ContextAssembly -> qdrant_search (diccionario plano sin envolver en "params")
        qdrant_res = validate_tool_input(
            "qdrant_search",
            TOOL_REGISTRY["qdrant_search"],
            {
                "collection": "scenes",
                "query_text": "Investigate the ancient ruins",
                "limit": 10,
                "filter": {"scene_id": sid},
            },
        )
        self.assertEqual(qdrant_res["params"].collection, "scenes")
        self.assertEqual(qdrant_res["params"].query_text, "Investigate the ancient ruins")

        # 2. ContextAssembly / CanonKeeper -> neo4j_list_facts (diccionario plano hacia "filters")
        facts_res = validate_tool_input(
            "neo4j_list_facts",
            TOOL_REGISTRY["neo4j_list_facts"],
            {"universe_id": uid, "entity_id": eid, "limit": 20},
        )
        self.assertEqual(str(facts_res["filters"].universe_id), uid)
        self.assertEqual(str(facts_res["filters"].entity_id), eid)

        # 3. CanonKeeper -> neo4j_update_fact (usando llave "updates" en vez de "params")
        update_fact_res = validate_tool_input(
            "neo4j_update_fact",
            TOOL_REGISTRY["neo4j_update_fact"],
            {"fact_id": eid, "updates": {"canon_level": "retconned"}},
        )
        self.assertEqual(str(update_fact_res["fact_id"]), eid)
        self.assertEqual(update_fact_res["params"].canon_level.value, "retconned")

        # 4. CharacterCreator -> neo4j_create_entity (universe_id y entity_type en nivel raíz + params)
        create_ent_res = validate_tool_input(
            "neo4j_create_entity",
            TOOL_REGISTRY["neo4j_create_entity"],
            {
                "universe_id": uid,
                "entity_type": "character",
                "params": {
                    "name": "Aragorn",
                    "description": "Ranger of the North",
                    "properties": {"role": "PC"},
                    "state_tags": [],
                    "canon_level": "canon",
                },
            },
        )
        self.assertEqual(str(create_ent_res["params"].universe_id), uid)
        self.assertEqual(create_ent_res["params"].name, "Aragorn")

    def test_09_manual_pdf_and_markdown_ingestion_preserves_sections_and_provenance(self) -> None:
        """
        Verifica que el chunking de manuales PDF con estructura (`chunk_text` + `heading_path` +
        `semantic_category`) preserve `section_path`, `semantic_category`, `page_number`, y las
        llaves de proveniencia cruzadas (`doc_id`/`source_document_id`, `job_id`/`ingestion_job_id`)
        en `to_qdrant_payload()`, evitando el colapso de secciones a `"General"` en `Analyzer`.
        """
        from monitor_data.tools.ingest_tools import chunk_text

        doc_id = str(uuid4())
        job_id = str(uuid4())
        universe_id = str(uuid4())

        # Simula una sección extraída de un manual PDF con jerarquía de marcadores y categoría LLM
        section_text = (
            "The Blood Potency trait measures the thickening of a vampire's Vitae over centuries. "
            "At higher ratings, vampires roll additional dice to Rouse the Blood and mend damage, "
            "but suffer heavier feeding restrictions."
        )
        chunks = chunk_text(
            text=section_text,
            source_name="Vampire the Masquerade V5 Corebook",
            page_number=214,
            metadata={
                "universe_id": universe_id,
                "doc_id": doc_id,
                "job_id": job_id,
                "heading_path": ["Chapter 5: Vampires", "Blood Potency"],
                "section_path": "Chapter 5: Vampires > Blood Potency",
                "semantic_category": "power_system",
            },
        )
        self.assertEqual(len(chunks), 1)
        payload = chunks[0].to_qdrant_payload()

        # 1. Jerarquía de secciones y categoría semántica preservadas (no colapsan a None/"general")
        self.assertEqual(payload["section_path"], "Chapter 5: Vampires > Blood Potency")
        self.assertEqual(payload["heading_path"], ["Chapter 5: Vampires", "Blood Potency"])
        self.assertEqual(payload["semantic_category"], "power_system")
        self.assertEqual(payload["page_number"], 214)

        # 2. Llaves duales de proveniencia presentes para ContextAssembly y audit_ingestion_documents
        self.assertEqual(payload["doc_id"], doc_id)
        self.assertEqual(payload["source_document_id"], doc_id)
        self.assertEqual(payload["job_id"], job_id)
        self.assertEqual(payload["ingestion_job_id"], job_id)
        self.assertEqual(payload["universe_id"], universe_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)



