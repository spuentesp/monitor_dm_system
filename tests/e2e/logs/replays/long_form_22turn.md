# Long-Form Narration Replay

- **API**: `http://localhost:8000/api`
- **Player model**: `ollama/qwen2.5:latest`
- **Benchmark**: `narrative_weighted_derelict`
- **Bootstrap**: `demo (Millhaven)`
- **Session ID**: `b7a0d6d1-f276-48ce-bafb-d2785e8e79f3`
- **Universe ID**: `617c1c6b-6a4d-4539-98cb-e590b49d5e5b`
- **Goal steps**: `22`
- **Turns played**: `22`
- **Avg latency**: `34.61s`
- **Rolls observed**: `19`
- **Fallback markers**: `0`
- **Canon entities at end**: `0`
- **Generated at**: `2026-06-26T00:49:23.838697+00:00`

---

## Turn 1 — `char_creation_accept` _(phase=active_play, lat=17.08s)_

**PLAYER:** I step into the dimly lit chamber, my eyes adjusting to the faint glow of holographic blue lights. My name is Kael Draven, a void-born salvage engineer, and I've been tasked with recovering valuable artifacts from the derelict ship adrift in the Void Nebula.

**GM:**

The chamber swallows you. Hull plating groans somewhere deep within the ship's skeleton. Frost creeps along exposed conduits. Your breath fogs in the recycled air—too cold, too still. Holographic emitters flicker overhead, casting fractured blue light across cargo containers rusted shut and a maintenance drone sprawled on the deck like a gutted beetle. Its optical sensors track your movement. Dead. Waiting. The silence here has weight. The void presses against the hull outside. You feel it in your teeth.

> resolution=`preplay_ack`

```json
{
  "type": "preplay_ack",
  "phase": "active_play",
  "saved_character": {
    "entity_id": "5adc15ed-d734-45d2-855f-30eee5cfca48",
    "sheet_id": "10064174-40c4-4b79-9656-63d81aa35ea8",
    "profile_id": null,
    "saved_to_universe_id": "617c1c6b-6a4d-4539-98cb-e590b49d5e5b"
  }
}
```

## Turn 2 — `char_creation_stat_roll` _(phase=active_play, lat=51.35s)_

**PLAYER:** I glance around the chamber, taking note of the rusted containers and the stationary drone before me. My hand subconsciously reaches for the utility belt at my waist, where various tools are stowed.

**GM:**

The chamber breathes cold. Rusted containers line the walls—some open, some sealed tight. Corrosion eats through seams like slow infection. A maintenance drone hangs from the ceiling, motionless, its limbs frozen mid-repair. One of the containers at your feet has a lid buckled but not torn. The seal has rusted shut. Inside: darkness.

Your fingers find the z-hook on your belt. You could pry it open. You could also walk away. The drone's optical sensor faces the corner, dead and dark.

Roll your Strength for me.

> resolution=`scene_turn`  ·  success=`pending`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "propose_roll",
  "intent_type": "action",
  "success_level": "pending",
  "roll_breakdown": "propose_roll — Strength check (DC 12)",
  "roll_detail": null,
  "stat": "Strength",
  "difficulty_class": 12,
  "effects": [],
  "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Strength around DC 12.",
  "consequence_options": [],
  "requires_player_choice": true,
  "narrative_pressure": "rising",
  "turn_id": "e4353ff6-18fa-4473-b1b9-20d258c53104",
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
  "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362",
  "dice_request": {
    "spec": "1d20-5",
    "reason": "That sounds risky — roll your Strength for me.",
    "stat": "Strength",
    "difficulty_class": 12,
    "modifier": -5,
    "roll_under": false,
    "action_type": "action",
    "intent_type": "action",
    "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Strength around DC 12.",
    "original_action": "I glance around the chamber, taking note of the rusted containers and the stationary drone before me. My hand subconsciously reaches for the utility belt at my waist, where various tools are stowed."
  }
}
```

## Turn 3 — `first_in_fiction_action` _(phase=active_play, lat=56.37s)_

**PLAYER:** I release a breath I didn't realize I was holding and survey the chamber more thoroughly. My gaze lands on the rusted container lid. Carefully, I remove the z-hook from my belt and start prying at the seal.

**GM:**

The z-hook bites into the rusted seam. Corrosion flakes away in orange-green dust. Your shoulders strain. Metal groans, fights, then surrenders with a shriek that echoes off the chamber walls.

Inside: a body. Sealed in this tomb for months, maybe years. Rank air escapes. The corpse wears a faded uniform—Order insignia on the collar, barely visible beneath the decay. One hand clutches a data-slate, fingers locked in rigor. A crack runs across the slate's screen, but something still flickers in the damaged display.

The drone above you hangs silent, optical sensor pointed at the corner. It does not turn.

You can take the slate. You can examine it here. The smell is already crawling into your lungs.

> resolution=`scene_turn`  ·  success=`pending`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "propose_roll",
  "intent_type": "action",
  "success_level": "pending",
  "roll_breakdown": "propose_roll — Strength check (DC 12)",
  "roll_detail": null,
  "stat": "Strength",
  "difficulty_class": 12,
  "effects": [],
  "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Strength around DC 12.",
  "consequence_options": [],
  "requires_player_choice": true,
  "narrative_pressure": "rising",
  "turn_id": "7111a887-9547-455e-8cb4-c39e5a39bceb",
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
  "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362",
  "dice_request": {
    "spec": "1d20-5",
    "reason": "That sounds risky — roll your Strength for me.",
    "stat": "Strength",
    "difficulty_class": 12,
    "modifier": -5,
    "roll_under": false,
    "action_type": "action",
    "intent_type": "action",
    "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Strength around DC 12.",
    "original_action": "I release a breath I didn't realize I was holding and survey the chamber more thoroughly. My gaze lands on the rusted container lid. Carefully, I remove the z-hook from my belt and start prying at the seal."
  }
}
```

