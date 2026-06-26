# Long-Form Narration Replay

- **API**: `http://localhost:8000/api`
- **Player model**: `ollama/qwen2.5:latest`
- **Benchmark**: `narrative_weighted_derelict`
- **Bootstrap**: `demo (Millhaven)`
- **Session ID**: `b2c014ba-04d8-447e-882a-2048466dc796`
- **Universe ID**: `e24735f2-0515-44ab-a518-b6a48347d62c`
- **Goal steps**: `22`
- **Turns played**: `22`
- **Avg latency**: `25.37s`
- **Rolls observed**: `19`
- **Fallback markers**: `0`
- **Canon entities at end**: `0`
- **Generated at**: `2026-06-25T17:15:17.305719+00:00`

---

## Turn 1 — `char_creation_accept` _(phase=awaiting_character, lat=12.62s)_

**PLAYER:** I step into the dimly lit chamber, my eyes adjusting to the faint light. The air is thick with the scent of metal and old machinery. I introduce myself as Kael Draven, a void-born salvage engineer, and begin to survey the wreckage around me, already formulating plans for what can be salvaged.

**GM:**

The chamber swallows sound. Your boots echo against iron grating, each step ringing through hollow space. Above, pipes hiss steam into darkness you cannot name. The wreckage sprawls before you—twisted struts, shattered housings, things that might once have been machines. Now they are corpses of metal, leaking fluids that catch the faint light like black tears.

You speak your name into the void. It falls flat. No one answers. No one has answered in a long time here.

The air tastes of copper and cold. Somewhere deeper in this place, something shifts—a groan of stressed metal, or something breathing. The difference no longer matters. You learned long ago that the void takes everything eventually. You are simply here to pick the bones first.

A corridor branches left, choked with debris. Right, the darkness thins near a doorway where pale light bleeds through corroded seams. The machinery around you offers no clues. Salvage? Possible. Survival? That has never been guaranteed.

You are Kael Draven now. Void-born. Salvage engineer. The titles mean nothing here. Only what you do next matters.

> resolution=`ooc_answer`

```json
{
  "type": "ooc_answer",
  "phase": "awaiting_character"
}
```

## Turn 2 — `char_creation_stat_roll` _(phase=active_play, lat=9.86s)_

**PLAYER:** I roll my stats, focusing onexterity, intelligence, and charisma.

**GM:**

You come into this world sharp-edged. Quick hands. Quicker mind. You know how to talk your way past locked doors and through the ones that weren't built to open. The numbers don't lie: you're nimble, clever, and silver-tongued. What the numbers can't tell you is how much darkness those gifts have already carried you through. The city breathes rust and regret. You exhale along with it. You are here. You are watching. You are already calculating exits.

> resolution=`preplay_ack`

```json
{
  "type": "preplay_ack",
  "phase": "active_play",
  "saved_character": {
    "entity_id": "6a60e0f4-6698-4840-be6c-4781ece16306",
    "sheet_id": "df1dbcb4-e577-4f8a-a3e0-51e586fe6e65",
    "profile_id": null,
    "saved_to_universe_id": "e24735f2-0515-44ab-a518-b6a48347d62c"
  }
}
```

## Turn 3 — `first_in_fiction_action` _(phase=ooc, lat=14.68s)_

**PLAYER:** I survey the room, noting the heavy doors on all sides and the group of rough-looking men by the bar. Is there a recent rumor board or any signs of a job posting nearby?

**GM:**

The Rust Nail's interior reeks of wet iron and stale ale. Four heavy doors line the walls—one to the kitchens, two to the street, one boarded shut with fresh nails. A cluster of five men occupies the bar's far end, their voices low, hands never far from their belts. Scars crease their faces like old rust.

Near the hearth, a corkboard hangs crooked on the wall. Weathered papers flutter against it. Job postings. Notices. A reward handbill bearing a woman's sketched face—the words MISSING or MAY SHE REST are scratched out and replaced with something else, something written in a hand that trembles.

The chalked specials board reads: LAMB STEW. SALT PORK. SELL YOUR SORROWS CHEAP.

The rough men glance your way once. Then they return to their drinks. Nothing good waits for curious strangers in Millhaven.

> resolution=`ooc_answer`

```json
{
  "type": "ooc_answer",
  "phase": "ooc",
  "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
  "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec",
  "ooc": true
}
```

## Turn 4 — `social_inquiry` _(phase=active_play, lat=27.07s)_

**PLAYER:** I approach the bartender, my eyes scanning the room for any potential threats as I draw closer. "Excuse me," I say, my voice steady. "Have you heard anything about a derelict ship they've been talking about? Something about old Rust Nail?"

**GM:**

The bartender is a thick-necked woman with burn scars climbing her left arm. She does not look up from the glass she is polishing. The establishment is half-full—off-duty haulers, a pair of dock inspectors sharing cold coffee, a hooded figure in the corner nursing something darker than what the others are drinking.

