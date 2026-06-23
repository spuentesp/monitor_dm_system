## 3. Current Flow Defects (Diagnosed)

| Defect | Where | Impact |
|--------|-------|--------|
| Three GM messages before player speaks | `chat.py create_session` | Removes opening agency; reads like a form |
| Character rolled before player agrees | `_maybe_do_char_creation` → `gsr.roll_character()` | Violates agency; DiS explicitly says "players roll their own characters" |
| Stat block dumped inline with GM prose | `format_character_sheet` | Breaks immersion; looks like a UI widget |
| "Before we begin, tell me…" intro | Removed in last session, but was a bullet-point form | Creates a service-desk tone |
| `MONITOR could not start the live GM loop yet` | `_run_scene_turn` except handler | Technical language in diegetic space |
| `NarratorSignature.narrative_text` desc says "2-4 paragraphs" | `prompts/narrator.py` | Forces verbosity; a GM reaction to "hello?" is two sentences |
| Narrator has no system-prompt persona | `NarratorModule` | No consistent GM voice, tone, or constraints |
| Resolver always rolls dice regardless of player readiness | `resolve_turn` branch 3 | Should not roll until character sheet is confirmed |
| `_FORCED_NARRATIVE_RE` fires on "I kill him" sentences | `resolver.py` | Correct pattern but no GM-voiced pushback when forced narrative is inappropriate |
| No concept of session phase | `SceneState` / `chat.py` | GM cannot know if player is still in pre-play, character definition, or active play |
| No player intent recognition before rolling | `resolve_turn` | Rolling on "what types of characters are there?" (an OOC question) is wrong |
| Opening hook sources only Axioms | `_fetch_opening_hook` | Ignores LoreFacts and Entity atmosphere; Axioms are dry world-truths not scene-setters |

---

