"""Tests for the pack publish endpoint and public gallery route (Phase 5).
Hermetic — the data-layer tools are patched."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from monitor_ui.routers import pack_library


PACK_ID = str(uuid4())


@pytest.mark.asyncio
async def test_publish_endpoint_returns_report_and_pack():
    report = {"publishable": True, "overall_score": 0.9, "reasons": []}
    with (
        patch.object(
            pack_library, "mongodb_publish_knowledge_pack", return_value={"report": report, "pack": MagicMock_pack()}
        ) as pub,
        patch.object(pack_library, "_pack_to_dict", return_value={"pack_id": PACK_ID, "status": "published"}),
    ):
        out = await pack_library.publish_pack(PACK_ID, min_score=0.5)
    assert out["report"]["publishable"] is True
    assert out["pack"]["status"] == "published"
    pub.assert_called_once()


@pytest.mark.asyncio
async def test_publish_endpoint_422_when_gate_fails():
    with (
        patch.object(
            pack_library,
            "mongodb_publish_knowledge_pack",
            side_effect=ValueError("Pack not publishable: pack status is pending"),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await pack_library.publish_pack(PACK_ID)
    assert exc_info.value.status_code == 422
    assert "not publishable" in exc_info.value.detail


@pytest.mark.asyncio
async def test_public_gallery_lists_published():
    with (
        patch.object(pack_library, "mongodb_list_published_packs", return_value=[MagicMock_pack()]) as lst,
        patch.object(pack_library, "_pack_to_dict", side_effect=lambda p: {"pack_id": PACK_ID}),
    ):
        out = await pack_library.list_public_packs(limit=10)
    assert out == [{"pack_id": PACK_ID}]
    lst.assert_called_once_with(10)


def test_public_route_registered_before_pack_id_route():
    """`/packs/public` must not be swallowed by `/packs/{pack_id}`."""
    paths = [(r.path, sorted(r.methods)) for r in pack_library.router.routes]
    public_idx = next(i for i, (p, _) in enumerate(paths) if p == "/packs/public")
    by_id_idx = next(i for i, (p, _) in enumerate(paths) if p == "/packs/{pack_id}")
    assert public_idx < by_id_idx


def MagicMock_pack():
    from unittest.mock import MagicMock

    return MagicMock()
