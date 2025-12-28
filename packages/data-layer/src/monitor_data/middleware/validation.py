"""
Validation middleware for MONITOR Data Layer.

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only
CALLED BY: MCP server (server.py)

This middleware validates all incoming requests against Pydantic schemas
before they reach the database clients or tool implementations.
"""

from typing import Any, Dict, Type, TypeVar
from pydantic import BaseModel, ValidationError


T = TypeVar("T", bound=BaseModel)


class RequestValidationError(Exception):
    """Raised when request validation fails."""

    def __init__(self, errors: list[Dict[str, Any]]):
        self.errors = errors
        error_messages = []
        for error in errors:
            loc = " -> ".join(str(l) for l in error.get("loc", []))
            msg = error.get("msg", "Unknown error")
            error_messages.append(f"{loc}: {msg}")
        
        super().__init__(
            f"Request validation failed: {'; '.join(error_messages)}"
        )


def validate_request(schema: Type[T], data: Dict[str, Any]) -> T:
    """
    Validate request data against a Pydantic schema.

    Args:
        schema: Pydantic model class to validate against
        data: Request data dictionary

    Returns:
        Validated Pydantic model instance

    Raises:
        RequestValidationError: If validation fails

    Examples:
        >>> from monitor_data.schemas.universe import UniverseCreate
        >>> data = {"name": "Test", "multiverse_id": "uuid", ...}
        >>> validated = validate_request(UniverseCreate, data)
        >>> assert isinstance(validated, UniverseCreate)
    """
    try:
        return schema(**data)
    except ValidationError as e:
        raise RequestValidationError(e.errors()) from e


def validate_response(schema: Type[T], data: Any) -> T:
    """
    Validate response data against a Pydantic schema.

    This is primarily used for internal validation to ensure
    tool implementations return correctly structured data.

    Args:
        schema: Pydantic model class to validate against
        data: Response data (can be dict or Pydantic model)

    Returns:
        Validated Pydantic model instance

    Raises:
        RequestValidationError: If validation fails

    Examples:
        >>> from monitor_data.schemas.universe import UniverseResponse
        >>> data = {"id": "uuid", "name": "Test", ...}
        >>> validated = validate_response(UniverseResponse, data)
    """
    try:
        # If already a Pydantic model, validate it
        if isinstance(data, BaseModel):
            return schema(**data.model_dump())
        # Otherwise treat as dict
        return schema(**data)
    except ValidationError as e:
        raise RequestValidationError(e.errors()) from e
