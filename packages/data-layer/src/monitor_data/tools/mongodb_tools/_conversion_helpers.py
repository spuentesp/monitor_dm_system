"""
Shared document conversion helpers for MongoDB tools.

DRY: Common patterns for converting MongoDB documents to Pydantic responses.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, TypeVar
from uuid import UUID

T = TypeVar("T")


def coerce_uuid(value: Any) -> UUID | None:
    """Coerce a value to UUID, returning None if not valid."""
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def coerce_datetime(value: Any) -> datetime:
    """Coerce a value to datetime, returning epoch if not valid."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.min
    return datetime.min


def convert_field(
    doc: dict[str, Any],
    key: str,
    *,
    coercer: Callable[[Any], T] = lambda x: x,
    default: T | None = None,
) -> T | None:
    """Extract and coerce a field from a document, returning default if missing."""
    value = doc.get(key, default)
    if value is None:
        return default
    try:
        return coercer(value)
    except (TypeError, ValueError):
        return default


def convert_uuid_field(doc: dict[str, Any], key: str) -> UUID | None:
    """Extract a UUID field from a document."""
    return coerce_uuid(doc.get(key))


def convert_list_of_uuids(doc: dict[str, Any], key: str) -> list[UUID]:
    """Extract a list of UUIDs from a document."""
    return [r for r in [coerce_uuid(v) for v in doc.get(key, [])] if r is not None]


def convert_list(
    doc: dict[str, Any],
    key: str,
    *,
    mapper: Callable[[Any], Any],
) -> list[Any]:
    """Extract a list and map each element through a converter."""
    return [mapper(v) for v in doc.get(key, [])]


def apply_legacy_type_map(
    raw_type: str,
    legacy_map: dict[str, str],
    default: str,
) -> str:
    """Normalize a legacy type string using a mapping dict."""
    return legacy_map.get(raw_type, raw_type if raw_type else default)


# =============================================================================
# GENERIC DOCUMENT → RESPONSE CONVERTER
# =============================================================================


def document_to_response(
    doc: dict[str, Any],
    response_cls: type[T],
    *,
    uuid_fields: list[str],
    datetime_fields: list[str] | None = None,
    optional_uuid_fields: list[str] | None = None,
    nested_converters: dict[str, Callable[[Any], Any]] | None = None,
    field_renames: dict[str, str] | None = None,
    legacy_type_field: str | None = None,
    legacy_type_map: dict[str, str] | None = None,
    default_type: str | None = None,
) -> T:
    """
    Generic document-to-response converter.

    Args:
        doc: MongoDB document dict
        response_cls: Pydantic response class to instantiate
        uuid_fields: Fields that are UUIDs
        datetime_fields: Fields that are datetimes
        optional_uuid_fields: Fields that are optional UUIDs
        nested_converters: Dict of {field: converter_fn} for nested conversions
        field_renames: Dict of {old_name: new_name} for field renaming
        legacy_type_field: Field name containing legacy type to normalize
        legacy_type_map: Legacy type mapping dict
        default_type: Default type if legacy field is empty

    Returns:
        Instantiated response class
    """
    # Handle field renames
    if optional_uuid_fields is None:
        optional_uuid_fields = []
    if datetime_fields is None:
        datetime_fields = ["created_at", "updated_at"]
    data = dict(doc)
    if field_renames:
        for old, new in field_renames.items():
            if old in data:
                data[new] = data.pop(old)

    # Convert UUID fields
    for field in uuid_fields:
        if field in data:
            data[field] = coerce_uuid(data[field])

    # Convert optional UUID fields
    for field in optional_uuid_fields:
        if field in data:
            data[field] = coerce_uuid(data[field])

    # Convert datetime fields
    for field in datetime_fields:
        if data.get(field):
            data[field] = coerce_datetime(data[field])

    # Handle legacy type normalization
    if legacy_type_field and legacy_type_map:
        raw = data.get(legacy_type_field)
        data[legacy_type_field] = apply_legacy_type_map(str(raw), legacy_type_map, str(default_type or ""))

    # Apply nested converters
    if nested_converters:
        for field, converter in nested_converters.items():
            if field in data:
                value = data[field]
                if isinstance(value, list):
                    data[field] = [converter(item) for item in value]
                else:
                    data[field] = converter(value)

    return response_cls(**data)
