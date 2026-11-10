"""Meta-tests for scripts/measure_streaming_latency.py (Phase 7, task 3).

Only the pure helpers are tested hermetically — the timing run needs a live
backend with a configured model (the coordinator runs the script itself).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "measure_streaming_latency.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("measure_streaming_latency", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


msl = _load_mod()


class TestSseParsing:
    def test_payload_extraction(self):
        assert msl.sse_payload('data: {"a": 1}') == '{"a": 1}'
        assert msl.sse_payload("data: [DONE]") == "[DONE]"
        assert msl.sse_payload("") is None
        assert msl.sse_payload("event: message") is None

    def test_parse_frame_classifies(self):
        kind, frame = msl.parse_frame('data: {"type": "token", "text": "hi"}')
        assert kind == "data"
        assert frame == {"type": "token", "text": "hi"}
        assert msl.parse_frame("data: [DONE]") == ("done", None)
        assert msl.parse_frame("data: not json") == ("skip", None)
        assert msl.parse_frame(": comment") == ("skip", None)


class TestFrameShapes:
    def test_send_stream_token_and_done(self):
        assert msl.frame_text({"type": "token", "text": "Well "}, "send-stream") == "Well "
        assert msl.frame_text({"type": "done", "text": "full"}, "send-stream") == ""
        assert msl.is_final_frame({"type": "done"}, "send-stream") is True
        assert msl.is_final_frame({"type": "token", "text": "x"}, "send-stream") is False

    def test_openai_chunk_shapes(self):
        chunk = {"choices": [{"delta": {"content": "Well met."}, "finish_reason": None}]}
        assert msl.frame_text(chunk, "openai") == "Well met."
        first = {"choices": [{"delta": {"role": "assistant"}, "finish_reason": None}]}
        assert msl.frame_text(first, "openai") == ""
        stop = {"choices": [{"delta": {}, "finish_reason": "stop"}]}
        assert msl.is_final_frame(stop, "openai") is True
        assert msl.is_final_frame(chunk, "openai") is False


class TestSummarize:
    def test_aggregates_ttft_and_total(self):
        runs = [
            {"ttft_seconds": 0.2, "total_seconds": 1.0},
            {"ttft_seconds": 0.4, "total_seconds": 2.0},
            {"ttft_seconds": 0.6, "total_seconds": 3.0},
        ]
        summary = msl.summarize(runs)
        assert summary["runs"] == 3
        assert summary["ttft_seconds"]["min"] == 0.2
        assert summary["ttft_seconds"]["median"] == 0.4
        assert summary["ttft_seconds"]["max"] == 0.6
        assert summary["total_seconds"]["max"] == 3.0
        assert summary["first_token_before_completion"] is True

    def test_first_token_after_completion_is_flagged(self):
        runs = [{"ttft_seconds": 2.0, "total_seconds": 1.0}]
        assert msl.summarize(runs)["first_token_before_completion"] is False

    def test_missing_ttft_is_reported_as_none(self):
        runs = [{"ttft_seconds": None, "total_seconds": 1.0}]
        summary = msl.summarize(runs)
        assert summary["ttft_seconds"]["min"] is None
        assert summary["first_token_before_completion"] is False

    def test_report_is_json_serializable(self):
        summary = msl.summarize([{"ttft_seconds": 0.1, "total_seconds": 0.5}])
        assert json.loads(json.dumps(summary))["runs"] == 1
