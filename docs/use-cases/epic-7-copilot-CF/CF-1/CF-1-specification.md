# CF-1: Record or Capture Assisted Session

**Actor:** Human GM
**Trigger:** Co-Pilot → Start Recording / Capture Session

**Purpose:** Capture a human-led session in real time so it can be segmented into story/scenes, reviewed, and later canonized without replacing the GM's authority.

**Flow:**
1. GM starts assisted capture mode for an existing or new story
2. System enters passive observation:
   - GM types notes into the assistant chat, or
   - the table session is recorded/transcribed for later ingestion
3. System parses and categorizes incoming material (action, dialogue, lore, decision, consequence)
4. System creates or updates draft story/scene documents in MongoDB
5. For each significant event:
   - append turns to the draft scene transcript
   - create `ProposedChange` items tagged with timestamp, participants, and location
6. GM can annotate in real time ("this is important", "NPC name: Varys", "this should not be canon")
7. Session ends → scene drafts and pending proposals are ready for review
8. → CF-2 (Generate recap) or → CF-8 (Review CanonKeeper queue)

**Input Modes:**
- Live text/chat notes entered during play
- Uploaded or pasted transcript after play
- Microphone/audio capture for GM Assistant session recording
- Hybrid notes + post-session cleanup

**Output:** Draft story/scene transcript with pending proposals grouped for GM review

### Implementation

**Layer 1 (Data Layer):**
```python
mongodb_create_scene(story_id, params, status="draft")   # Draft scene shell
mongodb_append_turn(scene_id, turn)                       # Transcript/event stream
mongodb_create_proposal(scene_id, type, content)          # Pending canon change
mongodb_update_scene(scene_id, {"status": "review"})    # Ready for GM/CanonKeeper review
```

**Layer 2 (Agents):**
- `Orchestrator.start_recording_session(story_id)` — Initialize assisted capture mode
- `Narrator.parse_gm_input(text, context)` — Categorize GM narration/chat notes
- `Narrator.segment_session_into_scenes(transcript)` — Split a session into scene units
- `Indexer.extract_entities_realtime(text)` — Detect new NPCs, locations, and terms

**Layer 3 (CLI):**
```bash
monitor copilot record --story <UUID>
# Interactive mode with live input
```

**State:**
```python
class RecordingState(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    FINALIZING = "finalizing"
```

---
