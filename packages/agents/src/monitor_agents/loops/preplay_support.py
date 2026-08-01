import asyncio
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from monitor_agents.llm_errors import classify_llm_error
from monitor_agents.loops.scene_support import strip_entity_tags
from monitor_agents.services.roleplay_error_recorder import RoleplayErrorRecorder
from monitor_data.schemas.roleplay_errors import RoleplayErrorCategory, RoleplayErrorSource

logger = logging.getLogger(__name__)


def _safe_universe_uuid(session: dict[str, Any]) -> uuid.UUID | None:
    """Best-effort UUID parse of session universe_id for error correlation."""
    raw = session.get("universe_id")
    if not raw:
        return None
    try:
        return uuid.UUID(str(raw))
    except (TypeError, ValueError):
        return None

# ---------------------------------------------------------------------------
# OOC Detection (moved from chat_support.py)
# ---------------------------------------------------------------------------

_OOC_PATTERNS = re.compile(
    r"\b(ooc|out of character|what (can|type|kind|sort|class|race|species|character|role|archetype)|"
    r"how (do|does|can|should|would)|who (can|could) i|what are (the|my|available)|"
    r"how (does|do) (combat|dice|roll|stat|skill|check|the game)|"
    r"what (is|are) (the|a|an)? ?(rule|mechanic|stat|attribute|skill|ability|dice|system)|"
    r"what (looks|seems|feels) (most )?(dangerous|risky|off|wrong)|"
    r"what('?s| is) (the )?(risk|danger|catch)|first impression|"
    r"before i commit|before i go in|before i board|if there's something i should know|"
    r"explain|tell me about|can (i|you)|what if i|is there a|do i have|before we (start|begin))\b",
    re.IGNORECASE,
)
_OOC_BLOCK_RE = re.compile(r"^\s*\(\((?P<content>.*?)\)\)\s*$", re.IGNORECASE | re.DOTALL)


def normalize_ooc_text(text: str) -> str:
    """Strip explicit `(( ... ))` OOC wrappers when present."""
    raw = (text or "").strip()
    match = _OOC_BLOCK_RE.match(raw)
    if match:
        return match.group("content").strip()
    # Unclosed "(( ..." — the player started an OOC aside but never closed
    # it (e.g. "(( Oracle:"). Treat the remainder as the OOC content.
    if raw.startswith("(("):
        return raw[2:].strip()
    return raw


def is_ooc_question(text: str) -> bool:
    """Return `True` when the player's text looks like an OOC rules/world-info question."""
    raw = (text or "").strip()
    if _OOC_BLOCK_RE.match(raw):
        return True
    if raw.startswith("(("):
        # Unclosed OOC wrapper — still meta intent, don't route in-fiction.
        return True
    return bool(_OOC_PATTERNS.search(normalize_ooc_text(raw)))


# ---------------------------------------------------------------------------
# Begin Story intent (typed alternative to the Begin Story button)
# ---------------------------------------------------------------------------

_BEGIN_STORY_PHRASES = frozenset(
    {
        "begin",
        "begin story",
        "begin the story",
        "begin narration",
        "begin the narration",
        "start",
        "start story",
        "start the story",
        "start narration",
        "start the narration",
        "confirm",
        "confirmed",
        "looks good",
        "lgtm",
        "go ahead",
        "proceed",
        "let's begin",
        "lets begin",
        "let's go",
        "lets go",
        "ready",
        "i'm ready",
        "im ready",
        "yes",
        "yeah",
        "yep",
        "ok",
        "okay",
        "sure",
        "continue",
    }
)


def is_begin_story_command(text: str) -> bool:
    """Return `True` when the player's text confirms the Session Zero agreements.

    The story-agreements loop treats ANY input while awaiting confirmation as
    a revision request and re-presents the summary, so typing "begin story"
    in chat used to loop forever. The router checks this before dispatching
    a pre-play turn and routes matching messages through the same finalize
    path as the Begin Story button. Only matched while agreements are
    awaiting confirmation, so short affirmations ("yes", "ok") are safe.
    """
    raw = (text or "").strip()
    if not raw or _OOC_BLOCK_RE.match(raw):
        return False
    normalized = re.sub(r"\s+", " ", raw.lower()).strip(" .!?")
    return normalized in _BEGIN_STORY_PHRASES


