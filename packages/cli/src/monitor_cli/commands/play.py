"""
MONITOR Play — Solo Play interactive REPL.

LAYER: 3 (cli)
IMPORTS FROM: monitor_agents (Layer 2)
NEVER IMPORTS: monitor_data (Layer 1)

Usage:
    $ monitor play
    $ monitor play --tone grim
    $ monitor play --gm-profile <uuid>
    $ monitor play --scene <scene-id> --story <story-id>
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import typing
from typing import Any
from uuid import UUID, uuid4

# reason: nest_asyncio lacks type stubs; suppress until upstream adds py.typed
import nest_asyncio  # type: ignore
import typer
from monitor_agents.canonkeeper.agent import CanonKeeper
from monitor_agents.loops.character_creation_loop import CharacterCreationLoop
from monitor_agents.loops.conversation_loop import ConversationLoop, ConversationMode
from monitor_agents.loops.preplay_support import resolve_authored_session_zero_questions
from monitor_agents.loops.scene_loop import SceneLoop
from monitor_agents.loops.session_zero_loop import SessionZeroLoop
from monitor_agents.loops.story_loop import StoryLoop
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

nest_asyncio.apply()

app = typer.Typer(help="Start or continue a solo-play session")
console = Console()
logger = logging.getLogger(__name__)


@app.command()
def start(
    tone: str = typer.Option(
        "dramatic",
        "--tone",
        "-t",
        help="Narrative tone (dramatic/grim/horror/heroic/mystery/adventure)",
    ),
    play_mode: str = typer.Option(
        "narrative",
        "--mode",
        "-m",
        help="Play mode: narrative (default) / dice_standard / dice_game_system",
    ),
    universe_id: str | None = typer.Option(None, "--universe", "-u", help="Universe UUID to play in"),
    gm_profile_id: str | None = typer.Option(
        None, "--gm-profile", "-g", help="GM Profile UUID — overrides tone when set"
    ),
    scene_id: str | None = typer.Option(None, "--scene", "-s", help="Existing scene UUID to resume"),
    story_id: str | None = typer.Option(None, "--story", "-S", help="Story UUID"),
    max_turns: int = typer.Option(50, "--max-turns", help="Maximum turns per scene"),
    new_character: str | None = typer.Option(
        None,
        "--new-character",
        "-c",
        help="Create a new character before starting play",
    ),
) -> None:
    """Start a solo-play session with the AI Game Master."""
    asyncio.run(
        _run_play(
            tone=tone,
            play_mode=play_mode,
            universe_id=universe_id,
            gm_profile_id=gm_profile_id,
            scene_id=scene_id,
            story_id=story_id,
            max_turns=max_turns,
            new_character=new_character,
        )
    )


async def _run_play(
    *,
    tone: str,
    play_mode: str,
    universe_id: str | None,
    gm_profile_id: str | None,
    scene_id: str | None,
    story_id: str | None,
    max_turns: int,
    new_character: str | None,
) -> None:
    """Async core of the play command."""
    # Imports moved to module level for clarity and DRY reuse

    # Resolve UUIDs
    resolved_universe: UUID | None = UUID(universe_id) if universe_id else None
    resolved_story: UUID | None = UUID(story_id) if story_id else None
    resolved_scene: UUID | None = UUID(scene_id) if scene_id else None

    # Interactive Guided Setup (P-10/P-11)
    if not resolved_universe:
        resolved_universe = await _select_universe_interactive()

    if not resolved_universe:
        # Fallback or exit if no universe selected/created
        console.print("[yellow]No universe selected. Exiting.[/yellow]")
        raise typer.Exit()

    if not resolved_story:
        resolved_story = await _select_story_interactive(resolved_universe)

    if not resolved_story:
        console.print("[yellow]No story selected. Exiting.[/yellow]")
        raise typer.Exit()

    # Character Selection (P-10/P-11)
    resolved_actor_id: UUID | None = None
    if new_character:
        resolved_actor_id = await _create_new_character(
            new_character, resolved_universe, resolved_scene or uuid4(), resolved_story
        )
    else:
        resolved_actor_id = await _select_character_interactive(resolved_universe, resolved_story)

    if not resolved_actor_id:
        console.print("[yellow]No character selected. Exiting.[/yellow]")
        raise typer.Exit()

    # Note: Layer 3 (CLI) should NOT import from monitor_data (Layer 1).
    # We pass the gm_profile_id to SceneLoop (Layer 2) which can handle it.
    resolved_gm_profile = UUID(gm_profile_id) if gm_profile_id else None

    # Resolve GM profile name for display only
    # (SceneLoop will reload the full profile inside the loop)
    if resolved_gm_profile:
        try:
            profile = SceneLoop.get_gm_profile(resolved_gm_profile)
            if profile:
                tone = profile.get("name", tone)
        except Exception:
            pass

    # Start or resume the story loop to handle world state and scene progression
    story_loop = StoryLoop(story_id=resolved_story, universe_id=resolved_universe)

    console.print("[dim]Initializing story and world state...[/dim]")
    story_state = await story_loop.start_or_resume()

    # If the user explicitly provided a scene_id, we respect it,
    # otherwise we take the current scene from the story state.
    scene_val = resolved_scene or story_state.get("current_scene_id")
    current_scene_id: UUID = UUID(str(scene_val)) if scene_val else uuid4()

    while True:
        loop = SceneLoop(
            scene_id=current_scene_id,
            story_id=resolved_story,
            universe_id=resolved_universe,
            gm_profile_id=resolved_gm_profile,
            max_turns=max_turns,
            play_mode=play_mode,
            session_tone=tone,
            actor_id=resolved_actor_id,
            # story_state was already available here (start_or_resume /
            # complete_current_scene / create_flashback all return it) but
            # was never passed to SceneLoop -- the arc_label/tension_score/
            # story_premise injection in Narrator._generate_narrative_and_
            # proposals was dead code for CLI play too. See
            # CHARACTER_TEMPLATES_AND_GM_CONDITIONING_PLAN.md Q3.
            story_state=story_state,
        )

        # Banner
        console.print(
            Panel.fit(
                f"[bold]MONITOR — Solo Play[/bold]\n"
                f"Scene: [cyan]{current_scene_id}[/cyan]\n"
                f"Story: [cyan]{resolved_story}[/cyan]\n"
                f"Tone:  [yellow]{tone}[/yellow]\n"
                f"Mode:  [yellow]{play_mode}[/yellow]\n"
                f"GM Profile: [yellow]{gm_profile_id or 'default'}[/yellow]",
                title="🎭 Game Master",
                border_style="bright_blue",
            )
        )
        console.print("[dim]Type your actions or dialogue. Use [bold]/quit[/bold] to end the session.[/dim]")
        console.print("[dim]Use [bold]/ooc[/bold] before a message for out-of-character questions.[/dim]\n")

        turn_number = 0
        scene_completed_naturally = False
        user_quit = False

        while turn_number < max_turns:
            try:
                # Prompt for input
                console.print("[bold green]>[/bold green] ", end="")
                user_input = input().strip()
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Session interrupted.[/dim]")
                user_quit = True
                break

            if not user_input:
                continue

            # Handle commands
            if user_input.lower() in ("/quit", "/exit", "/q"):
                console.print("[dim]Ending session...[/dim]")
                user_quit = True
                break

            if user_input.lower() in ("/help", "/h"):
                _print_help()
                continue

            if user_input.lower() == "/status":
                _print_status(current_scene_id, resolved_story, tone, play_mode, turn_number, max_turns)
                continue

            if user_input.lower() == "/backtrack":
                console.print("[yellow]Backtracking to previous turn...[/yellow]")
                backtrack_result = await loop.backtrack()
                if "error" in backtrack_result:
                    console.print(f"[red]Error:[/red] {backtrack_result['error']}")
                else:
                    turn_number = max(0, turn_number - 1)
                    console.print("[green]State restored. You can re-enter your action.[/green]")
                continue

            if user_input.lower().startswith("/flashback "):
                flashback_desc = user_input[11:].strip()
                if not flashback_desc:
                    console.print(
                        "[red]Error:[/red] Please provide a description for the flashback. e.g. /flashback A meeting in the old tavern 5 years ago"
                    )
                    continue

                console.print(f"[yellow]Initiating flashback: {flashback_desc}[/yellow]")
                # End current scene
                await loop.finalize()

                # Create flashback scene
                story_state = await story_loop.create_flashback(purpose=flashback_desc, time_description="A past event")

                current_scene_id = typing.cast(UUID, story_state.get("current_scene_id"))
                console.print("\n[bold cyan]--- Flashback Started ---[/bold cyan]\n")
                break  # Exit inner turn loop to restart with new scene

            if user_input.lower() == "/party":
                # Switch character (P-13)
                new_actor_id = await _select_character_interactive(resolved_universe, resolved_story)
                if new_actor_id and new_actor_id != resolved_actor_id:
                    resolved_actor_id = new_actor_id
                    console.print(f"[green]Switched to character {resolved_actor_id}[/green]")
                    # We need to restart the loop with the new actor
                    break
                continue

            if user_input.lower() == "/npc-studio":
                # Enter NPC Studio (Simulated room / Actor mode)
                await _run_npc_studio(resolved_universe, current_scene_id, resolved_story)
                continue

            if user_input.lower() == "/godmode":
                # Toggle between current play_mode and 'narrative' (default).
                if play_mode == "narrative":
                    play_mode = "dice_game_system"  # Switch back to dice rules
                    console.print("[yellow]God Mode disabled. Rules and dice are back in play.[/yellow]")
                else:
                    play_mode = "narrative"
                    console.print("[bold green]Narrative God Mode enabled. Your words are law.[/bold green]")
                continue

            if user_input.lower() == "/inventory":
                # Show party inventory (P-13)
                await _show_inventory(resolved_story)  # In a real app, we'd use party_id linked to story
                continue

            # OOC prefix handling — wrap in ((...)) rather than strip, so
            # the explicit signal reaches the GM as the same syntax it
            # already recognizes (gm_awareness.py documents "((" as an OOC
            # marker). A plain-text-only prefix never reached the model.
            if user_input.lower().startswith("/ooc "):
                user_input = f"(({user_input[5:].strip()}))"

            # Run the turn
            turn_number += 1
            console.print(f"[dim]--- Turn {turn_number} ---[/dim]")

            try:
                result = await loop.run(user_input)

                # Display narrative — split ((...)) OOC asides from
                # in-fiction prose so a response mixing both (e.g. mostly
                # narration with one OOC note) renders each part in its
                # own panel. *action* markup needs no special handling;
                # Rich's Markdown renderer already italicizes it.
                narrative = result.get("narrative_text") or result.get("narrative", "")
                if narrative:
                    for is_ooc, block in _split_narration_blocks(narrative):
                        if is_ooc:
                            console.print(Panel(block, title="OOC", border_style="yellow"))
                        else:
                            console.print(Panel(Markdown(block), title="GM", border_style="blue"))

                # Show resolution if present
                resolution = result.get("resolution")
                if resolution and isinstance(resolution, dict):
                    _show_resolution(resolution)

                # Check if scene is complete
                if result.get("scene_complete"):
                    scene_completed_naturally = True
                    console.print(
                        Panel(
                            "[bold]Scene Complete[/bold]\nThe scene has reached its natural conclusion.",
                            border_style="green",
                        )
                    )
                    break

            except Exception as exc:
                console.print(f"[red]Error during turn:[/red] {exc}")
                console.print("[dim]You can continue playing or type /quit to exit.[/dim]")

        # We have exited the turn loop for this scene.
        await loop.finalize()

        if user_quit:
            console.print("[green]Session saved. See you next time![/green]")
            break

        if turn_number >= max_turns and not scene_completed_naturally:
            console.print(f"\n[yellow]Maximum turns ({max_turns}) reached for this scene.[/yellow]")
            # Do we transition to a new scene automatically on timeout?
            # Usually yes, or prompt user. For now, let's treat it as a break.
            break

        if scene_completed_naturally:
            console.print("[dim]Simulating world events and transitioning to next scene...[/dim]")
            outcome = {
                "scene_complete": True,
                "total_minutes_passed": turn_number * 10,
            }  # rough estimate
            story_state = await story_loop.complete_current_scene(scene_id=current_scene_id, outcome=outcome)

            if story_state.get("story_complete"):
                console.print(
                    Panel(
                        "[bold]Story Complete[/bold]\nThe arc has reached its conclusion.",
                        border_style="green",
                    )
                )
                break

            next_scene_id = story_state.get("current_scene_id")
            if next_scene_id and next_scene_id != current_scene_id:
                current_scene_id = next_scene_id
                console.print("\n[bold cyan]--- New Scene ---[/bold cyan]\n")
                continue
            else:
                console.print("[red]Error:[/red] Failed to bootstrap next scene.")
                break


async def _select_universe_interactive() -> UUID | None:
    """Interactively select a universe or create a new one."""
    agent = CanonKeeper(agent_id="setup-1")

    console.print("\n[bold]Select a Universe[/bold]")

    try:
        raw_universes = await agent.call_tool("neo4j_list_universes", {"filters": {}})
        universes_data = json.loads(raw_universes) if isinstance(raw_universes, str) else raw_universes
        universes = universes_data if isinstance(universes_data, list) else []
    except Exception as exc:
        logger.debug(f"Failed to list universes: {exc}")
        universes = []

    if not universes:
        console.print("No universes found. Let's create a new one!")
        return await _create_universe_interactive()

    for i, u in enumerate(universes):
        console.print(f"  [cyan]{i + 1}[/cyan]) {u.get('name')} [dim]({u.get('genre', 'unknown')})[/dim]")

    console.print("  [cyan]n[/cyan]) Create a new universe")
    console.print("  [cyan]q[/cyan]) Quit")

    choice = typer.prompt("\nSelect an option", default="1")

    if choice.lower() == "q":
        return None
    if choice.lower() == "n":
        return await _create_universe_interactive()

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(universes):
            return UUID(universes[idx]["id"])
    except (ValueError, IndexError):
        pass

    console.print("[red]Invalid selection.[/red]")
    return await _select_universe_interactive()


async def _create_universe_interactive() -> UUID | None:
    """Interactively create a new universe."""
    console.print("\n[bold]Create New Universe[/bold]")
    name = typer.prompt("Universe Name")
    genre = typer.prompt("Genre (e.g. Fantasy, Sci-Fi, Cyberpunk)", default="Fantasy")

    keeper = CanonKeeper()

    try:
        # We need a multiverse first. Use the default one or create one.
        multiverses = await keeper.call_tool("neo4j_list_multiverses", {})
        m_data = json.loads(multiverses) if isinstance(multiverses, str) else multiverses

        if not m_data:
            m_res = await keeper.create_multiverse(
                {
                    "name": f"{name} World",
                    "system_name": "generic",
                    "description": f"Main world for {name}",
                }
            )
            multiverse_id = m_res["id"]
        else:
            multiverse_id = m_data[0]["id"]

        u_res = await keeper.create_universe(
            {
                "multiverse_id": str(multiverse_id),
                "name": name,
                "genre": genre,
                "description": f"A {genre} universe called {name}.",
            }
        )
        console.print(f"[green]Universe '{name}' created![/green]")
        return UUID(u_res["id"])
    except Exception as exc:
        console.print(f"[red]Error creating universe:[/red] {exc}")
        return None


async def _select_story_interactive(universe_id: UUID) -> UUID | None:
    """Interactively select a story or create a new one."""
    agent = CanonKeeper(agent_id="setup-1")

    console.print("\n[bold]Select a Story[/bold]")

    try:
        raw_stories = await agent.call_tool(
            "neo4j_list_stories", {"params": {"universe_id": str(universe_id), "limit": 20}}
        )
        stories_data = json.loads(raw_stories) if isinstance(raw_stories, str) else raw_stories
        stories = stories_data.get("stories", []) if isinstance(stories_data, dict) else []
    except Exception as exc:
        logger.debug(f"Failed to list stories: {exc}")
        stories = []

    if not stories:
        console.print("No stories found in this universe. Let's start a new one!")
        return await _create_story_interactive(universe_id)

    for i, s in enumerate(stories):
        console.print(f"  [cyan]{i + 1}[/cyan]) {s.get('title')} [dim]({s.get('status', 'active')})[/dim]")

    console.print("  [cyan]n[/cyan]) Start a new story")
    console.print("  [cyan]q[/cyan]) Quit")

    choice = typer.prompt("\nSelect an option", default="1")

    if choice.lower() == "q":
        return None
    if choice.lower() == "n":
        return await _create_story_interactive(universe_id)

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(stories):
            return UUID(stories[idx]["id"])
    except (ValueError, IndexError):
        pass

    console.print("[red]Invalid selection.[/red]")
    return await _select_story_interactive(universe_id)


async def _create_story_interactive(universe_id: UUID) -> UUID | None:
    """Interactively start a new story."""
    console.print("\n[bold]Start New Story[/bold]")
    title = typer.prompt("Story Title", default="A New Adventure")
    typer.prompt("Story Premise", default="A hero embarks on a journey.")

    keeper = CanonKeeper()

    try:
        s_res = await keeper.create_story(
            story_id=uuid4(),
            universe_id=universe_id,
            title=title,
            story_type="campaign",
        )
        # Note: CanonKeeper.create_story usually returns the dict or object
        s_id = s_res.get("id") if isinstance(s_res, dict) else getattr(s_res, "id", None)
        console.print(f"[green]Story '{title}' started![/green]")
        return UUID(str(s_id))
    except Exception as exc:
        console.print(f"[red]Error starting story:[/red] {exc}")
        return None


async def _select_character_interactive(universe_id: UUID, story_id: UUID) -> UUID | None:
    """Interactively select a character for the story."""
    agent = CanonKeeper(agent_id="setup-1")

    console.print("\n[bold]Select your Character[/bold]")

    try:
        # story_raw is intentionally not used here — we list characters by universe
        # rather than via PARTICIPATES edges, which would require traversal through the story
        raw_entities = await agent.call_tool(
            "neo4j_list_entities",
            {"filters": {"universe_id": str(universe_id), "entity_type": "character", "limit": 20}},
        )
        entities_data = json.loads(raw_entities) if isinstance(raw_entities, str) else raw_entities
        characters = entities_data.get("entities", []) if isinstance(entities_data, dict) else []
    except Exception as exc:
        logger.debug(f"Failed to list characters: {exc}")
        characters = []

    if not characters:
        console.print("No characters found in this universe. Let's create a new one!")
        return await _create_character_via_loop(universe_id, story_id)

    for i, c in enumerate(characters):
        console.print(f"  [cyan]{i + 1}[/cyan]) {c.get('name')} [dim]({c.get('sub_type', 'character')})[/dim]")

    console.print("  [cyan]n[/cyan]) Create a new character")
    console.print("  [cyan]q[/cyan]) Quit")

    choice = typer.prompt("\nSelect an option", default="1")

    if choice.lower() == "q":
        return None
    if choice.lower() == "n":
        return await _create_character_via_loop(universe_id, story_id)

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(characters):
            return UUID(characters[idx]["id"])
    except (ValueError, IndexError):
        pass

    console.print("[red]Invalid selection.[/red]")
    return await _select_character_interactive(universe_id, story_id)


async def _create_character_via_loop(universe_id: UUID, story_id: UUID) -> UUID | None:
    """Trigger the conversational character creation loop."""
    # We'll reuse the existing _create_new_character which starts the loop
    # We just need a dummy name to trigger it if we want it to be fully conversational
    return await _create_new_character("New Hero", universe_id, uuid4(), story_id)


async def _show_inventory(story_id: UUID) -> None:
    """Show the party inventory."""
    agent = CanonKeeper(agent_id="cli-1")

    try:
        # Resolve party_id from story_id (omitted for brevity, using a mock/dummy for now)
        # In a real app, stories have a :HAS_PARTY relationship to a Party node
        raw_party = await agent.call_tool("neo4j_get_story", {"story_id": str(story_id)})
        party_data = json.loads(raw_party) if isinstance(raw_party, str) else raw_party
        party_id = party_data.get("party_id") or str(story_id)  # Fallback

        raw_inv = await agent.call_tool("mongodb_get_party_inventory", {"party_id": party_id})
        inv = json.loads(raw_inv) if isinstance(raw_inv, str) else raw_inv

        if not inv:
            console.print("[yellow]Inventory is empty.[/yellow]")
            return

        table = Table(title="Party Inventory")
        table.add_column("Item", style="green")
        table.add_column("Qty", style="cyan")
        table.add_column("Category", style="blue")

        for item in inv.get("items", []):
            table.add_row(item.get("name"), str(item.get("quantity")), item.get("category"))

        console.print(table)
        console.print(f"Total Gold: [yellow]{inv.get('gold', 0)}[/yellow]")
    except Exception as exc:
        console.print(f"[red]Error fetching inventory:[/red] {exc}")


async def _run_npc_studio(universe_id: UUID, scene_id: UUID, story_id: UUID) -> None:
    """Run an interactive NPC Studio session."""
    agent = CanonKeeper(agent_id="cli-1")

    console.print(
        Panel.fit(
            "[bold]NPC Studio[/bold]\n"
            "Talk to NPCs as characters or actors.\n"
            "Commands: [cyan]/mode[/cyan] (toggle), [cyan]/exit[/cyan]",
            title="🎬 Studio",
            border_style="magenta",
        )
    )

    # 1. Select NPCs in the scene
    try:
        raw_entities = await agent.call_tool("neo4j_get_entities_by_scene", {"scene_id": str(scene_id)})
        entities = json.loads(raw_entities) if isinstance(raw_entities, str) else raw_entities
        npcs = [e for e in entities if e.get("entity_type") == "character"]
    except Exception:
        npcs = []

    if not npcs:
        console.print("[yellow]No NPCs found in this scene.[/yellow]")
        return

    console.print("Select NPCs to join the room (comma-separated indices):")
    for i, npc in enumerate(npcs):
        console.print(f"  [cyan]{i + 1}[/cyan]) {npc.get('name')}")

    choice = typer.prompt("\nSelect NPCs", default="1")
    try:
        indices = [int(x.strip()) - 1 for x in choice.split(",")]
        selected_ids = [UUID(npcs[i]["id"]) for i in indices if 0 <= i < len(npcs)]
    except (ValueError, IndexError):
        console.print("[red]Invalid selection.[/red]")
        return

    if not selected_ids:
        return

    # 2. Start Conversation Loop
    mode = ConversationMode.DIRECT
    conv_loop = await ConversationLoop.start(
        universe_id=universe_id,
        mode=mode,
        npc_ids=selected_ids,
        scene_id=scene_id,
        story_id=story_id,
    )

    console.print(f"\n[green]Room ready with {len(selected_ids)} NPCs. Mode: {mode.value.upper()}[/green]\n")

    while True:
        try:
            console.print(f"[bold magenta]{mode.value.upper()} >[/bold magenta] ", end="")
            user_input = input().strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue

        if user_input.lower() in ("/exit", "/quit", "/q"):
            break

        if user_input.lower() == "/mode":
            # Toggle mode
            new_mode = ConversationMode.ACTOR if mode == ConversationMode.DIRECT else ConversationMode.DIRECT
            console.print(f"[yellow]Switching to {new_mode.value.upper()} mode...[/yellow]")
            await conv_loop.finish()  # Finish current session
            mode = new_mode
            conv_loop = await ConversationLoop.start(
                universe_id=universe_id,
                mode=mode,
                npc_ids=selected_ids,
                scene_id=scene_id,
                story_id=story_id,
            )
            continue

        # Process turn
        responses = await conv_loop.step(user_input)
        for resp in responses:
            name = resp.get("npc_name", "NPC")
            text = resp.get("text", "")
            color = "cyan" if mode == ConversationMode.DIRECT else "yellow"
            title = f"{name}" if mode == ConversationMode.DIRECT else f"{name} (Actor)"
            console.print(Panel(text, title=title, border_style=color))

    await conv_loop.finish()
    console.print("[dim]Studio session ended.[/dim]\n")


def _print_help() -> None:
    """Show available commands."""
    console.print(
        Panel.fit(
            "[bold]Commands:[/bold]\n"
            "  [cyan]/quit[/cyan]      — End session and save\n"
            "  [cyan]/ooc[/cyan]       — Ask an out-of-character question\n"
            "  [cyan]/backtrack[/cyan] — Undo the last turn and try again\n"
            "  [cyan]/flashback[/cyan] — Temporarily jump to a past event\n"
            "  [cyan]/npc-studio[/cyan] — Chat with NPCs in a dedicated room (as NPCs or Actors)\n"
            "  [cyan]/status[/cyan]    — Show current session info\n"
            "  [cyan]/inventory[/cyan] — Show items and gold\n"
            "  [cyan]/help[/cyan]      — Show this help\n\n"
            "[bold]Tips:[/bold]\n"
            "  • Describe what your character does or says\n"
            "  • The GM narrates the world and consequences\n"
            "  • Use ((double parentheses)) for OOC in any message",
            title="Help",
            border_style="dim",
        )
    )


def _print_status(scene_id: UUID, story_id: UUID, tone: str, play_mode: str, turn: int, max_turns: int) -> None:
    """Show current session status."""
    console.print(
        Panel.fit(
            f"Scene:  [cyan]{scene_id}[/cyan]\n"
            f"Story:  [cyan]{story_id}[/cyan]\n"
            f"Tone:   [yellow]{tone}[/yellow]\n"
            f"Mode:   [yellow]{play_mode}[/yellow]\n"
            f"Turn:   [green]{turn}[/green] / {max_turns}",
            title="Session Status",
            border_style="cyan",
        )
    )


_OOC_BLOCK_RE = re.compile(r"\({2,}(.*?)\){2,}", re.DOTALL)


def _split_narration_blocks(text: str) -> list[tuple[bool, str]]:
    """Split GM narration into ``(is_ooc, text)`` chunks.

    ``((double parentheses))`` mark a fourth-wall-breaking OOC aside
    (rules answers, meta commands, direct address to the player);
    everything else is in-fiction narration/dialogue and renders as-is
    (markdown handles ``*action*`` italics natively — no split needed
    for that marker). Tolerates 2+ parens on each side (models
    occasionally emit ``(((...)))``). Chunks are yielded in the order
    they appear; empty chunks (consecutive markers, leading/trailing
    whitespace-only spans) are dropped.
    """
    chunks: list[tuple[bool, str]] = []
    pos = 0
    for match in _OOC_BLOCK_RE.finditer(text):
        before = text[pos : match.start()].strip()
        if before:
            chunks.append((False, before))
        ooc_text = match.group(1).strip()
        if ooc_text:
            chunks.append((True, ooc_text))
        pos = match.end()
    tail = text[pos:].strip()
    if tail:
        chunks.append((False, tail))
    return chunks


def _show_resolution(resolution: dict[str, Any]) -> None:
    """Display mechanical resolution results."""
    roll = resolution.get("roll")
    outcome = resolution.get("outcome")
    difficulty = resolution.get("difficulty")

    parts: list[str] = []
    if roll:
        parts.append(f"🎲 Roll: [bold]{roll}[/bold]")
    if difficulty:
        parts.append(f"Difficulty: {difficulty}")
    if outcome:
        color = (
            "green"
            if outcome in ("success", "critical_success")
            else "red"
            if outcome in ("failure", "critical_failure")
            else "yellow"
        )
        parts.append(f"Result: [{color}]{outcome}[/{color}]")

    if parts:
        console.print(Panel(" | ".join(parts), title="Resolution", border_style="magenta"))


def build_cli_session_zero_loop(
    game_context: dict[str, Any],
    universe_id: UUID | None,
    tone: str = "dramatic",
) -> SessionZeroLoop | None:
    """Build a SessionZeroLoop driven by a curated prompt_collection.

    Reuses the shared agents-layer resolver so the CLI and the web backend
    author from the same collections. Returns ``None`` when no authored
    ``session_zero`` collection is bound for this system/universe — the CLI
    then skips the narrative interview and goes straight to mechanical
    character creation (previous behaviour).
    """
    session = {
        "universe_id": str(universe_id) if universe_id else None,
        "system_id": game_context.get("system_id"),
        "system_label": game_context.get("name"),
        "tone": tone,
    }
    authored = resolve_authored_session_zero_questions(session, game_context)
    if not authored:
        return None
    return SessionZeroLoop(
        tone=tone,
        system_name=game_context.get("name") or "Unknown System",
        max_questions=len(authored),
        authored_questions=authored,
    )


async def _run_cli_session_zero(sz_loop: SessionZeroLoop) -> Any:
    """Drive an authored Session Zero interview at the console. Returns the
    summary (or None). Safe to call only when build_cli_session_zero_loop
    returned a loop."""
    console.print("\n[bold]Session Zero[/bold] — let's discover who you are.\n")
    result = await sz_loop.start()
    while not result.get("complete"):
        console.print(f"[cyan]{result.get('gm_message', '')}[/cyan]")
        answer = input("> ").strip()
        result = await sz_loop.process_player_input(answer)
    summary = result.get("summary")
    if summary is not None:
        name = getattr(summary, "character_name", None) or ""
        concept = getattr(summary, "concept", "") or ""
        console.print(Panel(f"{name}\n{concept}".strip(), title="Your character concept"))
    return summary


async def _create_new_character(
    game_system_name: str,
    universe_id: UUID | None,
    scene_id: UUID,
    story_id: UUID,
) -> UUID:
    """
    Create a new character using the Character Creation Loop.

    This function:
    1. Loads the game system context from MongoDB
    2. Starts the CharacterCreationLoop
    3. Guides the user through the character creation process
    4. Saves the character to Neo4j via CanonKeeper
    5. Returns the character ID

    Args:
        game_system_name: Name of the game system (e.g., "D&D 5e", "Vampire: The Masquerade")
        universe_id: UUID of the universe (required for character creation)
        scene_id: UUID of the scene
        story_id: UUID of the story

    Returns:
        UUID of the created character

    Raises:
        typer.Exit: If character creation fails or is cancelled
    """
    # Load game system context from MongoDB via agent (respects layer boundaries)
    console.print(f"\n[cyan]Loading game system: {game_system_name}[/cyan]")
    try:
        agent = CanonKeeper(agent_id="char-creation")
        all_systems_raw = await agent.call_tool("mongodb_list_game_systems", {"include_builtin": True, "limit": 50})
        all_systems = json.loads(all_systems_raw) if isinstance(all_systems_raw, str) else all_systems_raw
        systems = all_systems.get("game_systems", []) if isinstance(all_systems, dict) else []
        game_context = next((s for s in systems if s.get("name") == game_system_name), None)
        if not game_context:
            console.print(f"[red]Error:[/red] Game system '{game_system_name}' not found.")
            console.print("[dim]Available systems can be listed with: monitor list systems[/dim]")
            raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to load game system: {exc}")
        raise typer.Exit(code=1)

    # Verify universe_id is provided
    if not universe_id:
        console.print("[red]Error:[/red] universe_id is required for character creation.")
        console.print("Use --universe or -u to specify the universe.")
        raise typer.Exit(code=1)

    # Initialize character creation loop
    console.print("\n[bold]Starting Character Creation[/bold]")
    console.print("=" * 50)

    # Optional narrative Session Zero interview, driven by a curated
    # prompt_collection (parity with the web preplay flow). Skipped silently
    # when no authored session_zero collection is bound.
    try:
        sz_loop = build_cli_session_zero_loop(game_context, universe_id)
        if sz_loop is not None:
            await _run_cli_session_zero(sz_loop)
    except Exception as exc:
        console.print(f"[dim]Session Zero skipped: {exc}[/dim]")

    char_loop = CharacterCreationLoop(
        scene_id=scene_id,
        story_id=story_id,
        game_context=game_context,
    )

    # Start the loop and get the first prompt
    try:
        result = await char_loop.start()
    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to start character creation: {exc}")
        raise typer.Exit(code=1)

    if result.get("error"):
        console.print(f"[red]Error:[/red] {result['error']}")
        raise typer.Exit(code=1)

    if result.get("complete"):
        console.print("[green]Character creation completed immediately.[/green]")
        character_data = result.get("character", {})
        return await _save_character_to_neo4j(character_data, universe_id)

    # Interactive character creation loop
    while not result.get("complete"):
        # Display GM message/prompt
        gm_message = result.get("gm_message", "")
        if gm_message:
            console.print(
                Panel(
                    Markdown(gm_message),
                    title="Character Creation",
                    border_style="cyan",
                )
            )

        # Get player input
        console.print("[bold green]>[/bold green] ", end="")
        try:
            player_input = input().strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Character creation cancelled.[/yellow]")
            raise typer.Exit(code=1)

        if not player_input:
            console.print("[dim]Please provide input or type 'quit' to cancel.[/dim]")
            continue

        if player_input.lower() in ("quit", "exit", "cancel", "q"):
            console.print("[yellow]Character creation cancelled.[/yellow]")
            raise typer.Exit(code=1)

        # Process player input
        try:
            result = await char_loop.process_player_input(player_input)
        except Exception as exc:
            console.print(f"[red]Error:[/red] Failed to process input: {exc}")
            console.print("[dim]You can continue or type 'quit' to cancel.[/dim]")
            continue

        if result.get("error"):
            console.print(f"[red]Error:[/red] {result['error']}")
            continue

    # Character creation complete
    character_data = result.get("character", {})
    console.print("\n[green]Character creation complete![/green]")
    console.print("=" * 50)

    # Display character sheet if available
    if character_data.get("sheet_markdown"):
        console.print(Markdown(character_data["sheet_markdown"]))

    # Save character to Neo4j
    character_id = await _save_character_to_neo4j(character_data, universe_id)
    console.print(f"[green]Character saved with ID: {character_id}[/green]")

    return character_id


async def _save_character_to_neo4j(character_data: dict[str, Any], universe_id: UUID) -> UUID:
    """
    Save character data to Neo4j via CanonKeeper.

    Args:
        character_data: Character data from CharacterCreationLoop
        universe_id: UUID of the universe

    Returns:
        UUID of the saved character

    Raises:
        typer.Exit: If saving fails
    """
    import uuid

    ck = CanonKeeper()

    # Extract character properties
    properties = {
        "character_name": character_data.get("name"),
        "concept": character_data.get("concept"),
        "system_name": character_data.get("system_name"),
        "attributes": character_data.get("attributes", {}),
        "skills": character_data.get("skills", {}),
        "resources": character_data.get("resources", {}),
        "choices": character_data.get("choices", {}),
        "background": character_data.get("background"),
    }

    # Create entity as dict (CanonKeeper accepts any dict-like object)
    entity_create: dict[str, Any] = {
        "universe_id": str(universe_id),
        "name": character_data.get("name") or "Unknown Character",
        "entity_type": "character",
        "sub_type": "player_character",
        "is_archetype": False,
        "description": character_data.get("concept") or "",
        "properties": properties,
        "state_tags": [],
        "authority": "player",
        "canon_level": "canon",
        "confidence": 1.0,
        "detail_level": "full",
    }

    try:
        result = await ck.create_entity(entity_create)
        character_id = UUID(result.get("id", uuid.uuid4()))
        return character_id
    except Exception as exc:
        console.print(f"[red]Error:[/red] Failed to save character to Neo4j: {exc}")
        raise typer.Exit(code=1)
