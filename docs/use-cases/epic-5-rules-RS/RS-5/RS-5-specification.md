# RS-5: Card-Based Mechanics

**Actor:** User (GM/System Designer)
**Trigger:** Manage → Rules → Card System, or during play with card-based game

**Purpose:** Support RPG systems that use cards instead of or alongside dice (e.g., Savage Worlds Adventure Cards, Castle Falkenstein, Dragonlance SAGA, Through the Breach).

**Flow:**

1. **Define Card Deck:**
   - Standard playing cards (52-card, with/without jokers)
   - Tarot deck (78 cards, major/minor arcana)
   - Custom deck (game-specific cards)
   - Define card meanings/values

2. **Configure Deck Behavior:**
   - Reshuffle triggers (joker drawn, between scenes, manual)
   - Discard pile visibility
   - Card persistence (hands, holds, reserves)
   - Multiple simultaneous decks

3. **Draw Mechanics:**
   - Single draw
   - Multiple draw (best of, choose from)
   - Opposed draws
   - Hand management (hold cards for later)

4. **Card-to-Outcome Mapping:**
   - Suits → Types of success/effect
   - Values → Degree of success
   - Face cards → Special outcomes
   - Jokers → Critical effects

5. **Integration with Dice:**
   - Cards for initiative, dice for checks
   - Cards modify dice rolls
   - Hybrid resolution systems

### Implementation

**Layer 1 (Data Layer):**
```python
# Deck management
mongodb_create_deck(game_system_id, params) -> deck_id
mongodb_get_deck_state(story_id, deck_id) -> DeckState
mongodb_draw_cards(story_id, deck_id, count=1) -> list[Card]
mongodb_return_cards(story_id, deck_id, cards, to="discard")  # discard or deck
mongodb_shuffle_deck(story_id, deck_id, include_discard=True)
mongodb_peek_deck(story_id, deck_id, count=1) -> list[Card]  # GM only

# Hand management (for systems with persistent hands)
mongodb_get_hand(story_id, entity_id) -> Hand
mongodb_add_to_hand(story_id, entity_id, cards)
mongodb_play_from_hand(story_id, entity_id, card_id) -> Card
mongodb_discard_hand(story_id, entity_id)
```

**Layer 2 (Agents):**
- `Resolver.draw_cards(deck_id, count, purpose)` — Draw and interpret
- `Resolver.resolve_card_check(character_id, skill, cards)` — Apply card-based resolution
- `Orchestrator.deal_initiative_cards(participants)` — For card-based initiative
- `CanonKeeper.record_card_play(entity_id, card, outcome)` — Log card usage

**Layer 3 (CLI):**
```bash
# Deck management
monitor rules deck create --system <SYSTEM_ID> --type standard
monitor rules deck create --system <SYSTEM_ID> --type tarot
monitor rules deck create --system <SYSTEM_ID> --type custom --file ./deck.json

# In play REPL
> /draw                    # Draw one card
> /draw 3                  # Draw three cards
> /draw 3 best             # Draw three, keep best
> /draw initiative         # Deal initiative cards
> /hand                    # View current hand
> /play <CARD>             # Play from hand
> /shuffle                 # Shuffle discard back into deck
> /deck status             # Show cards remaining, discards

# Deck state queries
monitor play deck-status --story <UUID>
```

**Card System Schema:**
```python
@dataclass
class CardDeck:
    id: UUID
    game_system_id: UUID
    name: str
    deck_type: DeckType  # standard, tarot, custom

    # Card definitions
    cards: list[CardDefinition]
    include_jokers: bool = True
    joker_count: int = 2

    # Deck behavior
    reshuffle_on: list[ReshuffleTrigger]  # joker, scene_end, manual, empty
    show_discards: bool = True
    allow_hands: bool = False
    max_hand_size: int | None = None

    # Interpretation rules
    suit_meanings: dict[str, str]  # {"hearts": "social", "spades": "combat"}
    value_scale: dict[str, int]  # {"ace": 1, "king": 13} or {"ace": 14}
    special_cards: list[SpecialCard]

class DeckType(Enum):
    STANDARD = "standard"    # 52-card poker deck
    STANDARD_JOKERS = "standard_jokers"  # 54-card with jokers
    TAROT = "tarot"          # 78-card tarot
    CUSTOM = "custom"        # User-defined deck

@dataclass
class CardDefinition:
    id: str                  # "hearts_ace", "major_fool", etc.
    suit: str | None         # "hearts", "major_arcana", etc.
    value: str               # "ace", "2", "king", "fool"
    numeric_value: int       # For comparison
    display_name: str        # "Ace of Hearts"
    short_name: str          # "A♥"
    meaning: str | None      # Optional interpretation text

@dataclass
class SpecialCard:
    card_id: str             # Which card
    effect: str              # What happens when drawn
    trigger_reshuffle: bool = False

@dataclass
class DeckState:
    deck_id: UUID
    story_id: UUID

    # Current state
    draw_pile: list[str]     # Card IDs remaining (shuffled order)
    discard_pile: list[str]  # Card IDs in discard
    held_cards: dict[UUID, list[str]]  # entity_id -> held card IDs

    # Statistics
    total_draws: int
    cards_remaining: int
    jokers_drawn: int
    last_shuffled: datetime
    last_draw: datetime | None

@dataclass
class Hand:
    entity_id: UUID
    cards: list[Card]
    max_size: int | None
    drawn_this_scene: int

@dataclass
class CardDraw:
    id: UUID
    story_id: UUID
    scene_id: UUID
    turn_id: UUID | None

    deck_id: UUID
    drawn_by: UUID | None   # Entity ID
    cards: list[Card]
    draw_type: DrawType     # single, multiple_best, multiple_choose, opposed
    purpose: str            # "initiative", "skill_check", "damage", etc.

    interpretation: str     # What the draw means
    outcome: str           # The resolved result

    drawn_at: datetime

class DrawType(Enum):
    SINGLE = "single"
    MULTIPLE_BEST = "multiple_best"     # Draw N, keep highest
    MULTIPLE_CHOOSE = "multiple_choose"  # Draw N, player chooses
    OPPOSED = "opposed"                  # Two-party draw
    HAND_PLAY = "hand_play"             # Played from hand

@dataclass
class Card:
    definition: CardDefinition
    deck_id: UUID
    instance_id: str         # Unique for this specific card in deck
```

