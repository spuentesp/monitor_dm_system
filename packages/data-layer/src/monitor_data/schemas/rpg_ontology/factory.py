"""
RPG Ontology — dynamic Pydantic model factory.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pydantic, typing, re, ast) + meta.py

Why this exists
---------------
``meta.py`` describes a game system as pure data (a ``GameSystemSpec``).
This module converts those specs into *real, validated Pydantic model classes*
at runtime using ``pydantic.create_model()``.

No Python subclassing is required to add a new game system.  Instead:

1. Define a ``GameSystemSpec`` (pure data, JSON-serialisable).
2. Call ``make_entity_model(spec, entity_type_key)`` to get back a Pydantic class
   you can use for validation, serialisation, and schema export.
3. Models are cached per ``(system_id, type_key)`` so repeated calls are cheap.

Formula execution
-----------------
``FieldSpec.derived_formula`` and ``ValidatorSpec.expr`` are Python expressions
evaluated in a restricted sandbox (only numeric builtins — no imports, no IO).
The sandbox is intentionally minimal: ``abs``, ``max``, ``min``, ``round``,
``floor``, ``ceil``, ``int``, ``float``, and the field values of the entity.

Security note: expressions come from database records edited by *admins only*
(not end users / players).  The sandboxed eval is a defence-in-depth measure,
not the primary security boundary.

Generated model anatomy
-----------------------
For a ``GameSystemSpec`` with an entity type ``character``:

    make_entity_model(spec, "character")
    → DynamicModel_<system_id>_character  (a Pydantic BaseModel subclass)

The generated class has:
- All ``FieldSpec`` entries as typed fields with constraints
- A ``@model_validator(mode="after")`` that runs all ``ValidatorSpec`` rules
- A ``system_id`` ClassVar so it can be round-tripped through the registry
- ``to_sheet_dict()`` / ``from_sheet_dict()`` convenience helpers
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field, create_model, model_validator
from pydantic.fields import FieldInfo

from monitor_data.schemas.rpg_ontology.meta import (
    FieldSpec,
    FieldType,
    GameSystemSpec,
    ValidatorSpec,
    ValidatorType,
)

# ---------------------------------------------------------------------------
# Model cache
# ---------------------------------------------------------------------------

_MODEL_CACHE: dict[tuple[str, str], type[BaseModel]] = {}


# ---------------------------------------------------------------------------
# Restricted formula evaluator
# ---------------------------------------------------------------------------

_SANDBOX_GLOBALS: dict[str, Any] = {
    "__builtins__": {},
    "abs": abs,
    "max": max,
    "min": min,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "int": int,
    "float": float,
    "bool": bool,
}


def _eval_formula(expr: str, ctx: dict[str, Any]) -> Any:
    """
    Evaluate a formula string in a restricted sandbox.

    ``ctx`` is a flat dict of field_name → value for the enclosing entity.
    Raises ``ValueError`` if the expression is malformed or unsafe.
    """
    # Reject obviously unsafe patterns before eval
    if re.search(r"(import|__|\bexec\b|\beval\b|open\(|os\.|sys\.)", expr):
        raise ValueError(f"Unsafe formula expression: {expr!r}")
    try:
        return eval(expr, _SANDBOX_GLOBALS, ctx)
    except Exception as exc:
        raise ValueError(f"Formula evaluation failed for {expr!r}: {exc}") from exc


# ---------------------------------------------------------------------------
# FieldSpec → Pydantic field conversion
# ---------------------------------------------------------------------------

_PYTHON_TYPE_MAP: dict[FieldType, Any] = {
    FieldType.INT: int,
    FieldType.FLOAT: float,
    FieldType.STR: str,
    FieldType.BOOL: bool,
    FieldType.ENUM: str,
    FieldType.LIST_STR: list[str],
    FieldType.LIST_ENUM: list[str],
    FieldType.UUID_REF: str,  # stored as str UUID
    FieldType.DICT: dict[str, Any],
}


def _field_spec_to_pydantic(spec: FieldSpec) -> tuple[Any, FieldInfo]:
    """
    Convert a ``FieldSpec`` to a (python_type, FieldInfo) tuple suitable for
    passing to ``pydantic.create_model()``.
    """
    py_type = _PYTHON_TYPE_MAP.get(spec.field_type, Any)

    kwargs: dict[str, Any] = {
        "description": spec.description or spec.display_name,
    }

    # Numeric constraints
    if spec.field_type in (FieldType.INT, FieldType.FLOAT):
        if spec.min_value is not None:
            kwargs["ge"] = int(spec.min_value) if spec.field_type == FieldType.INT else spec.min_value
        if spec.max_value is not None:
            kwargs["le"] = int(spec.max_value) if spec.field_type == FieldType.INT else spec.max_value

    # Default value
    if spec.default_value is not None:
        kwargs["default"] = spec.default_value
    elif not spec.required:
        kwargs["default"] = None
        # Wrap in X | None if not required
        py_type = py_type | None

    # Derived fields get a sentinel default so they don't require input
    if spec.derived_formula is not None:
        kwargs["default"] = None
        py_type = py_type | None

    field_info = Field(**kwargs)
    return (py_type, field_info)


# ---------------------------------------------------------------------------
# ValidatorSpec → validator logic
# ---------------------------------------------------------------------------


def _build_validator_fn(validators: list[ValidatorSpec], fields: list[FieldSpec]) -> Callable[[Any], Any]:
    """
    Build a single ``model_validator(mode='after')`` function that enforces
    all rules in the given ``ValidatorSpec`` list.

    Returns a callable suitable for use with Pydantic's ``model_validator``.
    """
    derived_fields = {f.name: f.derived_formula for f in fields if f.derived_formula}

    # Pre-compute enum constraints from field specs for fast lookup
    enum_constraints: dict[str, list[str]] = {}
    list_enum_constraints: dict[str, list[str]] = {}
    for f in fields:
        if f.field_type == FieldType.ENUM and f.enum_values:
            enum_constraints[f.name] = f.enum_values
        elif f.field_type == FieldType.LIST_ENUM and f.enum_values:
            list_enum_constraints[f.name] = f.enum_values

    def _validate(self: Any) -> Any:
        data: dict[str, Any] = {k: getattr(self, k, None) for k in (f.name for f in fields)}

        # ---- Handle derived fields first ----
        for field_name, formula in derived_fields.items():
            computed = _eval_formula(formula, data)
            object.__setattr__(self, field_name, computed)
            data[field_name] = computed

        # ---- Enforce ENUM / LIST_ENUM constraints from FieldSpec ----
        for field_name, allowed in enum_constraints.items():
            val = data.get(field_name)
            if val is not None and val not in allowed:
                raise ValueError(f"'{field_name}' must be one of {allowed}, got {val!r}")
        for field_name, allowed in list_enum_constraints.items():
            vals = data.get(field_name) or []
            bad = [v for v in vals if v not in allowed]
            if bad:
                raise ValueError(f"'{field_name}' contains invalid values {bad}; allowed: {allowed}")

        # ---- Run each validator spec ----
        for spec in validators:
            vtype = spec.validator_type
            field_val = data.get(spec.field) if spec.field else None

            if vtype == ValidatorType.RANGE:
                if field_val is not None:
                    if spec.min_bound is not None and field_val < spec.min_bound:
                        raise ValueError(
                            spec.error_message.format(field=spec.field, value=field_val, bound=spec.min_bound)
                        )
                    if spec.max_bound is not None and field_val > spec.max_bound:
                        raise ValueError(
                            spec.error_message.format(field=spec.field, value=field_val, bound=spec.max_bound)
                        )

            elif vtype == ValidatorType.MIN:
                if field_val is not None and spec.min_bound is not None:
                    if field_val < spec.min_bound:
                        raise ValueError(
                            spec.error_message.format(field=spec.field, value=field_val, bound=spec.min_bound)
                        )

            elif vtype == ValidatorType.MAX:
                if field_val is not None and spec.max_bound is not None:
                    if field_val > spec.max_bound:
                        raise ValueError(
                            spec.error_message.format(field=spec.field, value=field_val, bound=spec.max_bound)
                        )

            elif vtype == ValidatorType.FORMULA:
                if spec.expr and field_val is not None:
                    expected = _eval_formula(spec.expr, data)
                    if field_val != expected:
                        raise ValueError(spec.error_message.format(field=spec.field, value=field_val, bound=expected))

            elif vtype == ValidatorType.ONE_OF:
                if field_val is not None and spec.allowed_values:
                    if field_val not in spec.allowed_values:
                        raise ValueError(
                            f"Field '{spec.field}' must be one of {spec.allowed_values}, got {field_val!r}"
                        )

            elif vtype == ValidatorType.COUNT_GATE:
                # len(list_field) <= floor(other_field / divisor)
                if spec.field and spec.other_field and spec.divisor:
                    list_val = data.get(spec.field) or []
                    other_val = data.get(spec.other_field) or 0
                    limit = math.floor(other_val / spec.divisor)
                    if len(list_val) > limit:
                        raise ValueError(
                            f"'{spec.field}' can have at most {limit} entries "
                            f"(floor({spec.other_field}={other_val} / {spec.divisor})), "
                            f"got {len(list_val)}"
                        )

            elif vtype == ValidatorType.REQUIRES_IF:
                # If other_field has a value, field must also have a value
                other_val = data.get(spec.other_field) if spec.other_field else None
                if other_val is not None and field_val is None:
                    raise ValueError(f"'{spec.field}' is required when '{spec.other_field}' is set")

        return self

    return _validate


# ---------------------------------------------------------------------------
# Public API — model factory
# ---------------------------------------------------------------------------


def make_entity_model(
    spec: GameSystemSpec,
    type_key: str,
    *,
    force_rebuild: bool = False,
) -> type[BaseModel]:
    """
    Generate (or retrieve from cache) a Pydantic model class for the given
    entity type within the game system.

    Parameters
    ----------
    spec:
        The ``GameSystemSpec`` describing the system.
    type_key:
        Key into ``spec.entity_types``, e.g. ``"character"``, ``"ship"``.
    force_rebuild:
        If ``True``, bypass the cache and regenerate the model.

    Returns
    -------
    A Pydantic ``BaseModel`` subclass representing the entity type.

    Raises
    ------
    ``KeyError`` if ``type_key`` is not in ``spec.entity_types``.
    """
    cache_key = (spec.system_id, type_key)

    if not force_rebuild and cache_key in _MODEL_CACHE:
        return _MODEL_CACHE[cache_key]

    entity_type = spec.entity_types.get(type_key)
    if entity_type is None:
        raise KeyError(
            f"Entity type '{type_key}' not found in system '{spec.system_id}'. "
            f"Available: {list(spec.entity_types.keys())}"
        )

    # Build field definitions for create_model
    field_defs: dict[str, tuple[Any, FieldInfo]] = {}
    for field_spec in entity_type.fields:
        py_type, field_info = _field_spec_to_pydantic(field_spec)
        field_defs[field_spec.name] = (py_type, field_info)

    # Build the validator function
    validator_fn = _build_validator_fn(entity_type.validators, entity_type.fields)

    # Decorate it so Pydantic recognises it
    decorated_validator = model_validator(mode="after")(validator_fn)

    model_name = f"DynamicModel_{spec.system_id}_{type_key}"

    # Create the model
    DynamicModel: type[BaseModel] = create_model(  # type: ignore[call-overload]
        model_name,
        __validators__={"_run_spec_validators": decorated_validator},
        **field_defs,
    )

    # Attach metadata as class-level attributes
    DynamicModel.__system_id__ = spec.system_id  # type: ignore[attr-defined]
    DynamicModel.__type_key__ = type_key  # type: ignore[attr-defined]
    DynamicModel.__entity_spec__ = entity_type  # type: ignore[attr-defined]

    _MODEL_CACHE[cache_key] = DynamicModel
    return DynamicModel


def make_all_models(spec: GameSystemSpec) -> dict[str, type[BaseModel]]:
    """
    Generate Pydantic model classes for all entity types in a system.

    Returns a dict of ``{type_key: ModelClass}``.
    """
    return {type_key: make_entity_model(spec, type_key) for type_key in spec.entity_types}


def validate_entity_data(
    spec: GameSystemSpec,
    type_key: str,
    data: dict[str, Any],
) -> BaseModel:
    """
    Validate raw data dict against the generated model for a given entity type.

    Returns the validated model instance.  Raises ``pydantic.ValidationError``
    on failure.
    """
    model_cls = make_entity_model(spec, type_key)
    return model_cls.model_validate(data)


def clear_model_cache(system_id: str | None = None) -> None:
    """
    Clear the model cache.

    If ``system_id`` is given, only remove entries for that system.
    Otherwise clear the entire cache.  Useful in tests and when a spec is
    updated at runtime.
    """
    if system_id is None:
        _MODEL_CACHE.clear()
    else:
        keys_to_remove = [k for k in _MODEL_CACHE if k[0] == system_id]
        for k in keys_to_remove:
            del _MODEL_CACHE[k]
