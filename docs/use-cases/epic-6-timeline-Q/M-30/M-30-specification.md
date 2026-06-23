# M-30: Manage World Time

**Actor:** User or Orchestrator
**Trigger:** Manage → Universe → Time, or automatic during play

**Purpose:** Track in-world time, calendars, and time-dependent events.

**Flow:**
1. Define or select calendar system:
   - Standard (Earth-like: days, weeks, months, years)
   - Custom (e.g., "28 days per month, 10 months per year")
   - Fantasy (e.g., "The Reckoning of Kings", custom month names)
2. Set current world date/time for universe
3. During play:
   - Time advances per scene (short rest = hours, long rest = days)
   - Travel advances time based on distance
   - Orchestrator prompts: "How much time passes?"
4. Time-dependent effects:
   - Deadlines ("The ritual completes in 3 days")
   - Aging (characters grow older)
   - Seasonal changes (winter arrives, harvest season)
   - Scheduled events (festivals, eclipses)
5. Query time-relative events ("What happened last month?")

**Output:** World clock, calendar display, time-relative event queries

#### Implementation

**Layer 1 (Data Layer):**
```python
# Calendar system definition
neo4j_create_calendar(universe_id, params) -> calendar_id
neo4j_get_calendar(universe_id) -> Calendar
neo4j_update_world_time(universe_id, new_time)

# Time-dependent facts and events
neo4j_create_event(params, scheduled_time=...)  # Future events
neo4j_list_events(universe_id, time_range=...)  # Query by time
neo4j_list_deadlines(universe_id, before=...)   # Upcoming deadlines
```

**Layer 2 (Agents):**
- `Orchestrator.advance_time(duration, reason)` — Move world clock forward
- `ContextAssembly.get_time_context(universe_id)` — Current date, upcoming events
- `Narrator.describe_time_passage(duration, events)` — Narrate what happens

**Layer 3 (CLI):**
```bash
monitor manage universe time --universe <UUID>              # View current time
monitor manage universe time --universe <UUID> --set "Day 15 of Harvest, Year 342"
monitor manage universe time --universe <UUID> --advance "3 days"
monitor manage universe calendar --universe <UUID>         # Define calendar
```

**Calendar Schema:**
```python
@dataclass
class Calendar:
    id: UUID
    universe_id: UUID
    name: str                          # "The Imperial Calendar"

    hours_per_day: int = 24
    days_per_week: int = 7
    weeks_per_month: int = 4
    months_per_year: int = 12

    day_names: list[str] | None        # ["Moonday", "Tirsday", ...]
    month_names: list[str] | None      # ["Deepwinter", "Thawing", ...]

    epoch_name: str = "Year"           # "Year", "Age", "Cycle"
    current_date: WorldDate

@dataclass
class WorldDate:
    year: int
    month: int
    day: int
    hour: int = 0

    def advance(self, days: int = 0, hours: int = 0) -> "WorldDate": ...
    def format(self, calendar: Calendar) -> str: ...

@dataclass
class Deadline:
    id: UUID
    description: str
    target_date: WorldDate
    entity_ids: list[UUID]             # Who/what is affected
    consequence: str                   # What happens if missed
    status: DeadlineStatus             # pending, met, missed
```

**Time Passage During Play:**
```python
class TimeDuration(Enum):
    MOMENT = "moment"        # Seconds to minutes
    SHORT_REST = "short"     # ~1 hour
    LONG_REST = "long"       # 8 hours / overnight
    DAY = "day"              # 24 hours
    TRAVEL_DAY = "travel"    # Day of travel
    WEEK = "week"
    MONTH = "month"
    SEASON = "season"        # ~3 months
    YEAR = "year"

async def advance_time(universe_id: UUID, duration: TimeDuration, reason: str):
    # 1. Calculate new world date
    calendar = await neo4j_get_calendar(universe_id)
    new_date = calendar.current_date.advance(duration)

    # 2. Check for triggered events
    triggered = await neo4j_list_events(universe_id,
        after=calendar.current_date, before=new_date)

    # 3. Check for missed deadlines
    missed = await neo4j_list_deadlines(universe_id, before=new_date, status="pending")

    # 4. Update world time
    await neo4j_update_world_time(universe_id, new_date)

    # 5. Generate narration if events occurred
    if triggered or missed:
        return await narrator.describe_time_passage(duration, triggered, missed)
```

---