"Rust Nail." She sets the glass down with a soft click. Her eyes flick to you, flat and assessing. "That's a name you don't hear much anymore. Not since it went dark six months back. Maybe seven." She resumes polishing. "Transmissions stopped. Then the beacon went silent. They sent a skeleton crew to investigate. Two salvage drones. Nobody came back to file a report."

The dock inspectors glance your way for a moment. Then they look back at their coffee.

"There's a memorial dock on the east pier," the bartender continues. "For the crew. If that's what you're asking about." Her voice drops half a register. "But if you're looking for the ship itself—good luck. Last I heard, it's somewhere in the Driftward Graveyard. Past the quarantine buoys." She slides a glass of something amber toward you. "That'll be ten credits. And friend? Most who go looking for the Rust Nail don't come back to buy another round."

> resolution=`scene_turn`  ·  success=`success`  ·  effects=`['fiction_advances']`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "trivial",
  "intent_type": "dialogue",
  "success_level": "success",
  "roll_breakdown": "trivial — no roll needed",
  "roll_detail": null,
  "stat": "Charisma",
  "difficulty_class": 12,
  "effects": [
    "fiction_advances"
  ],
  "risk_preview": "This is a routine action — no stakes beyond the narrative.",
  "consequence_options": [],
  "requires_player_choice": false,
  "narrative_pressure": "steady",
  "turn_id": "11344487-f394-45bb-870c-ff1ba1e3123d",
  "resolution_id": "b4c835b7-6632-4654-9fae-145c13212a63",
  "working_state": {
    "state_id": "1158e683-a4d0-4209-be3a-f31074068a80",
    "entity_id": "6a60e0f4-6698-4840-be6c-4781ece16306",
    "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec",
    "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
    "current_stats": {
      "narrative_pressure": "steady",
      "last_success_level": "success"
    },
    "resources": {},
    "conditions": []
  },
  "scene_checkpoint": {
    "turn_id": "11344487-f394-45bb-870c-ff1ba1e3123d",
    "resolution_id": null,
    "success_level": "success",
    "narrative_pressure": "steady",
    "xp_awarded": 0,
    "summary": "The bartender is a thick-necked woman with burn scars climbing her left arm. She does not look up from the glass she is polishing. The establishment is half-full—off-duty haulers, a pair of dock inspectors sharing col... [success]",
    "resources": {},
    "conditions": [],
    "updated_at": "2026-06-25T17:05:35.259492+00:00"
  },
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
  "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec"
}
```

## Turn 5 — `lore_recall` _(phase=active_play, lat=29.92s)_

**PLAYER:** I lean in slightly, maintaining eye contact with the bartender. "Excuse me, ma'am," I say, my voice low but steady. "I'm looking for any information on a derelict ship that might be of interest to salvage engineers."

**GM:**

The bartender's hands pause on the glass she was polishing. She studies you now—really studies you—with the practiced eye of someone who has poured drinks for spacers, smugglers, and fools alike.

"Salavage engineers." She repeats the phrase like she's tasting something off about it. "That's a clean way of putting it."

The hooded figure in the corner shifts. You catch the faintest click of a glass being set down.

"Most salvage engineers I meet don't ask about ships by name. They already know which wreck they want." She reaches under the bar and pulls out a battered datapad, sliding it across the counter without turning it on. "Driftward Graveyard coordinates. Officially sealed. Unofficially, everyone who's anyone in the salvage trade has a copy."

Her scarred hand taps the edge of the datapad.

"This will cost you more than ten credits. And it comes with a warning I don't normally give." Her voice drops lower. "The last salvage team that went after the Rust Nail? They weren't after scrap. They were looking for something in the cargo hold. Something the manifest said wasn't there."

The dock inspectors have gone quiet. Not leaving—just listening.

"I don't know what they found. I don't want to know." She holds your gaze. "The coordinates are yours for fifty credits and a promise: you don't come back here asking for another favor."

> resolution=`scene_turn`  ·  success=`success`  ·  effects=`['fiction_advances']`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "trivial",
  "intent_type": "dialogue",
  "success_level": "success",
  "roll_breakdown": "trivial — no roll needed",
  "roll_detail": null,
  "stat": "Charisma",
  "difficulty_class": 12,
  "effects": [
    "fiction_advances"
  ],
  "risk_preview": "This is a routine action — no stakes beyond the narrative.",
  "consequence_options": [],
  "requires_player_choice": false,
  "narrative_pressure": "steady",
  "turn_id": "a35e8478-c310-48b2-9677-51033dbbc631",
  "resolution_id": "1eb15e91-14ad-422e-84de-f3d2b70462da",
  "working_state": {
    "state_id": "1158e683-a4d0-4209-be3a-f31074068a80",
    "entity_id": "6a60e0f4-6698-4840-be6c-4781ece16306",
    "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec",
    "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
    "current_stats": {
      "narrative_pressure": "steady",
      "last_success_level": "success"
    },
    "resources": {},
    "conditions": []
  },
  "scene_checkpoint": {
    "turn_id": "a35e8478-c310-48b2-9677-51033dbbc631",
    "resolution_id": null,
    "success_level": "success",
    "narrative_pressure": "steady",
    "xp_awarded": 0,
    "summary": "The bartender's hands pause on the glass she was polishing. She studies you now—really studies you—with the practiced eye of someone who has poured drinks for spacers, smugglers, and fools alike.\n\n\"Salavage engineers.... [success]",
    "resources": {},
    "conditions": [],
    "updated_at": "2026-06-25T17:06:10.406049+00:00"
  },
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
  "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec"
}
```

