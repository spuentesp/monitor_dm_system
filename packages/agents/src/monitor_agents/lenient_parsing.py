"""Lenient validation of LLM output against pydantic schemas.

LAYER: 2 (agents)
IMPORTS FROM: pydantic, json_repair, structlog, dspy (ChatAdapter field markers)
CALLED BY: analyzer._call_module parse-failure recovery; Parts A and B batch code

Two live failures on 2026-11-10 each lost a whole extraction batch:
- ``ExtractedEntityArchetype.group_type`` came back as ``"corp"``, which is not
  a ``GroupType`` value (the model copied the Lancer ``sub_type`` into it);
- a ``list[ExtractedAxiom]`` came back with each item as a JSON string.

``lenient_validate`` repairs what the schema can tolerate — an unknown enum value
maps to the schema's ``other`` member when it has one, a JSON string where an
object is expected is parsed — and returns the repaired item plus a record of
each repair. It never swallows a value the schema cannot accept: that still
raises ``ValidationError``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import UnionType
from typing import Any, Union, get_args, get_origin

import json_repair
import structlog
from dspy import Prediction
from dspy.adapters.chat_adapter import field_header_pattern
from pydantic import BaseModel, TypeAdapter, ValidationError

log = structlog.get_logger()

_TEXT_LIMIT = 200


@dataclass(frozen=True, slots=True)
class Repair:
    """One repair made while validating leniently."""

    path: str  # e.g. "group_type", "[2]", "[2].statement"
    kind: str  # "unknown_enum" | "json_string"
    original: str
    repaired: str


def _short(text: str) -> str:
    return text if len(text) <= _TEXT_LIMIT else text[:_TEXT_LIMIT] + "..."


def _other_member(enum_cls: type[Enum]) -> Enum | None:
    for member in enum_cls:
        if str(member.value).casefold() == "other" or member.name.casefold() == "other":
            return member
    return None


def _repair_enum(value: Any, enum_cls: type[Enum], path: str, repairs: list[Repair]) -> Any:
    if not isinstance(value, str):
        return value
    by_value = {str(member.value): member for member in enum_cls}
    if value in by_value:
        return value
    target = next((member for member in enum_cls if member.name == value), None)
    if target is None:
        target = next(
            (member for member in enum_cls if str(member.value).casefold() == value.casefold()),
            None,
        )
    if target is None:
        target = _other_member(enum_cls)
    if target is None:
        return value  # No "other" member: let the schema reject it.
    repairs.append(Repair(path=path, kind="unknown_enum", original=_short(value), repaired=str(target.value)))
    return str(target.value)


def _repair(value: Any, annotation: Any, path: str, repairs: list[Repair]) -> Any:
    if value is None or annotation is Any or annotation is object:
        return value
    if hasattr(annotation, "__metadata__"):  # Annotated[T, ...]: repair against T.
        args = get_args(annotation)
        if args:
            return _repair(value, args[0], path, repairs)
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        non_none = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(non_none) == 1:
            return _repair(value, non_none[0], path, repairs)
        return value
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return _repair_enum(value, annotation, path, repairs)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if isinstance(value, str):
            parsed = json_repair.loads(value)
            if not isinstance(parsed, dict):
                return value
            repairs.append(
                Repair(
                    path=path,
                    kind="json_string",
                    original=_short(value),
                    repaired=_short(str(parsed)),
                )
            )
            value = parsed
        if isinstance(value, dict):
            out = dict(value)
            for name, field in annotation.model_fields.items():
                if name in out:
                    child = f"{path}.{name}" if path else name
                    out[name] = _repair(out[name], field.annotation, child, repairs)
            return out
        return value
    if origin in (list, tuple, set, frozenset):
        item_annotation = get_args(annotation)[0] if get_args(annotation) else Any
        if isinstance(value, str):
            parsed = json_repair.loads(value)
            if not isinstance(parsed, list):
                return value
            repairs.append(
                Repair(
                    path=path,
                    kind="json_string",
                    original=_short(value),
                    repaired=_short(str(parsed)),
                )
            )
            value = parsed
        if isinstance(value, (list, tuple, set, frozenset)):
            return [_repair(item, item_annotation, f"{path}[{index}]", repairs) for index, item in enumerate(value)]
        return value
    if origin is dict:
        value_annotation = get_args(annotation)[1] if get_args(annotation) else Any
        if isinstance(value, dict):
            return {key: _repair(item, value_annotation, f"{path}.{key}", repairs) for key, item in value.items()}
        return value
    return value


def lenient_validate(annotation: Any, payload: Any) -> tuple[Any, list[Repair]]:
    """Validate `payload` against `annotation`, repairing what lenient parsing allows.

    Returns the validated item and one Repair per change made on the way. Raises
    pydantic.ValidationError when the payload is still invalid after repair.
    """
    repairs: list[Repair] = []
    repaired = _repair(payload, annotation, "", repairs)
    value = TypeAdapter(annotation).validate_python(repaired)
    return value, repairs


def _split_chat_sections(completion: str) -> dict[str, str]:
    """Split a ChatAdapter completion into field sections, as ChatAdapter.parse does."""
    sections: list[tuple[str | None, list[str]]] = [(None, [])]
    for line in completion.splitlines():
        match = field_header_pattern.match(line.strip())
        if match:
            header = match.group(1)
            remaining_content = line[match.end() :].strip()
            sections.append((header, [remaining_content] if remaining_content else []))
        else:
            sections[-1][1].append(line)
    return {key: "\n".join(lines).strip() for key, lines in sections if key is not None}


def recover_parse_failure(exc: BaseException) -> Prediction | None:
    """Rebuild a dspy Prediction from a failed ChatAdapter parse, repairing what we can.

    This is the application point for the two live batch-loss failures: the model's
    answer is in ``exc.lm_response`` even though field validation rejected it, so
    each output field is re-validated through ``lenient_validate`` instead of the
    batch being dropped. Returns None when the reply cannot be recovered
    field-for-field, so the caller can fall back to its existing retry. Every
    repair is logged, one record each.
    """
    signature = getattr(exc, "signature", None)
    completion = getattr(exc, "lm_response", None)
    output_fields = getattr(signature, "output_fields", None)
    if not isinstance(completion, str) or not completion.strip() or not output_fields:
        return None
    sections = _split_chat_sections(completion)
    values: dict[str, Any] = {}
    repairs: list[Repair] = []
    try:
        for name, field in output_fields.items():
            if name not in sections:
                return None
            value, field_repairs = lenient_validate(field.annotation, sections[name])
            values[name] = value
            repairs.extend(
                Repair(
                    path=f"{name}{repair.path}",
                    kind=repair.kind,
                    original=repair.original,
                    repaired=repair.repaired,
                )
                for repair in field_repairs
            )
    except (ValidationError, ValueError, TypeError):
        return None
    for repair in repairs:
        log.warning(
            "lenient_parse_repair",
            path=repair.path,
            kind=repair.kind,
            original=repair.original,
            repaired=repair.repaired,
        )
    return Prediction.from_completions([values], signature=signature)