**Card Resolution:**
```python
async def resolve_card_check(
    character: Entity,
    skill: str,
    difficulty: str,
    deck_id: UUID,
    context: Context
) -> Resolution:
    # 1. Get game system's card rules
    deck = await mongodb_get_deck(deck_id)
    system = await mongodb_get_game_system(deck.game_system_id)

    # 2. Draw card(s) based on system rules
    cards = await mongodb_draw_cards(context.story_id, deck_id, count=1)

    # 3. Calculate skill modifier (if hybrid system)
    skill_value = character.skills.get(skill, 0)

    # 4. Interpret card result
    card = cards[0]
    base_value = card.numeric_value + skill_value

    # 5. Apply suit effects (if applicable)
    suit_bonus = system.card_rules.suit_effects.get(card.suit, {})

    # 6. Check for special cards
    if card.id in [sc.card_id for sc in deck.special_cards]:
        special = next(sc for sc in deck.special_cards if sc.card_id == card.id)
        if special.trigger_reshuffle:
            await mongodb_shuffle_deck(context.story_id, deck_id)

    # 7. Determine outcome
    success = base_value >= difficulty_threshold

    return CardResolution(
        card=card,
        base_value=base_value,
        modifiers=suit_bonus,
        success=success,
        description=f"Drew {card.display_name} + {skill_value} = {base_value}"
    )
```

**Card-Based Initiative (Savage Worlds style):**
```python
async def deal_initiative(
    participants: list[Entity],
    story_id: UUID,
    deck_id: UUID
) -> list[InitiativeOrder]:
    # 1. Shuffle if new round
    await mongodb_shuffle_deck(story_id, deck_id)

    # 2. Deal one card per participant
    initiative = []
    for entity in participants:
        cards = await mongodb_draw_cards(story_id, deck_id, count=1)
        card = cards[0]

        # Check for edge: Quick (deal two, keep better)
        if entity.has_edge("Quick"):
            extra = await mongodb_draw_cards(story_id, deck_id, count=1)
            if extra[0].numeric_value > card.numeric_value:
                card = extra[0]

        initiative.append(InitiativeOrder(
            entity_id=entity.id,
            card=card,
            value=card.numeric_value,
            suit_order=SUIT_ORDER[card.suit]  # spades > hearts > diamonds > clubs
        ))

    # 3. Sort by card value (suit breaks ties)
    initiative.sort(key=lambda x: (x.value, x.suit_order), reverse=True)

    # 4. Check for Joker (act any time, +2 to all rolls)
    for init in initiative:
        if init.card.value == "joker":
            init.joker_bonus = True
            init.act_when_desired = True

    return initiative
```

**Built-in Deck Types:**
```python
STANDARD_52 = CardDeck(
    name="Standard Playing Cards",
    deck_type=DeckType.STANDARD,
    cards=[
        CardDefinition(f"{suit}_{value}", suit, value, numeric_value, ...)
        for suit in ["hearts", "diamonds", "clubs", "spades"]
        for value, numeric_value in [
            ("2", 2), ("3", 3), ("4", 4), ("5", 5), ("6", 6),
            ("7", 7), ("8", 8), ("9", 9), ("10", 10),
            ("jack", 11), ("queen", 12), ("king", 13), ("ace", 14)
        ]
    ],
    include_jokers=False
)

SAVAGE_WORLDS_DECK = CardDeck(
    name="Savage Worlds Initiative Deck",
    deck_type=DeckType.STANDARD_JOKERS,
    cards=[...],  # 54 cards
    include_jokers=True,
    joker_count=2,
    reshuffle_on=[ReshuffleTrigger.JOKER],
    special_cards=[
        SpecialCard("joker_red", "Act any time, +2 to all trait rolls", trigger_reshuffle=True),
        SpecialCard("joker_black", "Act any time, +2 to all trait rolls", trigger_reshuffle=True)
    ],
    suit_meanings={
        "spades": "Fastest suit (wins ties)",
        "hearts": "Second fastest",
        "diamonds": "Third",
        "clubs": "Slowest suit"
    }
)

TAROT_78 = CardDeck(
    name="Tarot Deck",
    deck_type=DeckType.TAROT,
    cards=[
        # Major Arcana (0-21)
        CardDefinition("major_fool", "major_arcana", "fool", 0, "The Fool", "0"),
        CardDefinition("major_magician", "major_arcana", "magician", 1, "The Magician", "I"),
        # ... 20 more major arcana
        # Minor Arcana (suits: wands, cups, swords, pentacles)
        # ... 56 minor arcana cards
    ]
)
```

---