## Turn 6 — `social_deal` _(phase=active_play, lat=22.63s)_

**PLAYER:** I make my way to the counter, where the bartender is still eyeing me carefully. "Mind if I take a look at your inventory?" I ask, glancing around to ensure no one is watching too closely.

**GM:**

The bartender's eyes narrow. Her fingers drum once against the bar top—a slow, deliberate rhythm.

"Inventory." She says it flat, like she's repeating a word in a language she doesn't speak well. "You're in a port-side dive asking about a ghost ship and salvage crews that vanished. Now you want to browse my stock like I'm running a supply depot."

She pulls the datapad back slightly, not hiding it, but not offering it either.

"I told you what I have. Coordinates. A warning. A clean exit from this conversation." Her scarred hand flattens against the bar between you. "If you're looking for weapons, rations, or ship's parts, you want the markets on Deck Seven. I pour drinks and I listen. That's my inventory."

The hooded figure in the corner rises. You catch a glimpse of a gaunt face beneath the shadow—a woman, maybe, or a man worn thin. She drops credits on her table and moves toward the door without looking back.

The dock inspectors exchange a glance. One of them snorts quietly into his coffee.

The bartender waits.

"You want the datapad, it costs fifty credits. You want something else—" She shrugs, a single hard motion. "You're in the wrong place."

> resolution=`scene_turn`  ·  success=`success`  ·  effects=`['fiction_advances']`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "trivial",
  "intent_type": "dialogue",
  "success_level": "success",
  "roll_breakdown": "trivial — no roll needed",
  "roll_detail": null,
  "stat": "Charisma",
  "difficulty_class": 12,
  "effects": [
    "fiction_advances"
  ],
  "risk_preview": "This is a routine action — no stakes beyond the narrative.",
  "consequence_options": [],
  "requires_player_choice": false,
  "narrative_pressure": "steady",
  "turn_id": "29e9f2f8-62e2-4ddb-8f45-9f4569d7a589",
  "resolution_id": "4f0a87c3-d207-404e-b247-0656f7db311f",
  "working_state": {
    "state_id": "1158e683-a4d0-4209-be3a-f31074068a80",
    "entity_id": "6a60e0f4-6698-4840-be6c-4781ece16306",
    "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec",
    "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
    "current_stats": {
      "narrative_pressure": "steady",
      "last_success_level": "success"
    },
    "resources": {},
    "conditions": []
  },
  "scene_checkpoint": {
    "turn_id": "29e9f2f8-62e2-4ddb-8f45-9f4569d7a589",
    "resolution_id": null,
    "success_level": "success",
    "narrative_pressure": "steady",
    "xp_awarded": 0,
    "summary": "The bartender's eyes narrow. Her fingers drum once against the bar top—a slow, deliberate rhythm.\n\n\"Inventory.\" She says it flat, like she's repeating a word in a language she doesn't speak well. \"You're in a port-sid... [success]",
    "resources": {},
    "conditions": [],
    "updated_at": "2026-06-25T17:06:38.361862+00:00"
  },
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
  "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec"
}
```

## Turn 7 — `exploration_intent` _(phase=active_play, lat=35.98s)_

**PLAYER:** I glance at the bartender and then towards the cluster of men by the bar, making sure they're not paying attention. "Of course, I won't take long," I say, reaching for a dataslate to input my request.

**GM:**

The dataslate's glow is faint. Your fingers move across the interface, pulling up a search query on the Rust Nail's registry. The bartender watches your hands, then your face, then back to your hands.

She says nothing.

One of the dock inspectors shifts on his stool. The creak of leather. The soft click of a boot against the floor rung. You don't look up. Your peripheral vision catches him watching—not you, not yet, but the dataslate's pale rectangle of light against the bar's darkness.

The query runs. Results populate the screen. You keep your face neutral.

Three names. Three salvage licenses, all flagged dormant. One death certificate filed six months ago. The Rust Nail's last registered owner: a shell company dissolved eighteen months before the ship went dark.

The bartender leans forward, voice barely a murmur.

"If those boys see you pulling data on that ship, they won't ask questions. They'll just remember your face." Her scarred hand taps the datapad of coordinates again. "Fifty credits gets you out of here with what you need. And a clean slate."

The inspector's coffee cup rises to his lips. He is watching the door now.

The dataslate screen stays lit between you.

> resolution=`scene_turn`  ·  success=`success`  ·  effects=`['fiction_advances']`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "trivial",
  "intent_type": "dialogue",
  "success_level": "success",
  "roll_breakdown": "trivial — no roll needed",
  "roll_detail": null,
  "stat": "Charisma",
  "difficulty_class": 12,
  "effects": [
    "fiction_advances"
  ],
  "risk_preview": "This is a routine action — no stakes beyond the narrative.",
  "consequence_options": [],
  "requires_player_choice": false,
  "narrative_pressure": "steady",
  "turn_id": "bfa090f9-0556-4443-b62b-be8c3e1ed867",
  "resolution_id": "904edd83-11a9-429b-bdea-936c468528a4",
  "working_state": {
    "state_id": "1158e683-a4d0-4209-be3a-f31074068a80",
    "entity_id": "6a60e0f4-6698-4840-be6c-4781ece16306",
    "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec",
    "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
    "current_stats": {
      "narrative_pressure": "steady",
      "last_success_level": "success"
    },
    "resources": {},
    "conditions": []
  },
  "scene_checkpoint": {
    "turn_id": "bfa090f9-0556-4443-b62b-be8c3e1ed867",
    "resolution_id": null,
    "success_level": "success",
    "narrative_pressure": "steady",
    "xp_awarded": 0,
    "summary": "The dataslate's glow is faint. Your fingers move across the interface, pulling up a search query on the Rust Nail's registry. The bartender watches your hands, then your face, then back to your hands.\n\nShe says nothin... [success]",
    "resources": {},
    "conditions": [],
    "updated_at": "2026-06-25T17:07:19.806106+00:00"
  },
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
  "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec"
}
```

