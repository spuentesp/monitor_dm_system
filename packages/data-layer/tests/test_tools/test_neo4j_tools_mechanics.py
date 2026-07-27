"""Unit tests for neo4j_tools mechanics module."""

from unittest.mock import Mock, patch

import pytest

from monitor_data.tools.neo4j_tools.mechanics import (
    neo4j_create_ability_system,
    neo4j_create_condition,
    neo4j_create_resolution_mechanic,
    neo4j_create_track,
    neo4j_link_entity_to_ability,
)

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_neo4j_client():
    """Mock Neo4j client."""
    client = Mock()
    client.execute_write = Mock()
    return client


# =============================================================================
# neo4j_create_ability_system TESTS
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_create_ability_system_with_parent_category(mock_get_client, mock_neo4j_client):
    """Test creating an ability system with a parent category."""
    mock_get_client.return_value = mock_neo4j_client
    neo4j_create_ability_system(
        name="Dominate",
        system_id="vtm20_system",
        parent_category="Discipline",
    )
    mock_neo4j_client.execute_write.assert_called_once()
    query = mock_neo4j_client.execute_write.call_args[0][0]
    params = mock_neo4j_client.execute_write.call_args[0][1]

    assert "MERGE" in query
    assert "AbilitySystem" in query
    assert params["name"] == "Dominate"
    assert params["system_id"] == "vtm20_system"
    assert params["parent_category"] == "Discipline"


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_create_ability_system_without_parent_category(mock_get_client, mock_neo4j_client):
    """Test creating an ability system without a parent category."""
    mock_get_client.return_value = mock_neo4j_client
    neo4j_create_ability_system(
        name="Celerity",
        system_id="vtm20_system",
    )
    mock_neo4j_client.execute_write.assert_called_once()
    query = mock_neo4j_client.execute_write.call_args[0][0]
    params = mock_neo4j_client.execute_write.call_args[0][1]

    assert "MERGE" in query
    assert "AbilitySystem" in query
    assert params["name"] == "Celerity"
    assert params["system_id"] == "vtm20_system"
    assert params["parent_category"] is None


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_create_ability_system_multiple_calls_idempotent(mock_get_client, mock_neo4j_client):
    """Test that calling create_ability_system multiple times is idempotent."""
    mock_get_client.return_value = mock_neo4j_client

    # Call twice with same parameters
    neo4j_create_ability_system(
        name="Fortitude",
        system_id="vtm20_system",
        parent_category="Discipline",
    )
    neo4j_create_ability_system(
        name="Fortitude",
        system_id="vtm20_system",
        parent_category="Discipline",
    )

    assert mock_neo4j_client.execute_write.call_count == 2
    # Both calls should use MERGE (same query)
    query1 = mock_neo4j_client.execute_write.call_args_list[0][0][0]
    query2 = mock_neo4j_client.execute_write.call_args_list[1][0][0]
    assert query1 == query2


