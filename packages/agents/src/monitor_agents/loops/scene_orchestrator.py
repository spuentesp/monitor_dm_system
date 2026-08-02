import uuid
import logging
from typing import Any
from pydantic import BaseModel, ConfigDict

from langgraph.graph import StateGraph, START, END

from monitor_agents.loops.story_loop import StoryLoop
from monitor_agents.loops.scene_orchestrator_support import (
    _server_roll_from_pending,
    _resolved_roll_from_pending,
    _dice_request_from_resolution,
)
from monitor_agents.loops.scene_support import strip_entity_tags

from monitor_agents.llm_errors import LLMProviderUnavailable

logger = logging.getLogger(__name__)


class SceneOrchestratorState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: str
    user_content: str
    session: dict[str, Any]
    actor_context: dict[str, Any] | None = None

    # Callbacks from Layer 3 to avoid circular imports
    callbacks: Any

    # Core objects
    story_id: str | None = None
    scene_id: str | None = None
    agents_available: bool = True
    
    # Internal routing
    next_node: str = "evaluate_intent"

    # Dice/input variables
    scene_input: str = ""
    resolution_override: dict[str, Any] | None = None
    npc_target: str | None = None

    # Output
    response_text: str | None = None
    metadata: dict[str, Any] | None = None


async def evaluate_intent(state: SceneOrchestratorState) -> SceneOrchestratorState:
    session = state.session
    callbacks = state.callbacks

    # Phase transition
    if session.get("phase") == "ooc":
        session["phase"] = "active_play"
        session["updated_at"] = callbacks.now_iso()
        callbacks.db_save_session(session)
    
    # 1. Pending consequence choice
    if session.get("pending_consequence") and session["pending_consequence"].get("options"):
        state.next_node = "handle_pending_choice"
        return state

    # 2. OOC Question
    if callbacks.is_ooc_question(state.user_content):
        state.next_node = "handle_ooc"
        return state
        
    # 3. Active conversation
    if session.get("conversation_active"):
        if callbacks.is_end_conversation_command(state.user_content):
            state.next_node = "handle_end_conversation"
        else:
            state.next_node = "handle_conversation"
        return state
        
    # 4. End scene
    if callbacks.is_end_scene_command(state.user_content):
        state.next_node = "handle_end_scene"
        return state
        
    # 5. Recap
    if callbacks.is_recap_command(state.user_content):
        state.next_node = "handle_recap"
        return state
        
    # 6. Start conversation
    npc_target = callbacks.is_start_conversation_command(state.user_content)
    if npc_target:
        state.npc_target = npc_target
        state.next_node = "handle_start_conversation"
        return state
        
    # 7. Default to core scene loop
    state.next_node = "prepare_core_scene_loop"
    return state


async def handle_pending_choice(state: SceneOrchestratorState) -> SceneOrchestratorState:
    callbacks = state.callbacks
    result = await callbacks.resolve_pending_consequence_choice(
        state.session,
        state.user_content,
        save_session=callbacks.db_save_session,
        now_fn=callbacks.now_iso,
    )
    if result is not None:
        state.response_text, state.metadata = result
    else:
        # Fallback if somehow None was returned
        state.response_text = "Missing consequence options."
        state.metadata = {}
    return state


async def handle_ooc(state: SceneOrchestratorState) -> SceneOrchestratorState:
    callbacks = state.callbacks
    session = state.session
    answer = await callbacks.answer_ooc_question(
        session,
        state.user_content,
        session_game_system_doc=callbacks.session_game_system_doc,
        gsr_available=callbacks.gsr_available,
    )
    session["phase"] = "ooc"
    session["updated_at"] = callbacks.now_iso()
    callbacks.db_save_session(session)
    state.response_text = answer
    state.metadata = {
        "type": "ooc_answer",
        "phase": "ooc",
        "story_id": state.story_id,
        "scene_id": state.scene_id,
        "ooc": True,
    }
    return state


async def handle_end_conversation(state: SceneOrchestratorState) -> SceneOrchestratorState:
    callbacks = state.callbacks
    session = state.session
    session.pop("conversation_active", None)
    session.pop("conversation_npc_name", None)
    session.pop("conversation_npc_id", None)
    callbacks.pop_conversation_loop(state.session_id)
    session["updated_at"] = callbacks.now_iso()
    callbacks.db_save_session(session)
    state.response_text = "The conversation ends. The world resumes around you. What do you do?"
    state.metadata = {
        "type": "conversation_end",
        "phase": "active_play",
        "conversation_active": False,
        "story_id": state.story_id,
        "scene_id": state.scene_id,
    }
    return state


