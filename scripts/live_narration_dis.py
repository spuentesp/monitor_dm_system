#!/usr/bin/env python3
import asyncio
import json
import logging
import sys
from uuid import uuid4

import nest_asyncio
import typer
from rich.console import Console

from monitor_agents.canonkeeper import CanonKeeper
from monitor_agents.loops.scene_loop import SceneLoop

nest_asyncio.apply()
console = Console()
logger = logging.getLogger(__name__)

app = typer.Typer(help="Run narration tests against the ingested DiS world.")

SCRIPTED_INPUTS = [
    # Arc 1: Information Gathering
    "I approach the barkeep at the hub station and ask for rumors about the derelict ship 'Ozymandias'.",
    "I ask what kind of defenses the Ozymandias might have, and if anyone else has gone looking for it.",
    # Arc 2: Dungeon & Puzzle
    "I take my ship, dock with the Ozymandias, and force open the main airlock with my tools.",
    "I cautiously explore the dark corridors, looking for the main reactor and any environmental puzzles to solve to restore power.",
    "I try to hack the engineering terminal to unlock the blast doors leading to the reactor.",
    # Arc 3: Boss Fight & Consequences
    "I confront the rogue defense construct guarding the reactor. I draw my weapon and attack it!",
    "I try to dodge its counter-attack and aim for its weak spot to disable it.",
    "With the construct defeated, I grab the valuable salvage and rush back to my ship to escape before the reactor overloads!"
]

async def find_dis_multiverse(keeper: CanonKeeper) -> str:
    m = await keeper.call_tool("neo4j_list_multiverses", {})
    multiverses = json.loads(m) if isinstance(m, str) else m
    
    # Sort by created_at descending to get the latest ingestion
    dis_m = [x for x in multiverses if "DiS Observe" in x.get("name", "")]
    if not dis_m:
        raise ValueError("No DiS Observe multiverse found. Run live ingestion first.")
    
    dis_m.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return dis_m[0]["id"]

async def run_test(mode: str):
    console.print(f"[bold cyan]Starting Narration Test in {mode} mode...[/bold cyan]")
    keeper = CanonKeeper()
    
    # 1. Find the ingested DiS Multiverse
    multiverse_id = await find_dis_multiverse(keeper)
    console.print(f"Found DiS Multiverse: {multiverse_id}")
    
    # 2. Create Universe
    universe_name = f"DiS Test Universe {uuid4().hex[:6]}"
    u_res = await keeper.create_universe({
        "multiverse_id": str(multiverse_id),
        "name": universe_name,
        "genre": "Sci-Fi",
        "description": "A gritty sci-fi salvage universe based on DiS.",
        "tone": "grim"
    })
    universe_id = u_res["id"]
    console.print(f"Created Universe: {universe_id} ({universe_name})")
    
    # 3. Create Story
    s_res = await keeper.create_story(
        story_id=uuid4(),
        universe_id=universe_id,
        title="Salvage Run on the Ozymandias",
        story_type="campaign",
    )
    story_id = s_res["id"] if isinstance(s_res, dict) else s_res.id
    console.print(f"Created Story: {story_id}")
    
    # 4. Initialize Scene Loop
    current_scene_id = uuid4()
    loop = SceneLoop(
        scene_id=current_scene_id,
        story_id=story_id,
        universe_id=universe_id,
        max_turns=50,
        play_mode="narrative",
        session_tone="grim sci-fi",
    )
    
    # 5. Run the turns
    if mode == "scripted":
        for idx, user_input in enumerate(SCRIPTED_INPUTS):
            console.print(f"\n[bold green]Player (Turn {idx+1}):[/bold green] {user_input}")
            result = await loop.run(user_input)
            
            narrative = result.get("narrative_text") or result.get("narrative", "")
            console.print(f"[bold blue]GM:[/bold blue] {narrative}\n")
            
            if result.get("scene_complete"):
                console.print("[bold yellow]--- Scene naturally completed ---[/bold yellow]")
                break
    else:
        from monitor_agents.dspy_runtime import _resolve_client
        from monitor_data.schemas.llm_config import ModelRole
        import litellm
        
        system_prompt = (
            "You are a player in a gritty sci-fi tabletop RPG. "
            "Your goal is to complete a 3-arc story: 1) gather info at a hub, 2) enter a derelict ship and solve a puzzle, 3) fight a boss and escape. "
            "Keep your actions concise (1-2 sentences). "
            "Base your next action strictly on the GM's previous response."
        )
        
        # Initial action
        player_action = "I am at the local hub station. I start looking for information about any derelict ships ripe for salvage."
        
        for idx in range(8): # Limit to 8 turns
            console.print(f"\n[bold green]LLM Player (Turn {idx+1}):[/bold green] {player_action}")
            result = await loop.run(player_action)
            
            narrative = result.get("narrative_text") or result.get("narrative", "")
            console.print(f"[bold blue]GM:[/bold blue] {narrative}\n")
            
            if result.get("scene_complete"):
                console.print("[bold yellow]--- Scene naturally completed ---[/bold yellow]")
                break
            
            # Generate next action
            prompt = f"The GM says:\n{narrative}\n\nWhat is your next action?"
            
            client = await _resolve_client("player", ModelRole.STANDARD)
            
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
            
            kwargs = {k: v for k, v in client.params.items() if v is not None}
            if client.api_key:
                kwargs["api_key"] = client.api_key
            
            if client.base_url:
                kwargs["api_base"] = client.base_url

            model_name = client.model
            if client.provider.value in ("anthropic", "minimax"):
                if not model_name.startswith("anthropic/"):
                    model_name = f"anthropic/{model_name}"
            else:
                if "/" not in model_name:
                    model_name = f"openai/{model_name}"
            
            response = await litellm.acompletion(
                model=model_name,
                messages=messages,
                max_tokens=150,
                **kwargs
            )
            player_action = response.choices[0].message.content.strip()

    await loop.finalize()
    console.print("\n[bold cyan]Test complete![/bold cyan]")

@app.command()
def scripted():
    """Run the 3-arc scripted play test."""
    asyncio.run(run_test("scripted"))

@app.command()
def unscripted():
    """Run the 3-arc unscripted LLM play test."""
    asyncio.run(run_test("unscripted"))

if __name__ == "__main__":
    app()
