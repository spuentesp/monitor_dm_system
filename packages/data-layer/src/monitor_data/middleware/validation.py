"""
Validation middleware for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (pydantic)
CALLED BY: MCP server (server.py)

This middleware validates all tool inputs against Pydantic schemas
before execution to ensure type safety and data integrity.
"""

import logging
from typing import Any, Callable, Dict, get_type_hints, get_args, get_origin
from uuid import UUID
from pydantic import BaseModel, ValidationError as PydanticValidationError

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when tool input validation fails."""

    def __init__(self, tool_name: str, errors: list):
        self.tool_name = tool_name
        self.errors = errors
        error_messages = [
            f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}"
            for err in errors
        ]
        super().__init__(
            f"Validation failed for '{tool_name}': {'; '.join(error_messages)}"
        )


def validate_tool_input(
    tool_name: str, tool_function: Callable, arguments: Dict[str, Any]
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

    Examples:
        >>> def my_tool(params: MyRequest) -> MyResponse:
        ...     pass
        >>> validate_tool_input("my_tool", my_tool, {"params": {"field": "value"}})
        {'params': <MyRequest object>}
    """
    try:
        # Get type hints from the function
        hints = get_type_hints(tool_function)

        if not hints:
            # No type hints, can't validate - return as is
            logger.warning(
                f"No type hints found for tool '{tool_name}', skipping validation"
            )
            return arguments

        # Find the first parameter that's a BaseModel (should be the request schema)
        # IMPORTANT: Preserve the parameter name (e.g., "params") for correct function calls
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

        if param_schema is None:
            # Function doesn't use Pydantic schema - validate simple types
            return _validate_simple_types(tool_name, hints, arguments)

        # Validate using Pydantic schema
        # Extract the parameter value from arguments using the parameter name
        try:
            if param_name not in arguments:
                raise ValidationError(
                    tool_name,
                    [{"loc": (param_name,), "msg": "Required parameter missing"}],
                )

            param_value = arguments[param_name]

            # Validate the parameter value against the schema
            validated_obj = param_schema(**param_value)

            # Return with parameter name preserved (critical for function calls!)
            return {param_name: validated_obj}

        except PydanticValidationError as e:
            # Prefix error locations with parameter name
            errors = [
                {"loc": (param_name,) + tuple(err["loc"]), "msg": err["msg"]}
                for err in e.errors()
            ]
            raise ValidationError(tool_name, errors)

    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Validation error for tool '{tool_name}': {e}")
        raise ValidationError(tool_name, [{"msg": str(e), "loc": ("validation",)}])


def _validate_simple_types(
    tool_name: str, hints: Dict[str, Any], arguments: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate arguments against simple type hints (str, int, UUID, etc.).

    Args:
        tool_name: Name of the tool
        hints: Type hints dictionary
        arguments: Input arguments

    Returns:
        Validated arguments

    Raises:
        ValidationError: If type validation fails
    """

    errors = []
    validated: Dict[str, Any] = {}

    # Check for missing required parameters (Comment 5 fix)
    for hint_key, hint_type in hints.items():
        if hint_key == "return":
            continue

        # Check if parameter is required (no default value)
        # Get function signature to check for defaults
        # This requires the function object, which we don't have here
        # For now, assume all parameters not provided are required
        if hint_key not in arguments:
            # Check if Optional type (means not required)
            origin = get_origin(hint_type)
            if origin is not None:
                # Could be Optional - skip required check
                continue

            errors.append({"loc": (hint_key,), "msg": "Required parameter missing"})

    for key, value in arguments.items():
        if key not in hints:
            # Extra argument not in function signature
            errors.append(
                {"loc": (key,), "msg": "Extra argument not in function signature"}
            )
            continue

        expected_type = hints[key]

        # Handle UUID type specially
        if expected_type == UUID:  # Comment 6 fix: removed "UUID" string comparison
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
                errors.append(
                    {"loc": (key,), "msg": f"Expected UUID, got {type(value).__name__}"}
                )
                continue

        # Basic type checking
        origin = get_origin(expected_type)
        if origin is None:
            # Simple type like str, int, bool
            # Comment 7 suggestion: check if expected_type is a valid type
            if isinstance(expected_type, type):
                if not isinstance(value, expected_type):
                    errors.append(
                        {
                            "loc": (key,),
                            "msg": f"Expected {expected_type.__name__}, got {type(value).__name__}",
                        }
                    )
                    continue
                validated[key] = value
            else:
                # Annotation is not a concrete type; pass through
                validated[key] = value
        else:
            # Complex type like Optional, List, etc. - just pass through
            validated[key] = value

    if errors:
        raise ValidationError(tool_name, errors)

    return validated


def get_validation_error_response(error: ValidationError) -> Dict[str, Any]:
    """
    Convert ValidationError to MCP error response format.

    Args:
        error: ValidationError exception

    Returns:
        Error response dict in MCP format

    Examples:
        >>> err = ValidationError("my_tool", [{"loc": ("field",), "msg": "required"}])
        >>> get_validation_error_response(err)
        {'error': True, 'code': 'VALIDATION_ERROR', 'message': '...', 'details': [...]}
    """
    return {
        "error": True,
        "code": "VALIDATION_ERROR",
        "message": str(error),
        "details": error.errors,
    }