## Turn 4 — `social_inquiry` _(phase=active_play, lat=28.16s)_

**PLAYER:** I close the container lid gently and straighten up, scanning the room for any other clues before approaching one of the maintenance drones to check if its optical sensors might provide more information or lead me elsewhere.

**GM:**

The chamber offers little else. Rusted containers. Corrosion. The drone hangs like a dead spider. You move closer, boots scraping against the floor. Up close, the drone's joints are frozen with ice—not frost, something older. Its optical sensor remains dark, pointed at the corner where shadow pools thick and undisturbed.

You find a access panel on its chassis. Fingers, cold and steady. You pry it open. Inside: a standard maintenance log, corroded beyond reading. But beneath the log, wedged into the drone's neural housing, a data chip. Unofficial. Someone installed it here deliberately. The chip's indicator light pulses faint amber—still active.

The corner the drone watches holds nothing visible. Just shadow. Just silence.

The container behind you holds a dead Order operative and a cracked slate.

The chip pulses.

> resolution=`scene_turn`  ·  success=`success`  ·  effects=`['fiction_advances']`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "trivial",
  "intent_type": "action",
  "success_level": "success",
  "roll_breakdown": "trivial — no roll needed",
  "roll_detail": null,
  "stat": "Strength",
  "difficulty_class": 12,
  "effects": [
    "fiction_advances"
  ],
  "risk_preview": "This is a routine action — no stakes beyond the narrative.",
  "consequence_options": [],
  "requires_player_choice": false,
  "narrative_pressure": "steady",
  "turn_id": "0cc264de-d07c-4f03-961a-aa3658ab63e2",
  "resolution_id": "cf753c87-cd31-4c39-b311-c8f726dfc662",
  "working_state": {
    "state_id": "e785256f-14bd-49a0-9412-ef662cd7e758",
    "entity_id": "5adc15ed-d734-45d2-855f-30eee5cfca48",
    "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362",
    "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
    "current_stats": {
      "narrative_pressure": "steady",
      "last_success_level": "success"
    },
    "resources": {},
    "conditions": []
  },
  "scene_checkpoint": {
    "turn_id": "0cc264de-d07c-4f03-961a-aa3658ab63e2",
    "resolution_id": null,
    "success_level": "success",
    "narrative_pressure": "steady",
    "xp_awarded": 0,
    "summary": "The chamber offers little else. Rusted containers. Corrosion. The drone hangs like a dead spider. You move closer, boots scraping against the floor. Up close, the drone's joints are frozen with ice—not frost, somethin... [success]",
    "resources": {},
    "conditions": [],
    "updated_at": "2026-06-26T00:37:58.829055+00:00"
  },
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
  "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362"
}
```

## Turn 5 — `lore_recall` _(phase=active_play, lat=43.7s)_

**PLAYER:** I approach the nearest rusted container and carefully pry open the access panel on its side, hoping to find some sort of log or maintenance record that might provide more context.

**GM:**

The container's panel resists. You work the corroded edges, feeling metal flake beneath your fingers. It gives. Stinks of rust and something chemical underneath—lubricant gone sour over decades.

Inside: stacked canisters, mostly empty. A maintenance toolkit lashed to the interior wall, tools oxidized past use. And pressed flat against the back panel, a folded sheet of paper—impossible, in this humidity. You pull it free.

The paper is synthetic. Field report, judging by the formatting. Top line reads: *SUBJECT: Puentes. STATUS: TERMINATED. DISPOSITION: SEALED.*

Below that, a partial list of names. Some crossed out. Some not. The last entry—handwritten in ink that's still dark—reads: *Draven, Kael. Location: SECTOR 7. Priority: PRIMARY.*

Someone knew you were here. Someone wrote it down.

The container holds nothing else.

The drone's amber light pulses. The dead operative's slate flickers in the corner. The names on that list stare up at you, waiting.

> resolution=`scene_turn`  ·  success=`success`  ·  effects=`['fiction_advances']`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "trivial",
  "intent_type": "action",
  "success_level": "success",
  "roll_breakdown": "trivial — no roll needed",
  "roll_detail": null,
  "stat": "Strength",
  "difficulty_class": 12,
  "effects": [
    "fiction_advances"
  ],
  "risk_preview": "This is a routine action — no stakes beyond the narrative.",
  "consequence_options": [],
  "requires_player_choice": false,
  "narrative_pressure": "steady",
  "turn_id": "fbde5646-b19c-445d-a234-9593f4604fee",
  "resolution_id": "117b3ee4-aa1f-484e-9e15-6f3fb836ce79",
  "working_state": {
    "state_id": "e785256f-14bd-49a0-9412-ef662cd7e758",
    "entity_id": "5adc15ed-d734-45d2-855f-30eee5cfca48",
    "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362",
    "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
    "current_stats": {
      "narrative_pressure": "steady",
      "last_success_level": "success"
    },
    "resources": {},
    "conditions": []
  },
  "scene_checkpoint": {
    "turn_id": "fbde5646-b19c-445d-a234-9593f4604fee",
    "resolution_id": null,
    "success_level": "success",
    "narrative_pressure": "steady",
    "xp_awarded": 0,
    "summary": "The container's panel resists. You work the corroded edges, feeling metal flake beneath your fingers. It gives. Stinks of rust and something chemical underneath—lubricant gone sour over decades.\n\nInside: stacked canis... [success]",
    "resources": {},
    "conditions": [],
    "updated_at": "2026-06-26T00:38:46.253772+00:00"
  },
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
  "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362"
}
```

## Turn 6 — `social_deal` _(phase=active_play, lat=20.01s)_

**PLAYER:** I reach into the canisters, feeling for any remaining usable materials before carefully sealing up the container again. Next, I inspect the maintenance toolkit, looking for anything that might still be useful.

**GM:**