async def handle_conversation(state: SceneOrchestratorState) -> SceneOrchestratorState:
    callbacks = state.callbacks
    resp, meta = await callbacks.run_conversation_turn(
        state.session_id,
        state.user_content,
        state.session,
        db_save_session=callbacks.db_save_session,
    )
    state.response_text = resp
    state.metadata = meta
    return state


async def handle_end_scene(state: SceneOrchestratorState) -> SceneOrchestratorState:
    callbacks = state.callbacks
    resp, meta = await callbacks.run_end_scene(
        state.session_id,
        state.session,
        sessions=callbacks.sessions,
        messages=callbacks.messages,
        db_save_session=callbacks.db_save_session,
        db_load_messages=callbacks.db_load_messages,
        bootstrap_story_scene=callbacks.bootstrap_story_scene,
    )
    state.response_text = resp
    state.metadata = meta
    return state


async def handle_recap(state: SceneOrchestratorState) -> SceneOrchestratorState:
    callbacks = state.callbacks
    resp, meta = await callbacks.run_recap_command(state.session)
    state.response_text = resp
    state.metadata = meta
    return state


async def handle_start_conversation(state: SceneOrchestratorState) -> SceneOrchestratorState:
    callbacks = state.callbacks
    resp, meta = await callbacks.run_start_conversation(
        state.session_id,
        state.npc_target,
        state.session,
        db_save_session=callbacks.db_save_session,
    )
    state.response_text = resp
    state.metadata = meta
    return state


async def prepare_core_scene_loop(state: SceneOrchestratorState) -> SceneOrchestratorState:
    callbacks = state.callbacks
    session = state.session
    
    resolved_roll = _server_roll_from_pending(session, state.user_content) or _resolved_roll_from_pending(
        session, state.user_content
    )
    
    scene_input = state.user_content
    resolution_override = None
    
    if resolved_roll is not None:
        scene_input, resolution_override = resolved_roll
        session.pop("pending_dice_request", None)
        session["updated_at"] = callbacks.now_iso()
        callbacks.db_save_session(session)
    elif session.get("pending_dice_request"):
        session.pop("pending_dice_request", None)
        session["updated_at"] = callbacks.now_iso()
        callbacks.db_save_session(session)
        
    if (not state.scene_id or not state.story_id) and session.get("universe_id"):
        state.story_id, state.scene_id, _ = callbacks.bootstrap_story_scene(session)
        callbacks.db_save_session(session)
        
    state.scene_input = scene_input
    state.resolution_override = resolution_override
    
    return state


