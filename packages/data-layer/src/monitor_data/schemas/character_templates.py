"""
Pydantic schemas for portable character templates (G-6 / P&F §6).

A character template is a *portable* description of a player character: the
concept, the personality, the voice, the backstory beats. It deliberately
carries **no** stats, no skills, no universe binding and no game-system
binding — a template says *who this person is*; the world they are played in
supplies the mechanics. A template is instantiated into a real character per
campaign.

Storage: the existing ``characters`` collection (additive optional fields), so
a template is a character document that additionally carries the template
fields and ``is_template: true``. One collection means a persona already used
in OOC chat stays reachable, and the live character readers keep working
untouched. The character list excludes templates.

See ``docs/architecture/GAP_REMEDIATION_PLAN.md`` §G-6.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CharacterTemplateCreate(BaseModel):
    """Create a portable character template.

    No stats, skills, universe_id or game_system_id — by design (P&F §6).
    """

    name: str = Field(min_length=1, max_length=200, description="Template name")
    concept: str = Field(
        default="",
        max_length=2000,
        description="One-line concept: who this character is, in the author's words",
    )
    personality: str = Field(default="", max_length=4000, description="Free-text personality notes")
    backstory_beats: list[str] = Field(
        default_factory=list,
        description="Ordered backstory beats used to draft answers during character creation",
    )
    voice: str = Field(
        default="",
        max_length=2000,
        description="How the character speaks — tone, cadence, verbal tics",
    )
    portrait_url: str | None = Field(default=None, max_length=1000, description="Portrait image URL")
    first_message: str = Field(default="", max_length=8000, description="Opening message when chat starts")
    gm_notes: str = Field(
        default="",
        max_length=8000,
        description="Author's notes for the AI — not shown to players",
    )


class CharacterTemplateUpdate(BaseModel):
    """Update a portable character template. Unset fields are left alone."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    concept: str | None = Field(default=None, max_length=2000)
    personality: str | None = Field(default=None, max_length=4000)
    backstory_beats: list[str] | None = None
    voice: str | None = Field(default=None, max_length=2000)
    portrait_url: str | None = Field(default=None, max_length=1000)
    first_message: str | None = Field(default=None, max_length=8000)
    gm_notes: str | None = Field(default=None, max_length=8000)


class CharacterTemplateResponse(BaseModel):
    """A portable character template."""

    template_id: str = Field(description="Template ID (the character document's id)")
    name: str
    concept: str = ""
    personality: str = ""
    backstory_beats: list[str] = Field(default_factory=list)
    voice: str = ""
    portrait_url: str | None = None
    first_message: str = ""
    gm_notes: str = ""
    usage_count: int = Field(default=0, description="How many characters were instantiated from it")
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CharacterTemplateFilter(BaseModel):
    """Filter parameters for listing character templates."""

    name_contains: str | None = Field(default=None, max_length=200)
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class CharacterTemplateListResponse(BaseModel):
    """Response for listing character templates."""

    templates: list[CharacterTemplateResponse] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    offset: int = 0