# =============================================================================
# neo4j_create_track TESTS
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_create_track_resource_type(mock_get_client, mock_neo4j_client):
    """Test creating a track with resource type."""
    mock_get_client.return_value = mock_neo4j_client
    neo4j_create_track(
        name="Blood Pool",
        system_id="vtm20_system",
        track_type="resource",
    )
    mock_neo4j_client.execute_write.assert_called_once()
    query = mock_neo4j_client.execute_write.call_args[0][0]
    params = mock_neo4j_client.execute_write.call_args[0][1]

    assert "MERGE" in query
    assert "Track" in query
    assert params["name"] == "Blood Pool"
    assert params["system_id"] == "vtm20_system"
    assert params["track_type"] == "resource"


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_create_track_advancement_type(mock_get_client, mock_neo4j_client):
    """Test creating a track with advancement type."""
    mock_get_client.return_value = mock_neo4j_client
    neo4j_create_track(
        name="Generation",
        system_id="vtm20_system",
        track_type="advancement",
    )
    mock_neo4j_client.execute_write.assert_called_once()
    query = mock_neo4j_client.execute_write.call_args[0][0]
    params = mock_neo4j_client.execute_write.call_args[0][1]

    assert "MERGE" in query
    assert "Track" in query
    assert params["name"] == "Generation"
    assert params["system_id"] == "vtm20_system"
    assert params["track_type"] == "advancement"


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_create_track_multiple_calls_idempotent(mock_get_client, mock_neo4j_client):
    """Test that calling create_track multiple times is idempotent."""
    mock_get_client.return_value = mock_neo4j_client

    # Call twice with same parameters
    neo4j_create_track(
        name="Willpower",
        system_id="vtm20_system",
        track_type="resource",
    )
    neo4j_create_track(
        name="Willpower",
        system_id="vtm20_system",
        track_type="resource",
    )

    assert mock_neo4j_client.execute_write.call_count == 2
    # Both calls should use MERGE (same query)
    query1 = mock_neo4j_client.execute_write.call_args_list[0][0][0]
    query2 = mock_neo4j_client.execute_write.call_args_list[1][0][0]
    assert query1 == query2


# =============================================================================
# neo4j_create_condition TESTS
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_create_condition_basic(mock_get_client, mock_neo4j_client):
    """Test creating a condition."""
    mock_get_client.return_value = mock_neo4j_client
    neo4j_create_condition(name="Frenzy", system_id="vtm20_system")
    mock_neo4j_client.execute_write.assert_called_once()
    query = mock_neo4j_client.execute_write.call_args[0][0]
    params = mock_neo4j_client.execute_write.call_args[0][1]

    assert "MERGE" in query
    assert "Condition" in query
    assert params["name"] == "Frenzy"
    assert params["system_id"] == "vtm20_system"


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_create_condition_torpor(mock_get_client, mock_neo4j_client):
    """Test creating a torpor condition."""
    mock_get_client.return_value = mock_neo4j_client
    neo4j_create_condition(name="Torpor", system_id="vtm20_system")
    mock_neo4j_client.execute_write.assert_called_once()
    query = mock_neo4j_client.execute_write.call_args[0][0]
    params = mock_neo4j_client.execute_write.call_args[0][1]

    assert "MERGE" in query
    assert "Condition" in query
    assert params["name"] == "Torpor"
    assert params["system_id"] == "vtm20_system"


# =============================================================================
# neo4j_create_resolution_mechanic TESTS
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_create_resolution_mechanic_roll_pool(mock_get_client, mock_neo4j_client):
    """Test creating a resolution mechanic with roll pool type."""
    mock_get_client.return_value = mock_neo4j_client
    neo4j_create_resolution_mechanic(
        name="Rouse Check",
        system_id="vtm20_system",
        mechanic_type="roll_pool",
    )
    mock_neo4j_client.execute_write.assert_called_once()
    query = mock_neo4j_client.execute_write.call_args[0][0]
    params = mock_neo4j_client.execute_write.call_args[0][1]

    assert "MERGE" in query
    assert "ResolutionMechanic" in query
    assert params["name"] == "Rouse Check"
    assert params["system_id"] == "vtm20_system"
    assert params["mechanic_type"] == "roll_pool"


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_create_resolution_mechanic_dice_pool(mock_get_client, mock_neo4j_client):
    """Test creating a resolution mechanic with dice pool type."""
    mock_get_client.return_value = mock_neo4j_client
    neo4j_create_resolution_mechanic(
        name="Attack Roll",
        system_id="vtm20_system",
        mechanic_type="dice_pool",
    )
    mock_neo4j_client.execute_write.assert_called_once()
    query = mock_neo4j_client.execute_write.call_args[0][0]
    params = mock_neo4j_client.execute_write.call_args[0][1]

    assert "MERGE" in query
    assert "ResolutionMechanic" in query
    assert params["name"] == "Attack Roll"
    assert params["system_id"] == "vtm20_system"
    assert params["mechanic_type"] == "dice_pool"


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_create_resolution_mechanic_multiple_calls_idempotent(mock_get_client, mock_neo4j_client):
    """Test that calling create_resolution_mechanic multiple times is idempotent."""
    mock_get_client.return_value = mock_neo4j_client

    # Call twice with same parameters
    neo4j_create_resolution_mechanic(
        name="Rouse Check",
        system_id="vtm20_system",
        mechanic_type="roll_pool",
    )
    neo4j_create_resolution_mechanic(
        name="Rouse Check",
        system_id="vtm20_system",
        mechanic_type="roll_pool",
    )

    assert mock_neo4j_client.execute_write.call_count == 2
    # Both calls should use MERGE (same query)
    query1 = mock_neo4j_client.execute_write.call_args_list[0][0][0]
    query2 = mock_neo4j_client.execute_write.call_args_list[1][0][0]
    assert query1 == query2


