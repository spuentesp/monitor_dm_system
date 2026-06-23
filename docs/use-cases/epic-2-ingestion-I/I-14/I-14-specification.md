# I-14: Spatial & Visual Ingestion (Maps)

**Actor:** User / IngestionLoop
**Trigger:** Uploading an image file with "map" in the name or designated as a map.

**Purpose:** Extract locations and their hierarchical relationships (A is inside B) from maps.

**Flow:**
1. User uploads map image.
2. `IngestionLoop` routes to `process_vision`.
3. `MapExtractorModule` (DSPy) analyzes image description/metadata.
4. Generates `Location` entities and `LOCATED_IN` axioms.
5. Populates the `spatial_scale` property (local/regional/global).

**Output:** KnowledgePack with spatial nodes and edges.

---
