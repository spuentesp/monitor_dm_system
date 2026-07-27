"""
Preplay Orchestrator — LangGraph StateMachine for the pre-play lifecycle.

LAYER: 2 (agents)
"""
import logging
import re
import asyncio
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field
from langgraph.graph import StateGraph, END

from monitor_agents.loops.preplay_support import (
    is_ooc_question,
    answer_ooc_question,
    _generate_prologue,
    infer_character_name_from_text,
    persist_session_character,
    _seed_answers_from_persona,
    resolve_authored_session_zero_questions,
)

logger = logging.getLogger(__name__)

# Fallbacks for optional loops
try:
    from monitor_agents.loops.session_zero_loop import SessionZeroLoop, DEFAULT_MAX_QUESTIONS
    _SESSION_ZERO_AVAILABLE = True
except ImportError:
    _SESSION_ZERO_AVAILABLE = False

try:
    from monitor_agents.loops.character_creation_loop import CharacterCreationLoop
    _CHAR_CREATION_AVAILABLE = True
except ImportError:
    _CHAR_CREATION_AVAILABLE = False


class PreplayState(BaseModel):
    session_id: str
    user_content: str
    session_data: dict[str, Any]
    system_doc: dict[str, Any] | None = None
    gsr_available: bool = False
    
    # Internal routing
    next_step: str = "evaluate"
    
    # State tracking
    world_lore: list[str] = Field(default_factory=list)
    system_context: str = ""
    
    # Outputs
    response_text: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        arbitrary_types_allowed = True


# Global Loop Caches (same logic as before)
_CHAR_CREATION_LOOPS_MAX = 16
_CHAR_CREATION_LOOPS: dict[str, Any] = {}
_SESSION_ZERO_LOOPS_MAX = 16
_SESSION_ZERO_LOOPS: dict[str, Any] = {}


def _evict_oldest(cache: dict[str, Any], max_size: int) -> None:
    """Bound an insertion-ordered loop cache by evicting the oldest entries."""
    while len(cache) > max_size:
        cache.pop(next(iter(cache)))


def get_character_creation_loop(session_id: str, system_doc: Any) -> Any:
    if not _CHAR_CREATION_AVAILABLE or not system_doc:
        return None
    if session_id in _CHAR_CREATION_LOOPS:
        return _CHAR_CREATION_LOOPS[session_id]
    try:
        loop = CharacterCreationLoop(game_context=system_doc)
        _CHAR_CREATION_LOOPS[session_id] = loop
        _evict_oldest(_CHAR_CREATION_LOOPS, _CHAR_CREATION_LOOPS_MAX)
        return loop
    except Exception as exc:
        logger.debug("CharacterCreationLoop creation failed: %s", exc)
        return None


def get_session_zero_loop(
    session_id: str,
    session: dict[str, Any],
    world_lore: list[str],
    system_context: str,
    seed_answers: list[dict[str, str]] | None = None,
    ask_campaign_intent: bool = False,
    authored_questions: list[dict[str, Any]] | None = None,
) -> Any:
    if not _SESSION_ZERO_AVAILABLE:
        return None
    if session_id in _SESSION_ZERO_LOOPS:
        return _SESSION_ZERO_LOOPS[session_id]
    try:
        authored = list(authored_questions or [])
        # A curated set drives the interview: pin the budget to its count so
        # the LLM does not pad beyond what the curator authored.
        max_questions = len(authored) if authored else DEFAULT_MAX_QUESTIONS
        loop = SessionZeroLoop(
            tone=session.get("tone", "dramatic"),
            system_name=session.get("system_label") or "Unknown System",
            world_lore=world_lore,
            system_context=system_context,
            max_questions=max_questions,
            seed_answers=seed_answers,
            ask_campaign_intent=ask_campaign_intent,
            authored_questions=authored,
        )
        _SESSION_ZERO_LOOPS[session_id] = loop
        _evict_oldest(_SESSION_ZERO_LOOPS, _SESSION_ZERO_LOOPS_MAX)
        return loop
    except Exception as exc:
        logger.debug("SessionZeroLoop creation failed: %s", exc)
        return None