The canisters yield dregs. A quarter-liter of industrial solvent, still sealed. Two replacement fuses—not corroded. You pocket them. The container clicks shut, rust flaking beneath your palms.

The toolkit hangs by a single intact strap. You unlash it, lay it open. Needle-nose pliers, still functional. A flathead screwdriver with a chipped tip. A tube of grease—rock-hard, useless. The pliers go into your gear. The screwdriver stays.

Behind you, the drone's amber pulse quickens.

You turn. The corner remains empty. The shadow remains undisturbed.

But the data chip is warm now. Warmer than it should be.

The operative's slate flickers again, longer this time. A fragment of text surfaces: *...PUENTES TERMINATED. DRONE ASSET COMPROMISED. SECTOR 7 IS...*

The rest dissolves into static.

The cold deepens. The drone watches its empty corner. You hold the chip, feeling its heat against your frozen fingers.

Something is listening.
</think>

> resolution=`scene_turn`  ·  success=`success`  ·  effects=`['fiction_advances']`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "trivial",
  "intent_type": "action",
  "success_level": "success",
  "roll_breakdown": "trivial — no roll needed",
  "roll_detail": null,
  "stat": "Wisdom",
  "difficulty_class": 13,
  "effects": [
    "fiction_advances"
  ],
  "risk_preview": "This is a routine action — no stakes beyond the narrative.",
  "consequence_options": [],
  "requires_player_choice": false,
  "narrative_pressure": "steady",
  "turn_id": "b658b209-a781-4969-bf6c-ddeda3c3499c",
  "resolution_id": "7a4985a3-71b0-4f5a-87d2-e9a338c6f263",
  "working_state": {
    "state_id": "e785256f-14bd-49a0-9412-ef662cd7e758",
    "entity_id": "5adc15ed-d734-45d2-855f-30eee5cfca48",
    "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362",
    "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
    "current_stats": {
      "narrative_pressure": "steady",
      "last_success_level": "success"
    },
    "resources": {},
    "conditions": []
  },
  "scene_checkpoint": {
    "turn_id": "b658b209-a781-4969-bf6c-ddeda3c3499c",
    "resolution_id": null,
    "success_level": "success",
    "narrative_pressure": "steady",
    "xp_awarded": 0,
    "summary": "The canisters yield dregs. A quarter-liter of industrial solvent, still sealed. Two replacement fuses—not corroded. You pocket them. The container clicks shut, rust flaking beneath your palms.\n\nThe toolkit hangs by a... [success]",
    "resources": {},
    "conditions": [],
    "updated_at": "2026-06-26T00:39:11.333194+00:00"
  },
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
  "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362"
}
```

## Turn 7 — `exploration_intent` _(phase=active_play, lat=29.43s)_

**PLAYER:** I examine the room silently, ensuring no other useful items are overlooked, then approach the airlock. Carefully, I press my ear to the door and listen for any signs of life or movement before cycling it open.

**GM:**

You sweep the room with your eyes. The walls sweat condensation. Cable conduits run along the ceiling, dark and dead. A secondary panel near the floor—sealed, welded shut by age or intent. The floor grating beneath your boots holds decades of sediment. Nothing moves. Nothing gleams.

You cross to the airlock. The seal around its edges is intact, which means pressurization holds on the other side. You press your ear to the cold metal. The vibration of the station's life support hums through the steel—a low, steady thrum. Beneath it, nothing. No footsteps. No voices. No weapon discharge.

The airlock's manual release lever sits to your right, coated in the same fine dust as everything else.

The question is what waits beyond.
</think>

> resolution=`scene_turn`  ·  success=`pending`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "propose_roll",
  "intent_type": "action",
  "success_level": "pending",
  "roll_breakdown": "propose_roll — Wisdom check (DC 13)",
  "roll_detail": null,
  "stat": "Wisdom",
  "difficulty_class": 13,
  "effects": [],
  "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Wisdom around DC 13.",
  "consequence_options": [],
  "requires_player_choice": true,
  "narrative_pressure": "rising",
  "turn_id": "e688e13e-ce69-4d7b-944b-cf59fcd94fa5",
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
  "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362",
  "dice_request": {
    "spec": "1d20-5",
    "reason": "That sounds risky — roll your Wisdom for me.",
    "stat": "Wisdom",
    "difficulty_class": 13,
    "modifier": -5,
    "roll_under": false,
    "action_type": "action",
    "intent_type": "action",
    "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Wisdom around DC 13.",
    "original_action": "I examine the room silently, ensuring no other useful items are overlooked, then approach the airlock. Carefully, I press my ear to the door and listen for any signs of life or movement before cycling it open."
  }
}
```

## Turn 8 — `first_combat_intent` _(phase=active_play, lat=44.44s)_

**PLAYER:** I cycle the airlock door, listening intently for any unusual sounds or changes in pressure, then sweep my light across the room one last time before reaching for my cutter and holsters it, ready for any potential threats.

**GM:**

The airlock cycles with a pneumatic gasp. Stale air rushes past you, carrying the mineral tang of recycled atmosphere and something else beneath it—ozone, maybe. Electrical discharge. You step through into a corridor, your light carving through the dark.

The passage stretches thirty meters in either direction. Emergency lighting strips line the floor, dead. Debris litters the grating—fallen ceiling panels, unidentifiable wreckage. To your left, a door marked *SECTOR 7 AUXILIARY CONTROL* hangs ajar, its locking mechanism visibly shattered from the inside.

To your right, the corridor terminates at a sealed bulkhead. Beyond it, the faint blue glow of active terminals pulses through the gap beneath the door.

But it is the center of the corridor that snags your attention.

A body. Coverall suit. No visible wounds. Lying face-down in the sediment, one arm outstretched toward the sealed bulkhead. A credential badge is clipped to its collar, but the distance and the dark make the name unreadable.

The station is quiet. Too quiet.

Something happened here. Something recent.

Roll your Wisdom for me.

