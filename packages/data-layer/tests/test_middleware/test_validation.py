"""
Unit tests for validation middleware.

Tests cover:
- validate_request with valid data
- validate_request with invalid data
- validate_response with valid data
- validate_response with invalid data
- RequestValidationError formatting
"""

import pytest
from uuid import uuid4
from pydantic import BaseModel, Field

from monitor_data.middleware.validation import (
    validate_request,
    validate_response,
    RequestValidationError,
)


# =============================================================================
# TEST MODELS
# =============================================================================


class TestModel(BaseModel):
    """Test Pydantic model for validation tests."""

    name: str
    value: int
    optional: str = "default"


class NestedModel(BaseModel):
    """Test nested Pydantic model."""

    id: str
    data: TestModel


# =============================================================================
# TESTS: validate_request
# =============================================================================


def test_validate_request_valid_data():
    """validate_request accepts valid data."""
    data = {"name": "test", "value": 42}
    result = validate_request(TestModel, data)
    
    assert isinstance(result, TestModel)
    assert result.name == "test"
    assert result.value == 42
    assert result.optional == "default"


def test_validate_request_with_optional():
    """validate_request accepts valid data with optional field."""
    data = {"name": "test", "value": 42, "optional": "custom"}
    result = validate_request(TestModel, data)
    
    assert result.optional == "custom"


def test_validate_request_missing_required():
    """validate_request raises on missing required field."""
    data = {"name": "test"}  # missing 'value'
    
    with pytest.raises(RequestValidationError) as exc_info:
        validate_request(TestModel, data)
    
    assert "validation failed" in str(exc_info.value).lower()
    assert len(exc_info.value.errors) > 0


def test_validate_request_wrong_type():
    """validate_request raises on wrong type."""
    data = {"name": "test", "value": "not_an_int"}
    
    with pytest.raises(RequestValidationError) as exc_info:
        validate_request(TestModel, data)
    
    assert len(exc_info.value.errors) > 0


def test_validate_request_nested_valid():
    """validate_request handles nested models."""
    data = {
        "id": str(uuid4()),
        "data": {"name": "nested", "value": 100},
    }
    result = validate_request(NestedModel, data)
    
    assert isinstance(result, NestedModel)
    assert isinstance(result.data, TestModel)
    assert result.data.name == "nested"


def test_validate_request_nested_invalid():
    """validate_request raises on invalid nested data."""
    data = {
        "id": str(uuid4()),
        "data": {"name": "nested"},  # missing 'value'
    }
    
    with pytest.raises(RequestValidationError) as exc_info:
        validate_request(NestedModel, data)
    
    assert len(exc_info.value.errors) > 0


def test_validate_request_extra_fields():
    """validate_request ignores extra fields by default."""
    data = {"name": "test", "value": 42, "extra": "ignored"}
    result = validate_request(TestModel, data)
    
    assert result.name == "test"
    assert result.value == 42
    assert not hasattr(result, "extra")


# =============================================================================
# TESTS: validate_response
# =============================================================================


def test_validate_response_with_dict():
    """validate_response accepts dict data."""
    data = {"name": "test", "value": 42}
    result = validate_response(TestModel, data)
    
    assert isinstance(result, TestModel)
    assert result.name == "test"
    assert result.value == 42


def test_validate_response_with_model():
    """validate_response accepts Pydantic model."""
    original = TestModel(name="test", value=42)
    result = validate_response(TestModel, original)
    
    assert isinstance(result, TestModel)
    assert result.name == "test"
    assert result.value == 42


def test_validate_response_invalid_dict():
    """validate_response raises on invalid dict."""
    data = {"name": "test"}  # missing 'value'
    
    with pytest.raises(RequestValidationError):
        validate_response(TestModel, data)


def test_validate_response_invalid_model():
    """validate_response validates model structure."""
    # Create a model with different structure
    class OtherModel(BaseModel):
        other_field: str
    
    original = OtherModel(other_field="test")
    
    with pytest.raises(RequestValidationError):
        validate_response(TestModel, original)


# =============================================================================
# TESTS: RequestValidationError
# =============================================================================


def test_request_validation_error_message():
    """RequestValidationError formats error message correctly."""
    try:
        validate_request(TestModel, {"name": "test"})
    except RequestValidationError as e:
        assert "validation failed" in str(e).lower()
        assert len(e.errors) > 0
        assert isinstance(e.errors, list)


def test_request_validation_error_multiple():
    """RequestValidationError handles multiple validation errors."""
    try:
        validate_request(TestModel, {})  # missing both required fields
    except RequestValidationError as e:
        # Should have errors for both 'name' and 'value'
        assert len(e.errors) >= 2


def test_request_validation_error_location():
    """RequestValidationError includes field location in message."""
    try:
        validate_request(
            NestedModel, {"id": "test", "data": {"name": "test"}}
        )  # nested missing value
    except RequestValidationError as e:
        error_str = str(e)
        # Error message should include location path
        assert "data" in error_str.lower() or "value" in error_str.lower()


# =============================================================================
# TESTS: Edge cases
# =============================================================================


def test_validate_empty_dict():
    """validate_request handles empty dict."""
    
    class EmptyModel(BaseModel):
        pass
    
    result = validate_request(EmptyModel, {})
    assert isinstance(result, EmptyModel)


def test_validate_with_defaults():
    """validate_request uses default values."""
    
    class DefaultModel(BaseModel):
        field1: str = "default1"
        field2: int = 42
    
    result = validate_request(DefaultModel, {})
    assert result.field1 == "default1"
    assert result.field2 == 42


def test_validate_with_field_validator():
    """validate_request runs Pydantic validators."""
    
    class ValidatedModel(BaseModel):
        positive_value: int = Field(..., gt=0)
    
    # Valid data
    result = validate_request(ValidatedModel, {"positive_value": 10})
    assert result.positive_value == 10
    
    # Invalid data (not positive)
    with pytest.raises(RequestValidationError):
        validate_request(ValidatedModel, {"positive_value": -5})