## Turn 8 — `first_combat_intent` _(phase=active_play, lat=26.99s)_

**PLAYER:** I move towards the entrance of the derelict ship, my hand resting on the hilt of my cutter as I shine my lamp around the dark corridor.

**GM:**

The derelict looms against the void-black sky. Your lamp cuts a pale wound through the darkness, illuminating the hull's scarred plating. The name etched into the rusted metal reads *Ostensible*—faded, half-eaten by corrosion.

The airlock stands open. Not broken. Not forced. Simply open, like a mouth waiting.

Your cutter's hilt is cold against your palm. Inside, the corridor stretches into black nothing. Your lamp's beam dies three meters ahead, swallowed by shadow. The metal beneath your boots is slick with something your light refuses to name. The silence is absolute—no hum of power, no distant groan of stressed hull. Nothing.

A draft moves past you, coming from inside. It carries the smell of old recycled air and copper.

You step across the threshold. The deck plating groans beneath your weight—once, like a bone settling. Your lamp sweeps left. Corridor. Sealed doors. Scorch marks climbing the walls in patterns too deliberate to be accidents.

Ahead, the darkness thickens.

Your lamp flickers. Once.

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
  "turn_id": "fee79178-ee2a-4f00-a317-0b406660996d",
  "resolution_id": "e3427bd3-10ee-453a-bdfb-4264d57bc567",
  "working_state": {
    "state_id": "1158e683-a4d0-4209-be3a-f31074068a80",
    "entity_id": "6a60e0f4-6698-4840-be6c-4781ece16306",
    "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec",
    "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
    "current_stats": {
      "narrative_pressure": "steady",
      "last_success_level": "success"
    },
    "resources": {},
    "conditions": []
  },
  "scene_checkpoint": {
    "turn_id": "fee79178-ee2a-4f00-a317-0b406660996d",
    "resolution_id": null,
    "success_level": "success",
    "narrative_pressure": "steady",
    "xp_awarded": 0,
    "summary": "The derelict looms against the void-black sky. Your lamp cuts a pale wound through the darkness, illuminating the hull's scarred plating. The name etched into the rusted metal reads *Ostensible*—faded, half-eaten by c... [success]",
    "resources": {},
    "conditions": [],
    "updated_at": "2026-06-25T17:07:51.043606+00:00"
  },
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
  "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec"
}
```

## Turn 9 — `combat_engaged` _(phase=active_play, lat=23.06s)_

**PLAYER:** I quickly scan the corridor with my lamp, identifying potential threats before charging forward, cutter at the ready.

**GM:**

Your lamp sweeps the corridor in sharp arcs. Sealed doors, left and right. Emergency lighting strips—dead, black as veins. The scorch marks climb higher here, branching like frozen lightning. No bodies. No blood. Just the marks and the smell of copper thickening as you move deeper.

You charge forward. Boots pounding rusted metal. Your cutter's hum joins the silence like a voice speaking alone in an empty cathedral.

The corridor opens into a junction. Three paths. Your lamp finds the first—collapsed bulkhead, debris piled floor to ceiling. The second—a ladder descending into darker dark. The third stretches ahead, and at its end, a door. Sealed. The seal light blinks amber.

Alive.

Someone sealed that door from inside.

Your lamp flickers again. Holds. The amber light pulses, steady as a heartbeat.

Something shifts in the walls. A click. A groan of metal settling.

Or something else.

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
  "turn_id": "d85e2826-bd95-4c9d-91df-8e0bbd0eebb1",
  "resolution_id": "71bba710-dbeb-40aa-8a40-94042c0a913d",
  "working_state": {
    "state_id": "1158e683-a4d0-4209-be3a-f31074068a80",
    "entity_id": "6a60e0f4-6698-4840-be6c-4781ece16306",
    "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec",
    "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
    "current_stats": {
      "narrative_pressure": "steady",
      "last_success_level": "success"
    },
    "resources": {},
    "conditions": []
  },
  "scene_checkpoint": {
    "turn_id": "d85e2826-bd95-4c9d-91df-8e0bbd0eebb1",
    "resolution_id": null,
    "success_level": "success",
    "narrative_pressure": "steady",
    "xp_awarded": 0,
    "summary": "Your lamp sweeps the corridor in sharp arcs. Sealed doors, left and right. Emergency lighting strips—dead, black as veins. The scorch marks climb higher here, branching like frozen lightning. No bodies. No blood. Just... [success]",
    "resources": {},
    "conditions": [],
    "updated_at": "2026-06-25T17:08:17.038913+00:00"
  },
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
  "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec"
}
```

