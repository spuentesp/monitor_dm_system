"""Image-generation settings (Task 10, Layer 1).

The Settings model is the single source of truth for the per-deployment
defaults — values come from environment variables via ``monitor_data.config``
and the live UI overrides live in a MongoDB singleton document with
``_id="global"``. The UI layer merges the two, with the Mongo overrides
winning on a per-field basis.

Bounds are enforced here, not in the router. Tight bounds keep a
misconfigured ``image_max_per_actor_hour`` from accidentally slowing the
generation pipeline to a halt, and reject pathologically small ``0``
budgets that would deadlock the whole scene. The router still surfaces
the 422 cleanly via FastAPI's standard validation.

The schema intentionally never invents a "lines_and_veils" rule set when
the campaign has none — that's ``image_policy.check_image_policy``'s
job, called separately by the router with the active SceneState.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ImageGenerationSettings(BaseModel):
    """Persisted + defaulted image-generation settings.

    Defaults are populated by ``monitor_data.config.settings`` (env / .env).
    The same shape is the response and PUT body for the
    ``/api/image/settings`` endpoints.
    """

    image_moderation_mode: Literal["provider_default", "lines_and_veils"] = Field(
        default="provider_default",
        description="Image moderation policy applied before the provider is invoked.",
    )
    image_max_per_scene: int = Field(
        default=4,
        ge=0,
        le=100,
        description="Hard cap on successful generations per scene (0 disables).",
    )
    image_max_per_conversation: int = Field(
        default=8,
        ge=0,
        le=100,
        description="Hard cap on successful generations per conversation/session.",
    )
    image_max_per_actor_hour: int = Field(
        default=12,
        ge=0,
        le=1000,
        description="Hard cap on successful generations per actor per hour.",
    )
    image_suggestions_enabled: bool = Field(
        default=True,
        description="Whether the scene loop may emit image suggestion chips.",
    )


__all__ = ["ImageGenerationSettings"]
