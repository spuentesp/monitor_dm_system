"""
Vision and Spatial Prompts for Ingestion.

LAYER: 2 (agents)
"""

import dspy
from pydantic import BaseModel, Field


class MapLocation(BaseModel):
    """A location identified on a map."""

    name: str = Field(description="Name of the location")
    type: str = Field(description="Type of location (e.g., city, tavern, dungeon, room)")
    description: str = Field(description="Brief visual description from the map")
    contained_in: str | None = Field(None, description="Parent location name if hierarchical")
    coordinates: str | None = Field(None, description="Relative or grid coordinates if available")


class MapExtraction(BaseModel):
    """The result of map spatial analysis."""

    locations: list[MapLocation]
    scale_hint: str = Field(description="Scale of the map (e.g., local, regional, global)")
    lore_hints: list[str] = Field(description="Lore or labels found on the map")


class MapExtractorSignature(dspy.Signature):  # type: ignore[misc]
    """
    Extract spatial hierarchies and locations from a map image description or OCR metadata.
    Focus on finding 'LOCATED_IN' relationships and defining the 'spatial_scale'.
    """

    image_description = dspy.InputField(desc="Textual description of the map image or OCR labels")
    context = dspy.InputField(desc="World/System context for the map")

    extraction: MapExtraction = dspy.OutputField()


class MapExtractorModule(dspy.Module):  # type: ignore[misc]
    """DSPy module for map extraction."""

    def __init__(self) -> None:
        super().__init__()
        self.extractor = dspy.Predict(MapExtractorSignature)

    def forward(self, image_description: str, context: str = "") -> MapExtraction:
        return self.extractor(image_description=image_description, context=context).extraction  # type: ignore[no-any-return]
