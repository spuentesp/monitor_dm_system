"""The analyzer's limit must sit inside the job's, so it can fail with a clear reason."""

import pytest
from monitor_agents.ingestion import agent


@pytest.mark.unit
def test_stage_limit_fits_inside_the_45_minute_job():
    assert agent.analyze_timeout_for_job(45 * 60) == 40 * 60


@pytest.mark.unit
def test_a_long_job_keeps_the_stage_default():
    assert agent.analyze_timeout_for_job(24 * 60 * 60) == agent._ANALYZE_STAGE_TIMEOUT_SECS


@pytest.mark.unit
def test_a_very_short_job_still_gets_a_usable_limit():
    assert agent.analyze_timeout_for_job(30) == 60


@pytest.mark.unit
async def test_clearing_old_chunks_targets_only_this_source():
    from unittest.mock import AsyncMock, MagicMock, patch
    from uuid import uuid4

    source = uuid4()
    qdrant = MagicMock()
    qdrant.get_client.return_value.delete = AsyncMock()
    with patch("monitor_data.db.qdrant.get_qdrant_client", return_value=qdrant):
        await agent._delete_source_chunks(source)
    selector = qdrant.get_client.return_value.delete.await_args.kwargs["points_selector"]
    assert selector.must[0].key == "source_id" and selector.must[0].match.value == str(source)


@pytest.mark.unit
async def test_a_qdrant_failure_does_not_stop_indexing():
    from unittest.mock import patch
    from uuid import uuid4

    with patch("monitor_data.db.qdrant.get_qdrant_client", side_effect=RuntimeError("down")):
        await agent._delete_source_chunks(uuid4())
