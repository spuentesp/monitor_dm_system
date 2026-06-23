# ST-7: Scheduled World Events

**Actor:** System (automatic) or GM (manual trigger)
**Trigger:** Time advancement (M-30) reaches event date

**Purpose:** Trigger pre-planned events when world time reaches their scheduled date.

**Flow:**

1. **Define Scheduled Event:**
   - Event description
   - Trigger date/time (world time)
   - Scope: Universe, region, location
   - Visibility: Public, faction-specific, secret
   - Consequences if not addressed

2. **Event Monitoring:**
   - System tracks all scheduled events
   - When time advances, check for triggered events
   - Events can trigger other events (cascades)

3. **Event Firing:**
   - Create notification for GM
   - Optionally auto-generate narration
   - Update world state (facts, entity states)
   - Advance related plot threads

4. **Event Types:**
   - **Fixed:** Happens at exact time regardless
   - **Conditional:** Happens if conditions met
   - **Recurring:** Repeats on schedule
   - **Deadline:** Something bad if not addressed by date

### Implementation

**Layer 1 (Data Layer):**
```python
# Event management
neo4j_create_scheduled_event(universe_id, params) -> event_id
neo4j_list_scheduled_events(universe_id, before=date) -> list[ScheduledEvent]
neo4j_get_scheduled_event(event_id) -> ScheduledEvent
neo4j_update_scheduled_event(event_id, params)
neo4j_fire_scheduled_event(event_id) -> list[Consequence]

# During time advancement
async def check_scheduled_events(universe_id, old_date, new_date):
    events = await neo4j_list_scheduled_events(
        universe_id,
        after=old_date,
        before=new_date
    )
    for event in events:
        if event.should_fire(new_date):
            await fire_event(event)
```

**Layer 2 (Agents):**
- `Orchestrator.schedule_event(params)` — Create scheduled event
- `Orchestrator.check_scheduled_events(time_delta)` — Check during time advance
- `Narrator.describe_event_occurrence(event)` — Generate narration
- `CanonKeeper.apply_event_consequences(event)` — Update world state

**Layer 3 (CLI):**
```bash
monitor story event schedule --universe <UUID> --date "Year 1, Month 3, Day 15"
monitor story event list --universe <UUID>
monitor story event trigger <EVENT_ID>  # Manual trigger
```

**Scheduled Event Schema:**
```python
@dataclass
class ScheduledEvent:
    id: UUID
    universe_id: UUID
    story_id: UUID | None  # If story-specific

    title: str
    description: str

    trigger_date: WorldDate
    event_type: EventType  # fixed, conditional, recurring, deadline

    scope: EventScope  # universe, region, location
    scope_id: UUID | None  # Region/location ID

    visibility: Visibility  # public, faction, secret
    visible_to: list[UUID]  # Faction/entity IDs if not public

    conditions: list[EventCondition] | None  # For conditional events
    recurrence: RecurrenceRule | None  # For recurring events

    consequences: list[EventConsequence]
    missed_consequences: list[EventConsequence] | None  # For deadlines

    status: EventStatus  # scheduled, fired, cancelled, missed
    fired_at: WorldDate | None

class EventType(Enum):
    FIXED = "fixed"
    CONDITIONAL = "conditional"
    RECURRING = "recurring"
    DEADLINE = "deadline"

@dataclass
class EventConsequence:
    type: ConsequenceType  # fact, state_change, entity_spawn, notification
    content: dict
    automatic: bool  # Apply automatically or require GM approval

@dataclass
class RecurrenceRule:
    interval: str  # "daily", "weekly", "monthly", "yearly"
    count: int | None  # Number of occurrences, None = infinite
    until: WorldDate | None  # End date
```

**Example Scheduled Events:**

```python
# Festival (recurring)
ScheduledEvent(
    title="Harvest Festival",
    trigger_date=WorldDate(month=9, day=21),
    event_type=EventType.RECURRING,
    recurrence=RecurrenceRule(interval="yearly"),
    consequences=[
        EventConsequence(type="fact", content={"statement": "Harvest Festival begins"}),
        EventConsequence(type="state_change", content={"location_id": city_id, "tag": "celebrating"})
    ]
)

# Deadline
ScheduledEvent(
    title="Villain's Ritual Completes",
    trigger_date=WorldDate(year=1, month=6, day=1),
    event_type=EventType.DEADLINE,
    consequences=[
        EventConsequence(type="fact", content={"statement": "The dark ritual is complete"})
    ],
    missed_consequences=[
        EventConsequence(type="fact", content={"statement": "Darkness spreads across the land"})
    ]
)
```

---
