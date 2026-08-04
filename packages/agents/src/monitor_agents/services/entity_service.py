"""
Entity Service — Encapsulates core RPG entity logic (SYS-1, P-21).

LAYER: 2 (agents)
IMPORTS FROM: monitor_data (Layer 1)
CALLED BY: CLI, UI Routers, Agents
"""

import anyio
from uuid import UUID

from monitor_data.schemas.entities import (
    LevelUpRequest,
    LevelUpResponse,
    DowntimeResponse,
)
from monitor_data.schemas.character_sheets import CharacterSheetFilter
from monitor_data.schemas.working_state import WorkingStateUpdate
from monitor_data.tools.mongodb_tools.working_state import (
    mongodb_get_working_state,
    mongodb_update_working_state,
)
from monitor_data.tools.mongodb_tools.character_sheets import mongodb_list_character_sheets
from monitor_data.tools.mongodb_tools import mongodb_get_game_system


class EntityProgressionService:
    """Service handling character advancement and progression mechanics."""

    @staticmethod
    async def process_level_up(character_id: UUID, request: LevelUpRequest) -> LevelUpResponse:
        """Spend accumulated XP to advance a character to the next level (P-21)."""
        current_xp = 0
        current_level = 1
        state_id: UUID | None = None

        # 1. Get current XP/level from working state
        if request.scene_id:
            try:
                scene_uuid = UUID(request.scene_id)
                ws = await anyio.to_thread.run_sync(lambda: mongodb_get_working_state(character_id, scene_uuid))
                if ws and getattr(ws, "state", None):
                    current_xp = int(ws.state.xp or 0)
                    current_level = int(ws.state.level or 1)
                    state_id = ws.state.state_id
            except Exception:
                pass  # Fall through to character sheet

        # 1b. Get current XP/level from character sheet
        if current_xp == 0 and not state_id:
            try:
                sheets = await anyio.to_thread.run_sync(
                    lambda: mongodb_list_character_sheets(
                        CharacterSheetFilter(entity_id=character_id, is_active=True, limit=1)
                    )
                )
                if sheets.sheets:
                    sheet = sheets.sheets[0]
                    current_xp = sheet.experience_points
                    current_level = sheet.total_level
            except Exception:
                pass

        # 2. Load the game system's advancement model
        system_id_str = request.system_id
        if not system_id_str:
            try:
                sheets = await anyio.to_thread.run_sync(
                    lambda: mongodb_list_character_sheets(
                        CharacterSheetFilter(entity_id=character_id, is_active=True, limit=1)
                    )
                )
                if sheets.sheets and sheets.sheets[0].game_system_id:
                    system_id_str = str(sheets.sheets[0].game_system_id)
            except Exception:
                pass

        if not system_id_str:
            raise ValueError("No game system specified and none found on character sheet")

        try:
            system = await anyio.to_thread.run_sync(lambda: mongodb_get_game_system(UUID(system_id_str)))
        except Exception as exc:
            raise ValueError(f"Game system not found: {exc}") from exc

        advancement = getattr(system, "advancement", None) if system else None
        if not advancement:
            raise ValueError("Game system has no advancement model — cannot level up")

        # 3. Check if XP is sufficient for next level
        next_level = current_level + 1
        progression_table = advancement.progression_table or []

        next_entry = None
        for entry in progression_table:
            if entry.level == next_level:
                next_entry = entry
                break

        if next_entry and next_entry.xp_required is not None:
            if current_xp < next_entry.xp_required:
                raise ValueError(
                    f"Insufficient XP: have {current_xp}, need {next_entry.xp_required} for level {next_level}"
                )

        if advancement.max_level and current_level >= advancement.max_level:
            raise ValueError(f"Already at max level {advancement.max_level}")

        # 4. Apply level-up
        features_gained = list(next_entry.features_gained) if next_entry else []
        resource_increases = dict(next_entry.resource_increases) if next_entry else {}

        if state_id:
            new_stats = {"xp": current_xp, "level": next_level}
            await anyio.to_thread.run_sync(
                lambda: mongodb_update_working_state(
                    state_id,
                    WorkingStateUpdate(current_stats=new_stats),
                )
            )

        return LevelUpResponse(
            entity_id=str(character_id),
            old_level=current_level,
            new_level=next_level,
            xp_remaining=current_xp - (next_entry.xp_required if next_entry and next_entry.xp_required else 0),
            features_gained=features_gained,
            resource_increases=resource_increases,
            message=f"Level up! {current_level} → {next_level}",
        )

    @staticmethod
    async def get_downtime_options(character_id: UUID, scene_id: str | None, system_id: str | None) -> DowntimeResponse:
        """Get available progression options for a character during downtime (P-21)."""
        current_xp = 0
        current_level = 1

        # 1. Get current XP/level
        if scene_id:
            try:
                scene_uuid = UUID(scene_id)
                ws = await anyio.to_thread.run_sync(lambda: mongodb_get_working_state(character_id, scene_uuid))
                if ws and getattr(ws, "state", None):
                    current_xp = int(ws.state.xp or 0)
                    current_level = int(ws.state.level or 1)
            except Exception:
                pass

        if current_xp == 0:
            try:
                sheets = await anyio.to_thread.run_sync(
                    lambda: mongodb_list_character_sheets(
                        CharacterSheetFilter(entity_id=character_id, is_active=True, limit=1)
                    )
                )
                if sheets.sheets:
                    sheet = sheets.sheets[0]
                    current_xp = sheet.experience_points
                    current_level = sheet.total_level
                    if not system_id and sheet.game_system_id:
                        system_id = str(sheet.game_system_id)
            except Exception:
                pass

        # 2. Load advancement model
        if not system_id:
            return DowntimeResponse(
                entity_id=str(character_id),
                current_xp=current_xp,
                current_level=current_level,
                can_level_up=False,
                message="No game system found — cannot evaluate progression",
            )

        try:
            system = await anyio.to_thread.run_sync(lambda: mongodb_get_game_system(UUID(system_id)))
        except Exception as exc:
            raise ValueError(f"Game system not found: {exc}") from exc

        advancement = getattr(system, "advancement", None) if system else None
        if not advancement:
            return DowntimeResponse(
                entity_id=str(character_id),
                current_xp=current_xp,
                current_level=current_level,
                can_level_up=False,
                message="Game system has no advancement model",
            )

        # 3. Check if level-up is available
        next_level = current_level + 1
        next_entry = None
        for entry in advancement.progression_table or []:
            if entry.level == next_level:
                next_entry = entry
                break

        if advancement.max_level and current_level >= advancement.max_level:
            return DowntimeResponse(
                entity_id=str(character_id),
                current_xp=current_xp,
                current_level=current_level,
                can_level_up=False,
                message=f"Already at max level {advancement.max_level}",
            )

        xp_required = next_entry.xp_required if next_entry else None
        can_level = xp_required is None or current_xp >= xp_required

        message = (
            "Progression available"
            if can_level
            else (f"Need {xp_required - current_xp} more XP" if xp_required else "No progression table")
        )

        return DowntimeResponse(
            entity_id=str(character_id),
            current_xp=current_xp,
            current_level=current_level,
            can_level_up=can_level,
            next_level_xp_required=xp_required,
            available_features=list(next_entry.features_gained) if next_entry else [],
            available_resource_increases=dict(next_entry.resource_increases) if next_entry else {},
            message=message,
        )
