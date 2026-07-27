# ST-5: Balance Player Agency

**Actor:** Human GM or Autonomous GM
**Trigger:** Story → Balance (or automatic suggestion)

**Purpose:** Ensure story pressure without railroading.

**Flow:**
1. Analyze current story state:
   - Player goals and stated intentions
   - GM/story goals and direction
   - Divergence between them
2. Identify agency concerns:
   - **Railroading Risk:** Story forcing specific path
   - **Stagnation Risk:** No pressure, no direction
   - **Overwhelm Risk:** Too many options, paralysis
3. Suggest adjustments:
   - **Add Pressure:** Time limits, antagonist actions
   - **Add Options:** New paths, resources, allies
   - **Add Clarity:** Signpost important choices
   - **Reduce Complexity:** Resolve minor threads
4. GM reviews and applies suggestions
5. Update story outline with adjustments

**Output:** Agency analysis with balancing suggestions

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_get_story_outline(story_id)
mongodb_list_scenes(story_id)
neo4j_list_plot_threads(story_id)
neo4j_list_facts(story_id, type="player_intention")
```

**Layer 2 (Agents):**
- `ContextAssembly.analyze_story_flow(story_id)` — Compile state
- `Narrator.assess_agency(story_state)` — LLM analysis
- `Narrator.suggest_balance(assessment)` — Generate suggestions

**Layer 3 (CLI):**
```bash
monitor story balance --story <UUID>
monitor story balance --story <UUID> --apply <SUGGESTION_ID>
```

**Agency Assessment:**
```python
@dataclass
class AgencyAssessment:
    story_id: UUID

    player_goals: list[str]           # What players want
    story_direction: list[str]        # Where narrative is heading
    alignment_score: float            # 0-1, how aligned

    railroading_risk: Risk            # low, medium, high
    stagnation_risk: Risk
    overwhelm_risk: Risk

    suggestions: list[BalanceSuggestion]

@dataclass
class BalanceSuggestion:
    type: SuggestionType   # add_pressure, add_options, add_clarity, simplify
    description: str
    implementation: str    # How to do it
    affected_threads: list[UUID]
```

**Balancing Prompt:**
```python
BALANCE_PROMPT = """
Analyze this story for player agency balance.

Player stated intentions: {player_goals}
Current story direction: {story_threads}
Recent player choices: {recent_decisions}
Open options: {available_paths}

Assess:
1. Are players being pushed toward a specific outcome? (railroading)
2. Is there enough pressure to drive decisions? (stagnation)
3. Are there too many unresolved threads? (overwhelm)

For each concern, suggest specific adjustments that:
- Preserve player choice
- Maintain story momentum
- Keep complexity manageable
"""
```

---
