from monitor_agents.canonkeeper.agent import (
    _axiom_authority_for_domain,
    _normalise_state_tag_update,
    _derive_detail_level,
    CanonKeeper,
)


def test_axiom_authority_for_domain():
    assert _axiom_authority_for_domain("physics") == "physics"
    assert _axiom_authority_for_domain("tech") == "physics"
    assert _axiom_authority_for_domain("society") == "society"
    assert _axiom_authority_for_domain("genre") == "genre"
    assert _axiom_authority_for_domain("magic") == "metaphysics"
    assert _axiom_authority_for_domain("unknown") == "metaphysics"
    assert _axiom_authority_for_domain(None) == "metaphysics"
    assert _axiom_authority_for_domain("") == "metaphysics"


def test_normalise_state_tag_update():
    # Empty case
    res = _normalise_state_tag_update({})
    assert res == {"entity_id": None, "add_tags": [], "remove_tags": []}

    # Populated case
    props = {"entity_id": "test_id", "add_tags": [" A", "B ", "A"], "remove_tags": ["C ", " c"]}
    res = _normalise_state_tag_update(props)
    assert res == {"entity_id": "test_id", "add_tags": ["a", "b"], "remove_tags": ["c"]}


def test_derive_detail_level():
    assert _derive_detail_level("character", {"name": "Bob"}, ["table_1"]) == "sketched"
    assert _derive_detail_level("character", {"name": "Bob"}, []) == "sketched"
    assert _derive_detail_level("character", {}, []) == "stub"

    assert _derive_detail_level("location", {"name": "Town"}, []) == "sketched"
    assert _derive_detail_level("location", {}, []) == "stub"

    assert _derive_detail_level("faction", {"name": "Guild"}, []) == "detailed"
    assert _derive_detail_level("organization", {}, []) == "sketched"

    assert _derive_detail_level("concept", {"name": "Magic"}, []) == "stub"

    assert _derive_detail_level("unknown", {"name": "Thing"}, []) == "sketched"
    assert _derive_detail_level("unknown", {}, []) == "stub"


def test_is_placeholder_name():
    assert CanonKeeper._is_placeholder_name("None") is True
    assert CanonKeeper._is_placeholder_name("unknown") is True
    assert CanonKeeper._is_placeholder_name(None) is True
    assert CanonKeeper._is_placeholder_name(" Valid ") is False
