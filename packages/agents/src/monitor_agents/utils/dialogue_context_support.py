"""Helpers for dialogue-aware runtime context retrieval.

These utilities keep conversation heuristics and ranking logic out of
``ContextAssembly`` so the retrieval flow remains orchestration-focused.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set


_DIALOGUE_HINTS = (
    "say",
    "ask",
    "tell",
    "speak",
    "reply",
    "answer",
    "greet",
    "whisper",
    "shout",
    "convince",
    "persuade",
    "negotiate",
    "bargain",
    "threaten",
    "question",
)


def _tokenize_terms(text: str) -> Set[str]:
    """Return lowercased lexical terms suitable for cheap overlap scoring."""
    if not text:
        return set()
    cleaned = text.lower()
    for ch in "\n\r\t,.!?;:\"'()[]{}":
        cleaned = cleaned.replace(ch, " ")
    return {token for token in cleaned.split() if len(token) >= 3}


def is_dialogue_action(player_action: str) -> bool:
    """Heuristic check for dialogue-driven actions.

    The goal is to keep this intentionally broad so we gather conversational
    continuity context whenever the player likely expects social interaction.
    """
    lowered = (player_action or "").strip().lower()
    if not lowered:
        return False
    if '"' in lowered or "'" in lowered:
        return True
    if any(hint in lowered for hint in _DIALOGUE_HINTS):
        return True
    return lowered.endswith("?")


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.min
    return datetime.min


def rank_conversation_turns(
    turns: Iterable[Dict[str, Any]],
    *,
    player_action: str,
    limit: int = 6,
) -> List[Dict[str, Any]]:
    """Rank conversation turns by lexical relevance and recency."""
    query_terms = _tokenize_terms(player_action)
    ranked: List[tuple[float, Dict[str, Any]]] = []

    for index, turn in enumerate(turns):
        text = str(turn.get("text") or turn.get("content") or "").strip()
        if not text:
            continue
        score = 0.0
        overlap = len(query_terms & _tokenize_terms(text))
        if overlap:
            score += 2.5 + overlap * 0.9
        role = str(turn.get("speaker_role") or "").lower()
        if role == "npc":
            score += 0.35
        timestamp = _parse_timestamp(turn.get("timestamp"))
        if timestamp != datetime.min:
            score += 0.2
        score += max(0.0, (18 - index) * 0.04)
        ranked.append((score, turn))

    ranked.sort(
        key=lambda item: (
            item[0],
            _parse_timestamp(item[1].get("timestamp")),
        ),
        reverse=True,
    )
    return [turn for _, turn in ranked[:limit]]


def build_dialogue_turn_windows(
    turns: Iterable[Dict[str, Any]],
    *,
    window_size: int = 3,
    max_windows: int = 8,
) -> List[Dict[str, Any]]:
    """Build bounded local turn windows for conversational retrieval."""
    ordered = sorted(
        [dict(turn) for turn in turns if isinstance(turn, dict)],
        key=lambda turn: _parse_timestamp(turn.get("timestamp")),
        reverse=True,
    )
    if not ordered:
        return []

    size = max(2, min(int(window_size), 6))
    windows: List[Dict[str, Any]] = []
    for index in range(len(ordered)):
        chunk = ordered[index : index + size]
        if len(chunk) < 2:
            continue
        center = chunk[0]
        window_text = " ".join(str(turn.get("text") or "").strip() for turn in chunk).strip()
        if not window_text:
            continue
        windows.append(
            {
                "center_turn": center,
                "turns": chunk,
                "window_text": window_text,
                "timestamp": center.get("timestamp"),
                "entity_name": center.get("entity_name"),
            }
        )
        if len(windows) >= max_windows:
            break
    return windows


def rank_dialogue_windows(
    windows: Iterable[Dict[str, Any]],
    *,
    player_action: str,
    preferred_speakers: Optional[Iterable[str]] = None,
    limit: int = 4,
) -> List[Dict[str, Any]]:
    """Rank turn windows by lexical overlap, recency, and speaker continuity."""
    query_terms = _tokenize_terms(player_action)
    preferred = {
        str(name).strip().lower() for name in (preferred_speakers or []) if str(name).strip()
    }
    ranked: List[tuple[float, Dict[str, Any]]] = []

    for index, window in enumerate(windows):
        text = str(window.get("window_text") or "").strip()
        if not text:
            continue

        score = 0.0
        overlap = len(query_terms & _tokenize_terms(text))
        if overlap:
            score += 2.0 + overlap * 0.75

        speaker = str(window.get("entity_name") or "").strip().lower()
        if speaker and speaker in preferred:
            score += 0.8

        # Recency banding: top 2 windows strongest, next 3 moderate, then light.
        if index < 2:
            score += 0.7
        elif index < 5:
            score += 0.35
        else:
            score += 0.1

        timestamp = _parse_timestamp(window.get("timestamp"))
        if timestamp != datetime.min:
            score += 0.15

        ranked.append((score, window))

    ranked.sort(
        key=lambda item: (
            item[0],
            _parse_timestamp(item[1].get("timestamp")),
        ),
        reverse=True,
    )
    return [window for _, window in ranked[:limit]]


def conversation_turns_to_memory_items(
    turns: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Project conversation turns into memory-like entries used by narrator context."""
    items: List[Dict[str, Any]] = []
    for turn in turns:
        text = str(turn.get("text") or turn.get("content") or "").strip()
        if not text:
            continue
        speaker = str(turn.get("entity_name") or turn.get("speaker_role") or "speaker").strip()
        items.append(
            {
                "content": f"{speaker}: {text}",
                "source": "conversation_turn",
                "speaker_role": turn.get("speaker_role"),
                "entity_name": turn.get("entity_name"),
                "conversation_id": turn.get("conversation_id"),
                "turn_index": turn.get("turn_index"),
                "timestamp": turn.get("timestamp"),
            }
        )
    return items


