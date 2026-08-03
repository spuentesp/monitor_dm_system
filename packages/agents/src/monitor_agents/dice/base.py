"""
Generic DiceEngine protocol + registry.

Sub-plan 4. Every game system (VtM V20, Lancer, D&D 5e, ...) can
plug in by implementing the DiceEngine protocol. The registry
maps a game system name to its engine, so the resolver picks the
right one based on ``scene_state.game_system``.

A DiceEngine is responsible for:
  1. Resolving a contested check for the system
     (d10 pool vs DC for VtM; d20 + mod for D&D; 2d6 + mod for Lancer)
  2. Handling system-specific spends (willpower reroll, luck points,
     stress expenditures)
  3. Returning a typed result the resolver can use to drive
     narrative outcome and resource updates

The protocol is intentionally small (one method, ``resolve_check``)
so engines are easy to implement. Other methods (reroll, spend) are
optional via default implementations.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DiceEngine(Protocol):
    """Protocol every game-system-specific dice engine implements.

    Concrete engines (e.g. ``PoolDiceEngine``) implement these methods
    for one mechanic class. Engines are stateless — they take
    all context as input and return a typed result.
    """

    name: str
    """Stable identifier of the engine. Used as the registry key."""

    def resolve_check(
        self,
        *,
        pool_size: int,
        difficulty: int,
        context: dict[str, Any] | None = None,
    ) -> Any:
        """Resolve a single contested check.

        Args:
            pool_size:    Number of dice to roll (VtM: pool of d10s;
                           D&D 5e: ignored; Lancer: ignored).
            difficulty:   Target number to beat (VtM: difficulty 1-10;
                           D&D 5e: DC).
            context:      Free-form engine-specific context (hunger
                           dice count, willpower remaining, ...).
                           Default empty.

        Returns:
            An engine-specific typed result (e.g. ``VtMContestedCheck``).
            Engines must define a result class with at least
            ``successes: int`` so callers can branch.
        """


class DiceEngineRegistry:
    """Maps a game system name to its DiceEngine.

    Engines register themselves on import (e.g. ``PoolDiceEngine`` calls
    ``default_dice_registry.register(engine)`` at module load). The
    resolver picks the right engine by looking up
    ``scene_state.game_system``.
    """

    def __init__(self) -> None:
        self._engines: dict[str, DiceEngine] = {}

    def register(self, engine: DiceEngine) -> None:
        """Add an engine to the registry. Overwrites if ``engine.name``
        is already registered."""
        self._engines[engine.name] = engine

    def get(self, name: str) -> DiceEngine:
        """Look up an engine by name. Falls back to the generic
        engine if the requested one is not registered, so the system
        never crashes for an unknown game system."""
        if name in self._engines:
            return self._engines[name]
        return self._engines.get("generic") or _fallback_engine()

    def has(self, name: str) -> bool:
        return name in self._engines


class _FallbackEngine:
    """Used when even the 'generic' engine isn't registered. The
    resolver path is best-effort — a missing engine is a dev
    misconfiguration, not a user error."""

    name = "generic"

    def resolve_check(self, **_kwargs: Any) -> Any:

        class _GenericResult:
            def __init__(self) -> None:
                self.successes = 0
                self.dice_formula = "1d20"
                self.raw_rolls: list[int] = []
                self.engine = "generic"

        return _GenericResult()


def _fallback_engine() -> DiceEngine:
    return _FallbackEngine()  # type: ignore[return-value]


default_dice_registry = DiceEngineRegistry()
"""Process-wide registry. Importing ``monitor_agents.dice`` ensures
all built-in engines (generic, VtM V20) are registered."""
