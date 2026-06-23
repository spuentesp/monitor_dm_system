"""
World Building Library — manages per-system lore repositories.

This utility ensures that files and URLs ingested for world building
are categorized by their associated game system or multiverse.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from monitor_data.db.mongodb import get_mongodb_client

logger = logging.getLogger(__name__)


class WorldLibrary:
    """
    Manages structured lore metadata for a Multiverse/Universe.
    """

    def __init__(self) -> None:
        self._mongodb = get_mongodb_client()
        self._collection = self._mongodb.get_collection("world_library")

    async def add_source(
        self,
        multiverse_id: UUID,
        source_type: str,  # "url" or "file"
        uri: str,
        system_name: str = "generic",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Record a new source in the library for a specific system.
        """
        import uuid
        import anyio
        from datetime import datetime, timezone

        entry_id = str(uuid.uuid4())
        doc = {
            "entry_id": entry_id,
            "multiverse_id": str(multiverse_id),
            "system_name": system_name,
            "source_type": source_type,
            "uri": uri,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc),
        }

        await anyio.to_thread.run_sync(lambda: self._collection.insert_one(doc))
        logger.info(f"Added {source_type} to library [{system_name}]: {uri}")
        return entry_id

    async def list_by_system(self, system_name: str) -> List[Dict[str, Any]]:
        """
        List all lore sources registered for a specific game system.
        """
        import anyio

        def _list() -> List[Dict[str, Any]]:
            cursor = self._collection.find({"system_name": system_name})
            return [dict(d) for d in cursor]

        return await anyio.to_thread.run_sync(_list)
