# M-4: Create Universe

**Actor:** User
**Trigger:** Manage → Universes → Create

**Purpose:** Create a **playable narrative instance / timeline** inside a multiverse. Multiple stories can occur inside the same universe, and accepted changes persist there.

**Flow:**
1. Select multiverse / setting (or create → M-2)
2. Prompt: Universe name (e.g., "Northern Kingdoms - Timeline A")
3. Choose basis:
   - fresh timeline from the setting baseline
   - branch/clone from an existing universe
4. Prompt: Genre (fantasy, sci-fi, horror, modern, etc.)
5. Prompt: Tone (serious, humorous, dark, epic)
6. Prompt: Tech level (medieval, renaissance, industrial, modern, futuristic)
7. Prompt: Description
8. Create Universe node in Neo4j
9. Confirm creation

#### Implementation

**Layer 1 (Data Layer):**
```python
neo4j_list_multiverses(omniverse_id)              # For selection
neo4j_create_universe(multiverse_id, params) -> UUID
```

**Layer 3 (CLI):**
```bash
monitor manage universe create --multiverse <UUID> --name "Middle-earth" --genre fantasy
# Interactive: monitor manage universe create
```

**Validation (Pydantic):**
```python
class CreateUniverseParams(BaseModel):
    multiverse_id: UUID
    name: str = Field(min_length=1, max_length=100)
    genre: Genre
    tone: Tone
    tech_level: TechLevel
    description: str = Field(max_length=2000)

class Genre(str, Enum):
    FANTASY = "fantasy"
    SCI_FI = "sci-fi"
    HORROR = "horror"
    MODERN = "modern"
    HISTORICAL = "historical"
    SUPERHERO = "superhero"
    POST_APOCALYPTIC = "post-apocalyptic"
    OTHER = "other"

class TechLevel(str, Enum):
    PRIMITIVE = "primitive"
    MEDIEVAL = "medieval"
    RENAISSANCE = "renaissance"
    INDUSTRIAL = "industrial"
    MODERN = "modern"
    NEAR_FUTURE = "near-future"
    FUTURISTIC = "futuristic"
    MIXED = "mixed"
```

**Database Writes:**

| Database | Node/Edge | Data |
|----------|-----------|------|
| Neo4j | `:Universe` | `{id, name, genre, tone, tech_level, description, canon_level: "canon", created_at}` |
| Neo4j | `(:Multiverse)-[:CONTAINS]->(:Universe)` | Edge |

---