## Turn 10 — `combat_finisher` _(phase=active_play, lat=24.22s)_

**PLAYER:** I swing my cutter in a wide arc, aiming for the enemy's midsection as it lunges at me, trying to catch it off balance.

**GM:**

Something detaches from the ceiling.

Your lamp catches it in strobing fragments—pale limbs too long, joints bending wrong, a face that might have been human once now stretched into something like hunger given form. It drops from the ventilation shaft above, silent, and lunges at your throat.

Your cutter swings wide. The hum of the blade cuts the stale air. The thing's weight crashes into you mid-arc—cold, wrong, heavier than it looks. Bones grind against your guard. Its breath is the smell of copper and void-cold recycled air. Teeth find the edge of your collar, grazing skin.

Your feet slide on the slick deck. You brace. The creature's grip is iron.

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
  "turn_id": "3ce48b33-cb33-4b60-9e8b-4b58d19c34f4",
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
  "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec",
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
    "original_action": "I swing my cutter in a wide arc, aiming for the enemy's midsection as it lunges at me, trying to catch it off balance."
  }
}
```

## Turn 11 — `tactical_assessment` _(phase=active_play, lat=37.27s)_

**PLAYER:** I pause for a moment to catch my breath and survey the situation. My heart races as I check my health and inventory quickly, then readjust my grip on the cutter. The creature lies motionless at my feet, its form distorting in the harsh light of my lamp. I decide to push forward cautiously, knowing danger may lurk around every corner.

**GM:**

You plant a boot on the creature's chest and shove. It slides across the deck with a wet scrape. Dead. Or close enough. Your fingers find the tear in your collar—skin unbroken, just the graze of teeth on fabric. Lucky. Not smart. Lucky.

You check your seal. Intact. Cutting fuel reads three-quarters. The emergency beacon in your pocket pulses faintly—you haven't activated it. Not yet. Not until you know what you're walking into.

The amber light on the sealed door fifty meters ahead pulses slower now. Breathing. Waiting. You move toward it, footfalls deliberate, lamp sweeping the overhead ducts. The walls groan. Somewhere below, metal screams against metal—a distant pressure seal adjusting, or something trying to force its way through.

Twenty meters from the door, your lamp catches fresh scratches on the deck. Drag marks. Something was pulled here recently. The marks lead left, toward a maintenance hatch half-hidden in shadow.

The door's seal light flickers. Once. Twice.

Then holds.

Someone inside knows you're here.

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
  "turn_id": "01b4e685-88b6-4e31-a52f-5b15cd6c741c",
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
  "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec",
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
    "original_action": "I pause for a moment to catch my breath and survey the situation. My heart races as I check my health and inventory quickly, then readjust my grip on the cutter. The creature lies motionless at my feet, its form distorting in the harsh light of my lamp. I decide to push forward cautiously, knowing danger may lurk around every corner."
  }
}
```

## Turn 12 — `deeper_push` _(phase=active_play, lat=38.78s)_

**PLAYER:** I continue down the corridor, my cutter at the ready, pushing through the lingering fear and towards the unknown dangers that await.

**GM:**

Ten meters from the door. The seal light holds steady now. Watching.

The deck vibrates under your boots. Not machinery. Something alive. The vibration travels up through your legs, settles in your teeth.

You reach the door. Cold steel. A speaker grill dark above the frame. No handle on your side—just a manual release plate recessed into the wall. Standard design. Same on every bulkhead from here to the outer rings.

Your fingers find the plate. The metal is ice. You press.

Nothing. The seal holds. But you feel it—the faintest resistance, like something pressing back from the other side.