> resolution=`scene_turn`  ·  success=`pending`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "propose_roll",
  "intent_type": "action",
  "success_level": "pending",
  "roll_breakdown": "propose_roll — Wisdom check (DC 13)",
  "roll_detail": null,
  "stat": "Wisdom",
  "difficulty_class": 13,
  "effects": [],
  "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Wisdom around DC 13.",
  "consequence_options": [],
  "requires_player_choice": true,
  "narrative_pressure": "rising",
  "turn_id": "07c2f87e-fd99-4e1d-a320-587226cb6efd",
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
  "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362",
  "dice_request": {
    "spec": "1d20-5",
    "reason": "That sounds risky — roll your Wisdom for me.",
    "stat": "Wisdom",
    "difficulty_class": 13,
    "modifier": -5,
    "roll_under": false,
    "action_type": "action",
    "intent_type": "action",
    "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Wisdom around DC 13.",
    "original_action": "I cycle the airlock door, listening intently for any unusual sounds or changes in pressure, then sweep my light across the room one last time before reaching for my cutter and holsters it, ready for any potential threats."
  }
}
```

## Turn 9 — `combat_engaged` _(phase=active_play, lat=40.53s)_

**PLAYER:** I sprint down the corridor, light blade drawn and ready, ears straining for any sign of movement or threat.

**GM:**

The corridor swallows your sprint. Your boots pound the grating, each footfall echoing. The body lies three meters to your left—you catch it in peripheral vision without slowing. The credential badge glints for a half-second in your blade's glow. The shattered door of the auxiliary control room sweeps past on your right. Behind you, the airlock's pneumatic hiss fades.

Twelve meters from the bulkhead, the floor grating beneath your left foot gives way. Not entirely—it holds—but a section of corroded metal shifts under your weight, groaning against its corroded bolts. Your momentum pitches you forward. Your light blade catches the gleam of exposed cable conduit rushing toward your face.

You catch yourself on the wall. The grating holds. Barely. A panel two meters ahead now sits visibly depressed, weakened the same way.

The bulkhead door waits. Its blue glow pulses slow and patient beneath the gap. Something behind it runs on emergency power. Something here still lives—or at least, still draws power.

The body behind you remains exactly where it fell.

> resolution=`scene_turn`  ·  success=`pending`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "propose_roll",
  "intent_type": "action",
  "success_level": "pending",
  "roll_breakdown": "propose_roll — Strength check (DC 12)",
  "roll_detail": null,
  "stat": "Strength",
  "difficulty_class": 12,
  "effects": [],
  "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Strength around DC 12.",
  "consequence_options": [],
  "requires_player_choice": true,
  "narrative_pressure": "rising",
  "turn_id": "741c01d9-36b2-4ea8-9210-50ae1db44a9a",
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
  "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362",
  "dice_request": {
    "spec": "1d20-5",
    "reason": "That sounds risky — roll your Strength for me.",
    "stat": "Strength",
    "difficulty_class": 12,
    "modifier": -5,
    "roll_under": false,
    "action_type": "action",
    "intent_type": "action",
    "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Strength around DC 12.",
    "original_action": "I sprint down the corridor, light blade drawn and ready, ears straining for any sign of movement or threat."
  }
}
```

## Turn 10 — `combat_finisher` _(phase=active_play, lat=5.74s)_

**PLAYER:** I slash at the enemy's exposed flank as it lunges, driving my blade deep into its side.

**GM:**

…

> resolution=`scene_turn`  ·  success=`pending`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "forced_narrative_pushback",
  "intent_type": "action",
  "success_level": "pending",
  "roll_breakdown": null,
  "roll_detail": null,
  "stat": null,
  "difficulty_class": null,
  "effects": [],
  "risk_preview": null,
  "consequence_options": [],
  "requires_player_choice": true,
  "narrative_pressure": "spiking",
  "turn_id": null,
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 0,
  "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
  "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362"
}
```

## Turn 11 — `tactical_assessment` _(phase=active_play, lat=49.16s)_

**PLAYER:** I pull back from the fallen foe, taking a moment to reassess my surroundings and gather my thoughts.

**GM:**

The body twitches. A reflex. Neurons still firing in dead meat. You freeze.

Its fingers curl against the grating. Scrape. Then go still again.

The auxiliary control room breathes on your right—machinery humming behind that shattered door. The bulkhead pulses its blue invitation on your left. Between them, this corridor and its corroded floor and its not-quite-dead occupant.

You plant your feet. The weakened grating groans beneath your soles. Every step back toward the airlock means trusting metal that has already betrayed you once.

Or you advance. Toward whatever still draws power behind that sealed door. Toward answers this station is not eager to surrender.

The body does not move again.

Yet.

Roll your Strength for me.

> resolution=`scene_turn`  ·  success=`pending`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "propose_roll",
  "intent_type": "action",
  "success_level": "pending",
  "roll_breakdown": "propose_roll — Strength check (DC 12)",
  "roll_detail": null,
  "stat": "Strength",
  "difficulty_class": 12,
  "effects": [],
  "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Strength around DC 12.",
  "consequence_options": [],
  "requires_player_choice": true,
  "narrative_pressure": "rising",
  "turn_id": "ae57b87c-063b-46e6-bf25-1ca86d2c238a",
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
  "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362",
  "dice_request": {
    "spec": "1d20-5",
    "reason": "That sounds risky — roll your Strength for me.",
    "stat": "Strength",
    "difficulty_class": 12,
    "modifier": -5,
    "roll_under": false,
    "action_type": "action",
    "intent_type": "action",
    "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Strength around DC 12.",
    "original_action": "I pull back from the fallen foe, taking a moment to reassess my surroundings and gather my thoughts."
  }
}
```

## Turn 12 — `deeper_push` _(phase=active_play, lat=50.31s)_

**PLAYER:** I move towards the bulkhead, hand on the hilt of my blade as I prepare to enter the auxiliary control room.

**GM:**

