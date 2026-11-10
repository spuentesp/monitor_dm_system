"""Meta-tests for scripts/light_rp_recall_check.py (Phase 7, task 7 substitute).

Only the pure helpers are tested hermetically — the live 30-turn run needs a
person and a configured model (the coordinator runs the script itself).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "light_rp_recall_check.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("light_rp_recall_check", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


lr = _load_mod()


class TestPlanTurns:
    def test_plans_two_sittings_and_probes_for_thirty_turns(self):
        sitting_1, sitting_2, probes = lr.plan_turns(30, "zephyr-test1")
        assert len(sitting_1) + len(sitting_2) == 30
        assert len(sitting_1) == 15
        assert len(sitting_2) == 15
        assert len(probes) == 2

    def test_detail_is_planted_in_the_first_sitting(self):
        sitting_1, sitting_2, probes = lr.plan_turns(30, "zephyr-test2")
        assert any("zephyr-test2" in line for line in sitting_1)
        assert not any("zephyr-test2" in line for line in sitting_2)
        assert sitting_2[0].startswith("Hello again")
        assert all("safe word" in probe.lower() for probe in probes)

    def test_pads_to_the_requested_turn_count(self):
        sitting_1, sitting_2, probes = lr.plan_turns(40, "zephyr-test3")
        assert len(sitting_1) + len(sitting_2) == 40


class TestCheckRecall:
    def test_passes_when_any_probe_reply_carries_the_word(self):
        assert lr.check_recall(["no idea", "It was zephyr-abc, wasn't it?"], "zephyr-abc") is True

    def test_fails_when_no_reply_carries_the_word(self):
        assert lr.check_recall(["I don't recall.", "Hmm."], "zephyr-abc") is False

    def test_match_is_case_insensitive(self):
        assert lr.check_recall(["ZEPHYR-ABC"], "zephyr-abc") is True


class TestSseParsing:
    def test_parses_chunks_and_reassembles_the_reply(self):
        body = (
            'data: {"id": "c1", "monitor_session_id": "conv-1", "choices": [{"delta": {"role": "assistant"}}]}\n\n'
            'data: {"id": "c1", "choices": [{"delta": {"content": "Well "}}]}\n\n'
            'data: {"id": "c1", "choices": [{"delta": {"content": "met."}}]}\n\n'
            "data: [DONE]\n\n"
        )
        chunks = lr.parse_sse_chunks(body)
        text, session_id = lr.reply_text_from_chunks(chunks)
        assert text == "Well met."
        assert session_id == "conv-1"

    def test_skips_malformed_frames(self):
        body = 'data: {not json}\n\ndata: {"choices": [{"delta": {"content": "hi"}}]}\n\n'
        chunks = lr.parse_sse_chunks(body)
        assert len(chunks) == 1
        text, _ = lr.reply_text_from_chunks(chunks)
        assert text == "hi"


class TestCodeWord:
    def test_code_word_is_unique_per_run(self):
        assert lr.make_code_word() != lr.make_code_word()
