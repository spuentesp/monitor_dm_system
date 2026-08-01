"""LangGraph orchestration for character setup and Session Zero agreements."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import structlog
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from monitor_agents.loops.character_creation_loop import CharacterCreationLoop
from monitor_agents.loops.character_interview_loop import (
    CharacterInterviewLoop,
    DEFAULT_MAX_QUESTIONS,
)
from monitor_agents.loops.preplay_phases import PreplayPhase, normalize_preplay_phase
from monitor_agents.loops.preplay_support import (
    _seed_answers_from_persona,
    answer_ooc_question,
    is_ooc_question,
    persist_session_character,
    resolve_authored_questions,
    resolve_authored_session_zero_questions,
)
from monitor_agents.loops.story_agreements_loop import StoryAgreementsLoop
from monitor_agents.setting_intro import assemble_session_intro

log = structlog.get_logger()


class PreplayState(BaseModel):
    session_id: str
    user_content: str
    session_data: dict[str, Any]
    system_doc: dict[str, Any] | None = None
    gsr_available: bool = False

    next_step: str = "evaluate"
    world_lore: list[str] = Field(default_factory=list)
    system_context: str = ""
    response_text: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


_CHAR_CREATION_LOOPS_MAX = 16
_CHAR_CREATION_LOOPS: dict[str, Any] = {}
_CHARACTER_INTERVIEW_LOOPS_MAX = 16
_CHARACTER_INTERVIEW_LOOPS: dict[str, Any] = {}
# Backward-compatible name used by router cache-pop helpers and older tests.
_SESSION_ZERO_LOOPS = _CHARACTER_INTERVIEW_LOOPS
_SESSION_ZERO_LOOPS_MAX = _CHARACTER_INTERVIEW_LOOPS_MAX
_STORY_AGREEMENT_LOOPS_MAX = 16
_STORY_AGREEMENT_LOOPS: dict[str, StoryAgreementsLoop] = {}


def _evict_oldest(cache: dict[str, Any], max_size: int) -> None:
    while len(cache) > max_size:
        cache.pop(next(iter(cache)))


def _character_summary(session: dict[str, Any]) -> dict[str, Any]:
    summary = session.get("character_summary") or session.get("session_zero_summary") or {}
    return dict(summary) if isinstance(summary, dict) else {}


def _checkpoint_for(session: dict[str, Any] | None, stage: str) -> dict[str, Any] | None:
    checkpoint = (session or {}).get("preplay_checkpoint")
    if not isinstance(checkpoint, dict):
        return None
    if checkpoint.get("schema_version") != 1 or checkpoint.get("stage") != stage:
        return None
    state = checkpoint.get("state")
    return state if isinstance(state, dict) else None


def _restore_loop_state(loop: Any, session: dict[str, Any] | None, stage: str) -> Any:
    state = _checkpoint_for(session, stage)
    current = getattr(loop, "_state", None)
    if state is None or current is None:
        return loop
    try:
        loop._state = type(current).model_validate(state)
        # Rehydrate the loop's own question_number from the persisted state
        # so the next ask_question() / present_question() lands on the right
        # slot. The StoryAgreementsLoop stores its progression on the state
        # directly, so no extra step is needed.
        current_question_index = getattr(loop._state, "question_index", None)
        if current_question_index is not None and hasattr(loop, "_current_question_index"):
            loop._current_question_index = current_question_index
    except Exception as exc:
        log.warning("preplay.checkpoint_invalid", stage=stage, error=str(exc))
    return loop


def _save_checkpoint(session: dict[str, Any], stage: str, loop: Any) -> None:
    state = getattr(loop, "state", None) or getattr(loop, "_state", None)
    if state is None or not hasattr(state, "model_dump"):
        return
    session["preplay_checkpoint"] = {
        "schema_version": 1,
        "stage": stage,
        "state": state.model_dump(mode="json"),
    }


def clear_preplay_checkpoint(session: dict[str, Any] | None) -> None:
    """Drop the in-session pre-play checkpoint after Begin Story succeeds."""
    if isinstance(session, dict):
        session.pop("preplay_checkpoint", None)


def get_character_creation_loop(
    session_id: str,
    system_doc: Any,
    seed: dict[str, Any] | None = None,
    *,
    session: dict[str, Any] | None = None,
) -> Any:
    if not system_doc:
        return None
    if session_id in _CHAR_CREATION_LOOPS:
        return _CHAR_CREATION_LOOPS[session_id]
    try:
        loop = CharacterCreationLoop(game_context=system_doc, seed=seed)
        _restore_loop_state(loop, session, PreplayPhase.CHARACTER_CREATION.value)
        _CHAR_CREATION_LOOPS[session_id] = loop
        _evict_oldest(_CHAR_CREATION_LOOPS, _CHAR_CREATION_LOOPS_MAX)
        return loop
    except Exception as exc:
        log.warning("preplay.character_creation_unavailable", error=str(exc))
        return None


def get_character_interview_loop(
    session_id: str,
    session: dict[str, Any],
    world_lore: list[str],
    system_context: str,
    seed_answers: list[dict[str, str]] | None = None,
    authored_questions: list[dict[str, Any]] | None = None,
) -> Any:
    if session_id in _CHARACTER_INTERVIEW_LOOPS:
        return _CHARACTER_INTERVIEW_LOOPS[session_id]
    try:
        authored = list(authored_questions or [])
        max_questions = len(authored) if authored else DEFAULT_MAX_QUESTIONS
        loop = CharacterInterviewLoop(
            tone=session.get("tone", "dramatic"),
            system_name=session.get("system_label") or "Unknown System",
            world_lore=world_lore,
            system_context=system_context,
            max_questions=max_questions,
            seed_answers=seed_answers,
            ask_campaign_intent=False,
            authored_questions=authored,
        )
        _restore_loop_state(loop, session, PreplayPhase.CHARACTER_INTERVIEW.value)
        _CHARACTER_INTERVIEW_LOOPS[session_id] = loop
        _evict_oldest(_CHARACTER_INTERVIEW_LOOPS, _CHARACTER_INTERVIEW_LOOPS_MAX)
        return loop
    except Exception as exc:
        log.warning("preplay.character_interview_unavailable", error=str(exc))
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
    """Compatibility wrapper for the former character-focused SessionZeroLoop."""
    del ask_campaign_intent
    return get_character_interview_loop(
        session_id,
        session,
        world_lore,
        system_context,
        seed_answers=seed_answers,
        authored_questions=authored_questions,
    )


def get_story_agreements_loop(
    session_id: str,
    session: dict[str, Any],
    system_doc: dict[str, Any] | None,
) -> StoryAgreementsLoop | None:
    if session_id in _STORY_AGREEMENT_LOOPS:
        return _STORY_AGREEMENT_LOOPS[session_id]
    intro = session.get("session_intro")
    if not isinstance(intro, dict):
        return None
    authored = resolve_authored_questions(
        session,
        system_doc,
        category="story_agreements",
    )
    checkpoint = _checkpoint_for(session, PreplayPhase.SESSION_ZERO.value)
    loop = StoryAgreementsLoop(
        setting_intro=intro,
        character_name=session.get("speaker_label") or "the protagonist",
        default_tone=session.get("tone", "dramatic"),
        authored_questions=authored,
        checkpoint=checkpoint,
    )
    # Aggressive eviction of cached loops for sessions without a
    # checkpoint would otherwise restart the loop on a new visit. The
    # cache is bounded by MAX but we also drop the slot eagerly when
    # the player has confirmed agreements so the next phase isn't blocked.
    confirmed = isinstance(session.get("story_agreements"), dict) and session["story_agreements"].get("confirmed")
    if not confirmed:
        _STORY_AGREEMENT_LOOPS[session_id] = loop
        _evict_oldest(_STORY_AGREEMENT_LOOPS, _STORY_AGREEMENT_LOOPS_MAX)
    return loop


async def _persona_seed(session: dict[str, Any]) -> list[dict[str, str]] | None:
    persona_id = session.get("persona_id")
    if not persona_id:
        return None
    try:
        from monitor_data.tools.mongodb_tools import mongodb_get_character

        persona = await asyncio.to_thread(mongodb_get_character, UUID(str(persona_id)))
        return _seed_answers_from_persona(persona) or None if persona else None
    except Exception as exc:
        log.warning("preplay.persona_seed_failed", error=str(exc))
        return None


async def start_character_interview(
    session_id: str,
    session: dict[str, Any],
    *,
    system_doc: dict[str, Any] | None,
    world_lore: list[str] | None = None,
    system_context: str = "",
) -> tuple[str, dict[str, Any]]:
    seed_answers = await _persona_seed(session)
    # Checkpoint rehydration: when the loop is rebuilt from a cache miss or
    # a backend restart, the persisted state must replay the same answers
    # and resume from the same question index the player was on. The seed
    # answers only apply on a *fresh* interview (no answers recorded yet).
    checkpoint = _checkpoint_for(session, PreplayPhase.CHARACTER_INTERVIEW.value)
    if checkpoint and checkpoint.get("answers"):
        seed_answers = None
    loop = get_character_interview_loop(
        session_id,
        session,
        world_lore or [],
        system_context,
        seed_answers=seed_answers,
        authored_questions=resolve_authored_session_zero_questions(session, system_doc),
    )
    if loop is None:
        return "Tell me who you will play in this story.", {
            "type": "character_interview_start",
            "phase": PreplayPhase.CHARACTER_INTERVIEW.value,
        }
    result = await loop.start()
    session["phase"] = PreplayPhase.CHARACTER_INTERVIEW.value
    _save_checkpoint(session, session["phase"], loop)
    return result.get("gm_message", "Tell me about your character."), {
        "type": "character_interview_start",
        "phase": session["phase"],
        "question_number": result.get("question_number", 1),
        "total_questions": result.get("total_questions", DEFAULT_MAX_QUESTIONS),
        "category": result.get("category", "custom"),
    }


async def start_story_agreements(
    session_id: str,
    session: dict[str, Any],
    *,
    system_doc: dict[str, Any] | None,
) -> tuple[str, dict[str, Any]]:
    if not isinstance(session.get("session_intro"), dict):
        intro = await assemble_session_intro(session)
        session["session_intro"] = intro.model_dump(mode="json")
    session["phase"] = PreplayPhase.SESSION_ZERO.value
    session["story_agreements_started"] = True
    _STORY_AGREEMENT_LOOPS.pop(session_id, None)
    loop = get_story_agreements_loop(session_id, session, system_doc)
    if loop is None:
        return "We could not prepare Session Zero yet.", {
            "type": "story_agreements_error",
            "phase": session["phase"],
        }
    result = await loop.start()
    _save_checkpoint(session, session["phase"], loop)
    return result["gm_message"], {
        "type": "story_agreements_start",
        "phase": session["phase"],
        "question_number": result["question_number"],
        "total_questions": result["total_questions"],
        "category": result["category"],
        "session_intro": result["session_intro"],
    }


async def evaluate_intent(state: PreplayState) -> dict[str, Any]:
    session = state.session_data
    raw_phase = session.get("phase")
    phase = normalize_preplay_phase(raw_phase)
    # A persisted old `session_zero` without a bound PC was the character
    # interview, not the new story-agreement stage.
    if (
        raw_phase == PreplayPhase.SESSION_ZERO.value
        and not session.get("character_id")
        and not session.get("story_agreements_started")
    ):
        phase = PreplayPhase.CHARACTER_INTERVIEW.value
    session["phase"] = phase

    if is_ooc_question(state.user_content):
        return {"next_step": "handle_ooc"}
    if phase == PreplayPhase.CHARACTER_INTERVIEW.value:
        return {"next_step": "handle_character_interview"}
    if phase == PreplayPhase.CHARACTER_CREATION.value:
        return {"next_step": "handle_char_creation"}
    if phase == PreplayPhase.SESSION_ZERO.value:
        return {"next_step": "handle_story_agreements"}
    return {"next_step": "handle_character_interview"}


async def handle_ooc(state: PreplayState) -> dict[str, Any]:
    answer = await answer_ooc_question(
        state.session_data,
        state.user_content,
        session_game_system_doc=state.system_doc,
        gsr_available=state.gsr_available,
    )
    return {
        "response_text": answer,
        "metadata": {"type": "ooc_answer", "phase": state.session_data.get("phase")},
        "next_step": END,
    }


async def handle_character_interview(state: PreplayState) -> dict[str, Any]:
    session = state.session_data
    loop = get_session_zero_loop(
        state.session_id,
        session,
        state.world_lore,
        state.system_context,
        seed_answers=None,
        authored_questions=(
            resolve_authored_session_zero_questions(session, state.system_doc)
            if state.session_id not in _CHARACTER_INTERVIEW_LOOPS
            else None
        ),
    )
    if loop is None:
        return {
            "response_text": "Character setup is unavailable; please try again.",
            "metadata": {"type": "character_interview_error", "phase": session["phase"]},
            "next_step": END,
        }

    result = await loop.process_player_input(state.user_content)
    if not result.get("complete"):
        _save_checkpoint(session, PreplayPhase.CHARACTER_INTERVIEW.value, loop)
        return {
            "response_text": result.get("gm_message", "Tell me more."),
            "metadata": {
                "type": "character_interview_question",
                "phase": PreplayPhase.CHARACTER_INTERVIEW.value,
                "question_number": result.get("question_number", 0),
                "total_questions": result.get("total_questions", DEFAULT_MAX_QUESTIONS),
                "category": result.get("category", "custom"),
            },
            "session_data": session,
            "next_step": END,
        }

    summary = result.get("summary")
    summary_data = summary.model_dump() if hasattr(summary, "model_dump") else dict(summary or {})
    session["character_summary"] = summary_data
    session.pop("session_zero_summary", None)
    session["pending_character_concept"] = summary_data.get("concept") or state.user_content
    if summary_data.get("character_name"):
        session["speaker_label"] = summary_data["character_name"]
    _CHARACTER_INTERVIEW_LOOPS.pop(state.session_id, None)

    if state.system_doc and state.gsr_available:
        loop = get_character_creation_loop(
            state.session_id,
            state.system_doc,
            seed=summary_data,
            session=session,
        )
        if loop is not None:
            started = await loop.start()
            session["phase"] = PreplayPhase.CHARACTER_CREATION.value
            _save_checkpoint(session, session["phase"], loop)
            return {
                "response_text": (
                    result.get("gm_message", "")
                    + "\n\n---\n\n"
                    + started.get("gm_message", "Let's build the character sheet.")
                ),
                "metadata": {
                    "type": "character_interview_complete",
                    "phase": session["phase"],
                    "summary": summary_data,
                    "total_steps": started.get("total_steps", 0),
                },
                "session_data": session,
                "next_step": END,
            }

    saved = _persist_narrative_character(session, summary_data)
    response, metadata = await start_story_agreements(
        state.session_id,
        session,
        system_doc=state.system_doc,
    )
    metadata["saved_character"] = saved
    return {
        "response_text": result.get("gm_message", "") + "\n\n---\n\n" + response,
        "metadata": metadata,
        "session_data": session,
        "next_step": END,
    }


# Compatibility name for callers that still treat the character interview as Session Zero.
handle_session_zero = handle_character_interview


async def handle_char_creation(state: PreplayState) -> dict[str, Any]:
    session = state.session_data
    loop = get_character_creation_loop(
        state.session_id,
        state.system_doc,
        seed=_character_summary(session),
        session=session,
    )
    if loop is None:
        return {
            "response_text": "Character mechanics are unavailable; choose narrative-only play to continue.",
            "metadata": {"type": "char_creation_error", "phase": session["phase"]},
            "next_step": END,
        }

    result = await loop.process_player_input(state.user_content)
    if not result.get("complete"):
        _save_checkpoint(session, PreplayPhase.CHARACTER_CREATION.value, loop)
        return {
            "response_text": result.get("gm_message", "Tell me more about your character."),
            "metadata": {
                "type": "char_creation_step",
                "phase": PreplayPhase.CHARACTER_CREATION.value,
                "step_index": result.get("step_index", 0),
                "total_steps": result.get("total_steps", 0),
            },
            "session_data": session,
            "next_step": END,
        }

    char = result.get("character", {})
    sheet_md = result.get("sheet_markdown", "")
    preview = {
        "kind": "pc",
        "name": char.get("name") or session.get("speaker_label") or "Player Character",
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
    saved = persist_session_character(
        session,
        preview,
        {
            "source_type": session.get("system_source_type") or "generic_library",
            "source_label": (state.system_doc or {}).get("name", "Narrative"),
            "system_id": session.get("system_id"),
            "pack_id": session.get("pack_id"),
        },
    )
    _CHAR_CREATION_LOOPS.pop(state.session_id, None)
    response, metadata = await start_story_agreements(
        state.session_id,
        session,
        system_doc=state.system_doc,
    )
    metadata.update({"character": char, "sheet": sheet_md, "saved_character": saved})
    return {
        "response_text": f"{preview['name']} is ready.\n\n---\n\n{response}",
        "metadata": metadata,
        "session_data": session,
        "next_step": END,
    }


def _character_recap(session: dict[str, Any]) -> str:
    """Small review of the established character, prepended to the closing
    Session-Zero summary so the player confirms it before Begin Story."""
    summary = session.get("character_summary")
    if not isinstance(summary, dict):
        return ""
    lines = ["CHARACTER REVIEW — what we established:"]
    name = str(summary.get("character_name") or session.get("speaker_label") or "").strip()
    concept = str(summary.get("concept") or "").strip()
    appearance = str(summary.get("appearance") or "").strip()
    backstory = str(summary.get("backstory") or "").strip()
    if name:
        lines.append(f"- Name: {name}")
    if concept:
        lines.append(f"- Origin & concept: {concept}")
    if appearance:
        lines.append(f"- Appearance: {appearance}")
    if backstory:
        lines.append(f"- Story so far: {backstory[:400]}")
    return "\n".join(lines) if len(lines) > 1 else ""


async def handle_story_agreements(state: PreplayState) -> dict[str, Any]:
    session = state.session_data
    loop = get_story_agreements_loop(state.session_id, session, state.system_doc)
    if loop is None:
        response, metadata = await start_story_agreements(
            state.session_id,
            session,
            system_doc=state.system_doc,
        )
        return {
            "response_text": response,
            "metadata": metadata,
            "session_data": session,
            "next_step": END,
        }

    result = await loop.process_player_input(state.user_content)
    _save_checkpoint(session, PreplayPhase.SESSION_ZERO.value, loop)
    metadata = {
        "type": "story_agreements_summary" if result.get("complete") else "story_agreements_question",
        "phase": PreplayPhase.SESSION_ZERO.value,
        "question_number": result.get("question_number", 0),
        "total_questions": result.get("total_questions", 3),
        "category": result.get("category", "custom"),
        "awaiting_confirmation": bool(result.get("awaiting_confirmation")),
    }
    agreements = result.get("agreements")
    if agreements is not None:
        agreement_data = (
            agreements.model_dump(mode="json")
            if hasattr(agreements, "model_dump")
            else dict(agreements)
        )
        session["story_agreements"] = agreement_data
        metadata["story_agreements"] = agreement_data
        if agreement_data.get("story_premise"):
            session["story_premise"] = agreement_data["story_premise"]

    recap = _character_recap(session) if result.get("complete") else ""
    gm_message = result.get("gm_message", "Tell me more.")
    if recap:
        gm_message = recap + "\n\n---\n\n" + gm_message

    return {
        "response_text": gm_message,
        "metadata": metadata,
        "session_data": session,
        "next_step": END,
    }


def _persist_narrative_character(
    session: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any] | None:
    concept = summary.get("concept") or session.get("pending_character_concept") or ""
    preview: dict[str, Any] = {
        "kind": "pc",
        "name": summary.get("character_name") or session.get("speaker_label") or "Player Character",
        "description": concept,
        "concept": concept,
        "system_name": session.get("system_label") or "Narrative",
        "attributes": {},
        "resources": {},
        "skills": {},
        "sheet": summary.get("backstory") or concept,
        "tags": ["pc", "narrative_only"],
        "source": "narrative_only",
    }
    return persist_session_character(
        session,
        preview,
        {
            "source_type": "narrative_only",
            "source_label": session.get("system_label") or "Narrative",
        },
    )


def route_next(state: PreplayState) -> str:
    return state.next_step


workflow = StateGraph(PreplayState)
workflow.add_node("evaluate", evaluate_intent)
workflow.add_node("handle_ooc", handle_ooc)
workflow.add_node("handle_character_interview", handle_character_interview)
workflow.add_node("handle_char_creation", handle_char_creation)
workflow.add_node("handle_story_agreements", handle_story_agreements)
workflow.set_entry_point("evaluate")
workflow.add_conditional_edges(
    "evaluate",
    route_next,
    {
        "handle_ooc": "handle_ooc",
        "handle_character_interview": "handle_character_interview",
        "handle_char_creation": "handle_char_creation",
        "handle_story_agreements": "handle_story_agreements",
    },
)
workflow.add_edge("handle_ooc", END)
workflow.add_edge("handle_character_interview", END)
workflow.add_edge("handle_char_creation", END)
workflow.add_edge("handle_story_agreements", END)

PreplayOrchestrator = workflow.compile()