Your boot finds solid grating. Then another. You keep your weight centered, each step deliberate, the corroded sections groaning but holding.

The bulkhead looms closer. The blue glow intensifies beneath the gap—a thin blade of light cutting the darkness. Up close, the door bears scoring marks. Old ones. Something tried to force entry here before. Something failed.

The machinery hum grows louder through the metal. Not mechanical rhythm—something steadier. Something alive.

Your hand finds your blade's hilt. The grip is cold. Familiar.

The door's manual release sits to your right. A simple lever, still operational. Beyond it, the auxiliary control room waits with whatever still breathes power into this tomb.

The body behind you does not follow.

Not yet.

> resolution=`scene_turn`  ·  success=`success`  ·  effects=`['fiction_advances']`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "forced_narrative",
  "intent_type": "action",
  "success_level": "success",
  "roll_breakdown": "forced narrative — player declared outcome",
  "roll_detail": null,
  "stat": null,
  "difficulty_class": null,
  "effects": [
    "fiction_advances"
  ],
  "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on the relevant approach.",
  "consequence_options": [],
  "requires_player_choice": false,
  "narrative_pressure": "surging",
  "turn_id": "0b803ee1-fd84-43e2-a4da-497e9ef53214",
  "resolution_id": "3171518a-3ac5-475e-ab69-2422d026c116",
  "working_state": {
    "state_id": "e785256f-14bd-49a0-9412-ef662cd7e758",
    "entity_id": "5adc15ed-d734-45d2-855f-30eee5cfca48",
    "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362",
    "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
    "current_stats": {
      "narrative_pressure": "surging",
      "last_success_level": "success"
    },
    "resources": {},
    "conditions": []
  },
  "scene_checkpoint": {
    "turn_id": "0b803ee1-fd84-43e2-a4da-497e9ef53214",
    "resolution_id": null,
    "success_level": "success",
    "narrative_pressure": "surging",
    "xp_awarded": 0,
    "summary": "Your boot finds solid grating. Then another. You keep your weight centered, each step deliberate, the corroded sections groaning but holding.\n\nThe bulkhead looms closer. The blue glow intensifies beneath the gap—a thi... [success]",
    "resources": {},
    "conditions": [],
    "updated_at": "2026-06-26T00:43:18.482984+00:00"
  },
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
  "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362"
}
```

## Turn 13 — `puzzle_encounter` _(phase=active_play, lat=41.04s)_

**PLAYER:** I approach the bulkhead cautiously, eyeing the strange symbols etched into the metal before reaching for the handle of my blade.

**GM:**

The symbols cut into the metal in precise angles. Not language—geometry. Triangles nesting inside triangles, spiraling toward a center point that holds no comfort. You recognize nothing. The station's original builders left their mark here, or something else claimed this place before the silence.

Your fingers brush the hilt. The leather wrap is cracked but solid. You know this blade. You know what it has opened.

The manual release lever waits. Blue light bleeds through the seam where door meets frame. The hum beyond steadies—a rhythm like breathing. Slow. Patient.

Something knows you are here.

The body behind you remains still. Cold metal beneath your boots. The grating held. For now.

You stop two meters from the bulkhead. Close enough to read the symbols. Close enough to see the lever's shadow.

Roll your Strength for me.

> resolution=`scene_turn`  ·  success=`pending`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "propose_roll",
  "intent_type": "action",
  "success_level": "pending",
  "roll_breakdown": "propose_roll — Strength check (DC 12)",
  "roll_detail": null,
  "stat": "Strength",
  "difficulty_class": 12,
  "effects": [],
  "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Strength around DC 12.",
  "consequence_options": [],
  "requires_player_choice": true,
  "narrative_pressure": "rising",
  "turn_id": "a4ad7bcb-966b-41ba-9432-486fd9840912",
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
  "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362",
  "dice_request": {
    "spec": "1d20-5",
    "reason": "That sounds risky — roll your Strength for me.",
    "stat": "Strength",
    "difficulty_class": 12,
    "modifier": -5,
    "roll_under": false,
    "action_type": "action",
    "intent_type": "action",
    "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Strength around DC 12.",
    "original_action": "I approach the bulkhead cautiously, eyeing the strange symbols etched into the metal before reaching for the handle of my blade."
  }
}
```

## Turn 14 — `puzzle_solve` _(phase=active_play, lat=31.05s)_

**PLAYER:** I touch the symbols with a gloved finger, tracing the patterns carefully.

**GM:**

Your gloved finger traces the grooves. The metal is colder than it should be—cold enough to sting through the leather. The symbols feel deliberate under your touch. Each line cut with purpose, each angle intentional. This was not vandalism. This was declaration.

The blue light pulses beneath the door seam. Once. Twice. The rhythm shifts when your finger follows the innermost triangle. Coincidence. It must be coincidence.

The grating beneath your left foot shifts a centimeter. Rust flakes drift downward into the dark. The hum beyond the door steadies again—patient, waiting.

You are close now. Close enough that the cold is inside your bones.

The lever sits within arm's reach. The symbols demand attention. The light bleeds steady. Your blade waits at your hip.

Roll your Strength for me.

