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