# =============================================================================
# neo4j_link_entity_to_ability TESTS
# =============================================================================


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_link_entity_to_ability_creates_relationship(mock_get_client, mock_neo4j_client):
    """Test linking an entity to an ability system."""
    mock_get_client.return_value = mock_neo4j_client
    neo4j_link_entity_to_ability(
        entity_id="nosferatu_lineage",
        ability_system_name="Obfuscate",
    )
    mock_neo4j_client.execute_write.assert_called_once()
    query = mock_neo4j_client.execute_write.call_args[0][0]
    params = mock_neo4j_client.execute_write.call_args[0][1]

    assert "HAS_ACCESS_TO" in query
    assert params["entity_id"] == "nosferatu_lineage"
    assert params["ability_system_name"] == "Obfuscate"


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_link_entity_to_ability_discipline(mock_get_client, mock_neo4j_client):
    """Test linking an entity to a discipline."""
    mock_get_client.return_value = mock_neo4j_client
    neo4j_link_entity_to_ability(
        entity_id="tremere_character",
        ability_system_name="Thaumaturgy",
    )
    mock_neo4j_client.execute_write.assert_called_once()
    query = mock_neo4j_client.execute_write.call_args[0][0]
    params = mock_neo4j_client.execute_write.call_args[0][1]

    assert "HAS_ACCESS_TO" in query
    assert params["entity_id"] == "tremere_character"
    assert params["ability_system_name"] == "Thaumaturgy"


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_link_entity_to_ability_multiple_links(mock_get_client, mock_neo4j_client):
    """Test linking an entity to multiple abilities."""
    mock_get_client.return_value = mock_neo4j_client

    # Link entity to multiple abilities
    neo4j_link_entity_to_ability(
        entity_id="ventrue_character",
        ability_system_name="Dominate",
    )
    neo4j_link_entity_to_ability(
        entity_id="ventrue_character",
        ability_system_name="Fortitude",
    )

    assert mock_neo4j_client.execute_write.call_count == 2
    # Check both calls
    call1_params = mock_neo4j_client.execute_write.call_args_list[0][0][1]
    call2_params = mock_neo4j_client.execute_write.call_args_list[1][0][1]
    assert call1_params["entity_id"] == "ventrue_character"
    assert call1_params["ability_system_name"] == "Dominate"
    assert call2_params["entity_id"] == "ventrue_character"
    assert call2_params["ability_system_name"] == "Fortitude"


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_create_condition_idempotent(mock_get_client, mock_neo4j_client):
    """Test that calling create_condition multiple times is idempotent."""
    mock_get_client.return_value = mock_neo4j_client

    # Call twice with same parameters
    neo4j_create_condition(name="Frenzy", system_id="vtm20_system")
    neo4j_create_condition(name="Frenzy", system_id="vtm20_system")

    assert mock_neo4j_client.execute_write.call_count == 2
    # Both calls should use MERGE (same query)
    query1 = mock_neo4j_client.execute_write.call_args_list[0][0][0]
    query2 = mock_neo4j_client.execute_write.call_args_list[1][0][0]
    assert query1 == query2


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_link_entity_to_ability_idempotent(mock_get_client, mock_neo4j_client):
    """Test that linking the same entity to the same ability multiple times is idempotent."""
    mock_get_client.return_value = mock_neo4j_client

    # Link the same entity to the same ability twice
    neo4j_link_entity_to_ability(
        entity_id="nosferatu_character",
        ability_system_name="Obfuscate",
    )
    neo4j_link_entity_to_ability(
        entity_id="nosferatu_character",
        ability_system_name="Obfuscate",
    )

    assert mock_neo4j_client.execute_write.call_count == 2
    # Both calls should use MERGE on the relationship (same query)
    query1 = mock_neo4j_client.execute_write.call_args_list[0][0][0]
    query2 = mock_neo4j_client.execute_write.call_args_list[1][0][0]
    assert query1 == query2


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_create_track_with_other_type(mock_get_client, mock_neo4j_client):
    """Test creating a track with a different track type (e.g., damage type)."""
    mock_get_client.return_value = mock_neo4j_client
    neo4j_create_track(
        name="Aggravated Damage",
        system_id="vtm20_system",
        track_type="damage",
    )
    mock_neo4j_client.execute_write.assert_called_once()
    query = mock_neo4j_client.execute_write.call_args[0][0]
    params = mock_neo4j_client.execute_write.call_args[0][1]

    assert "MERGE" in query
    assert "Track" in query
    assert params["name"] == "Aggravated Damage"
    assert params["system_id"] == "vtm20_system"
    assert params["track_type"] == "damage"


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_create_resolution_mechanic_with_other_type(mock_get_client, mock_neo4j_client):
    """Test creating a resolution mechanic with a different mechanic type (e.g., flat_roll)."""
    mock_get_client.return_value = mock_neo4j_client
    neo4j_create_resolution_mechanic(
        name="Feeding Roll",
        system_id="vtm20_system",
        mechanic_type="flat_roll",
    )
    mock_neo4j_client.execute_write.assert_called_once()
    query = mock_neo4j_client.execute_write.call_args[0][0]
    params = mock_neo4j_client.execute_write.call_args[0][1]

    assert "MERGE" in query
    assert "ResolutionMechanic" in query
    assert params["name"] == "Feeding Roll"
    assert params["system_id"] == "vtm20_system"
    assert params["mechanic_type"] == "flat_roll"


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_link_entity_to_ability_same_entity_multiple_times(mock_get_client, mock_neo4j_client):
    """Test that calling link_entity_to_ability multiple times for same entity and ability is idempotent."""
    mock_get_client.return_value = mock_neo4j_client

    # Link the same entity to the same ability 3 times
    neo4j_link_entity_to_ability(
        entity_id="tremere_character",
        ability_system_name="Thaumaturgy",
    )
    neo4j_link_entity_to_ability(
        entity_id="tremere_character",
        ability_system_name="Thaumaturgy",
    )
    neo4j_link_entity_to_ability(
        entity_id="tremere_character",
        ability_system_name="Thaumaturgy",
    )

    # Should be called 3 times
    assert mock_neo4j_client.execute_write.call_count == 3
    # All calls should use MERGE (same query)
    query1 = mock_neo4j_client.execute_write.call_args_list[0][0][0]
    query2 = mock_neo4j_client.execute_write.call_args_list[1][0][0]
    query3 = mock_neo4j_client.execute_write.call_args_list[2][0][0]
    assert query1 == query2 == query3
    # All calls should have the same params
    params1 = mock_neo4j_client.execute_write.call_args_list[0][0][1]
    params2 = mock_neo4j_client.execute_write.call_args_list[1][0][1]
    params3 = mock_neo4j_client.execute_write.call_args_list[2][0][1]
    assert params1 == params2 == params3
    assert params1["entity_id"] == "tremere_character"
    assert params1["ability_system_name"] == "Thaumaturgy"


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_create_ability_system_empty_parent_category(mock_get_client, mock_neo4j_client):
    """Test creating an ability system with empty string parent_category."""
    mock_get_client.return_value = mock_neo4j_client
    neo4j_create_ability_system(
        name="Protean",
        system_id="vtm20_system",
        parent_category="",
    )
    mock_neo4j_client.execute_write.assert_called_once()
    query = mock_neo4j_client.execute_write.call_args[0][0]
    params = mock_neo4j_client.execute_write.call_args[0][1]

    assert "MERGE" in query
    assert "AbilitySystem" in query
    assert params["name"] == "Protean"
    assert params["system_id"] == "vtm20_system"
    # Empty string should be passed as-is, not converted to None
    assert params["parent_category"] == ""


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_create_track_with_max_characters(mock_get_client, mock_neo4j_client):
    """Test creating a track with a long name."""
    mock_get_client.return_value = mock_neo4j_client
    long_name = "A" * 200
    neo4j_create_track(
        name=long_name,
        system_id="vtm20_system",
        track_type="resource",
    )
    mock_neo4j_client.execute_write.assert_called_once()
    query = mock_neo4j_client.execute_write.call_args[0][0]
    params = mock_neo4j_client.execute_write.call_args[0][1]

    assert "MERGE" in query
    assert "Track" in query
    assert params["name"] == long_name
    assert params["system_id"] == "vtm20_system"
    assert params["track_type"] == "resource"


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_create_condition_with_special_characters(mock_get_client, mock_neo4j_client):
    """Test creating a condition with special characters in name."""
    mock_get_client.return_value = mock_neo4j_client
    neo4j_create_condition(
        name="Hunger-Frenzy (Clan)",
        system_id="vtm20_system",
    )
    mock_neo4j_client.execute_write.assert_called_once()
    query = mock_neo4j_client.execute_write.call_args[0][0]
    params = mock_neo4j_client.execute_write.call_args[0][1]

    assert "MERGE" in query
    assert "Condition" in query
    assert params["name"] == "Hunger-Frenzy (Clan)"
    assert params["system_id"] == "vtm20_system"


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_create_resolution_mechanic_with_complex_type(mock_get_client, mock_neo4j_client):
    """Test creating a resolution mechanic with a complex mechanic type."""
    mock_get_client.return_value = mock_neo4j_client
    neo4j_create_resolution_mechanic(
        name="Clash Roll",
        system_id="vtm20_system",
        mechanic_type="opposing_pool",
    )
    mock_neo4j_client.execute_write.assert_called_once()
    query = mock_neo4j_client.execute_write.call_args[0][0]
    params = mock_neo4j_client.execute_write.call_args[0][1]

    assert "MERGE" in query
    assert "ResolutionMechanic" in query
    assert params["name"] == "Clash Roll"
    assert params["system_id"] == "vtm20_system"
    assert params["mechanic_type"] == "opposing_pool"


@patch("monitor_data.tools.neo4j_tools.mechanics.get_neo4j_client")
def test_neo4j_link_entity_to_ability_with_uuid_entity_id(mock_get_client, mock_neo4j_client):
    """Test linking an entity with UUID entity_id to an ability system."""
    mock_get_client.return_value = mock_neo4j_client
    uuid_entity_id = "550e8400-e29b-41d4-a716-446655440000"
    neo4j_link_entity_to_ability(
        entity_id=uuid_entity_id,
        ability_system_name="Auspex",
    )
    mock_neo4j_client.execute_write.assert_called_once()
    query = mock_neo4j_client.execute_write.call_args[0][0]
    params = mock_neo4j_client.execute_write.call_args[0][1]

    assert "HAS_ACCESS_TO" in query
    assert params["entity_id"] == uuid_entity_id
    assert params["ability_system_name"] == "Auspex"