> resolution=`scene_turn`  ·  success=`pending`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "propose_roll",
  "intent_type": "action",
  "success_level": "pending",
  "roll_breakdown": "propose_roll — Strength check (DC 12)",
  "roll_detail": null,
  "stat": "Strength",
  "difficulty_class": 12,
  "effects": [],
  "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Strength around DC 12.",
  "consequence_options": [],
  "requires_player_choice": true,
  "narrative_pressure": "rising",
  "turn_id": "0e731f71-6b65-444c-ac0d-6c4d579ef9ee",
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
  "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362",
  "dice_request": {
    "spec": "1d20-5",
    "reason": "That sounds risky — roll your Strength for me.",
    "stat": "Strength",
    "difficulty_class": 12,
    "modifier": -5,
    "roll_under": false,
    "action_type": "action",
    "intent_type": "action",
    "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Strength around DC 12.",
    "original_action": "I touch the symbols with a gloved finger, tracing the patterns carefully."
  }
}
```

## Turn 15 — `puzzle_consequence` _(phase=active_play, lat=46.04s)_

**PLAYER:** I continue to trace the symbols, noting their intricate design as my finger follows the innermost triangle. The blue light pulses again in time with my movements, sending a chill down my spine.

**GM:**

The pulse answers your touch. Not metaphor. Not imagination. The blue light swells brighter as your finger completes the innermost triangle's arc. The cold beneath your glove intensifies—frost forming on the metal where your skin meets symbol.

The door shudders.

Rust rains from the frame. The grating beneath you groans, a sound like something heavy dragging across deck plating three levels down. The hum beyond the door deepens into a vibration you feel in your teeth.

Then—stillness. The blue light holds steady. Waiting.

Your finger remains on the symbol. The cold has stopped spreading. The door has not opened. Something changed in the geometry beneath your touch, or something is about to.

The lever waits. The symbols wait. The light waits.

Your boots shift on the grating. The metal sings a thin, stressed note.

Roll your Strength for me.

> resolution=`scene_turn`  ·  success=`pending`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "propose_roll",
  "intent_type": "action",
  "success_level": "pending",
  "roll_breakdown": "propose_roll — Strength check (DC 12)",
  "roll_detail": null,
  "stat": "Strength",
  "difficulty_class": 12,
  "effects": [],
  "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Strength around DC 12.",
  "consequence_options": [],
  "requires_player_choice": true,
  "narrative_pressure": "rising",
  "turn_id": "c56c340f-d376-4f33-aa75-871468d400c3",
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
  "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362",
  "dice_request": {
    "spec": "1d20-5",
    "reason": "That sounds risky — roll your Strength for me.",
    "stat": "Strength",
    "difficulty_class": 12,
    "modifier": -5,
    "roll_under": false,
    "action_type": "action",
    "intent_type": "action",
    "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Strength around DC 12.",
    "original_action": "I continue to trace the symbols, noting their intricate design as my finger follows the innermost triangle. The blue light pulses again in time with my movements, sending a chill down my spine."
  }
}
```

## Turn 16 — `loot_choice` _(phase=active_play, lat=41.1s)_

**PLAYER:** I focus on completing the triangle's arc with my finger, feeling the pulse of the blue light synchronize with my touch before slowly withdrawing my hand as the door begins to creak open.

**GM:**

You pull your hand back. The frost on your glove cracks, flakes drift down like ash. The door groans—a sound like a throat clearing before speech. The gap widens. Inches. Then a foot. The blue light spills out across the grating, pooling at your boots.

The cold deepens. Your breath does not fog. The air is too dry, too dead, to condense.

Beyond the threshold: a corridor. No—not a corridor. A throat. The walls curve inward, riveted plates slick with condensation that drips upward, defying gravity. The blue light traces channels cut into the floor, geometric patterns radiating outward like veins. At the far end, the passage bends. You cannot see what waits there.

The hum is louder now. It lives in your molars, your sinuses. Your heartbeat tries to match it and fails.

The symbol on the door glows faintly. Waiting to be touched again.

Something shifts in the dark beyond the bend. Metal on metal. A scrape. A settling.

You are not alone in here.