async def run_core_scene_loop(state: SceneOrchestratorState) -> SceneOrchestratorState:
    callbacks = state.callbacks
    session = state.session
    story_id = state.story_id
    scene_id = state.scene_id
    
    if not state.agents_available or not scene_id or not story_id:
        state.response_text = (
            "The narrative engine is standing by…\n\n"
            "*(Bind this session to a universe and opening scene to activate the live GM loop.)*"
        )
        state.metadata = {
            "agents_available": state.agents_available,
            "story_id": story_id,
            "scene_id": scene_id,
        }
        return state

    try:
        loop = callbacks.get_scene_loop(
            state.session_id,
            session,
            scene_id=scene_id,
            story_id=story_id,
            actor_context=state.actor_context,
            chat_log=_chat_log_for(callbacks, state.session_id),
        )
        if state.resolution_override is not None:
            result = await loop.run(
                user_input=state.scene_input,
                resolution_override=state.resolution_override,
            )
        else:
            result = await loop.run(user_input=state.scene_input)
    except Exception as exc:
        logger.exception("SceneLoop turn failed (session=%s): %s", state.session_id, exc)
        if LLMProviderUnavailable is not None and isinstance(exc, LLMProviderUnavailable):
            state.response_text = exc.user_message
            state.metadata = {
                "type": "llm_provider_error",
                "error_class": exc.info.error_class.value,
                "agents_available": state.agents_available,
                "story_id": story_id,
                "scene_id": scene_id,
                "error": exc.user_message,
            }
            return state
        state.response_text = "*(The GM is gathering their thoughts — try again in a moment.)*"
        state.metadata = {
            "agents_available": state.agents_available,
            "story_id": story_id,
            "scene_id": scene_id,
            "error": str(exc),
        }
        return state

    narrative = strip_entity_tags(result.get("narrative_text") or "") or "…"
    resolution = result.get("resolution") or {}
    
    metadata = {
        "type": "scene_turn",
        "degraded": result.get("degraded"),
        "phase": session.get("phase", "active_play"),
        "resolution_type": resolution.get("resolution_type"),
        "intent_type": resolution.get("intent_type"),
        "success_level": resolution.get("success_level"),
        "roll_breakdown": resolution.get("roll_breakdown"),
        "roll_detail": resolution.get("roll_detail"),
        "stat": resolution.get("stat"),
        "difficulty_class": resolution.get("difficulty_class"),
        "effects": resolution.get("effects", []),
        "risk_preview": resolution.get("risk_preview"),
        "consequence_options": resolution.get("consequence_options", []),
        "requires_player_choice": resolution.get("requires_player_choice", False),
        "narrative_pressure": resolution.get("narrative_pressure"),
        "suggested_actions": result.get("suggested_actions", []),
        "image_suggestions": result.get("image_suggestions", []),
        "turn_id": result.get("turn_id"),
        "resolution_id": result.get("resolution_id"),
        "working_state": result.get("working_state", {}),
        "scene_checkpoint": result.get("scene_checkpoint", {}),
        "social_read": result.get("social_read", {}),
        "relationship_snapshot": result.get("relationship_snapshot", {}),
        "turns_count": result.get("turns_count", 0),
        "story_id": story_id,
        "scene_id": scene_id,
    }

    dice_request = _dice_request_from_resolution(resolution, state.user_content)
    if dice_request:
        metadata["dice_request"] = dice_request
        session["pending_dice_request"] = {
            **dice_request,
            "scene_id": scene_id,
            "story_id": story_id,
            "turn_id": result.get("turn_id"),
            "created_at": callbacks.now_iso(),
        }
        session["updated_at"] = callbacks.now_iso()
        callbacks.db_save_session(session)
        
    if metadata.get("working_state"):
        session["latest_working_state"] = metadata["working_state"]
    if metadata.get("scene_checkpoint"):
        session["latest_scene_checkpoint"] = metadata["scene_checkpoint"]
    if metadata.get("social_read"):
        session["latest_social_read"] = metadata["social_read"]
    if metadata.get("relationship_snapshot"):
        session["latest_relationship_snapshot"] = metadata["relationship_snapshot"]

    if metadata["requires_player_choice"] and metadata["consequence_options"]:
        session["pending_consequence"] = {
            "turn_id": metadata.get("turn_id"),
            "resolution_id": metadata.get("resolution_id"),
            "options": list(metadata.get("consequence_options", [])),
            "risk_preview": metadata.get("risk_preview"),
            "created_at": callbacks.now_iso(),
        }
        session["updated_at"] = callbacks.now_iso()
        callbacks.db_save_session(session)
        metadata["awaiting_consequence_choice"] = True
    else:
        pending_cleared = session.pop("pending_consequence", None) is not None
        if metadata.get("working_state") or metadata.get("scene_checkpoint") or pending_cleared:
            session["updated_at"] = callbacks.now_iso()
            callbacks.db_save_session(session)

    # Handle scene completion and world advancement
    if result.get("scene_complete") and story_id and state.agents_available and StoryLoop is not None:
        try:
            story_loop = StoryLoop(
                story_id=uuid.UUID(story_id),
                universe_id=uuid.UUID(session["universe_id"]),
            )
            story_result = await story_loop.complete_current_scene(
                scene_id=uuid.UUID(scene_id),
                outcome=result,
            )

            if story_result.get("current_scene_id"):
                session["scene_id"] = str(story_result["current_scene_id"])
                metadata["next_scene_id"] = str(story_result["current_scene_id"])
                metadata["scene_transition"] = True

            if story_result.get("story_complete"):
                session["phase"] = "completed"
                metadata["story_complete"] = True

            callbacks.db_save_session(session)
        except Exception as exc:
            logger.warning("Failed to advance StoryLoop: %s", exc)

    if story_id and state.agents_available and getattr(callbacks, "get_story_state", None):
        try:
            story_state = await callbacks.get_story_state(uuid.UUID(story_id))
            if story_state:
                in_game_time = getattr(story_state, "in_game_time", None)
                metadata["arc_label"] = getattr(story_state, "arc_label", None)
                metadata["tension_score"] = getattr(story_state, "tension_score", None)
                metadata["active_threads"] = getattr(story_state, "active_threads", None)
                if getattr(callbacks, "set_story_state_cache", None):
                    callbacks.set_story_state_cache(story_id, {
                        "story_id": str(getattr(story_state, "story_id", "")),
                        "universe_id": str(getattr(story_state, "universe_id", "")),
                        "arc_label": getattr(story_state, "arc_label", None),
                        "tension_score": getattr(story_state, "tension_score", None),
                        "active_threads": getattr(story_state, "active_threads", None),
                        "completed_threads": getattr(story_state, "completed_threads", None),
                        "in_game_time": in_game_time.isoformat() if in_game_time is not None else None,
                        "world_ticks": getattr(story_state, "world_ticks", None),
                        "scenes_completed": getattr(story_state, "scenes_completed", None),
                    })
        except Exception as exc:
            logger.debug("Failed to fetch story state for metadata: %s", exc)

    state.response_text = narrative
    state.metadata = metadata
    return state