def collect_dialogue_query_terms(
    turns: Iterable[Dict[str, Any]],
    *,
    limit: int = 6,
) -> List[str]:
    """Extract compact query terms from ranked dialogue turns.

    This keeps conversational retrieval grounded in active speaker/entity names
    and high-signal utterance fragments without carrying the full transcript.
    """
    terms: List[str] = []
    seen: set[str] = set()

    for turn in turns:
        for raw in (turn.get("entity_name"), turn.get("speaker_role")):
            text = str(raw or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            terms.append(text)
            if len(terms) >= limit:
                return terms

        utterance = str(turn.get("text") or "").strip()
        if utterance:
            tokens = [token for token in _tokenize_terms(utterance) if len(token) >= 4]
            for token in tokens:
                key = token.lower()
                if key in seen:
                    continue
                seen.add(key)
                terms.append(token)
                if len(terms) >= limit:
                    return terms

    return terms


def collect_dialogue_window_terms(
    windows: Iterable[Dict[str, Any]],
    *,
    limit: int = 6,
) -> List[str]:
    """Extract compact retrieval terms from ranked dialogue windows."""
    terms: List[str] = []
    seen: set[str] = set()

    for window in windows:
        speaker = str(window.get("entity_name") or "").strip()
        if speaker:
            key = speaker.lower()
            if key not in seen:
                seen.add(key)
                terms.append(speaker)
                if len(terms) >= limit:
                    return terms

        text = str(window.get("window_text") or "").strip()
        if not text:
            continue

        for token in _tokenize_terms(text):
            if len(token) < 5:
                continue
            key = token.lower()
            if key in seen:
                continue
            seen.add(key)
            terms.append(token)
            if len(terms) >= limit:
                return terms

    return terms


def compose_dialogue_focus_terms(
    turns: Iterable[Dict[str, Any]],
    windows: Iterable[Dict[str, Any]],
    *,
    limit: int = 10,
) -> List[str]:
    """Compose a compact, de-duplicated dialogue term list for retrieval expansion."""
    merged: List[str] = []
    seen: set[str] = set()

    for term in [
        *collect_dialogue_query_terms(turns, limit=limit),
        *collect_dialogue_window_terms(windows, limit=limit),
    ]:
        text = str(term or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(text)
        if len(merged) >= limit:
            return merged

    return merged


def dialogue_windows_to_memory_items(
    windows: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Project ranked dialogue windows into compact memory-like items."""
    items: List[Dict[str, Any]] = []
    for window in windows:
        text = str(window.get("window_text") or "").strip()
        if not text:
            continue
        center = window.get("center_turn") or {}
        speaker = str(center.get("entity_name") or center.get("speaker_role") or "dialogue").strip()
        items.append(
            {
                "content": f"{speaker} context: {text}",
                "source": "conversation_window",
                "speaker_role": center.get("speaker_role"),
                "entity_name": center.get("entity_name"),
                "conversation_id": center.get("conversation_id"),
                "turn_index": center.get("turn_index"),
                "timestamp": center.get("timestamp"),
            }
        )
    return items