> resolution=`scene_turn`  ·  success=`success`  ·  effects=`['fiction_advances']`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "trivial",
  "intent_type": "action",
  "success_level": "success",
  "roll_breakdown": "trivial — no roll needed",
  "roll_detail": null,
  "stat": "Strength",
  "difficulty_class": 12,
  "effects": [
    "fiction_advances"
  ],
  "risk_preview": "This is a routine action — no stakes beyond the narrative.",
  "consequence_options": [],
  "requires_player_choice": false,
  "narrative_pressure": "steady",
  "turn_id": "e8eb7ca6-095e-47a7-a38c-afb08c45768b",
  "resolution_id": "e05263e5-620a-4c06-a986-c6ed39298a30",
  "working_state": {
    "state_id": "e785256f-14bd-49a0-9412-ef662cd7e758",
    "entity_id": "5adc15ed-d734-45d2-855f-30eee5cfca48",
    "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362",
    "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
    "current_stats": {
      "narrative_pressure": "steady",
      "last_success_level": "success"
    },
    "resources": {},
    "conditions": []
  },
  "scene_checkpoint": {
    "turn_id": "e8eb7ca6-095e-47a7-a38c-afb08c45768b",
    "resolution_id": null,
    "success_level": "success",
    "narrative_pressure": "steady",
    "xp_awarded": 0,
    "summary": "You pull your hand back. The frost on your glove cracks, flakes drift down like ash. The door groans—a sound like a throat clearing before speech. The gap widens. Inches. Then a foot. The blue light spills out across... [success]",
    "resources": {},
    "conditions": [],
    "updated_at": "2026-06-26T00:46:13.030539+00:00"
  },
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
  "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362"
}
```

## Turn 17 — `boss_intro` _(phase=active_play, lat=49.92s)_

**PLAYER:** I raise my blade, aiming for a swift strike as the first signs of a mechanical form begin to materialize in the flickering blue light.

**GM:**

Your blade sings free of its sheath. The edge catches the blue light—once, twice—before you move.

The thing in the dark resolves. Corroded pistons. A torso of welded plating, green patina bleeding through gaps. No face. Only a sensor-lens, cycling through amber, red, amber. It stands seven feet tall on articulated legs that click and whir. One arm ends in a industrial claw. The other arm—gone. Sheared clean at the elbow. Fresh sparks shower from the stump.

It sees you. The lens locks amber.

You are faster.

Your strike hits the joint where neck meets shoulder. The blade shears through corroded metal like paper. Sparks erupt. The thing's head lists sideways, hanging by a thread of cable and conduit. It makes no sound. The sensor-lens flickers—amber, red, amber—still active, still watching.

Then the claw arm swings. Wide. Desperate. You duck under it. The metal passes inches above your scalp, close enough to feel the hydraulic heat.

The construct collapses. Pivots. Crashes against the curved wall. The hum in your teeth stutters, skips, holds.

The head dangles. The lens dims to a sullen orange.

Behind it, the corridor stretches deeper. The blue light pulses at your feet. The geometry etched in the floor seems to breathe.

Something else waits further in. You know this now. You feel it in the way the cold gathers at your spine.

The path forward is open. For now.

> resolution=`scene_turn`  ·  success=`critical_success`  ·  effects=`['momentum_gained', 'fiction_advances']`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "dice",
  "intent_type": "action",
  "success_level": "critical_success",
  "roll_breakdown": "1d20(20) + -5 = 15 vs DC 12",
  "roll_detail": {
    "spec": "1d20-5",
    "total": 15,
    "rolls": [
      20
    ],
    "kept_rolls": [
      20
    ],
    "reason": "Strength check (DC 12, normal)",
    "roll_mode": "normal"
  },
  "stat": "Strength",
  "difficulty_class": 12,
  "effects": [
    "momentum_gained",
    "fiction_advances"
  ],
  "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Strength around DC 12.",
  "consequence_options": [
    "Press the advantage for extra information or position.",
    "Take the clean win and keep the scene stable."
  ],
  "requires_player_choice": false,
  "narrative_pressure": "surging",
  "turn_id": "b4b4892a-a87e-49f0-ab47-5edb84a82159",
  "resolution_id": "2300a790-cd91-4863-9f56-8d82702812ec",
  "working_state": {
    "state_id": "e785256f-14bd-49a0-9412-ef662cd7e758",
    "entity_id": "5adc15ed-d734-45d2-855f-30eee5cfca48",
    "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362",
    "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
    "current_stats": {
      "narrative_pressure": "surging",
      "last_success_level": "critical_success"
    },
    "resources": {},
    "conditions": []
  },
  "scene_checkpoint": {
    "turn_id": "b4b4892a-a87e-49f0-ab47-5edb84a82159",
    "resolution_id": null,
    "success_level": "critical_success",
    "narrative_pressure": "surging",
    "xp_awarded": 0,
    "summary": "Your blade sings free of its sheath. The edge catches the blue light—once, twice—before you move.\n\nThe thing in the dark resolves. Corroded pistons. A torso of welded plating, green patina bleeding through gaps. No fa... [critical success]",
    "resources": {},
    "conditions": [],
    "updated_at": "2026-06-26T00:47:06.623200+00:00"
  },
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
  "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362"
}
```

## Turn 18 — `boss_phase_two` _(phase=active_play, lat=22.05s)_

**PLAYER:** I swing my sword with all my might, aiming for the hinge where the arm is missing.

**GM:**

The construct's ruined shoulder joint sparks and sputters where your first strike cracked the casing. Cable and conduit hang exposed like viscera. The sensor-lens flickers amber, amber, red—a dying heartbeat in machine language. It tries to rise. The remaining leg motor whines, straining against bent plating.

The joint is there. Barely held. One clean strike would sever the head completely, drop the thing for good.

But the corridor behind it breathes blue light. The hum in your teeth sharpens. You feel the cold pressing at your spine—that deeper presence waiting further in. If you commit to this swing, you commit fully. No second chances. The construct's claw arm could still swing. The wider passage could birth more of them.

Your blade hangs ready. The joint waits.

Your muscles coil.

The hum grows louder.

Roll your Strength for me.
</think>

> resolution=`scene_turn`  ·  success=`pending`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "propose_roll",
  "intent_type": "action",
  "success_level": "pending",
  "roll_breakdown": "propose_roll — Strength check (DC 12)",
  "roll_detail": null,
  "stat": "Strength",
  "difficulty_class": 12,
  "effects": [],
  "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Strength around DC 12.",
  "consequence_options": [],
  "requires_player_choice": true,
  "narrative_pressure": "rising",
  "turn_id": "99e05bc1-e940-48aa-8b3f-1d2ec63adfef",
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
  "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362",
  "dice_request": {
    "spec": "1d20-5",
    "reason": "That sounds risky — roll your Strength for me.",
    "stat": "Strength",
    "difficulty_class": 12,
    "modifier": -5,
    "roll_under": false,
    "action_type": "action",
    "intent_type": "action",
    "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Strength around DC 12.",
    "original_action": "I swing my sword with all my might, aiming for the hinge where the arm is missing."
  }
}
```

## Turn 19 — `boss_finisher` _(phase=active_play, lat=58.87s)_

**PLAYER:** I follow through with the strike, feeling the sword bite into metal as the head of the construct splits apart. The sensor-lens goes dark as the lifeless body crumples to the ground. I pause, catching my breath, and turn to the GM.

**GM:**

The blade bites clean. Metal screams. The head separates from the torso in a spray of sparks and hydraulic fluid, clattering across the floor in a spin of dead metal. The sensor-lens gutters once—amber, red, nothing—then goes dark. The construct crumples. Collapses. The claw arm spasms once against the curved wall, then stills.

You stand over the ruin. Breath comes hard. The hum in your teeth wavers, skips, holds.

Then you hear it.

Not mechanical. Not the click of pistons or whir of servos. A sound like breathing. Slow. Wet. From somewhere deeper in the corridor where the blue light pools thick and still.

The geometry etched in the floor pulses once. Twice. The cold at your spine sharpens into something else—recognition. Something knows you killed it. Something is waiting.

The path forward remains open. But the air tastes different now. Heavier. Your blade hangs ready, slick with machine-fluid, and the silence that follows feels less empty than before.

It feels occupied.

> resolution=`scene_turn`  ·  success=`partial_success`  ·  effects=`['mixed_outcome', 'fiction_advances']`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "dice",
  "intent_type": "action",
  "success_level": "partial_success",
  "roll_breakdown": "1d20(15) + -5 = 10 vs DC 12",
  "roll_detail": {
    "spec": "1d20-5",
    "total": 10,
    "rolls": [
      15
    ],
    "kept_rolls": [
      15
    ],
    "reason": "Strength check (DC 12, normal)",
    "roll_mode": "normal"
  },
  "stat": "Strength",
  "difficulty_class": 12,
  "effects": [
    "mixed_outcome",
    "fiction_advances"
  ],
  "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Strength around DC 12.",
  "consequence_options": [
    "Succeed, but spend extra time or a limited resource.",
    "Succeed, but attract danger or unwanted attention.",
    "Pull back to stay safe and give up immediate momentum."
  ],
  "requires_player_choice": true,
  "narrative_pressure": "rising",
  "turn_id": "8d729515-6e1c-41e7-953c-3d69ab9ff51a",
  "resolution_id": "eda0a573-f545-4b92-acca-fc9b422ee2e9",
  "working_state": {
    "state_id": "e785256f-14bd-49a0-9412-ef662cd7e758",
    "entity_id": "5adc15ed-d734-45d2-855f-30eee5cfca48",
    "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362",
    "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
    "current_stats": {
      "narrative_pressure": "rising",
      "last_success_level": "partial_success"
    },
    "resources": {},
    "conditions": []
  },
  "scene_checkpoint": {
    "turn_id": "8d729515-6e1c-41e7-953c-3d69ab9ff51a",
    "resolution_id": null,
    "success_level": "partial_success",
    "narrative_pressure": "rising",
    "xp_awarded": 0,
    "summary": "The blade bites clean. Metal screams. The head separates from the torso in a spray of sparks and hydraulic fluid, clattering across the floor in a spin of dead metal. The sensor-lens gutters once—amber, red, nothing—t... [partial success]",
    "resources": {},
    "conditions": [],
    "updated_at": "2026-06-26T00:48:36.712896+00:00"
  },
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
  "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362",
  "awaiting_consequence_choice": true
}
```

