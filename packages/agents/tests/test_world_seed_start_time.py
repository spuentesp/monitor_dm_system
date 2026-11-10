"""World start date from the world seed (join Task 4).

Phase 3 soft-imports ``monitor_agents.world_seed`` looking for
``estimate_start_time(universe_id)`` and treats its result as the
``"world_seed"`` source of the story's in-game clock. These tests pin that
interface and the "return None when it cannot tell" contract.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _material(digest: str = "Setting: a drowned empire in its third century"):
    return SimpleNamespace(
        digest=lambda limit_per_section=6: digest,
        system_name=None,
        universe_name="The Drowned Empire",
    )


class TestEstimateStartTime:
    @pytest.mark.asyncio
    async def test_reads_the_worlds_start_date_from_the_model(self):
        from monitor_agents.world_seed.seed import estimate_start_time

        module = MagicMock()
        module.forward.return_value = SimpleNamespace(start_time="1012-03-01T12:00:00+00:00", reason="third century")
        universe_id = uuid4()

        with (
            patch("monitor_agents.world_seed.seed.gather_universe_material", AsyncMock(return_value=_material())),
            patch("monitor_agents.world_seed.signatures.WorldStartEstimateModule", MagicMock(return_value=module)),
        ):
            parsed = await estimate_start_time(universe_id)

        assert parsed is not None
        assert (parsed.year, parsed.month, parsed.day) == (1012, 3, 1)
        # The real callee got the universe's canon digest and the system name.
        kwargs = module.forward.call_args.kwargs
        assert "drowned empire" in kwargs["world_material"]
        assert kwargs["system_name"] == "The Drowned Empire"

    @pytest.mark.asyncio
    async def test_a_naive_answer_is_made_utc(self):
        from monitor_agents.world_seed.seed import estimate_start_time

        module = MagicMock()
        module.forward.return_value = SimpleNamespace(start_time="1012-03-01T12:00:00", reason="")

        with (
            patch("monitor_agents.world_seed.seed.gather_universe_material", AsyncMock(return_value=_material())),
            patch("monitor_agents.world_seed.signatures.WorldStartEstimateModule", MagicMock(return_value=module)),
        ):
            parsed = await estimate_start_time(uuid4())

        assert parsed is not None
        assert parsed.tzinfo is not None

    @pytest.mark.asyncio
    async def test_a_model_that_cannot_tell_yields_none(self):
        from monitor_agents.world_seed.seed import estimate_start_time

        module = MagicMock()
        module.forward.return_value = SimpleNamespace(start_time="", reason="the material has no chronology")

        with (
            patch("monitor_agents.world_seed.seed.gather_universe_material", AsyncMock(return_value=_material())),
            patch("monitor_agents.world_seed.signatures.WorldStartEstimateModule", MagicMock(return_value=module)),
        ):
            assert await estimate_start_time(uuid4()) is None

    @pytest.mark.asyncio
    async def test_an_unparseable_answer_yields_none(self):
        from monitor_agents.world_seed.seed import estimate_start_time

        module = MagicMock()
        module.forward.return_value = SimpleNamespace(start_time="sometime after the fall", reason="")

        with (
            patch("monitor_agents.world_seed.seed.gather_universe_material", AsyncMock(return_value=_material())),
            patch("monitor_agents.world_seed.signatures.WorldStartEstimateModule", MagicMock(return_value=module)),
        ):
            assert await estimate_start_time(uuid4()) is None

    @pytest.mark.asyncio
    async def test_an_empty_universe_never_calls_the_model(self):
        from monitor_agents.world_seed.seed import estimate_start_time

        module_cls = MagicMock()
        with (
            patch("monitor_agents.world_seed.seed.gather_universe_material", AsyncMock(return_value=_material(""))),
            patch("monitor_agents.world_seed.signatures.WorldStartEstimateModule", module_cls),
        ):
            assert await estimate_start_time(uuid4()) is None
        assert module_cls.call_count == 0

    @pytest.mark.asyncio
    async def test_a_failed_model_call_degrades_to_none(self):
        from monitor_agents.world_seed.seed import estimate_start_time

        module = MagicMock()
        module.forward.side_effect = RuntimeError("provider down")

        with (
            patch("monitor_agents.world_seed.seed.gather_universe_material", AsyncMock(return_value=_material())),
            patch("monitor_agents.world_seed.signatures.WorldStartEstimateModule", MagicMock(return_value=module)),
        ):
            assert await estimate_start_time(uuid4()) is None

    @pytest.mark.asyncio
    async def test_the_phase3_soft_import_contract(self):
        """Phase 3 does ``from monitor_agents import world_seed`` and looks
        for ``estimate_start_time(universe_id)`` returning a datetime or an
        ISO string (awaitable is accepted) — pin that surface."""
        from monitor_agents import world_seed

        estimate = getattr(world_seed, "estimate_start_time", None)
        assert callable(estimate)

        module = MagicMock()
        module.forward.return_value = SimpleNamespace(start_time="1012-03-01T09:00:00+00:00", reason="")
        with (
            patch("monitor_agents.world_seed.seed.gather_universe_material", AsyncMock(return_value=_material())),
            patch("monitor_agents.world_seed.signatures.WorldStartEstimateModule", MagicMock(return_value=module)),
        ):
            result = estimate(uuid4())
            # Phase 3 awaits the result when it is awaitable.
            assert hasattr(result, "__await__")
            parsed = await result
        assert parsed.year == 1012
