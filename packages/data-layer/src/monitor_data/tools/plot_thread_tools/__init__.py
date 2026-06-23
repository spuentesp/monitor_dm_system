"""
Plot thread detection and management tools (Temporal & Contradiction Gap).

LAYER: 1 (data-layer)

This package provides utilities for:
  - Detecting plot threads from scene content
  - Updating plot thread status based on scene outcomes
  - Classifying narrative content into thread categories

Public modules:
  - scene_thread_detection: Extract and update plot threads from scenes
"""

from monitor_data.tools.plot_thread_tools.scene_thread_detection import (
    classify_thread_content,
    detect_plot_threads_from_scene,
    update_thread_status_from_scene,
)

__all__ = [
    "detect_plot_threads_from_scene",
    "update_thread_status_from_scene",
    "classify_thread_content",
]
