"""
Prompt management router — inspect, override, and test DSPy prompt modules.

Provides a UI-facing API to:
  - List all registered DSPy signature modules across agents
  - Read signature instructions and field descriptions
  - Save instruction overrides (persisted in PostgreSQL system_config)
  - Run a live test call against the configured LLM and capture the raw prompt

Overrides are stored in the system_config table with key format:
  prompt_override:<module_id>
Value is a JSON object: {"instructions": "...", "updated_at": "..."}

Note: In v1, overrides only affect UI test runs. To apply them in production
modules a future step would inject them at module init time via dspy_runtime.
"""

from __future__ import annotations

import json
import textwrap
import time
from datetime import UTC, datetime
from typing import Any

import dspy
from fastapi import APIRouter, HTTPException
from monitor_data.db.postgres import get_postgres_client
from pydantic import BaseModel

router = APIRouter()

# ---------------------------------------------------------------------------
# Import DSPy signatures (best-effort — agents optional dep)
# ---------------------------------------------------------------------------

_AGENTS_AVAILABLE = False

try:
    from monitor_agents.dspy_runtime import get_dspy_lm

    # TurnIntentSignature removed — deprecated. Resolver handles intent classification.
    from monitor_agents.analyzer.analyzer import (
        AxiomExtractionSignature,
        EntityExtractionSignature,
        GameSystemDetectionSignature,
        LoreFactExtractionSignature,
    )
    from monitor_agents.canonkeeper.canonkeeper import (
        CanonKeeperReasoningSignature,
        PolicyCheckSignature,
    )
    from monitor_agents.context_assembly.context_assembly import QueryFormulationSignature
    from monitor_agents.narrator.narrator import (
        ContextAssemblySignature,
        NarratorSignature,
    )
    from monitor_agents.npc_voice.npc_voice import (
        NPCActorSignature,
        NPCDirectVoiceSignature,
    )
    from monitor_data.schemas.llm_config import ModelRole

    _AGENTS_AVAILABLE = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Static registry of all DSPy prompt modules
# ---------------------------------------------------------------------------

_REGISTRY: list[dict[str, Any]] = []