Roll your Strength.

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
  "turn_id": "d7c83f67-93fc-496e-882a-e4b9715d9221",
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
  "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec",
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
    "original_action": "I continue down the corridor, my cutter at the ready, pushing through the lingering fear and towards the unknown dangers that await."
  }
}
```

## Turn 13 — `puzzle_encounter` _(phase=active_play, lat=27.93s)_

**PLAYER:** I approach the sealed door slowly, my lamp casting shadows on the symbols etched into the steel. I run my fingers over the intricate patterns, trying to decipher their meaning.

**GM:**

The symbols are etched deep into the steel—deliberate cuts, not corrosion. Old. Older than the station's operational records. Some resemble navigational glyphs from pre-Expansion charters. Others are wrong. Geometric. They repeat in patterns that hurt to follow, like looking at a fold in space that shouldn't exist.

One cluster draws your eye. A repeated motif: three circles intersected by a diagonal line. Below it, fresh scratches. Someone added to the design recently. The cuts are still bright, uncorroded. Whoever—or whatever—marked this door wanted it marked.

Your lamp flickers. The seal light pulses once.

The vibration through the deck intensifies. Something behind that door shifts its weight.

Roll your Intelligence for me.

> resolution=`scene_turn`  ·  success=`pending`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "propose_roll",
  "intent_type": "action",
  "success_level": "pending",
  "roll_breakdown": "propose_roll — Intelligence check (DC 13)",
  "roll_detail": null,
  "stat": "Intelligence",
  "difficulty_class": 13,
  "effects": [],
  "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Intelligence around DC 13.",
  "consequence_options": [],
  "requires_player_choice": true,
  "narrative_pressure": "rising",
  "turn_id": "ac8539a1-d948-4cc8-afe1-06b38dd225dc",
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
  "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec",
  "dice_request": {
    "spec": "1d20-5",
    "reason": "That sounds risky — roll your Intelligence for me.",
    "stat": "Intelligence",
    "difficulty_class": 13,
    "modifier": -5,
    "roll_under": false,
    "action_type": "action",
    "intent_type": "action",
    "risk_preview": "This move carries concrete danger: failure can cost position, time, or resources, and the check is likely to hinge on Intelligence around DC 13.",
    "original_action": "I approach the sealed door slowly, my lamp casting shadows on the symbols etched into the steel. I run my fingers over the intricate patterns, trying to decipher their meaning."
  }
}
```

## Turn 14 — `puzzle_solve` _(phase=active_play, lat=28.2s)_

**PLAYER:** I focus intently on the intersecting circles, tracing the pattern with my finger and considering it against the other symbols as a potential code or map.

**GM:**

Your finger traces the three circles. The diagonal line bisects them. A pattern. A key, maybe. Or a warning.

The deck shudders. The seal light flickers red, then green, then red again.

Something presses against the door from within. Not knocking. Testing. Learning the seal's edge.

The manual release plate vibrates under your other hand. Warm now. Body heat, leaking through eight centimeters of steel.

You step back. The symbols on the door seem darker than before. The fresh scratches catch your lamp—eight parallel lines, then three, then eight again. A count. A sequence. But no panel opens, no mechanism responds.

The door does not yield to study.

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
  "turn_id": "8bf3dd82-f495-415a-b3cd-016c2897a95b",
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
  "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec",
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
    "original_action": "I focus intently on the intersecting circles, tracing the pattern with my finger and considering it against the other symbols as a potential code or map."
  }
}
```

## Turn 15 — `puzzle_consequence` _(phase=active_play, lat=23.57s)_

**PLAYER:** I concentrate on the pattern, then look up to see if any changes occur with the door or the symbols.

**GM:**

You look up.

The symbols have not changed. The door remains sealed. The seal light holds its steady red.

But the pressure against it has stopped. Whatever tested the threshold from within has gone still. Listening. Waiting for you to act, or waiting for you to leave.

The lamp steadies. The deck vibration fades to nothing. Silence fills the corridor—thick and absolute, like the station itself is holding its breath.

You are alone with the marks. Whatever comes next is yours to decide.

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
  "turn_id": "4243e7ad-bdcb-4824-9bcb-03253bb19736",
  "resolution_id": "f98a23ba-62a6-4d62-9dd6-99c1fd03b6df",
  "working_state": {
    "state_id": "1158e683-a4d0-4209-be3a-f31074068a80",
    "entity_id": "6a60e0f4-6698-4840-be6c-4781ece16306",
    "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec",
    "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
    "current_stats": {
      "narrative_pressure": "steady",
      "last_success_level": "success"
    },
    "resources": {},
    "conditions": []
  },
  "scene_checkpoint": {
    "turn_id": "4243e7ad-bdcb-4824-9bcb-03253bb19736",
    "resolution_id": null,
    "success_level": "success",
    "narrative_pressure": "steady",
    "xp_awarded": 0,
    "summary": "You look up.\n\nThe symbols have not changed. The door remains sealed. The seal light holds its steady red.\n\nBut the pressure against it has stopped. Whatever tested the threshold from within has gone still. Listening.... [success]",
    "resources": {},
    "conditions": [],
    "updated_at": "2026-06-25T17:11:43.475162+00:00"
  },
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
  "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec"
}
```

## Turn 16 — `loot_choice` _(phase=active_play, lat=27.13s)_

**PLAYER:** I step back from the door, my cutter ready as I examine the symbols one last time before turning to the alcove where I know the station's core is kept. Carefully, I unlock the hidden compartment and retrieve a small data core, ensuring not to touch any of the other salvaged items that might be sensitive or valuable. With the core in hand, I leave the other materials behind, closing the compartment as quietly as possible.

**GM:**

