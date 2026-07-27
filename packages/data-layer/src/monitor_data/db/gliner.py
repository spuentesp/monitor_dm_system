"""
GLiNER client for Named Entity Recognition (NER).

LAYER: 1 (data-layer)
IMPORTS FROM: External libraries only (httpx, pydantic) + monitor_data internals
CALLED BY: nlp_tools.py, ingest_tools.py (via MCP tools)

GLiNER is a lightweight NER model that can extract entities from text without
requiring large language models. This client provides a simple interface to
the GLiNER API service.

Usage:
    from monitor_data.db.gliner import extract_entities, extract_entities_batch

    entities = await extract_entities("The hero enters the tavern.")
    entities_list = await extract_entities_batch(["text a", "text b"])
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class Entity:
    """A named entity extracted from text."""

    text: str
    label: str
    start: int
    end: int
    confidence: float


class ExtractEntitiesRequest(BaseModel):
    """Request body for GLiNER API."""

    text: str
    labels: list[str] = Field(
        default_factory=lambda: [
            "person",
            "location",
            "organization",
            "product",
            "event",
            "work_of_art",
            "law",
            "language",
            "date",
            "time",
            "percent",
            "money",
            "quantity",
            "ordinal",
            "cardinal",
        ]
    )
    threshold: float = 0.5


class ExtractEntitiesBatchRequest(BaseModel):
    """Request body for batch GLiNER API."""

    texts: list[str]
    labels: list[str] = Field(
        default_factory=lambda: [
            "person",
            "location",
            "organization",
            "product",
            "event",
            "work_of_art",
            "law",
            "language",
            "date",
            "time",
            "percent",
            "money",
            "quantity",
            "ordinal",
            "cardinal",
        ]
    )
    threshold: float = 0.5


class EntityResponse(BaseModel):
    """Response from GLiNER API."""

    text: str
    entities: list[Entity]


# ---------------------------------------------------------------------------
# GLiNER Client
# ---------------------------------------------------------------------------


class GLiNERClient:
    """
    Client for the GLiNER NER service.

    The GLiNER service URL is resolved from the GLINER_URL environment
    variable, defaulting to http://localhost:8082.
    """

    def __init__(self, base_url: str | None = None):
        """
        Initialize the GLiNER client.

        Args:
            base_url: Base URL of the GLiNER API service.
                     Defaults to GLINER_URL env var or http://localhost:8082.
        """
        self.base_url = base_url or os.getenv("GLINER_URL", "http://localhost:8082").rstrip("/")
        self.timeout = 30.0

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def _post(self, endpoint: str, data: dict[str, Any]) -> dict[str, Any]:
        """Make a POST request to the GLiNER API."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=data)
            response.raise_for_status()
            return dict(response.json())

    async def extract_entities(
        self,
        text: str,
        labels: list[str] | None = None,
        threshold: float = 0.5,
    ) -> list[Entity]:
        """
        Extract named entities from text.

        Args:
            text: Input text to extract entities from.
            labels: List of entity labels to extract. If None, uses default labels.
            threshold: Confidence threshold for entity extraction (0.0 to 1.0).

        Returns:
            List of extracted entities.

        Raises:
            httpx.HTTPError: If the API request fails.
        """
        if not text or not text.strip():
            return []

        if labels is None:
            labels_str = os.getenv(
                "ENTITY_TYPES",
                "person,location,organization,product,event,work_of_art,law,language,date,time,percent,money,quantity,ordinal,cardinal",
            )
            labels = [lbl.strip() for lbl in labels_str.split(",") if lbl.strip()]

        request_data = {
            "text": text,
            "labels": labels,
            "threshold": threshold,
        }

        try:
            response = await self._post("predict", request_data)
            entities = [
                Entity(
                    text=e.get("text", ""),
                    label=e.get("label", ""),
                    start=e.get("start", 0),
                    end=e.get("end", 0),
                    confidence=e.get("confidence", 0.0),
                )
                for e in response.get("entities", [])
            ]
            return entities
        except httpx.HTTPError as e:
            logger.error(f"GLiNER API error: {e}")
            return []

    async def extract_entities_batch(
        self,
        texts: list[str],
        labels: list[str] | None = None,
        threshold: float = 0.5,
    ) -> list[list[Entity]]:
        """
        Extract named entities from multiple texts in batch.

        Args:
            texts: List of input texts to extract entities from.
            labels: List of entity labels to extract. If None, uses default labels.
            threshold: Confidence threshold for entity extraction (0.0 to 1.0).

        Returns:
            List of lists of extracted entities (one list per input text).

        Raises:
            httpx.HTTPError: If the API request fails.
        """
        if not texts:
            return [[]]

        texts = [t for t in texts if t and t.strip()]
        if not texts:
            return [[]]

        if labels is None:
            labels_str = os.getenv(
                "ENTITY_TYPES",
                "person,location,organization,product,event,work_of_art,law,language,date,time,percent,money,quantity,ordinal,cardinal",
            )
            labels = [lbl.strip() for lbl in labels_str.split(",") if lbl.strip()]

        request_data = {
            "texts": texts,
            "labels": labels,
            "threshold": threshold,
        }

        try:
            response = await self._post("predict_batch", request_data)
            entities_list = [
                [
                    Entity(
                        text=e.get("text", ""),
                        label=e.get("label", ""),
                        start=e.get("start", 0),
                        end=e.get("end", 0),
                        confidence=e.get("confidence", 0.0),
                    )
                    for e in result.get("entities", [])
                ]
                for result in response.get("results", [])
            ]
            return entities_list
        except httpx.HTTPError as e:
            logger.error(f"GLiNER batch API error: {e}")
            return [[] for _ in texts]

    async def health_check(self) -> bool:
        """
        Check if the GLiNER service is healthy.

        Returns:
            True if the service is healthy, False otherwise.
        """
        try:
            url = f"{self.base_url}/health"
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"GLiNER health check failed: {e}")
            return False


# ---------------------------------------------------------------------------
# Global client instance
# ---------------------------------------------------------------------------

_gliner_client: GLiNERClient | None = None


def get_gliner_client() -> GLiNERClient:
    """
    Get or create the global GLiNER client instance.

    Returns:
        The global GLiNER client.
    """
    global _gliner_client
    if _gliner_client is None:
        _gliner_client = GLiNERClient()
    return _gliner_client


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


async def extract_entities(
    text: str,
    labels: list[str] | None = None,
    threshold: float = 0.5,
) -> list[Entity]:
    """
    Extract named entities from text using the global GLiNER client.

    Args:
        text: Input text to extract entities from.
        labels: List of entity labels to extract. If None, uses default labels.
        threshold: Confidence threshold for entity extraction (0.0 to 1.0).

    Returns:
        List of extracted entities.
    """
    client = get_gliner_client()
    return await client.extract_entities(text, labels, threshold)


async def extract_entities_batch(
    texts: list[str],
    labels: list[str] | None = None,
    threshold: float = 0.5,
) -> list[list[Entity]]:
    """
    Extract named entities from multiple texts in batch.

    Args:
        texts: List of input texts to extract entities from.
        labels: List of entity labels to extract. If None, uses default labels.
        threshold: Confidence threshold for entity extraction (0.0 to 1.0).

    Returns:
        List of lists of extracted entities (one list per input text).
    """
    client = get_gliner_client()
    return await client.extract_entities_batch(texts, labels, threshold)
