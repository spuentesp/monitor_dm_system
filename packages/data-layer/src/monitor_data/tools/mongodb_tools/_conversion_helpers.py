"""
Shared document conversion helpers for MongoDB tools.

DRY: Common patterns for converting MongoDB documents to Pydantic responses.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, TypeVar
from uuid import UUID

T = TypeVar("T")


def coerce_uuid(value: Any) -> Optional[UUID]:
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
    doc: Dict[str, Any],
    key: str,
    *,
    coercer: Callable[[Any], T] = lambda x: x,
    default: Optional[T] = None,
) -> Optional[T]:
    """Extract and coerce a field from a document, returning default if missing."""
    value = doc.get(key, default)
    if value is None:
        return default
    try:
        return coercer(value)
    except (TypeError, ValueError):
        return default


def convert_uuid_field(doc: Dict[str, Any], key: str) -> Optional[UUID]:
    """Extract a UUID field from a document."""
    return coerce_uuid(doc.get(key))


def convert_list_of_uuids(doc: Dict[str, Any], key: str) -> List[UUID]:
    """Extract a list of UUIDs from a document."""
    return [r for r in [coerce_uuid(v) for v in doc.get(key, [])] if r is not None]


def convert_list(
    doc: Dict[str, Any],
    key: str,
    *,
    mapper: Callable[[Any], Any],
) -> List[Any]:
    """Extract a list and map each element through a converter."""
    return [mapper(v) for v in doc.get(key, [])]


def apply_legacy_type_map(
    raw_type: str,
    legacy_map: Dict[str, str],
    default: str,
) -> str:
    """Normalize a legacy type string using a mapping dict."""
    return legacy_map.get(raw_type, raw_type if raw_type else default)


# =============================================================================
# GENERIC DOCUMENT → RESPONSE CONVERTER
# =============================================================================


def document_to_response(
    doc: Dict[str, Any],
    response_cls: type[T],
    *,
    uuid_fields: List[str],
    datetime_fields: List[str] = ["created_at", "updated_at"],
    optional_uuid_fields: List[str] = [],
    nested_converters: Optional[Dict[str, Callable[[Any], Any]]] = None,
    field_renames: Optional[Dict[str, str]] = None,
    legacy_type_field: Optional[str] = None,
    legacy_type_map: Optional[Dict[str, str]] = None,
    default_type: Optional[str] = None,
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
        if field in data and data[field]:
            data[field] = coerce_datetime(data[field])

    # Handle legacy type normalization
    if legacy_type_field and legacy_type_map:
        raw = data.get(legacy_type_field)
        data[legacy_type_field] = apply_legacy_type_map(raw, legacy_type_map, default_type or "")

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