The alcove sits twelve meters back along the corridor. You know it by memory—by the faint hexagonal outline barely visible beneath accumulated grime.

The panel resists. Eight centimeters of steel, yes, but also time. Corrosion has fused the seam shut. The metal groans when you apply pressure—not loud, but loud enough in the station's silence.

The data core waits inside. Small. Lukewarm. A cylinder of compressed information that once ran this station's critical systems.

Your cutter hums. The compartment's edge gleams where rust flakes away.

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
  "turn_id": "9a77bb48-0294-4f1d-9081-93344fc3e180",
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
  "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec",
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
    "original_action": "I step back from the door, my cutter ready as I examine the symbols one last time before turning to the alcove where I know the station's core is kept. Carefully, I unlock the hidden compartment and retrieve a small data core, ensuring not to touch any of the other salvaged items that might be sensitive or valuable. With the core in hand, I leave the other materials behind, closing the compartment as quietly as possible."
  }
}
```

## Turn 17 — `boss_intro` _(phase=active_play, lat=28.02s)_

**PLAYER:** I assess the space, finding a narrow gap to the right of the alcove where I can position myself to watch both the door and the core, then draw my pistol and chamber a round, aiming it towards the potential threat.

**GM:**

The gap accepts you. Cold metal presses against your spine. From here, the door sits twelve meters ahead, red seal-light bleeding across the corridor floor. The alcove waits at your back—close enough to reach, close enough to guard.

You raise the pistol. Steady. The barrel points toward the threshold.

Silence holds. The station breathes around you in slow metallic sighs. Somewhere deeper in the hull, pipes tick as metal contracts. Nothing moves. Nothing approaches.

The data core sits in the alcove behind you. A cylinder of compressed memory. A small warmth against the cold.

You wait.

The red light pulses once—Loss pulse, not warning. The system registers your presence but makes no demand. The symbols on the door remain still. Whatever tested the threshold has not returned.

Yet.

Your finger rests beside the trigger guard. Not on it. Not yet.

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
  "turn_id": "0046b2e2-fd8e-4b8b-a1d7-e6952f3e6eb8",
  "resolution_id": "4f413877-7d38-4002-809b-945480b2433b",
  "working_state": {
    "state_id": "1158e683-a4d0-4209-be3a-f31074068a80",
    "entity_id": "6a60e0f4-6698-4840-be6c-4781ece16306",
    "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec",
    "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
    "current_stats": {
      "narrative_pressure": "steady",
      "last_success_level": "success"
    },
    "resources": {},
    "conditions": []
  },
  "scene_checkpoint": {
    "turn_id": "0046b2e2-fd8e-4b8b-a1d7-e6952f3e6eb8",
    "resolution_id": null,
    "success_level": "success",
    "narrative_pressure": "steady",
    "xp_awarded": 0,
    "summary": "The gap accepts you. Cold metal presses against your spine. From here, the door sits twelve meters ahead, red seal-light bleeding across the corridor floor. The alcove waits at your back—close enough to reach, close e... [success]",
    "resources": {},
    "conditions": [],
    "updated_at": "2026-06-25T17:12:53.138102+00:00"
  },
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
  "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec"
}
```

## Turn 18 — `boss_phase_two` _(phase=active_play, lat=24.09s)_

**PLAYER:** I squeeze the trigger, sending a bullet through the seal's weak point. The impact shakes the door as another red light flashes.

**GM:**

The round punches through oxidized metal. The seal fractures—not cleanly, but enough. Corroded bolts shriek as they tear free from the doorframe.

The alcove panel responds to the vibration. Eight centimeters of steel shudder in their housing. The gap widens by a finger's breadth.

You lower the pistol. The data core sits exposed in its housing. A cylinder of compressed memory. A small warmth against the cold.

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
  "turn_id": "e5a3380d-3e13-45f8-bcb8-292f71f80c04",
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
  "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec",
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
    "original_action": "I squeeze the trigger, sending a bullet through the seal's weak point. The impact shakes the door as another red light flashes."
  }
}
```

## Turn 19 — `boss_finisher` _(phase=active_play, lat=27.55s)_

**PLAYER:** I squeeze the trigger again, aiming for a more precise spot in the seal. The bullet finds its mark, and a larger crack forms, allowing a faint beam of light from outside to seep through. I step forward, keeping my pistol at the ready, and approach the data core.

**GM:**

The second shot punches deeper. The crack splits wide—a ragged mouth in the metal. White light bleeds through, cold and sterile. Beyond, you glimpse the edge of a sterile corridor. Empty. For now.

The alcove panel waits. Eight centimeters of steel still caught in their housing, but the fracture runs deep now. You could force it. The data core sits within reach—cylindrical, humming with faint heat against your palm.

Your pistol stays raised. The corridor beyond holds its breath.

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
  "turn_id": "a9a69080-00cc-4ab8-847b-7d385fd2f63e",
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
  "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec",
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
    "original_action": "I squeeze the trigger again, aiming for a more precise spot in the seal. The bullet finds its mark, and a larger crack forms, allowing a faint beam of light from outside to seep through. I step forward, keeping my pistol at the ready, and approach the data core."
  }
}
```