def route_intent(state: SceneOrchestratorState) -> str:
    return state.next_node


def _chat_log_for(callbacks: Any, session_id: str) -> list[Any] | None:
    """Live chat message list for a session via UI-provided callbacks."""
    try:
        messages = getattr(callbacks, "messages", None)
        if isinstance(messages, dict):
            log = messages.get(session_id)
            if isinstance(log, list):
                return log
        loader = getattr(callbacks, "db_load_messages", None)
        if callable(loader):
            loaded = loader(session_id)
            return loaded if isinstance(loaded, list) else None
    except Exception:
        return None
    return None


class SceneOrchestrator:
    def __init__(self) -> None:
        builder = StateGraph(SceneOrchestratorState)
        builder.add_node("evaluate_intent", evaluate_intent)
        builder.add_node("handle_pending_choice", handle_pending_choice)
        builder.add_node("handle_ooc", handle_ooc)
        builder.add_node("handle_end_conversation", handle_end_conversation)
        builder.add_node("handle_conversation", handle_conversation)
        builder.add_node("handle_end_scene", handle_end_scene)
        builder.add_node("handle_recap", handle_recap)
        builder.add_node("handle_start_conversation", handle_start_conversation)
        builder.add_node("prepare_core_scene_loop", prepare_core_scene_loop)
        builder.add_node("run_core_scene_loop", run_core_scene_loop)

        builder.add_edge(START, "evaluate_intent")
        builder.add_conditional_edges(
            "evaluate_intent",
            route_intent,
            {
                "handle_pending_choice": "handle_pending_choice",
                "handle_ooc": "handle_ooc",
                "handle_end_conversation": "handle_end_conversation",
                "handle_conversation": "handle_conversation",
                "handle_end_scene": "handle_end_scene",
                "handle_recap": "handle_recap",
                "handle_start_conversation": "handle_start_conversation",
                "prepare_core_scene_loop": "prepare_core_scene_loop",
            }
        )

        builder.add_edge("handle_pending_choice", END)
        builder.add_edge("handle_ooc", END)
        builder.add_edge("handle_end_conversation", END)
        builder.add_edge("handle_conversation", END)
        builder.add_edge("handle_end_scene", END)
        builder.add_edge("handle_recap", END)
        builder.add_edge("handle_start_conversation", END)
        builder.add_edge("prepare_core_scene_loop", "run_core_scene_loop")
        builder.add_edge("run_core_scene_loop", END)

        self.graph = builder.compile()

    async def run(self, state_dict: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        initial_state = SceneOrchestratorState(**state_dict)
        result_state = await self.graph.ainvoke(initial_state)
        # LangGraph typically returns a dict when invoked with a dict, but when invoked with BaseModel 
        # it might return dict or BaseModel depending on config. Let's handle both.
        if isinstance(result_state, dict):
            return result_state.get("response_text") or "", result_state.get("metadata") or {}
        return result_state.response_text or "", result_state.metadata or {}
