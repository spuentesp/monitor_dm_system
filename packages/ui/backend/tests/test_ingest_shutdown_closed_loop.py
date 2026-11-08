"""Shutdown must survive ingest futures bound to an already-closed event loop."""

from __future__ import annotations

import asyncio

from monitor_ui.routers import ingest


def test_shutdown_tolerates_future_from_closed_loop(monkeypatch) -> None:
    loop = asyncio.new_event_loop()
    fut = loop.create_future()
    fut.add_done_callback(lambda _f: None)  # as the router does; cancel() schedules it
    loop.close()  # fut.cancel() would now raise "Event loop is closed"

    monkeypatch.setattr(ingest, "_ingest_futures", {"tok": fut})
    ingest.prepare_ingest_runtime()
    assert ingest._ingest_executor is not None

    ingest.shutdown_ingest_runtime()  # must not raise

    assert ingest._ingest_futures == {}
    assert ingest._ingest_executor is None
    ingest.prepare_ingest_runtime()  # restore for other tests
