"""
MongoDB tools for Entity Template operations.

LAYER: 1 (data-layer)
Authority: MongoDB
Use Case: DL-17
"""

import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from monitor_data.db.mongodb import get_mongodb_client
from monitor_data.schemas.entity_templates import (
    EntityTemplateCreate,
    EntityTemplateFilter,
    EntityTemplateListResponse,
    EntityTemplateResponse,
    EntityTemplateUpdate,
)

logger = logging.getLogger(__name__)

# =============================================================================
# ENTITY TEMPLATE OPERATIONS (DL-17)
# =============================================================================


def mongodb_create_entity_template(params: EntityTemplateCreate) -> EntityTemplateResponse:
    """Create a new entity template in MongoDB."""
    client = get_mongodb_client()
    collection = client.get_collection("entity_templates")

    template_id = uuid4()
    now = datetime.now(UTC)

    template_doc = params.model_dump()
    template_doc["template_id"] = str(template_id)
    template_doc["universe_id"] = str(params.universe_id)
    if params.parent_template_id:
        template_doc["parent_template_id"] = str(params.parent_template_id)

    # Handle UUIDs in variable properties
    for prop in template_doc.get("variable_properties", []):
        if prop.get("table_id"):
            prop["table_id"] = str(prop["table_id"])

    template_doc["created_at"] = now
    template_doc["updated_at"] = now
    template_doc["usage_count"] = 0

    collection.insert_one(template_doc)

    res = mongodb_get_entity_template(template_id)
    assert res
    return res


def mongodb_get_entity_template(template_id: UUID) -> EntityTemplateResponse | None:
    """Retrieve an entity template by ID."""
    client = get_mongodb_client()
    collection = client.get_collection("entity_templates")

    doc = collection.find_one({"template_id": str(template_id)})
    if not doc:
        return None

    return EntityTemplateResponse(**doc)


def mongodb_list_entity_templates(filters: EntityTemplateFilter) -> EntityTemplateListResponse:
    """List entity templates with filtering."""
    client = get_mongodb_client()
    collection = client.get_collection("entity_templates")

    query = {}
    if filters.universe_id:
        query["universe_id"] = str(filters.universe_id)
    if filters.entity_type:
        query["entity_type"] = filters.entity_type.value
    if filters.parent_template_id:
        query["parent_template_id"] = str(filters.parent_template_id)

    total = collection.count_documents(query)
    cursor = collection.find(query).skip(filters.offset).limit(filters.limit)

    templates = [EntityTemplateResponse(**doc) for doc in cursor]

    return EntityTemplateListResponse(templates=templates, total=total, limit=filters.limit, offset=filters.offset)


def mongodb_update_entity_template(template_id: UUID, params: EntityTemplateUpdate) -> EntityTemplateResponse:
    """Update an existing entity template."""
    client = get_mongodb_client()
    collection = client.get_collection("entity_templates")

    update_data = params.model_dump(exclude_unset=True)
    if not update_data:
        res = mongodb_get_entity_template(template_id)
    assert res
    return res

    update_data["updated_at"] = datetime.now(UTC)

    # Handle UUIDs in variable properties if updated
    if "variable_properties" in update_data:
        for prop in update_data["variable_properties"]:
            if prop.get("table_id"):
                prop["table_id"] = str(prop["table_id"])

    result = collection.update_one({"template_id": str(template_id)}, {"$set": update_data})
    if result.matched_count == 0:
        raise ValueError(f"Entity template {template_id} not found")

    return mongodb_get_entity_template(template_id)


def mongodb_delete_entity_template(template_id: UUID) -> bool:
    """Delete an entity template."""
    client = get_mongodb_client()
    collection = client.get_collection("entity_templates")

    result = collection.delete_one({"template_id": str(template_id)})
    return result.deleted_count > 0


def mongodb_increment_template_usage(template_id: UUID) -> None:
    """Increment the usage count of a template."""
    client = get_mongodb_client()
    collection = client.get_collection("entity_templates")

    collection.update_one({"template_id": str(template_id)}, {"$inc": {"usage_count": 1}})