if _AGENTS_AVAILABLE:
    _REGISTRY = [
        {
            "module_id": "narrator.turn_narrative",
            "agent": "Narrator",
            "label": "Turn Narrative",
            "description": "Generates vivid GM prose for each player turn",
            "signature": NarratorSignature,
            "predictor_type": "ChainOfThought",
            "llm_node": "narrator",
            "llm_role": "heavy",
        },
        {
            "module_id": "narrator.context_assembly",
            "agent": "Narrator",
            "label": "Context Assembly",
            "description": "Ranks and compresses scene context before narration",
            "signature": ContextAssemblySignature,
            "predictor_type": "ChainOfThought",
            "llm_node": "context_assembly",
            "llm_role": "standard",
        },
        {
            "module_id": "canonkeeper.reasoning",
            "agent": "CanonKeeper",
            "label": "Canon Consistency Reasoning",
            "description": "Reasons about whether a proposed world-state change is canon-consistent",
            "signature": CanonKeeperReasoningSignature,
            "predictor_type": "ChainOfThought",
            "llm_node": "canonkeeper",
            "llm_role": "heavy",
        },
        {
            "module_id": "canonkeeper.policy_check",
            "agent": "CanonKeeper",
            "label": "Policy Check",
            "description": "Fast gate that detects hard policy violations before full reasoning",
            "signature": PolicyCheckSignature,
            "predictor_type": "Predict",
            "llm_node": "canonkeeper",
            "llm_role": "light",
        },
        {
            "module_id": "context_assembly.query_formulation",
            "agent": "ContextAssembly",
            "label": "Query Formulation",
            "description": "Generates optimised semantic retrieval queries from a player action",
            "signature": QueryFormulationSignature,
            "predictor_type": "Predict",
            "llm_node": "context_assembly",
            "llm_role": "light",
        },
        # Turn intent classification removed — deprecated.
        # Resolver._infer_intent_type() handles this with fast heuristics.
        {
            "module_id": "analyzer.axiom_extraction",
            "agent": "Analyzer",
            "label": "Axiom Extraction",
            "description": "Extracts ontological world truths from ingested source text",
            "signature": AxiomExtractionSignature,
            "predictor_type": "ChainOfThought",
            "llm_node": "indexer",
            "llm_role": "standard",
        },
        {
            "module_id": "analyzer.entity_extraction",
            "agent": "Analyzer",
            "label": "Entity Archetype Extraction",
            "description": "Identifies entity types and archetypes in source text",
            "signature": EntityExtractionSignature,
            "predictor_type": "ChainOfThought",
            "llm_node": "indexer",
            "llm_role": "standard",
        },
        {
            "module_id": "analyzer.lore_extraction",
            "agent": "Analyzer",
            "label": "Lore Fact Extraction",
            "description": "Extracts canonical narrative facts from source text",
            "signature": LoreFactExtractionSignature,
            "predictor_type": "ChainOfThought",
            "llm_node": "indexer",
            "llm_role": "standard",
        },
        {
            "module_id": "analyzer.game_system_detection",
            "agent": "Analyzer",
            "label": "Game System Detection",
            "description": "Detects RPG game mechanics and ruleset structure in source text",
            "signature": GameSystemDetectionSignature,
            "predictor_type": "Predict",
            "llm_node": "indexer",
            "llm_role": "light",
        },
        {
            "module_id": "npc_voice.direct",
            "agent": "NPCVoice",
            "label": "Direct NPC Voice",
            "description": "Speaks in-character as an NPC in real-time player dialogue",
            "signature": NPCDirectVoiceSignature,
            "predictor_type": "Predict",
            "llm_node": "npc_voice",
            "llm_role": "light",
        },
        {
            "module_id": "npc_voice.actor",
            "agent": "NPCVoice",
            "label": "NPC Actor Reflection",
            "description": "NPC speaks as an actor analysing their role (GM prep / off-duty mode)",
            "signature": NPCActorSignature,
            "predictor_type": "ChainOfThought",
            "llm_node": "npc_actor",
            "llm_role": "light",
        },
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OVERRIDE_KEY_PREFIX = "prompt_override:"


def _get_entry(module_id: str) -> dict[str, Any]:
    for entry in _REGISTRY:
        if entry["module_id"] == module_id:
            return entry
    raise HTTPException(status_code=404, detail=f"Module '{module_id}' not found")


def _get_fields(sig_class: type) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Extract input and output fields from a DSPy Signature class."""
    inputs: list[dict[str, str]] = []
    outputs: list[dict[str, str]] = []
    # reason: DSPy signature — dspy.Signature subclasses use dynamic field typing mypy can't model
    for name, field in sig_class.model_fields.items():  # type: ignore
        extra = field.json_schema_extra or {}
        field_type = extra.get("__dspy_field_type", "input")
        desc = extra.get("desc", "")
        entry = {"name": name, "desc": desc}
        if field_type == "output":
            outputs.append(entry)
        else:
            inputs.append(entry)
    return inputs, outputs


def _default_instructions(sig_class: type) -> str:
    return textwrap.dedent(sig_class.__doc__ or "").strip()


async def _load_override(module_id: str) -> dict[str, Any] | None:
    postgres = get_postgres_client()
    raw = await postgres.config_get(f"{_OVERRIDE_KEY_PREFIX}{module_id}")
    if not raw:
        return None
    try:
        data = json.loads(raw)
        # Empty object {} means "deleted override"
        if "instructions" not in data:
            return None
        # reason: json.loads returns Any and the function returns dict[str, Any] | None; the `"instructions" not in data` guard narrows but mypy can't bridge the union without an explicit cast
        return data  # type: ignore
    except Exception:
        return None


async def _save_override(module_id: str, data: dict[str, Any]) -> None:
    postgres = get_postgres_client()
    await postgres.config_set(f"{_OVERRIDE_KEY_PREFIX}{module_id}", json.dumps(data))


_ROLE_MAP = {
    "heavy": "heavy",
    "standard": "standard",
    "light": "light",
}


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class FieldInfo(BaseModel):
    name: str
    desc: str


class PromptModuleSummary(BaseModel):
    module_id: str
    agent: str
    label: str
    description: str
    predictor_type: str  # "Predict" | "ChainOfThought"
    llm_node: str
    llm_role: str  # "light" | "standard" | "heavy"
    has_override: bool


class PromptModuleDetail(PromptModuleSummary):
    default_instructions: str
    current_instructions: str
    input_fields: list[FieldInfo]
    output_fields: list[FieldInfo]
    override_updated_at: str | None = None


class PromptOverrideUpdate(BaseModel):
    instructions: str


class PromptTestRequest(BaseModel):
    inputs: dict[str, str]
    use_override: bool = True


class PromptTestResult(BaseModel):
    ok: bool
    outputs: dict[str, str] = {}
    raw_prompt: str | None = None
    raw_response: str | None = None
    latency_ms: float | None = None
    error: str | None = None


class AgentsAvailability(BaseModel):
    available: bool
    module_count: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/status", response_model=AgentsAvailability)
async def agents_status() -> AgentsAvailability:
    """Check whether the agents package is available."""
    return AgentsAvailability(available=_AGENTS_AVAILABLE, module_count=len(_REGISTRY))


@router.get("", response_model=list[PromptModuleSummary])
async def list_modules() -> list[PromptModuleSummary]:
    """List all registered DSPy prompt modules with override status."""
    if not _AGENTS_AVAILABLE:
        return []

    postgres = get_postgres_client()
    result = []
    for entry in _REGISTRY:
        raw = await postgres.config_get(f"{_OVERRIDE_KEY_PREFIX}{entry['module_id']}")
        has_override = False
        if raw:
            try:
                parsed = json.loads(raw)
                has_override = "instructions" in parsed
            except Exception:
                pass

        result.append(
            PromptModuleSummary(
                module_id=entry["module_id"],
                agent=entry["agent"],
                label=entry["label"],
                description=entry["description"],
                predictor_type=entry["predictor_type"],
                llm_node=entry["llm_node"],
                llm_role=entry["llm_role"],
                has_override=has_override,
            )
        )
    return result


@router.get("/{module_id}", response_model=PromptModuleDetail)
async def get_module(module_id: str) -> PromptModuleDetail:
    """Get full details of a prompt module including fields and current instructions."""
    if not _AGENTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Agents package not available")

    entry = _get_entry(module_id)
    sig = entry["signature"]
    inputs, outputs = _get_fields(sig)
    default_instr = _default_instructions(sig)

    override = await _load_override(module_id)
    current_instr = override["instructions"] if override else default_instr

    return PromptModuleDetail(
        module_id=entry["module_id"],
        agent=entry["agent"],
        label=entry["label"],
        description=entry["description"],
        predictor_type=entry["predictor_type"],
        llm_node=entry["llm_node"],
        llm_role=entry["llm_role"],
        has_override=override is not None,
        default_instructions=default_instr,
        current_instructions=current_instr,
        input_fields=[FieldInfo(**f) for f in inputs],
        output_fields=[FieldInfo(**f) for f in outputs],
        override_updated_at=override.get("updated_at") if override else None,
    )


@router.put("/{module_id}", response_model=PromptModuleDetail)
async def update_module_instructions(module_id: str, body: PromptOverrideUpdate) -> PromptModuleDetail:
    """Save an instruction override for a prompt module."""
    if not _AGENTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Agents package not available")

    entry = _get_entry(module_id)
    default_instr = _default_instructions(entry["signature"])

    # If instructions match the default, treat as a reset
    if body.instructions.strip() == default_instr.strip():
        await _save_override(module_id, {})
    else:
        await _save_override(
            module_id,
            {
                "instructions": body.instructions,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )

    return await get_module(module_id)


@router.delete("/{module_id}/overrides", status_code=204)
async def reset_module_instructions(module_id: str) -> None:
    """Remove instruction override, reverting to source defaults."""
    if not _AGENTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Agents package not available")

    _get_entry(module_id)
    # Write {} (empty object) — _load_override treats this as "no override"
    await _save_override(module_id, {})


@router.post("/{module_id}/test", response_model=PromptTestResult)
async def test_module(module_id: str, body: PromptTestRequest) -> PromptTestResult:
    """
    Run a live test invocation of a DSPy module.

    Returns model outputs plus the raw prompt sent to the LLM and the latency.
    Note: this calls the configured LLM — tokens will be consumed.
    """
    if not _AGENTS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Agents package not available")

    entry = _get_entry(module_id)
    sig = entry["signature"]
    default_instr = _default_instructions(sig)

    # Determine which instructions to use
    instructions = default_instr
    if body.use_override:
        override = await _load_override(module_id)
        if override and override.get("instructions"):
            instructions = override["instructions"]

    # Build the active signature (with override if needed)
    if instructions.strip() != default_instr.strip():
        active_sig = sig.with_instructions(instructions)
    else:
        active_sig = sig

    # Build the predictor
    pred_cls = dspy.ChainOfThought if entry["predictor_type"] == "ChainOfThought" else dspy.Predict
    predictor = pred_cls(active_sig)

    t0 = time.perf_counter()

    try:
        # Resolve LLM and call under explicit context so we can read its history
        role_str = entry["llm_role"]
        role = (
            ModelRole.HEAVY if role_str == "heavy" else (ModelRole.LIGHT if role_str == "light" else ModelRole.STANDARD)
        )
        lm = get_dspy_lm(entry["llm_node"], role)

        with dspy.context(lm=lm):
            result = predictor(**body.inputs)

        elapsed_ms = (time.perf_counter() - t0) * 1000

        # Extract output fields (everything not in inputs and not internal)
        inputs_set = set(body.inputs.keys())
        outputs: dict[str, str] = {}
        for key in vars(result):
            if key.startswith("_") or key == "completions":
                continue
            if key in inputs_set:
                continue
            val = getattr(result, key, None)
            if val is not None:
                outputs[key] = str(val)

        # Capture raw prompt from LM history
        raw_prompt: str | None = None
        raw_response: str | None = None
        if hasattr(lm, "history") and lm.history:
            last = lm.history[-1]
            msgs = last.get("messages") or last.get("prompt")
            if isinstance(msgs, list):
                parts = []
                for m in msgs:
                    role_label = m.get("role", "").upper()
                    content = m.get("content", "")
                    if isinstance(content, list):
                        # Multi-part content (vision, etc.)
                        content = " ".join(c.get("text", "") for c in content if isinstance(c, dict))
                    parts.append(f"[{role_label}]\n{content}")
                raw_prompt = "\n\n---\n\n".join(parts)
            elif msgs:
                raw_prompt = str(msgs)

            resp = last.get("response") or last.get("outputs")
            if resp:
                raw_response = str(resp)

        return PromptTestResult(
            ok=True,
            outputs=outputs,
            raw_prompt=raw_prompt,
            raw_response=raw_response,
            latency_ms=round(elapsed_ms, 1),
        )

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return PromptTestResult(
            ok=False,
            error=str(exc),
            latency_ms=round(elapsed_ms, 1),
        )
