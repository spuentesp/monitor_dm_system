"""ModelRole.coerce — enum/str/None interpretation at process boundaries."""

from monitor_data.schemas.llm_config import ModelRole


def test_enum_passthrough():
    assert ModelRole.coerce(ModelRole.HEAVY) is ModelRole.HEAVY


def test_valid_string():
    assert ModelRole.coerce("heavy") is ModelRole.HEAVY


def test_string_is_normalized():
    assert ModelRole.coerce("  Heavy ") is ModelRole.HEAVY


def test_none_passthrough():
    assert ModelRole.coerce(None) is None


def test_unknown_value_is_none():
    assert ModelRole.coerce("warp-core") is None
