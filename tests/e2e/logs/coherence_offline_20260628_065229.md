# Offline Coherence Test

- Generated: `2026-06-28T06:52:29.835911+00:00`
- Result: **PASS**

Coherence measured by the actual `check_consistency` and `extract_facts` nodes in `scene_loop.py`, not by keyword heuristics.

## Summary

| Metric | Value |
|--------|-------|
| Turns run | 10 |
| Turns with narrative | 10 |
| Empty narratives | 0 |
| Pending roll pushbacks | 9 |
| Total facts extracted | 2 |
| Total consistency violations | 0 |

## Notes

- ✓ Pending roll state machine: pushback triggered 9 time(s)
- ✓ Facts extraction: 2 facts accumulated
- ✓ check_consistency node: no name drift or genre drift detected

---

## Turn-by-Turn

### Turn 1

**Player:** I am Kael Draven, a void-born salvage engineer aboard the derelict station Iron Verdict.

**GM:** The datapad displays coordinates for the Iron Verdict derelict.

- Resolution: `propose_roll` / `pending`
- Pending roll: `STR` DC `12` (action: `I am Kael Draven, a void-born salvage engineer abo`)
- Facts: 1
  - Named entity mentioned: Iron Verdict
- Latency: 3024ms

### Turn 2

**Player:** I check my suit's cutting fuel: 75%. The station groans around me.

**GM:** The GM raises a hand. 'You still need to roll STR (DC 12) for: I am Kael Draven, a void-born salvage engineer aboard the de. Roll the dice to resolve this before continuing.'

- Resolution: `forced_narrative_pushback` / `pending`
- Pending roll: `STR` DC `12` (action: `I am Kael Draven, a void-born salvage engineer abo`)
- Facts: 2
  - Named entity mentioned: Iron Verdict
  - Named entity mentioned: Kael Draven
- Latency: 3497ms

### Turn 3

**Player:** I approach the bartender and ask for salvage contracts.

**GM:** The GM raises a hand. 'You still need to roll STR (DC 12) for: I am Kael Draven, a void-born salvage engineer aboard the de. Roll the dice to resolve this before continuing.'

- Resolution: `forced_narrative_pushback` / `pending`
- Pending roll: `STR` DC `12` (action: `I am Kael Draven, a void-born salvage engineer abo`)
- Facts: 0
- Latency: 3504ms

### Turn 4

**Player:** I take the datapad and head straight for the derelict ship.

**GM:** The GM raises a hand. 'You still need to roll STR (DC 12) for: I am Kael Draven, a void-born salvage engineer aboard the de. Roll the dice to resolve this before continuing.'

- Resolution: `forced_narrative_pushback` / `pending`
- Pending roll: `STR` DC `12` (action: `I am Kael Draven, a void-born salvage engineer abo`)
- Facts: 0
- Latency: 3005ms

### Turn 5

**Player:** I dock with the wreck. The hull reads 'Iron Verdict' in corroded letters.

**GM:** The GM raises a hand. 'You still need to roll STR (DC 12) for: I am Kael Draven, a void-born salvage engineer aboard the de. Roll the dice to resolve this before continuing.'

- Resolution: `forced_narrative_pushback` / `pending`
- Pending roll: `STR` DC `12` (action: `I am Kael Draven, a void-born salvage engineer abo`)
- Facts: 0
- Latency: 3503ms

### Turn 6

**Player:** I move down the corridor, cutter raised, scanning for threats.

**GM:** The GM raises a hand. 'You still need to roll STR (DC 12) for: I am Kael Draven, a void-born salvage engineer aboard the de. Roll the dice to resolve this before continuing.'

- Resolution: `forced_narrative_pushback` / `pending`
- Pending roll: `STR` DC `12` (action: `I am Kael Draven, a void-born salvage engineer abo`)
- Facts: 0
- Latency: 3505ms

### Turn 7

**Player:** The creature drops from the ceiling but I sidestep cleanly and strike with my cutter.

**GM:** The GM raises a hand. 'You still need to roll STR (DC 12) for: I am Kael Draven, a void-born salvage engineer aboard the de. Roll the dice to resolve this before continuing.'

- Resolution: `forced_narrative_pushback` / `pending`
- Pending roll: `STR` DC `12` (action: `I am Kael Draven, a void-born salvage engineer abo`)
- Facts: 0
- Latency: 3505ms

### Turn 8

**Player:** I reach a sealed door with an amber seal light. I examine the symbols.

**GM:** The GM raises a hand. 'You still need to roll STR (DC 12) for: I am Kael Draven, a void-born salvage engineer aboard the de. Roll the dice to resolve this before continuing.'

- Resolution: `forced_narrative_pushback` / `pending`
- Pending roll: `STR` DC `12` (action: `I am Kael Draven, a void-born salvage engineer abo`)
- Facts: 0
- Latency: 3505ms

### Turn 9

**Player:** I grab the manual release and haul the sealed door open with all my strength.

**GM:** The GM raises a hand. 'You still need to roll STR (DC 12) for: I am Kael Draven, a void-born salvage engineer aboard the de. Roll the dice to resolve this before continuing.'

- Resolution: `forced_narrative_pushback` / `pending`
- Pending roll: `STR` DC `12` (action: `I am Kael Draven, a void-born salvage engineer abo`)
- Facts: 0
- Latency: 3504ms

### Turn 10

**Player:** Beyond the door, a sterile corridor stretches ahead. I move cautiously.

**GM:** The GM raises a hand. 'You still need to roll STR (DC 12) for: I am Kael Draven, a void-born salvage engineer aboard the de. Roll the dice to resolve this before continuing.'

- Resolution: `forced_narrative_pushback` / `pending`
- Pending roll: `STR` DC `12` (action: `I am Kael Draven, a void-born salvage engineer abo`)
- Facts: 0
- Latency: 3505ms