## Turn 20 — `extraction` _(phase=active_play, lat=0.01s)_

**PLAYER:** I bend down to retrieve a small, glowing component from the construct’s torso before sprinting towards the door, the cold biting at my skin.

**GM:**

Choose one of the offered costs before we continue:
1. Succeed, but spend extra time or a limited resource.
2. Succeed, but attract danger or unwanted attention.
3. Pull back to stay safe and give up immediate momentum.

> resolution=`consequence_choice_prompt`

```json
{
  "type": "consequence_choice_prompt",
  "phase": "active_play",
  "awaiting_consequence_choice": true,
  "consequence_options": [
    "Succeed, but spend extra time or a limited resource.",
    "Succeed, but attract danger or unwanted attention.",
    "Pull back to stay safe and give up immediate momentum."
  ],
  "turn_id": "8d729515-6e1c-41e7-953c-3d69ab9ff51a"
}
```

## Turn 21 — `extraction_pressure` _(phase=active_play, lat=0.01s)_

**PLAYER:** I push open the emergency airlock with all my strength, feeling the pressure shift as the breach equalizes. The hiss of escaping atmosphere sounds in my ears as I squeeze through the narrow opening and into the relative safety of the corridor beyond.

**GM:**

Understood — Pull back to stay safe and give up immediate momentum. The scene absorbs that cost, and the pressure shifts around you. What do you do next?

> resolution=`consequence_choice`

```json
{
  "type": "consequence_choice",
  "phase": "active_play",
  "chosen_consequence": "Pull back to stay safe and give up immediate momentum.",
  "awaiting_consequence_choice": false,
  "turn_id": "8d729515-6e1c-41e7-953c-3d69ab9ff51a"
}
```

## Turn 22 — `wrap_up` _(phase=active_play, lat=35.1s)_

**PLAYER:** I pull myself through the airlock and into the sterile corridor of the space station, my breathing heavy as I catch my breath.

**GM:**

The airlock cycles open with a hiss. Beyond it: a corridor. Sterile white panels line the walls, interrupted by sealed bulkhead doors marked with faded designations. The lighting here flickers in irregular pulses—Loss of power, or something else. Your mag-boots find purchase on the deck plating with a heavy thunk, thunk, thunk. The recycled air tastes stale. Metallic. It catches at the back of your throat.

Twenty meters ahead, the corridor branches. To the left, emergency lighting casts everything in deep crimson. To the right, a single door stands ajar, spilling pale illumination across the threshold. Neither path invites. Both feel watched.

The station groans around you. Metal settling. Or something shifting beneath the hull.

You catch your breath. The question is simple: which way do you move, and how?

Roll your Strength for me.

> resolution=`scene_turn`  ·  success=`pending`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "propose_roll",
  "intent_type": "action",
  "success_level": "pending",
  "roll_breakdown": "propose_roll — Strength check (DC 12)",
  "roll_detail": null,
  "stat": "Strength",
  "difficulty_class": 12,
  "effects": [],
  "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Strength around DC 12.",
  "consequence_options": [],
  "requires_player_choice": true,
  "narrative_pressure": "rising",
  "turn_id": "26cb9e08-f5b5-48e0-8add-5c71905363b8",
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "aefc6176-9d77-40e1-8ad5-919a09daaeb8",
  "scene_id": "0c0dd957-b1fa-4eee-9c4d-30d7e9b8b362",
  "dice_request": {
    "spec": "1d20-5",
    "reason": "That sounds risky — roll your Strength for me.",
    "stat": "Strength",
    "difficulty_class": 12,
    "modifier": -5,
    "roll_under": false,
    "action_type": "action",
    "intent_type": "action",
    "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Strength around DC 12.",
    "original_action": "I pull myself through the airlock and into the sterile corridor of the space station, my breathing heavy as I catch my breath."
  }
}
```
