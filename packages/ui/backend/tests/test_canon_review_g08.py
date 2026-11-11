"""G08 — the CF-8 accept path refuses a contradiction silently.

A proposal that contradicts canon used to be accepted without a word. Now:
a proposal carrying a direct-contradiction flag needs an explicit override
reason, the override is audited, and an owner in hard-rejection mode gets a
flat refusal instead.

The canon check itself is stubbed here — it is measured by
``scripts/eval_canonkeeper_recall.py``, not by a route test.

Use Cases: CF-5, CF-8 (G08)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from monitor_data.schemas.base import ProposalType
from monitor_data.schemas.proposed_changes import ProposedChangeCreate
from monitor_ui.main import app
from tests.behavior._hermetic_stack import HermeticStack

client = TestClient(app)

_local_auth = pytest.mark.usefixtures("local_auth_mode")


@pytest.fixture
def hermetic(monkeypatch: pytest.MonkeyPatch) -> Any:
    """The hermetic stack, installed for the duration of the test."""
    stack = HermeticStack()
    stack.install(monkeypatch)
    try:
        yield stack
    finally:
        stack.uninstall()


def _pending_proposal(
    hermetic: HermeticStack,
    *,
    statement: str = "Mira Vale opened the sealed door.",
    universe_id: UUID | None = None,
    scene_id: UUID | None = None,
    flags: list[dict[str, Any]] | None = None,
) -> str:
    """A pending proposal in the queue, optionally carrying review flags."""
    from monitor_data.tools.mongodb_tools.proposals import mongodb_create_proposed_change

    universe_id = universe_id or uuid4()
    scene_id = scene_id or uuid4()
    hermetic.seed(
        "scenes",
        [
            {
                "scene_id": str(scene_id),
                "story_id": str(uuid4()),
                "universe_id": str(universe_id),
                "title": "The sealed door",
                "purpose": "Advance the harbour investigation.",
                "status": "active",
                "created_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        ],
    )
    created = mongodb_create_proposed_change(
        ProposedChangeCreate(
            scene_id=scene_id,
            change_type=ProposalType.FACT,
            content={"statement": statement, "universe_id": str(universe_id)},
            authority="gm",
            proposer="Test",
            source="capture_entry:entry-1",
        )
    )
    if flags:
        from monitor_data.tools.mongodb_tools.proposals import (
            mongodb_flag_proposal_review,
        )

        mongodb_flag_proposal_review(
            created.proposal_id,
            needs_review=True,
            reason=flags[0].get("explanation", "Contradicts established canon."),
            source=flags[0].get("kind", "direct_contradiction"),
            flags=flags,
        )
    return str(created.proposal_id)


def _direct_flag() -> dict[str, Any]:
    return {
        "kind": "direct_contradiction",
        "severity": "high",
        "explanation": "Mira Vale is a courier for the Grey Line; this says otherwise.",
        "implications": "",
        "rule": "",
        "detected_at": datetime.now(UTC).isoformat(),
    }


def _stub_check(monkeypatch: pytest.MonkeyPatch, flags: list[dict[str, Any]]) -> list[Any]:
    """Make the canon check return the given findings."""
    from monitor_agents.canonkeeper.agent import CanonKeeper

    async def _flags(self: Any, universe_id: UUID, statements: list[str]) -> list[dict[str, Any]]:
        return [
            {
                "statement": statements[0] if statements else "",
                "explanation": flag.get("explanation", ""),
                "implications": "",
                "contradiction_type": "semantic_opposite",
                "severity": "high",
                "flag_kind": flag.get("kind", "direct_contradiction"),
            }
            for flag in flags
        ]

    monkeypatch.setattr(CanonKeeper, "direct_contradiction_flags", _flags)
    return flags


class TestSoftBlock:
    @pytest.mark.usefixtures("local_auth_mode")
    def test_a_flagged_proposal_needs_an_override_reason(
        self, hermetic: HermeticStack
    ) -> None:
        proposal_id = _pending_proposal(hermetic, flags=[_direct_flag()])

        resp = client.post(
            f"/api/canon-review/{proposal_id}/accept",
            params={"reason": "Looks fine to me."},
        )

        assert resp.status_code == 409
        assert "override reason" in resp.json()["detail"]

    @pytest.mark.usefixtures("local_auth_mode")
    def test_an_override_accepts_the_proposal(
        self, hermetic: HermeticStack
    ) -> None:
        proposal_id = _pending_proposal(hermetic, flags=[_direct_flag()])

        resp = client.post(
            f"/api/canon-review/{proposal_id}/accept",
            params={
                "reason": "The fiction changed on purpose.",
                "override_reason": "Mira left the Grey Line last night — on purpose.",
            },
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "accepted"
        assert body["decision_metadata"]["override_reason"] == (
            "Mira left the Grey Line last night — on purpose."
        )

    @pytest.mark.usefixtures("local_auth_mode")
    def test_the_override_is_audited(self, hermetic: HermeticStack) -> None:
        proposal_id = _pending_proposal(hermetic, flags=[_direct_flag()])

        client.post(
            f"/api/canon-review/{proposal_id}/accept",
            params={
                "reason": "On purpose.",
                "override_reason": "The fiction changed.",
            },
        )

        audit = list(hermetic.collection("canon_override_audit").find({}))
        assert len(audit) == 1
        assert audit[0]["proposal_id"] == proposal_id
        assert audit[0]["reason"] == "The fiction changed."
        assert audit[0]["flag_kinds"] == ["direct_contradiction"]

    @pytest.mark.usefixtures("local_auth_mode")
    def test_an_unflagged_proposal_is_accepted_as_before(
        self, hermetic: HermeticStack, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_check(monkeypatch, [])
        proposal_id = _pending_proposal(hermetic)

        resp = client.post(
            f"/api/canon-review/{proposal_id}/accept",
            params={"reason": "Confirmed at the table."},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "accepted"
        assert resp.json()["decision_metadata"]["override_reason"] is None
        assert hermetic.collection("canon_override_audit").count_documents({}) == 0

    @pytest.mark.usefixtures("local_auth_mode")
    def test_a_contradiction_found_now_stamps_the_proposal(
        self, hermetic: HermeticStack, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The check runs at the decision point, so a late conflict is caught."""
        _stub_check(monkeypatch, [_direct_flag()])
        proposal_id = _pending_proposal(hermetic)

        resp = client.post(
            f"/api/canon-review/{proposal_id}/accept",
            params={"reason": "Looks fine to me."},
        )

        assert resp.status_code == 409
        stored = hermetic.collection("proposed_changes").find_one({"proposal_id": proposal_id})
        assert stored is not None
        assert stored["needs_review"] is True
        assert stored["review_flags"][0]["kind"] == "direct_contradiction"

    @pytest.mark.usefixtures("local_auth_mode")
    def test_a_failed_check_never_blocks_an_acceptance(
        self, hermetic: HermeticStack, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from monitor_agents.canonkeeper.agent import CanonKeeper

        async def _boom(self: Any, universe_id: UUID, statements: list[str]) -> list[dict[str, Any]]:
            raise RuntimeError("the model is down")

        monkeypatch.setattr(CanonKeeper, "direct_contradiction_flags", _boom)
        proposal_id = _pending_proposal(hermetic)

        resp = client.post(
            f"/api/canon-review/{proposal_id}/accept",
            params={"reason": "Confirmed at the table."},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "accepted"


class TestHardRejection:
    @pytest.mark.usefixtures("local_auth_mode")
    def test_hard_mode_refuses_a_flagged_proposal(
        self, hermetic: HermeticStack, local_auth_mode: Any
    ) -> None:
        import monitor_ui.routers.canon_review as canon_review

        async def _hard(db: Any, principal: Any) -> dict[str, Any]:
            return {"hard_rejection": True}

        original = canon_review._owner_canon_settings
        canon_review._owner_canon_settings = _hard  # type: ignore[assignment]
        try:
            proposal_id = _pending_proposal(hermetic, flags=[_direct_flag()])

            resp = client.post(
                f"/api/canon-review/{proposal_id}/accept",
                params={
                    "reason": "On purpose.",
                    "override_reason": "The fiction changed.",
                },
            )
        finally:
            canon_review._owner_canon_settings = original  # type: ignore[assignment]

        assert resp.status_code == 409
        assert "hard rejection is on" in resp.json()["detail"]
        # The proposal is untouched.
        stored = hermetic.collection("proposed_changes").find_one(
            {"proposal_id": proposal_id}
        )
        assert stored is not None
        assert stored["status"] == "pending"

    @pytest.mark.usefixtures("local_auth_mode")
    def test_hard_mode_leaves_unflagged_proposals_alone(
        self, hermetic: HermeticStack, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import monitor_ui.routers.canon_review as canon_review

        async def _hard(db: Any, principal: Any) -> dict[str, Any]:
            return {"hard_rejection": True}

        monkeypatch.setattr(canon_review, "_owner_canon_settings", _hard)
        _stub_check(monkeypatch, [])
        proposal_id = _pending_proposal(hermetic)

        resp = client.post(
            f"/api/canon-review/{proposal_id}/accept",
            params={"reason": "Confirmed at the table."},
        )

        assert resp.status_code == 200, resp.text