async def evaluate_intent(state: PreplayState) -> dict[str, Any]:
    """Determine which phase or sub-loop to route to."""
    session = state.session_data
    phase = session.get("phase", "awaiting_character")
    
    if is_ooc_question(state.user_content):
        return {"next_step": "handle_ooc"}
        
    if phase in {"awaiting_character", "char_creation", "session_zero"}:
        session["pending_character_concept"] = state.user_content

    if phase == "session_zero":
        return {"next_step": "handle_session_zero"}
    elif phase == "char_creation":
        return {"next_step": "handle_char_creation"}
    else:
        return {"next_step": "handle_new_character"}


async def handle_ooc(state: PreplayState) -> dict[str, Any]:
    answer = await answer_ooc_question(
        state.session_data,
        state.user_content,
        session_game_system_doc=state.system_doc,
        gsr_available=state.gsr_available,
    )
    return {
        "response_text": answer,
        "metadata": {"type": "ooc_answer", "phase": state.session_data.get("phase", "awaiting_character")},
        "next_step": END,
    }


async def handle_session_zero(state: PreplayState) -> dict[str, Any]:
    session = state.session_data
    # Only resolve authored questions when we'd actually build a loop (cache
    # miss). On a cache hit the questions were already baked in at creation, so
    # re-resolving would be a wasted Mongo round-trip every turn.
    authored = (
        resolve_authored_session_zero_questions(session, state.system_doc)
        if state.session_id not in _SESSION_ZERO_LOOPS
        else None
    )
    sz_loop = get_session_zero_loop(
        state.session_id,
        session,
        state.world_lore,
        state.system_context,
        authored_questions=authored,
    )
    if not sz_loop:
        return {"next_step": "handle_char_creation"}
        
    try:
        result = await sz_loop.process_player_input(state.user_content)
        campaign_intent = result.get("campaign_intent")
        if campaign_intent and not session.get("story_premise"):
            session["story_premise"] = campaign_intent

        if result.get("complete"):
            summary = result.get("summary")
            if summary:
                session["session_zero_summary"] = summary.model_dump() if hasattr(summary, "model_dump") else summary
                if getattr(summary, "character_name", None):
                    session["speaker_label"] = summary.character_name
                session["pending_character_concept"] = getattr(summary, "concept", None) or state.user_content

            session["phase"] = "char_creation"
            
            if state.system_doc and state.gsr_available and _CHAR_CREATION_AVAILABLE:
                cc_loop = get_character_creation_loop(state.session_id, state.system_doc)
                if cc_loop:
                    start_result = await cc_loop.start()
                    gm_msg = start_result.get("gm_message", "Let's build your character.")
                    response = result.get("gm_message", "") + "\n\n---\n\n" + gm_msg
                    return {
                        "response_text": response,
                        "metadata": {
                            "type": "session_zero_complete",
                            "phase": "char_creation",
                            "summary": summary.model_dump() if hasattr(summary, "model_dump") else summary,
                            "total_steps": start_result.get("total_steps", 0),
                        },
                        "session_data": session,
                        "next_step": END,
                    }
                    
            # No mechanics: go to active_play
            session["phase"] = "active_play"
            prologue = await _generate_prologue(session, result.get("gm_message", ""))
            return {
                "response_text": prologue,
                "metadata": {
                    "type": "session_zero_complete",
                    "phase": "active_play",
                    "summary": summary.model_dump() if hasattr(summary, "model_dump") else summary,
                },
                "session_data": session,
                "next_step": END,
            }
        else:
            gm_msg = result.get("gm_message", "Tell me more.")
            return {
                "response_text": gm_msg,
                "metadata": {
                    "type": "session_zero_question",
                    "phase": "session_zero",
                    "question_number": result.get("question_number", 0),
                    "total_questions": result.get("total_questions", DEFAULT_MAX_QUESTIONS),
                    "category": result.get("category", "custom"),
                    "campaign_intent_captured": bool(campaign_intent),
                },
                "session_data": session,
                "next_step": END,
            }
    except Exception as exc:
        logger.debug("handle_session_zero failed: %s", exc)
        return {"next_step": "handle_char_creation"}