def session_facts_block(session: dict[str, Any]) -> str:
    """Compact facts the pre-play stages stored on the session.

    Used to ground OOC answers ("who am I?", "what is this story?") so the
    narrator doesn't plead ignorance about the character it helped create.
    """
    lines: list[str] = []
    summary = session.get("character_summary") or session.get("session_zero_summary") or {}
    if isinstance(summary, dict):
        name = str(summary.get("character_name") or session.get("speaker_label") or "").strip()
        if name:
            lines.append(f"Player character: {name}")
        concept = str(summary.get("concept") or "").strip()
        if concept:
            lines.append(f"Concept: {concept}")
        backstory = str(summary.get("backstory") or "").strip()
        if backstory:
            lines.append(f"Backstory: {backstory}")
    elif session.get("speaker_label"):
        lines.append(f"Player character: {session['speaker_label']}")

    agreements = session.get("story_agreements") or {}
    if isinstance(agreements, dict):
        premise = str(agreements.get("story_premise") or session.get("story_premise") or "").strip()
        if premise:
            lines.append(f"Story premise: {premise}")
        themes = [str(theme) for theme in agreements.get("themes") or [] if theme]
        if themes:
            lines.append("Themes: " + ", ".join(themes))

    notes = [str(note).strip() for note in session.get("director_notes") or [] if str(note).strip()]
    if notes:
        lines.append("Player direction (established by the player, treat as true):")
        lines.extend(f"- {note}" for note in notes[-20:])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Director notes — player-established facts asserted OOC
# ---------------------------------------------------------------------------

_DIRECTOR_NOTES_MAX = 20
_QUESTION_WORDS = frozenset(
    {
        "who", "what", "where", "when", "why", "how", "which",
        "can", "could", "do", "does", "did", "is", "are", "am", "was", "were",
        "should", "would", "will", "may", "might",
    }
)


def looks_like_question(text: str) -> bool:
    """Heuristic: trailing question mark, or a leading question word.

    A "?" mid-sentence ("...okay? i want X") does not make the whole
    statement a question — those are director notes and must be recorded.
    """
    stripped = (text or "").strip().lower()
    if not stripped:
        return False
    if stripped.endswith("?"):
        return True
    first = stripped.split(None, 1)[0].strip(".,!;:")
    return first in _QUESTION_WORDS


def record_director_note(session: dict[str, Any], text: str) -> bool:
    """Persist a player-established fact asserted OOC (e.g. "this happens in
    Santiago") onto the session so later turns can see it.

    Statements are recorded verbatim, deduped, and capped at the most recent
    20. Questions ("who am I?") are NOT facts and are skipped. The list is
    mutated in place so a cached SceneLoop holding the same reference sees
    new notes on the next turn.
    """
    entry = (text or "").strip()
    if not entry or looks_like_question(entry):
        return False
    notes = session.setdefault("director_notes", [])
    if not isinstance(notes, list):
        notes = session["director_notes"] = []
    if entry in notes:
        return False
    notes.append(entry)
    del notes[:-_DIRECTOR_NOTES_MAX]
    return True


OOC_EXCHANGES_CAP = 8


