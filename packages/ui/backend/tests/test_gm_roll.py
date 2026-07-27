"""Tests for POST /api/gm/roll — server-authoritative dice for the /gm roller.

The /gm dice roller must roll on the server (doctrine: server-authoritative
rolls, not client-cheatable). These tests lock the endpoint contract: valid
expressions return roll_dice's DiceResult fields plus the parsed modifier, and
invalid or out-of-bounds expressions are rejected.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from monitor_ui.main import app

client = TestClient(app)


def test_gm_roll_simple_expression_with_modifier():
    response = client.post("/api/gm/roll", json={"expression": "1d20+3"})
    assert response.status_code == 200
    data = response.json()
    assert data["expression"] == "1d20+3"
    assert len(data["rolls"]) == 1
    assert 1 <= data["rolls"][0] <= 20
    assert data["total"] == data["rolls"][0] + 3
    assert data["modifier"] == 3
    assert data["kept_rolls"] == data["rolls"]


def test_gm_roll_keep_high_honored():
    response = client.post("/api/gm/roll", json={"expression": "2d20kh1"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["rolls"]) == 2
    assert all(1 <= r <= 20 for r in data["rolls"])
    assert data["kept_rolls"] == [max(data["rolls"])]
    assert data["total"] == max(data["rolls"])
    assert data["modifier"] == 0


def test_gm_roll_deterministic_with_patched_rng():
    with patch("monitor_data.utils.dice.random.randint", return_value=15):
        response = client.post("/api/gm/roll", json={"expression": "2d20+2"})
    assert response.status_code == 200
    data = response.json()
    assert data["rolls"] == [15, 15]
    assert data["total"] == 32
    assert data["modifier"] == 2


def test_gm_roll_negative_modifier():
    response = client.post("/api/gm/roll", json={"expression": "1d6-2"})
    assert response.status_code == 200
    data = response.json()
    assert data["modifier"] == -2
    assert data["total"] == data["rolls"][0] - 2


def test_gm_roll_garbage_expression_returns_422():
    response = client.post("/api/gm/roll", json={"expression": "not-a-dice-expression"})
    assert response.status_code == 422


def test_gm_roll_over_limit_expression_returns_422():
    # 1000 dice exceeds the endpoint cap (roll_dice itself has no upper bound).
    response = client.post("/api/gm/roll", json={"expression": "1000d6"})
    assert response.status_code == 422


def test_gm_roll_empty_expression_rejected():
    response = client.post("/api/gm/roll", json={"expression": ""})
    assert response.status_code == 422
