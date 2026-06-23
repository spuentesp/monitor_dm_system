"""
Validation middleware for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pydantic)
CALLED BY: MCP server (server.py)

This middleware validates all tool inputs against Pydantic schemas
before execution to ensure type safety and data integrity.
"""

import inspect
import logging
from typing import Any, Callable, Dict, Optional, get_args, get_origin, get_type_hints
from uuid import UUID

from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when tool input validation fails."""

    def __init__(self, tool_name: str, errors: list[dict[str, Any]]) -> None:
        self.tool_name = tool_name
        self.errors = errors
        error_messages = [
            f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in errors
        ]
        super().__init__(f"Validation failed for '{tool_name}': {'; '.join(error_messages)}")


def validate_tool_input(
    tool_name: str, tool_function: Callable[..., Any], arguments: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate tool input arguments against the function's Pydantic schema.

    Args:
        tool_name: Name of the tool being called
        tool_function: The actual function to be called
        arguments: Input arguments from MCP client

    Returns:
        Validated arguments dictionary

    Raises:
        ValidationError: If arguments don't match schema
    """
    try:
        # Get type hints from the function
        hints = get_type_hints(tool_function)

        if not hints:
            # No type hints, can't validate - return as is
            logger.warning(f"No type hints found for tool '{tool_name}', skipping validation")
            return arguments

        # Find the first parameter that's a BaseModel (should be the request schema)
        param_name = None
        param_schema = None
        for name, hint in hints.items():
            if name == "return":
                continue
            # Check if it's a BaseModel subclass
            if isinstance(hint, type) and issubclass(hint, BaseModel):
                param_name = name
                param_schema = hint
                break

        if param_schema is None:
            # Check for nested types (e.g., Optional[Schema])
            for name, hint in hints.items():
                if name == "return":
                    continue
                origin = get_origin(hint)
                if origin is not None:
                    args = get_args(hint)
                    for arg in args:
                        if isinstance(arg, type) and issubclass(arg, BaseModel):
                            param_name = name
                            param_schema = arg
                            break
                if param_schema:
                    break

        sig = inspect.signature(tool_function)

        if param_schema is None:
            # Function doesn't use Pydantic schema - validate simple types
            return _validate_simple_types(tool_name, hints, arguments, sig)

        # At this point, param_schema is not None, so param_name should also not be None
        # But mypy can't infer this, so we need to check
        if param_name is None:
            raise ValidationError(
                tool_name,
                [
                    {
                        "msg": "Could not determine parameter name for schema validation",
                        "loc": ("validation",),
                    }
                ],
            )

        # Validate using Pydantic schema
        try:
            if param_name not in arguments:
                # Check if the parameter has a default value
                param = sig.parameters.get(param_name)
                if param and param.default is not inspect.Parameter.empty:
                    param_value = param.default
                else:
                    raise ValidationError(
                        tool_name,
                        [{"loc": (param_name,), "msg": "Required parameter missing"}],
                    )
            else:
                param_value = arguments[param_name]

            # Validate the parameter value against the schema
            if isinstance(param_value, dict):
                validated_obj = param_schema(**param_value)
            else:
                # If it's already a model or other type, just use it
                validated_obj = param_value

            # Preserve any additional non-model arguments in the function signature
            other_hints = {
                name: hint for name, hint in hints.items() if name not in {"return", param_name}
            }
            other_args = {name: value for name, value in arguments.items() if name != param_name}

            validated_other_args = (
                _validate_simple_types(tool_name, other_hints, other_args, sig)
                if other_hints
                else {}
            )

            # Return with parameter name preserved
            return {**validated_other_args, param_name: validated_obj}

        except PydanticValidationError as e:
            errors = [
                {"loc": (param_name,) + tuple(err["loc"]), "msg": err["msg"]} for err in e.errors()
            ]
            raise ValidationError(tool_name, errors)

    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Validation error for tool '{tool_name}': {e}")
        raise ValidationError(tool_name, [{"msg": str(e), "loc": ("validation",)}])


def _validate_simple_types(
    tool_name: str,
    hints: Dict[str, Any],
    arguments: Dict[str, Any],
    sig: Optional[inspect.Signature] = None,
) -> Dict[str, Any]:
    """
    Validate arguments against simple type hints (str, int, UUID, etc.).

    Args:
        tool_name: Name of the tool
        hints: Type hints dictionary
        arguments: Input arguments
        sig: Optional function signature to check for defaults

    Returns:
        Validated arguments

    Raises:
        ValidationError: If type validation fails
    """
    errors = []
    validated: Dict[str, Any] = {}

    # Check for missing required parameters
    for name, hint_type in hints.items():
        if name == "return":
            continue

        if name not in arguments:
            # Check if it has a default value in the signature
            if sig and name in sig.parameters:
                param = sig.parameters[name]
                if param.default is not inspect.Parameter.empty:
                    continue

            # Check if Optional type (means not required)
            origin = get_origin(hint_type)
            if origin is not None:
                # Could be Optional - skip required check
                continue

            errors.append({"loc": (name,), "msg": "Required parameter missing"})

    for key, value in arguments.items():
        if key not in hints:
            if key == "return":
                continue
            errors.append({"loc": (key,), "msg": "Extra argument not in function signature"})
            continue

        expected_type = hints[key]

        # Handle UUID type
        if expected_type == UUID:
            if isinstance(value, str):
                try:
                    validated[key] = UUID(value)
                    continue
                except (ValueError, TypeError):
                    errors.append({"loc": (key,), "msg": "Invalid UUID format"})
                    continue
            elif isinstance(value, UUID):
                validated[key] = value
                continue
            else:
                errors.append({"loc": (key,), "msg": f"Expected UUID, got {type(value).__name__}"})
                continue

        # Basic type checking
        origin = get_origin(expected_type)
        if origin is None:
            if isinstance(expected_type, type):
                try:
                    type_ok = isinstance(value, expected_type)
                except TypeError:
                    validated[key] = value
                    continue
                if not type_ok:
                    errors.append(
                        {
                            "loc": (key,),
                            "msg": f"Expected {expected_type.__name__}, got {type(value).__name__}",
                        }
                    )
                    continue
                validated[key] = value
            else:
                validated[key] = value
        else:
            validated[key] = value

    if errors:
        raise ValidationError(tool_name, errors)

    return validated


def get_validation_error_response(error: ValidationError) -> Dict[str, Any]:
    """Convert ValidationError to MCP error response format."""
    return {
        "error": True,
        "code": "VALIDATION_ERROR",
        "message": str(error),
        "details": error.errors,
    }