async def handle_char_creation(state: PreplayState) -> dict[str, Any]:
    session = state.session_data
    
    if _CHAR_CREATION_AVAILABLE:
        cc_loop = get_character_creation_loop(state.session_id, state.system_doc)
        if cc_loop:
            try:
                result = await cc_loop.process_player_input(state.user_content)
                if result.get("complete"):
                    char = result.get("character", {})
                    sheet_md = result.get("sheet_markdown", "")
                    preview = {
                        "kind": "pc",
                        "name": char.get("name") or session.get("speaker_label") or "Adventurer",
                        "description": session.get("pending_character_concept") or "",
                        "concept": session.get("pending_character_concept") or "",
                        "system_name": (state.system_doc or {}).get("name", session.get("system_label") or ""),
                        "attributes": char.get("attributes") or {},
                        "resources": char.get("resources") or {},
                        "skills": char.get("skills") or {},
                        "sheet": sheet_md or str(char),
                        "tags": ["pc", "generated"],
                        "source": "character_creation_loop",
                    }
                    saved = None
                    try:
                        saved = persist_session_character(
                            session, preview,
                            {
                                "source_type": session.get("system_source_type") or "generic_library",
                                "source_label": (state.system_doc or {}).get("name", "Narrative"),
                                "system_id": session.get("system_id"),
                                "pack_id": session.get("pack_id"),
                            },
                        )
                    except Exception as exc:
                        logger.debug("char loop save failed: %s", exc)
                    
                    session["phase"] = "active_play"
                    _CHAR_CREATION_LOOPS.pop(state.session_id, None)
                    return {
                        "response_text": f"{preview['name']} is ready. I have the sheet for reference. Let's begin in the fiction — what do you do?",
                        "metadata": {
                            "type": "char_creation_complete",
                            "phase": "active_play",
                            "character": char,
                            "sheet": sheet_md,
                            "saved_character": saved,
                        },
                        "session_data": session,
                        "next_step": END,
                    }
                else:
                    return {
                        "response_text": result.get("gm_message", "Tell me more about your character."),
                        "metadata": {
                            "type": "char_creation_step",
                            "phase": "char_creation",
                            "step_index": result.get("step_index", 0),
                            "total_steps": result.get("total_steps", 0),
                        },
                        "next_step": END,
                    }
            except Exception as exc:
                logger.debug("char creation loop failed: %s", exc)
                
    # Legacy fallback logic
    lower = state.user_content.strip().lower()
    _SKIP_RE = re.compile(r"\b(skip|no|nah|narrative|don'?t|pass|just play|free.?form)\b", re.IGNORECASE)
    
    if _SKIP_RE.search(lower):
        concept = session.get("pending_character_concept") or state.user_content
        preview = {
            "kind": "pc",
            "name": session.get("speaker_label") or infer_character_name_from_text(concept),
            "description": concept,
            "concept": concept,
            "system_name": session.get("system_label") or "Narrative",
            "attributes": {}, "resources": {}, "skills": {},
            "sheet": concept, "tags": ["pc", "narrative_only"], "source": "narrative_only",
        }
        saved = None
        try:
            saved = persist_session_character(session, preview, {
                "source_type": "narrative_only",
                "source_label": session.get("system_label") or "Narrative",
            })
        except Exception:
            pass
        session["phase"] = "active_play"
        return {
            "response_text": "No numbers needed — your story speaks for itself. Let's begin.",
            "metadata": {"type": "preplay_ack", "phase": "active_play", "saved_character": saved},
            "session_data": session,
            "next_step": END,
        }

    if state.system_doc and state.gsr_available:
        try:
            from monitor_agents.game_system import GameSystemRuntime
            gsr = GameSystemRuntime(state.system_doc)
            rolled = gsr.roll_character()
            sheet = gsr.format_character_sheet(rolled)
            preview = {
                "kind": "pc",
                "name": session.get("speaker_label") or infer_character_name_from_text(session.get("pending_character_concept")),
                "description": session.get("pending_character_concept") or "",
                "concept": session.get("pending_character_concept") or "",
                "system_name": state.system_doc.get("name", session.get("system_label") or ""),
                "attributes": rolled.get("stats", {}),
                "resources": rolled.get("derived", {}),
                "skills": {},
                "rolls_detail": rolled.get("rolls_detail", {}),
                "sheet": sheet,
                "special_abilities": [],
                "tags": ["pc", "generated"],
                "source": "runtime_roll",
            }
            saved = None
            try:
                saved = persist_session_character(session, preview, {
                    "source_type": session.get("system_source_type") or ("generic_library" if session.get("system_id") else "narrative_only"),
                    "source_label": state.system_doc.get("name", session.get("system_label") or "Narrative"),
                    "system_id": session.get("system_id"),
                    "pack_id": session.get("pack_id"),
                })
            except Exception:
                pass
            session["phase"] = "active_play"
            name = preview.get("name") or "Your character"
            return {
                "response_text": f"{name} is ready. I have the sheet for reference. Let's begin in the fiction — what do you do?",
                "metadata": {
                    "type": "char_stats_rolled",
                    "phase": "active_play",
                    "stats": rolled.get("stats", {}),
                    "derived": rolled.get("derived", {}),
                    "sheet": sheet,
                    "saved_character": saved,
                },
                "session_data": session,
                "next_step": END,
            }
        except Exception as exc:
            logger.debug("stat roll failed: %s", exc)

    session["phase"] = "active_play"
    return {
        "response_text": "Stats locked. You're in. What do you do?",
        "metadata": {"type": "preplay_ack", "phase": "active_play"},
        "session_data": session,
        "next_step": END,
    }


