"""
Tests for validation middleware.

Tests Pydantic schema validation for tool inputs.
"""

import pytest
from uuid import uuid4, UUID
from pydantic import BaseModel, Field
from monitor_data.middleware.validation import (
    validate_tool_input,
    ValidationError,
    get_validation_error_response,
)


# =============================================================================
# TEST SCHEMAS
# =============================================================================


class SimpleRequest(BaseModel):
    """Test schema with simple fields."""

    name: str
    count: int
    enabled: bool = False


class UUIDRequest(BaseModel):
    """Test schema with UUID fields."""

    entity_id: UUID
    universe_id: UUID


class NestedRequest(BaseModel):
    """Test schema with nested structure."""

    title: str
    metadata: dict
    tags: list = Field(default_factory=list)


# =============================================================================
# SIMPLE TYPE VALIDATION TESTS
# =============================================================================


def test_validate_simple_types_valid():
    """Test validation with simple types passes for valid input."""

    def test_tool(params: SimpleRequest) -> str:
        return "success"

    # MCP format: arguments wrapped in parameter name
    arguments = {"params": {"name": "test", "count": 5, "enabled": True}}

    result = validate_tool_input("test_tool", test_tool, arguments)

    # Validation preserves parameter name
    assert "params" in result
    assert result["params"].name == "test"
    assert result["params"].count == 5
    assert result["params"].enabled is True


def test_validate_simple_types_missing_required():
    """Test validation fails for missing required field."""

    def test_tool(params: SimpleRequest) -> str:
        return "success"

    # MCP format: arguments wrapped in parameter name, but missing required field
    arguments = {"params": {"count": 5}}  # Missing 'name'

    with pytest.raises(ValidationError) as exc_info:
        validate_tool_input("test_tool", test_tool, arguments)

    error = exc_info.value
    assert error.tool_name == "test_tool"
    assert len(error.errors) > 0


def test_validate_simple_types_wrong_type():
    """Test validation fails for wrong type."""

    def test_tool(params: SimpleRequest) -> str:
        return "success"

    # MCP format: arguments wrapped in parameter name, but with wrong type
    arguments = {"params": {"name": "test", "count": "not_a_number"}}  # Wrong type

    with pytest.raises(ValidationError) as exc_info:
        validate_tool_input("test_tool", test_tool, arguments)

    error = exc_info.value
    assert error.tool_name == "test_tool"


def test_validate_with_defaults():
    """Test validation uses default values correctly."""

    def test_tool(params: SimpleRequest) -> str:
        return "success"

    # MCP format: arguments wrapped in parameter name
    arguments = {"params": {"name": "test", "count": 5}}  # No 'enabled'

    result = validate_tool_input("test_tool", test_tool, arguments)

    # Check default value in validated object
    assert result["params"].enabled is False  # Default value


# =============================================================================
# UUID VALIDATION TESTS
# =============================================================================


def test_validate_uuid_valid():
    """Test validation with valid UUIDs."""

    def test_tool(params: UUIDRequest) -> str:
        return "success"

    entity_id = uuid4()
    universe_id = uuid4()

    # MCP format: arguments wrapped in parameter name
    arguments = {
        "params": {"entity_id": str(entity_id), "universe_id": str(universe_id)}
    }

    result = validate_tool_input("test_tool", test_tool, arguments)

    # Result should contain validated object with UUID fields
    assert "params" in result
    assert isinstance(result["params"].entity_id, UUID)
    assert isinstance(result["params"].universe_id, UUID)
    assert result["params"].entity_id == entity_id
    assert result["params"].universe_id == universe_id


def test_validate_uuid_invalid():
    """Test validation fails for invalid UUID."""

    def test_tool(params: UUIDRequest) -> str:
        return "success"

    # MCP format: arguments wrapped in parameter name
    arguments = {"params": {"entity_id": "not-a-uuid", "universe_id": str(uuid4())}}

    with pytest.raises(ValidationError) as exc_info:
        validate_tool_input("test_tool", test_tool, arguments)

    error = exc_info.value
    assert error.tool_name == "test_tool"


# =============================================================================
# NESTED STRUCTURE VALIDATION TESTS
# =============================================================================


def test_validate_nested_structure():
    """Test validation with nested structures."""

    def test_tool(params: NestedRequest) -> str:
        return "success"

    # MCP format: arguments wrapped in parameter name
    arguments = {
        "params": {
            "title": "Test",
            "metadata": {"key": "value"},
            "tags": ["tag1", "tag2"],
        }
    }

    result = validate_tool_input("test_tool", test_tool, arguments)

    # Result should contain validated object
    assert "params" in result
    assert result["params"].title == "Test"
    assert result["params"].metadata == {"key": "value"}
    assert result["params"].tags == ["tag1", "tag2"]


# =============================================================================
# NO SCHEMA VALIDATION TESTS
# =============================================================================


def test_validate_no_schema_passes_through():
    """Test validation passes through when no Pydantic schema."""

    def test_tool(name: str, count: int) -> str:
        return "success"

    arguments = {"name": "test", "count": 5}

    result = validate_tool_input("test_tool", test_tool, arguments)

    assert result["name"] == "test"
    assert result["count"] == 5


def test_validate_no_type_hints():
    """Test validation passes through when no type hints."""

    def test_tool(x, y):  # No type hints
        return "success"

    arguments = {"x": 1, "y": 2}

    result = validate_tool_input("test_tool", test_tool, arguments)

    assert result == arguments


# =============================================================================
# ERROR RESPONSE TESTS
# =============================================================================


def test_get_validation_error_response_format():
    """Test validation error response has correct format."""
    error = ValidationError(
        "test_tool", [{"loc": ("field",), "msg": "Field required", "type": "missing"}]
    )

    response = get_validation_error_response(error)

    assert response["error"] is True
    assert response["code"] == "VALIDATION_ERROR"
    assert "message" in response
    assert "details" in response
    assert response["details"] == error.errors


def test_validation_error_string_representation():
    """Test ValidationError has informative string representation."""
    errors = [
        {"loc": ("name",), "msg": "Field required"},
        {"loc": ("count",), "msg": "Not an integer"},
    ]

    error = ValidationError("test_tool", errors)

    error_str = str(error)
    assert "test_tool" in error_str
    assert "name" in error_str
    assert "count" in error_str