def record_ooc_exchange(session: dict[str, Any], question: str, answer: str) -> None:
    """Append an OOC Q&A pair to the session for later narrator context.

    In-place append (same shared-reference pattern as director notes) so a
    cached SceneLoop sees new exchanges on the next turn. Cap: newest 8.
    """
    exchanges = session.setdefault("ooc_exchanges", [])
    if not isinstance(exchanges, list):
        exchanges = session["ooc_exchanges"] = []
    exchanges.append(
        {
            "question": question.strip(),
            "answer": answer.strip(),
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )
    del exchanges[:-OOC_EXCHANGES_CAP]


# ---------------------------------------------------------------------------
# Character inference & storage (moved from chat_loops.py / entities.py)
# ---------------------------------------------------------------------------

def infer_character_name_from_text(text: str | None, fallback: str = "Player Character") -> str:
    """Best-effort name guess from a conversational character description."""
    if not text:
        return fallback

    patterns = (r"\b(?:my name is|call me|i am|i'm)\s+([A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+){0,2})",)
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = " ".join(part.capitalize() for part in match.group(1).split())
            if candidate:
                return candidate
    return fallback


def _persist_generated_entity(
    *,
    universe_id: str,
    preview: dict[str, Any],
    source_meta: dict[str, Any],
) -> dict[str, Any]:
    """Persist a generated PC/NPC to the selected world using canonical stores."""
    from monitor_data.schemas.base import Authority, CanonLevel, EntityType
    from monitor_data.schemas.character_sheets import CharacterSheetCreate
    from monitor_data.schemas.entities import EntityCreate
    from monitor_data.schemas.npc_profiles import NPCProfileCreate, NPCProfileUpdate
    from monitor_data.tools.mongodb_tools import (
        mongodb_create_character_sheet,
        mongodb_create_npc_profile,
        mongodb_update_npc_profile,
    )
    from monitor_data.tools.neo4j_tools.entities import neo4j_create_entity
    from uuid import UUID

    universe_uuid = UUID(universe_id)

    kind = str(preview.get("kind", "pc")).lower()
    state_tags = [str(tag) for tag in dict.fromkeys([*(preview.get("tags") or []), kind, "generated"])]
    role = "PC" if kind == "pc" else "NPC"

    entity = neo4j_create_entity(
        EntityCreate(
            universe_id=universe_uuid,
            name=str(preview.get("name") or ("Generated NPC" if kind == "npc" else "Generated Character")),
            entity_type=EntityType.CHARACTER,
            sub_type=None,
            is_archetype=False,
            description=str(preview.get("description") or ""),
            properties={
                "role": role,
                "concept": preview.get("concept") or preview.get("description") or "",
                "generation_source": source_meta.get("source_type"),
                "system_name": preview.get("system_name") or source_meta.get("source_label"),
                "tier": preview.get("tier"),
            },
            state_tags=state_tags,
            archetype_id=None,
            authority=Authority.SYSTEM,
            canon_level=CanonLevel.CANON,
            confidence=1.0,
        )
    )

    sheet = mongodb_create_character_sheet(
        CharacterSheetCreate(
            entity_id=entity.id,
            game_system_id=UUID(source_meta["system_id"]) if source_meta.get("system_id") else None,
            system_source_type=str(source_meta.get("source_type") or "narrative_only"),
            system_source_id=str(
                source_meta.get("pack_id")
                or source_meta.get("system_id")
                or source_meta.get("game_system_id")
                or entity.id
            ),
            system_name=str(preview.get("system_name") or source_meta.get("source_label") or "Narrative"),
            source_persona_id=preview.get("source_persona_id"),
            stats=dict(preview.get("attributes") or {}),
            resources=dict(preview.get("resources") or {}),
            skills=dict(preview.get("skills") or {}),
            background=None,
            alignment=None,
            notes=str(preview.get("sheet") or preview.get("description") or ""),
            special_abilities=list(preview.get("special_abilities") or []),
        )
    )

    profile_id = None
    if kind == "npc":
        profile_payload = NPCProfileCreate(
            entity_id=entity.id,
            values=list(preview.get("values") or []),
            desires=list(preview.get("desires") or []),
            speech_style=preview.get("speech_style"),
            gm_notes=str(preview.get("sheet") or preview.get("description") or ""),
            current_emotional_state="neutral",
        )
        try:
            profile = mongodb_create_npc_profile(profile_payload)
        except ValueError:
            profile = mongodb_update_npc_profile(
                entity.id,
                NPCProfileUpdate(
                    values=profile_payload.values,
                    desires=profile_payload.desires,
                    speech_style=profile_payload.speech_style,
                    gm_notes=profile_payload.gm_notes,
                    current_emotional_state=profile_payload.current_emotional_state,
                    relationship_states=None,
                    add_preference=None,
                    add_trigger=None,
                    add_secret=None,
                ),
            )
        profile_id = str(profile.profile_id)

    return {
        "entity_id": str(entity.id),
        "sheet_id": str(sheet.sheet_id),
        "profile_id": profile_id,
        "saved_to_universe_id": str(entity.universe_id),
    }


def persist_session_character(
    session: dict[str, Any],
    preview: dict[str, Any],
    source_meta: dict[str, Any],
) -> dict[str, Any] | None:
    """Persist a pre-play character into the selected world and bind it to the session."""
    universe_id = session.get("universe_id") or session.get("world_id")
    if not universe_id:
        return None

    persona_id = session.get("persona_id")
    if persona_id and "source_persona_id" not in preview:
        preview = {**preview, "source_persona_id": persona_id}

    saved = _persist_generated_entity(
        universe_id=str(universe_id),
        preview=preview,
        source_meta=source_meta,
    )
    entity_id = saved.get("entity_id")
    if entity_id:
        session["character_id"] = entity_id
        session["speaker_character_id"] = entity_id
        controlled = list(session.get("controlled_character_ids", []))
        if entity_id not in controlled:
            controlled.append(entity_id)
        session["controlled_character_ids"] = controlled
    return saved


def _seed_answers_from_persona(persona: dict[str, Any]) -> list[dict[str, str]]:
    """Turn a saved standalone-character persona into Session Zero prior_answers."""
    seed: list[dict[str, str]] = []
    name = str(persona.get("name") or "").strip()
    description = str(persona.get("description") or "").strip()
    personality = str(persona.get("personality") or "").strip()
    first_message = str(persona.get("first_message") or "").strip()

    if name:
        seed.append({"question": "What are you called?", "answer": name, "category": "name"})
    if description:
        seed.append(
            {
                "question": "Who are you, in broad strokes?",
                "answer": description,
                "category": "origin",
            }
        )
    if personality:
        seed.append(
            {
                "question": "What are you like?",
                "answer": personality,
                "category": "custom",
            }
        )
    if first_message:
        seed.append(
            {
                "question": "How do you first present yourself?",
                "answer": first_message,
                "category": "custom",
            }
        )
    return seed


# ---------------------------------------------------------------------------
# OOC answer and Prologue generation
# ---------------------------------------------------------------------------


def _build_ooc_signature() -> Any:
    """Lazily define the DSPy signature so `import dspy` stays deferred."""
    import dspy

    class OocAnswerSignature(dspy.Signature):  # type: ignore[misc]
        """Answer a player's out-of-character (OOC) message in the GM's meta voice.

        The player is talking TO the game master, not acting in the fiction:
        asking rules/world questions, or giving direction ("this happens in
        Santiago"). Answer the question or acknowledge the direction BRIEFLY
        in ((double-paren)) OOC style, grounded in the session facts. NEVER
        narrate new fiction, NEVER advance the scene, NEVER invent locations,
        NPCs, or events. If the player gave direction, confirm what you
        recorded in one or two sentences.
        """

        ooc_message: str = dspy.InputField(
            desc="The player's OOC message — a meta question or a director note"
        )
        session_facts: str = dspy.InputField(
            desc="Established facts: character, premise, player director notes"
        )
        world_lore: str = dspy.InputField(desc="Relevant world/system lore (may be empty)")
        mechanical_hint: str = dspy.InputField(desc="Rules hint to include when relevant (may be empty)")
        answer: str = dspy.OutputField(
            desc="Short meta answer in ((...)) style — no fiction, 1-4 sentences"
        )

    return OocAnswerSignature


async def answer_ooc_question(
    session: dict[str, Any],
    question: str,
    *,
    session_game_system_doc: Any,
    gsr_available: bool,
) -> str:
    """Answer an OOC message and record the exchange for later GM context."""
    answer = await _compose_ooc_answer(
        session,
        question,
        session_game_system_doc=session_game_system_doc,
        gsr_available=gsr_available,
    )
    record_ooc_exchange(session, normalize_ooc_text(question), answer)
    return answer


async def _compose_ooc_answer(
    session: dict[str, Any],
    question: str,
    *,
    session_game_system_doc: Any,
    gsr_available: bool,
) -> str:
    """Answer an OOC question in-fiction, drawing from the game system schema and entity archetypes."""
    question = normalize_ooc_text(question)
    system_doc = session_game_system_doc(session) if callable(session_game_system_doc) else session_game_system_doc
    universe_id = session.get("universe_id")

    # Player statements made OOC are table direction ("lets be clear: this is
    # happening in Santiago") — persist them so the next scene turn honours
    # them instead of improvising a new setting.
    record_director_note(session, question)

    mechanical_hint = ""
    if system_doc and gsr_available:
        try:
            from monitor_agents.game_system import GameSystemRuntime

            gsr = GameSystemRuntime(system_doc)
            probe_text = question
            lower_q = question.lower()
            if "would i roll to" in lower_q:
                probe_text = lower_q.replace("would i roll to", "i ")
            elif "what do i roll for" in lower_q:
                probe_text = lower_q.replace("what do i roll for", "i ")

            action_type, stat_name, dc = await gsr.infer_action_stat(probe_text)
            core_formula = (system_doc.get("core_mechanic") or {}).get("formula") or "the system's core mechanic"
            if any(
                word in lower_q
                for word in (
                    "roll", "shoot", "attack", "sneak", "talk",
                    "convince", "search", "repair", "hack",
                )
            ):
                mechanical_hint = (
                    f"Mechanically, I'd usually call for **{stat_name}** using **{core_formula}**. "
                    f"For a risky attempt, expect pressure around **{dc}** unless the fiction changes it."
                )
        except Exception as exc:
            logger.debug("answer_ooc_question mechanical hint failed: %s", exc)
            info = classify_llm_error(exc)
            await RoleplayErrorRecorder.record(
                source=RoleplayErrorSource.PREPLAY,
                category=RoleplayErrorCategory.LLM,
                message=info.message,
                fatal=False,
                llm_error_class=info.error_class.value,
                universe_id=_safe_universe_uuid(session),
            )

    # Gather entity archetypes for character type questions
    archetype_lines: list[str] = []
    try:
        from monitor_data.db.neo4j import get_neo4j_client

        neo = get_neo4j_client()
        rows = await asyncio.to_thread(
            neo.execute_read,
            "MATCH (e:Entity) WHERE e.entity_type = 'character' AND e.is_archetype = true "
            "AND e.universe_id = $uid "
            "RETURN e.name AS name, e.description AS desc "
            "LIMIT 8",
            {"uid": universe_id or ""},
        )
        for r in rows:
            name = r.get("name", "")
            desc = (r.get("desc") or "")[:120]
            if name:
                archetype_lines.append(f"{name}: {desc}" if desc else name)
    except Exception:
        pass

    # Try LLM answer — a dedicated meta-voice signature, NOT the narration
    # pipeline (which is prompted to produce fiction and sometimes answered
    # OOC questions by inventing whole new scenes).
    try:
        import dspy

        from monitor_agents.dspy_runtime import dspy_context_for
        from monitor_data.schemas.llm_config import ModelRole

        facts = session_facts_block(session)
        lore_block = "\n".join(archetype_lines[:6]) if archetype_lines else ""
        with dspy_context_for("ooc_answer", ModelRole.LIGHT):
            prediction = dspy.Predict(_build_ooc_signature())(
                ooc_message=question,
                session_facts=facts or "(nothing established yet)",
                world_lore=lore_block or "(none available)",
                mechanical_hint=mechanical_hint or "(none)",
            )
        answer = strip_entity_tags(str(getattr(prediction, "answer", ""))).strip()
        if answer and len(answer) > 30:
            if mechanical_hint and mechanical_hint.lower() not in answer.lower():
                return f"{answer}\n\n{mechanical_hint}"
            return answer
    except Exception as exc:
        logger.debug("answer_ooc_question LLM failed: %s", exc)
        info = classify_llm_error(exc)
        await RoleplayErrorRecorder.record(
            source=RoleplayErrorSource.PREPLAY,
            category=RoleplayErrorCategory.LLM,
            message=info.message,
            fatal=False,
            llm_error_class=info.error_class.value,
            universe_id=_safe_universe_uuid(session),
        )

    # Fallback
    if archetype_lines:
        intro = "Out here, people survive in different ways.\n\n"
        body = "\n".join(f"- {line}" for line in archetype_lines[:5])
        closing = "\n\nWhat pulls at you?"
        if mechanical_hint:
            closing = f"\n\n{mechanical_hint}\n\nWhat pulls at you?"
        return intro + body + closing

    sys_name = session.get("system_label") or "this world"
    base = (
        f"In {sys_name}, who you are is defined by what you do and how you survive. "
        "Tell me about your character — even a rough idea is enough to start."
    )
    return f"{base}\n\n{mechanical_hint}" if mechanical_hint else base


async def _generate_prologue(session: dict[str, Any], summary_text: str) -> str:
    """Generate a prologue opening that incorporates the character's backstory."""
    try:
        from monitor_agents.narrator.agent import Narrator

        narrator = Narrator()
        summary = session.get("session_zero_summary") or {}
        concept = summary.get("concept", "") if isinstance(summary, dict) else ""
        backstory = summary.get("backstory", "") if isinstance(summary, dict) else ""

        prologue = await narrator.generate_opening(
            user_input=(
                f"[Prologue — the character's backstory follows]\n"
                f"Concept: {concept}\nBackstory: {backstory}\n"
                f"Set the opening scene that incorporates this backstory."
            ),
            context={"entities": [], "memories": [], "turns": []},
            game_context=None,
            session_tone=session.get("tone", "dramatic"),
        )
        if prologue and len(prologue) > 40:
            return prologue
    except Exception as exc:
        logger.debug("_generate_prologue LLM call failed: %s", exc)
        info = classify_llm_error(exc)
        await RoleplayErrorRecorder.record(
            source=RoleplayErrorSource.PREPLAY,
            category=RoleplayErrorCategory.LLM,
            message=info.message,
            fatal=False,
            llm_error_class=info.error_class.value,
            universe_id=_safe_universe_uuid(session),
        )

    if summary_text:
        return summary_text + "\n\nThe story begins. What do you do?"
    return "Your character is ready. The story begins — what do you do?"

def resolve_authored_questions(
    session: dict[str, Any],
    session_game_system_doc: Any,
    *,
    category: str,
) -> list[dict[str, Any]]:
    """Resolve authored questions for a universe/system-scoped prompt category."""
    try:
        from monitor_data.schemas.prompt_collections import PromptCollectionFilter
        from monitor_data.tools.mongodb_tools import (
            mongodb_get_prompt_collection,
            mongodb_list_prompt_collections,
        )
        _PROMPT_COLLECTIONS_AVAILABLE = True
    except ImportError:
        _PROMPT_COLLECTIONS_AVAILABLE = False
        
    if not _PROMPT_COLLECTIONS_AVAILABLE:
        return []
    
    def _entries_to_questions(collection: Any) -> list[dict[str, Any]]:
        entries = sorted(collection.entries, key=lambda e: e.order)
        return [
            {
                "question_text": e.question_text,
                "category": e.category,
                "is_final": e.is_final,
                "answer_options": list(e.answer_options),
            }
            for e in entries
            if (e.question_text or "").strip()
        ]

    try:
        explicit_id = session.get("authored_prompt_collection_id")
        if explicit_id:
            collection = mongodb_get_prompt_collection(uuid.UUID(str(explicit_id)))
            if collection and collection.entries:
                return _entries_to_questions(collection)

        system_id = None
        try:
            system_doc = session_game_system_doc(session) if callable(session_game_system_doc) else session_game_system_doc
            if isinstance(system_doc, dict) and system_doc.get("system_id"):
                system_id = uuid.UUID(str(system_doc["system_id"]))
        except Exception as exc:
            logger.debug("prompt-collection: system_id resolve failed: %s", exc)

        universe_id = session.get("universe_id")
        universe_uuid = uuid.UUID(str(universe_id)) if universe_id else None

        for filt in (
            PromptCollectionFilter(category=category, universe_id=universe_uuid) if universe_uuid else None,
            PromptCollectionFilter(category=category, system_id=system_id) if system_id else None,
        ):
            if filt is None:
                continue
            listing = mongodb_list_prompt_collections(filt)
            if listing.collections:
                return _entries_to_questions(listing.collections[0])
    except Exception as exc:
        logger.debug("resolve_authored_questions(%s) failed: %s", category, exc)

    return []


def resolve_authored_session_zero_questions(
    session: dict[str, Any],
    session_game_system_doc: Any,
) -> list[dict[str, Any]]:
    """Compatibility wrapper for character-interview prompt collections."""
    return resolve_authored_questions(
        session,
        session_game_system_doc,
        category="session_zero",
    )