async def handle_new_character(state: PreplayState) -> dict[str, Any]:
    session = state.session_data
    
    acknowledgement = ""
    try:
        from monitor_agents.narrator.agent import Narrator
        from monitor_agents.loops.scene_support import strip_entity_tags
        narrator = Narrator()
        result = await narrator.narrate_turn(
            scene_id=UUID('00000000-0000-0000-0000-000000000000'),
            user_input=f"[Character intro] {state.user_content}",
            resolution=None,
            context={"entities": [], "memories": [], "turns": []},
            game_context=state.system_doc,
            session_tone=session.get("tone", "dramatic"),
        )
        acknowledgement = strip_entity_tags(result.get("narrative_text", "")).strip()
    except Exception as exc:
        logger.debug("LLM ack failed: %s", exc)
    
    if not acknowledgement:
        acknowledgement = "Understood. That's who you are."
        
    if _SESSION_ZERO_AVAILABLE:
        seed_answers = None
        persona_id = session.get("persona_id")
        if persona_id:
            try:
                from monitor_data.tools.mongodb_tools import mongodb_get_character
                persona = await asyncio.to_thread(mongodb_get_character, UUID(persona_id))
                if persona:
                    seed_answers = _seed_answers_from_persona(persona) or None
            except Exception as exc:
                logger.debug("session zero persona seed fetch failed: %s", exc)
                
        if not seed_answers and isinstance(state.user_content, str) and state.user_content.strip():
            seed_answers = [{"question": "Who are you, and where does your story begin?", "answer": state.user_content.strip(), "category": "origin"}]
            
        sz_loop = get_session_zero_loop(
            state.session_id, session, state.world_lore, state.system_context,
            seed_answers=seed_answers, ask_campaign_intent=not session.get("story_premise"),
            authored_questions=(
                resolve_authored_session_zero_questions(session, state.system_doc)
                if state.session_id not in _SESSION_ZERO_LOOPS
                else None
            ),
        )
        if sz_loop:
            try:
                start_result = await sz_loop.start()
                session["phase"] = "session_zero"
                return {
                    "response_text": acknowledgement + "\n\n" + start_result.get("gm_message", "Tell me more about your character."),
                    "metadata": {
                        "type": "session_zero_start",
                        "phase": "session_zero",
                        "question_number": start_result.get("question_number", 1),
                        "total_questions": start_result.get("total_questions", DEFAULT_MAX_QUESTIONS),
                        "category": start_result.get("category", "custom"),
                        "saved_character": None,
                    },
                    "session_data": session,
                    "next_step": END,
                }
            except Exception as exc:
                logger.debug("session zero start failed: %s", exc)
                
    saved = None
    if state.system_doc and state.gsr_available:
        if _CHAR_CREATION_AVAILABLE:
            cc_loop = get_character_creation_loop(state.session_id, state.system_doc)
            if cc_loop:
                try:
                    start_result = await cc_loop.start()
                    session["phase"] = "char_creation"
                    return {
                        "response_text": acknowledgement + "\n\n" + start_result.get("gm_message", "Let's build your character."),
                        "metadata": {
                            "type": "char_creation_start",
                            "phase": "char_creation",
                            "total_steps": start_result.get("total_steps", 0),
                            "saved_character": None,
                        },
                        "session_data": session,
                        "next_step": END,
                    }
                except Exception as exc:
                    logger.debug("char creation start failed: %s", exc)
                    
        mech_offer = ""
        try:
            from monitor_agents.game_system import GameSystemRuntime
            gsr = GameSystemRuntime(state.system_doc)
            attrs = gsr.primary_attributes
            attr_names = [a.get("name", "") for a in attrs[:4] if a.get("name")]
            creation_method = gsr.ability_method_description()
            if len(attr_names) > 1:
                attr_list = f"{', '.join(attr_names[:-1])} and {attr_names[-1]}"
            elif attr_names:
                attr_list = attr_names[0]
            else:
                attr_list = ""
            if attr_list:
                mech_offer = (
                    f"\n\nWhen you're ready, I can ground that in the system — "
                    f"your core stats will be {attr_list}. "
                    + (f"They're generated by {creation_method.lower().rstrip('.')}. " if creation_method else "")
                    + "Want me to roll them, or would you rather assign them yourself?"
                )
        except Exception:
            pass
            
        session["phase"] = "char_creation"
        response = acknowledgement + mech_offer
    else:
        session["phase"] = "active_play"
        response = acknowledgement
        preview: dict[str, Any] = {
            "kind": "pc",
            "name": session.get("speaker_label") or infer_character_name_from_text(state.user_content),
            "description": state.user_content,
            "concept": state.user_content,
            "system_name": session.get("system_label") or "Narrative",
            "attributes": {}, "resources": {}, "skills": {},
            "sheet": state.user_content, "tags": ["pc", "narrative_only"], "source": "narrative_only",
        }
        try:
            saved = persist_session_character(session, preview, {
                "source_type": "narrative_only",
                "source_label": session.get("system_label") or "Narrative",
            })
        except Exception:
            pass
            
    return {
        "response_text": response,
        "metadata": {"type": "preplay_ack", "phase": session["phase"], "saved_character": saved},
        "session_data": session,
        "next_step": END,
    }


def route_next(state: PreplayState) -> str:
    return state.next_step


# Build the Graph
workflow = StateGraph(PreplayState)
workflow.add_node("evaluate", evaluate_intent)
workflow.add_node("handle_ooc", handle_ooc)
workflow.add_node("handle_session_zero", handle_session_zero)
workflow.add_node("handle_char_creation", handle_char_creation)
workflow.add_node("handle_new_character", handle_new_character)

workflow.set_entry_point("evaluate")
workflow.add_conditional_edges("evaluate", route_next, {
    "handle_ooc": "handle_ooc",
    "handle_session_zero": "handle_session_zero",
    "handle_char_creation": "handle_char_creation",
    "handle_new_character": "handle_new_character",
})
workflow.add_edge("handle_ooc", END)
workflow.add_edge("handle_session_zero", END)
workflow.add_edge("handle_char_creation", END)
workflow.add_edge("handle_new_character", END)

PreplayOrchestrator = workflow.compile()
