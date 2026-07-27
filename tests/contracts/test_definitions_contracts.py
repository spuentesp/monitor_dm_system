"""
Tests for Definitions Contracts.

These tests verify preconditions, postconditions, and invariants
for universe, multiverse, and entity definitions.

Use Cases: DL-1, DL-2, DL-3, DL-4
"""

from uuid import uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from monitor_data.contracts.definitions import (
    ContractResult,
    UniverseCreateContract,
)


class TestContractResult:
    """Tests for ContractResult dataclass."""

    def test_ok_result(self):
        """ContractResult.ok creates passing result."""
        result = ContractResult.ok()
        assert result.passed is True
        assert result.message == "OK"
        assert result.details == {}

    def test_ok_result_with_details(self):
        """ContractResult.ok with details."""
        result = ContractResult.ok({"key": "value"})
        assert result.passed is True
        assert result.details == {"key": "value"}

    def test_fail_result(self):
        """ContractResult.fail creates failing result."""
        result = ContractResult.fail("Test failure")
        assert result.passed is False
        assert result.message == "Test failure"
        assert result.details == {}

    def test_fail_result_with_details(self):
        """ContractResult.fail with details."""
        result = ContractResult.fail("Test failure", {"key": "value"})
        assert result.passed is False
        assert result.message == "Test failure"
        assert result.details == {"key": "value"}


class TestUniverseCreateContract:
    """Tests for UniverseCreateContract."""

    def test_preconditions_valid(self):
        """Valid universe passes preconditions."""
        contract = UniverseCreateContract(
            name="Test Universe",
            tags=["fantasy", "medieval"],
        )

        results = contract.preconditions()
        # Filter for failures only
        failures = [r for r in results if not r.passed]
        assert len(failures) == 0

    def test_preconditions_empty_name_fails(self):
        """Empty universe name fails preconditions."""
        contract = UniverseCreateContract(name="   ")

        results = contract.preconditions()
        failures = [r for r in results if not r.passed]
        assert len(failures) > 0
        assert any("empty" in f.message.lower() for f in failures)

    def test_preconditions_name_too_long_fails(self):
        """Name exceeding 200 chars - Pydantic validates during construction."""
        # Pydantic validation happens at construction time
        # So this tests that Pydantic rejects names > 200 chars
        with pytest.raises(Exception):  # Pydantic raises ValidationError
            UniverseCreateContract(name="A" * 201)

    def test_postconditions_valid(self):
        """Valid creation result passes postconditions."""
        contract = UniverseCreateContract(name="Test Universe")

        created = {"id": str(uuid4()), "name": "Test Universe"}
        results = contract.postconditions(created)

        failures = [r for r in results if not r.passed]
        assert len(failures) == 0

    def test_postconditions_missing_id_fails(self):
        """Missing id in created object fails postconditions."""
        contract = UniverseCreateContract(name="Test Universe")

        created = {"name": "Test Universe"}  # Missing id
        results = contract.postconditions(created)

        failures = [r for r in results if not r.passed]
        assert len(failures) > 0
        assert any("id" in f.message.lower() for f in failures)

    def test_postconditions_name_mismatch_fails(self):
        """Name mismatch fails postconditions."""
        contract = UniverseCreateContract(name="Test Universe")

        created = {"id": str(uuid4()), "name": "Different Name"}
        results = contract.postconditions(created)

        failures = [r for r in results if not r.passed]
        assert len(failures) > 0
        assert any("name" in f.message.lower() for f in failures)


class TestUniverseCreateContractPropertyBased:
    """Property-based tests for UniverseCreateContract."""

    @given(
        name=st.text(min_size=1, max_size=200).filter(lambda s: s.strip()),
        tags=st.lists(st.text(min_size=1, max_size=50), max_size=10),
    )
    @settings(max_examples=50)
    def test_valid_universe_names_always_pass(self, name, tags):
        """All valid names pass preconditions."""
        contract = UniverseCreateContract(name=name, tags=tags)
        results = contract.preconditions()
        failures = [r for r in results if not r.passed]
        assert len(failures) == 0

    @given(
        name=st.text(min_size=0, max_size=0).map(
            lambda x: "   "
        ),  # Empty or whitespace
    )
    @settings(max_examples=20)
    def test_whitespace_only_name_fails(self, name):
        """Whitespace-only name fails preconditions."""
        contract = UniverseCreateContract(name=name)
        results = contract.preconditions()
        failures = [r for r in results if not r.passed]
        assert len(failures) > 0

    @given(
        name=st.text(min_size=201, max_size=500),
    )
    @settings(max_examples=20)
    def test_long_name_fails(self, name):
        """Name over 200 chars - Pydantic validation catches it."""
        with pytest.raises(Exception):  # Pydantic ValidationError
            UniverseCreateContract(name=name)
