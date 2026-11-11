"""Every number the Analyzer batches with, as a setting with an env override (I-17).

Read at call time, not import time, so a test or an operator can change the
environment between runs without restarting the process. The pre-phase values
stay reachable through the same knobs:

=============================  ==============================  =====================
Setting                        Default                         Pre-phase behaviour
=============================  ==============================  =====================
MONITOR_ANALYZER_BATCH_WORDS   3000 (sections fill to this)    1000000 (no word cap)
MONITOR_ANALYZER_BATCH_SECTIONS 16 (hard cap per call)         2 (the old BATCH_SIZE)
MONITOR_ANALYZER_SUMMARY_BATCH  10 (sections per summary call)  1 (one call per section)
MONITOR_ANALYZER_LLM_CACHE      0 (disk cache off)              n/a (new, off)
MONITOR_ANALYZER_LLM_CACHE_DIR  ~/.cache/monitor/analyzer-llm   n/a
=============================  ==============================  =====================

Old settings side by side with new ones (the coordinator's 20-page slice)::

    MONITOR_ANALYZER_BATCH_SECTIONS=2 MONITOR_ANALYZER_BATCH_WORDS=1000000 \
    MONITOR_ANALYZER_SUMMARY_BATCH=1
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

# Word budget for one batched-extraction call. A section longer than the
# budget still travels alone — sections are the atomic unit of extraction.
DEFAULT_BATCH_WORDS = 3000

# Hard cap on sections in one batched-extraction call (the pre-phase
# BATCH_SIZE was 2; 16 lets many small sections share one call while the
# word budget keeps the prompt bounded).
DEFAULT_BATCH_SECTIONS = 16

# Sections per section-summary call (the pre-phase code called once per section).
DEFAULT_SUMMARY_BATCH = 10

# Disk cache of model responses: off by default, off in tests unless a test
# turns it on deliberately. Nothing is ever written under the repository.
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "monitor" / "analyzer-llm"


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(value, minimum)


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "0").strip().lower() in ("1", "true", "yes")


def batch_words() -> int:
    """Max words of section text in one batched-extraction call."""
    return _env_int("MONITOR_ANALYZER_BATCH_WORDS", DEFAULT_BATCH_WORDS)


def batch_sections() -> int:
    """Max sections in one batched-extraction call."""
    return _env_int("MONITOR_ANALYZER_BATCH_SECTIONS", DEFAULT_BATCH_SECTIONS)


def summary_batch() -> int:
    """Sections per section-summary call; 1 restores one call per section."""
    return _env_int("MONITOR_ANALYZER_SUMMARY_BATCH", DEFAULT_SUMMARY_BATCH)


def llm_cache_enabled() -> bool:
    """The disk response cache is off unless MONITOR_ANALYZER_LLM_CACHE says otherwise."""
    return _env_bool("MONITOR_ANALYZER_LLM_CACHE")


def llm_cache_dir() -> Path:
    """Where the disk cache lives — outside the repository by default."""
    raw = os.environ.get("MONITOR_ANALYZER_LLM_CACHE_DIR")
    if raw and raw.strip():
        return Path(raw).expanduser()
    return DEFAULT_CACHE_DIR


def settings_hash() -> str:
    """Fingerprint of the batching settings, so a settings change invalidates saved batches."""
    payload = json.dumps(
        {
            "batch_words": batch_words(),
            "batch_sections": batch_sections(),
            "summary_batch": summary_batch(),
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