## Turn 20 — `extraction` _(phase=active_play, lat=19.91s)_

**PLAYER:** I grab the data core with one hand and chamber another round, keeping my pistol at the ready as I turn to face the door.

**GM:**

Your fingers close around the data core. The cylinder pulls free from its housing with a wet, metallic click. Warmth bleeds through your glove. The core hums—a low, steady pulse against your palm.

Eight centimeters of corroded steel still hang in the alcove frame. The gap is wide enough. Barely.

You turn. The sterile corridor stretches ahead, white light pooling on polished floors. Empty. The silence presses against your ears.

The core pulses. Your pistol waits.

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
  "turn_id": "a43f18c0-b163-4f96-b278-871554179caa",
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
  "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec",
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
    "original_action": "I grab the data core with one hand and chamber another round, keeping my pistol at the ready as I turn to face the door."
  }
}
```

## Turn 21 — `extraction_pressure` _(phase=active_play, lat=27.0s)_

**PLAYER:** I yank the data core free and pivot, pressing the pistol against the remaining steel as I kick it hard with my boot. The panel shudders and cracks widen, buying me precious moments. I slam the door shut behind me just as a deafening alarm erupts, echoing through the station.

**GM:**

The steel screams. Your boot connects with the fractured panel and it buckles inward, the gap widening to a ragged mouth. You squeeze through, shoulder scraping corroded metal. The data core pulses against your palm—hot, insistent.

Behind you, the panel slams shut. The click of the magnetic seal echoes for half a heartbeat.

Then the alarm tears through the station. Red light floods the corridor in stuttering waves. Klaxons scream in metallic chorus. The walls themselves seem to pulse with warning.

Your boots ring against polished floors as you move. The corridor branches ahead—left toward a flickering maintenance hatch, right toward a sealed bulkhead marked with faded priority insignia. The alarm swallows all other sound. Every second counts now.

The core hums its steady rhythm. Your pistol waits. The station knows you're here.
</think>

> resolution=`scene_turn`  ·  success=`success`  ·  effects=`['momentum_gained', 'fiction_advances']`

```json
{
  "type": "scene_turn",
  "phase": "active_play",
  "resolution_type": "dice",
  "intent_type": "action",
  "success_level": "success",
  "roll_breakdown": "1d20(18) + -5 = 13 vs DC 12",
  "roll_detail": {
    "spec": "1d20-5",
    "total": 13,
    "rolls": [
      18
    ],
    "kept_rolls": [
      18
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
  "consequence_options": [],
  "requires_player_choice": false,
  "narrative_pressure": "steady",
  "turn_id": "d32c5b48-8c96-456b-8a12-2872dbaa1230",
  "resolution_id": "3b8cbde6-f94c-42bd-80ab-b3e40448cadd",
  "working_state": {
    "state_id": "1158e683-a4d0-4209-be3a-f31074068a80",
    "entity_id": "6a60e0f4-6698-4840-be6c-4781ece16306",
    "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec",
    "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
    "current_stats": {
      "narrative_pressure": "steady",
      "last_success_level": "success"
    },
    "resources": {},
    "conditions": []
  },
  "scene_checkpoint": {
    "turn_id": "d32c5b48-8c96-456b-8a12-2872dbaa1230",
    "resolution_id": null,
    "success_level": "success",
    "narrative_pressure": "steady",
    "xp_awarded": 0,
    "summary": "The steel screams. Your boot connects with the fractured panel and it buckles inward, the gap widening to a ragged mouth. You squeeze through, shoulder scraping corroded metal. The data core pulses against your palm—h... [success]",
    "resources": {},
    "conditions": [],
    "updated_at": "2026-06-25T17:14:51.502608+00:00"
  },
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
  "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec"
}
```

## Turn 22 — `wrap_up` _(phase=active_play, lat=21.57s)_

**PLAYER:** I force the remaining steel panel shut with my foot, securing it as best I can, then dash down the sterile corridor towards the hub.

**GM:**

The fractured panel resists. Corroded hinges fight you, metal groaning against metal. Your boot braces against the wall for leverage. The seal is imperfect—a thin gap remains, a breath between you and whatever comes next.

The klaxon drowns everything. Red light strobes across your visor in violent pulses.

Your lungs burn. The hub lies ahead—thirty meters of open corridor under constant sweep of the station's automated sentries.

The data core pulses against your palm. Hot. Urgent.

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
  "turn_id": "19adef6c-0d58-4528-ac1e-aa64fb18efc3",
  "resolution_id": null,
  "working_state": {},
  "scene_checkpoint": {},
  "social_read": {},
  "relationship_snapshot": {},
  "turns_count": 1,
  "story_id": "817ac577-f48a-4911-b475-b64103f2e261",
  "scene_id": "349765e8-6147-4c79-96fd-a8103431d8ec",
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
    "original_action": "I force the remaining steel panel shut with my foot, securing it as best I can, then dash down the sterile corridor towards the hub."
  }
}
```
