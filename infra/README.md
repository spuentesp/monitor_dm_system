# MONITOR Infrastructure

*Docker-based infrastructure for the MONITOR system.*

---

## Overview

This directory contains the Docker Compose configuration for running the complete MONITOR database stack:

1. **Neo4j** - Canonical graph database (truth layer)
2. **MongoDB** - Narrative documents and proposals
3. **Qdrant** - Vector database for semantic search
4. **MinIO** - Binary object storage (PDFs, images)
5. **OpenSearch** - Full-text search (optional)

---

## Quick Start

### 1. Copy Environment Variables

```bash
cp .env.example .env
```

Edit `.env` with your passwords and configuration.

### 2. Start All Services

```bash
docker compose up -d
```

### 3. Verify Services

```bash
docker compose ps
```

All services should show `Up` status.

### 4. Access UIs

- **Neo4j Browser**: http://localhost:7474
  - Username: `neo4j`
  - Password: `<your NEO4J_PASSWORD from .env>`

- **MinIO Console**: http://localhost:9001
  - Username: `monitor`
  - Password: `<your MINIO_PASSWORD from .env>`

- **OpenSearch Dashboards**: http://localhost:5601
  - Username: `admin`
  - Password: `<your OPENSEARCH_PASSWORD from .env>`

---

## Service Details

### Neo4j (Canonical Graph)

**Ports:**
- `7474`: HTTP (Browser UI)
- `7687`: Bolt (Database connection)

**Volumes:**
- `./neo4j/data`: Database files
- `./neo4j/logs`: Log files
- `./neo4j/import`: CSV import directory
- `./neo4j/plugins`: APOC and GDS plugins

**Configuration:**
- Heap: 512MB initial, 2GB max
- Page cache: 1GB
- Plugins: APOC, Graph Data Science

**Connection String:**
```
bolt://localhost:7687
```

---

### MongoDB (Narrative Layer)

**Ports:**
- `27017`: MongoDB server

**Volumes:**
- `./mongodb/data`: Database files
- `./mongodb/configdb`: Configuration
- `./mongodb/init`: Initialization scripts

**Connection String:**
```
mongodb://monitor:<password>@localhost:27017/monitor
```

**Collections:**
- `scenes` - Narrative scenes
- `turns` - Turn-by-turn logs
- `proposed_changes` - Canonization staging
- `resolutions` - Dice/rules outcomes
- `character_memories` - NPC/PC memories
- `documents` - Ingested source documents
- `snippets` - Document chunks
- `character_sheets` - Character sheets

---

### Qdrant (Vector Database)

**Ports:**
- `6333`: REST API
- `6334`: gRPC

**Volumes:**
- `./qdrant/storage`: Vector indices

**REST API:**
```
http://localhost:6333
```

**Collections:**
- `scene_chunks` - Scene summaries and turn embeddings
- `memory_chunks` - Character memory embeddings
- `snippet_chunks` - Document snippet embeddings

---

### MinIO (Object Storage)

**Ports:**
- `9000`: S3-compatible API
- `9001`: Web Console

**Volumes:**
- `./minio/data`: Object storage

**Default Buckets:**
- `monitor-documents` - Uploaded PDFs/manuals
- `monitor-images` - Character art, maps
- `monitor-exports` - Backup exports

**S3 Endpoint:**
```
http://localhost:9000
```

---

### OpenSearch (Full-Text Search)

**Ports:**
- `9200`: REST API
- `9600`: Performance Analyzer
- `5601`: Dashboards UI

**Volumes:**
- `./opensearch/data`: Index data

**REST API:**
```
https://localhost:9200
```

**Indices:**
- `monitor-scenes` - Scene full-text search
- `monitor-facts` - Fact full-text search
- `monitor-snippets` - Document snippet search

---

## Initialization

### Neo4j Schema

Run these Cypher commands in Neo4j Browser to create constraints:

```cypher
CREATE CONSTRAINT entity_concreta_id IF NOT EXISTS
FOR (n:EntityInstance) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT entity_axiomatica_id IF NOT EXISTS
FOR (n:EntityArchetype) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT universe_id IF NOT EXISTS
FOR (n:Universe) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT story_id IF NOT EXISTS
FOR (n:Story) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT fact_id IF NOT EXISTS
FOR (n:Fact) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT event_id IF NOT EXISTS
FOR (n:Event) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT source_id IF NOT EXISTS
FOR (n:Source) REQUIRE n.id IS UNIQUE;

CREATE CONSTRAINT axiom_id IF NOT EXISTS
FOR (n:Axiom) REQUIRE n.id IS UNIQUE;
```

Create indices:

```cypher
CREATE INDEX entity_universe IF NOT EXISTS
FOR (n:EntityInstance) ON (n.universe_id);

CREATE INDEX fact_universe IF NOT EXISTS
FOR (n:Fact) ON (n.universe_id);

CREATE INDEX fact_canon_level IF NOT EXISTS
FOR (n:Fact) ON (n.canon_level);

CREATE INDEX story_universe IF NOT EXISTS
FOR (n:Story) ON (n.universe_id);
```

---

### MongoDB Initialization

Create a file at `./mongodb/init/01-init.js`:

```javascript
db = db.getSiblingDB('monitor');

// Create collections with validation
db.createCollection('scenes', {
  validator: {
    $jsonSchema: {
      bsonType: 'object',
      required: ['scene_id', 'story_id', 'universe_id', 'title', 'status'],
      properties: {
        scene_id: { bsonType: 'string' },
        story_id: { bsonType: 'string' },
        universe_id: { bsonType: 'string' },
        title: { bsonType: 'string' },
        status: { enum: ['active', 'finalizing', 'completed'] }
      }
    }
  }
});

// Create indices
db.scenes.createIndex({ scene_id: 1 }, { unique: true });
db.scenes.createIndex({ story_id: 1, order: 1 });
db.scenes.createIndex({ status: 1 });

db.createCollection('proposed_changes');
db.proposed_changes.createIndex({ proposal_id: 1 }, { unique: true });
db.proposed_changes.createIndex({ scene_id: 1, status: 1 });
db.proposed_changes.createIndex({ status: 1 });

db.createCollection('character_memories');
db.character_memories.createIndex({ memory_id: 1 }, { unique: true });
db.character_memories.createIndex({ entity_id: 1, importance: -1 });

db.createCollection('documents');
db.documents.createIndex({ doc_id: 1 }, { unique: true });
db.documents.createIndex({ source_id: 1 });

db.createCollection('snippets');
db.snippets.createIndex({ snippet_id: 1 }, { unique: true });
db.snippets.createIndex({ doc_id: 1, chunk_index: 1 });
```

---

### Qdrant Collections

Create collections via REST API:

```bash
# Scene chunks
curl -X PUT 'http://localhost:6333/collections/scene_chunks' \
  -H 'Content-Type: application/json' \
  -d '{
    "vectors": {
      "size": 1536,
      "distance": "Cosine"
    }
  }'

# Memory chunks
curl -X PUT 'http://localhost:6333/collections/memory_chunks' \
  -H 'Content-Type: application/json' \
  -d '{
    "vectors": {
      "size": 1536,
      "distance": "Cosine"
    }
  }'

# Snippet chunks
curl -X PUT 'http://localhost:6333/collections/snippet_chunks' \
  -H 'Content-Type: application/json' \
  -d '{
    "vectors": {
      "size": 1536,
      "distance": "Cosine"
    }
  }'

# Create payload indices
curl -X PUT 'http://localhost:6333/collections/scene_chunks/index' \
  -H 'Content-Type: application/json' \
  -d '{
    "field_name": "universe_id",
    "field_schema": "keyword"
  }'
```

---

### MinIO Buckets

Create buckets via MinIO Console or mc client:

```bash
# Install MinIO client
wget https://dl.min.io/client/mc/release/linux-amd64/mc
chmod +x mc
sudo mv mc /usr/local/bin/

# Configure
mc alias set monitor http://localhost:9000 monitor <MINIO_PASSWORD>

# Create buckets
mc mb monitor/monitor-documents
mc mb monitor/monitor-images
mc mb monitor/monitor-exports

# Set policies
mc policy set download monitor/monitor-images
mc policy set private monitor/monitor-documents
```

---

## Maintenance

### Backup

#### Neo4j

```bash
docker compose exec neo4j neo4j-admin database dump neo4j --to-path=/var/lib/neo4j/data/dumps
```

#### MongoDB

```bash
docker compose exec mongodb mongodump --uri="mongodb://monitor:<password>@localhost:27017/monitor" --out=/data/backup
```

#### Qdrant

```bash
docker compose exec qdrant tar -czf /qdrant/storage/backup.tar.gz /qdrant/storage
```

### Restore

#### Neo4j

```bash
docker compose exec neo4j neo4j-admin database load neo4j --from-path=/var/lib/neo4j/data/dumps
```

#### MongoDB

```bash
docker compose exec mongodb mongorestore --uri="mongodb://monitor:<password>@localhost:27017/monitor" /data/backup
```

---

## Monitoring

### Health Checks

```bash
# Neo4j
curl http://localhost:7474/

# MongoDB
docker compose exec mongodb mongosh --eval "db.adminCommand('ping')"

# Qdrant
curl http://localhost:6333/healthz

# MinIO
curl http://localhost:9000/minio/health/live

# OpenSearch
curl -k https://localhost:9200/_cluster/health
```

### Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f neo4j
docker compose logs -f mongodb
docker compose logs -f qdrant
```

### Resource Usage

```bash
docker compose stats
```

---

## Troubleshooting

### Neo4j Won't Start

Check logs:
```bash
docker compose logs neo4j
```

Common issues:
- APOC plugin mismatch → ensure plugin version matches Neo4j version
- Memory limits → increase heap/pagecache in .env

### MongoDB Connection Refused

Check authentication:
```bash
docker compose exec mongodb mongosh -u monitor -p <password>
```

### Qdrant Collection Not Found

List collections:
```bash
curl http://localhost:6333/collections
```

Create if missing (see Initialization section above).

### MinIO Access Denied

Check credentials in .env match what you're using.

Reset admin password:
```bash
docker compose down
rm -rf ./minio/data
docker compose up -d minio
```

---

## Performance Tuning

### Neo4j

Edit `docker-compose.yml`:

```yaml
environment:
  - NEO4J_dbms_memory_heap_initial__size=1G
  - NEO4J_dbms_memory_heap_max__size=4G
  - NEO4J_dbms_memory_pagecache_size=2G
```

### MongoDB

Add to `docker-compose.yml`:

```yaml
command: --wiredTigerCacheSizeGB=2
```

### Qdrant

For large datasets, tune HNSW parameters:

```bash
curl -X PATCH 'http://localhost:6333/collections/scene_chunks' \
  -H 'Content-Type: application/json' \
  -d '{
    "hnsw_config": {
      "m": 32,
      "ef_construct": 200
    }
  }'
```

---

## Security

### Production Checklist

- [ ] Change all default passwords in `.env`
- [ ] Enable TLS for all services
- [ ] Configure firewall rules (only expose necessary ports)
- [ ] Enable authentication on all services
- [ ] Set up backup rotation
- [ ] Configure log aggregation
- [ ] Enable audit logging
- [ ] Set up monitoring/alerting
- [ ] Review and harden Docker security settings

### Network Isolation

In production, use separate networks:

```yaml
networks:
  frontend:
    internal: false
  backend:
    internal: true
```

Only expose MCP server to frontend network.

---

## References

- [DATABASE_INTEGRATION.md](../docs/architecture/DATABASE_INTEGRATION.md) - Data layer architecture
- [DATA_LAYER_API.md](../docs/architecture/DATA_LAYER_API.md) - API specifications
- [MCP_TRANSPORT.md](../docs/architecture/MCP_TRANSPORT.md) - MCP tool definitions
- [ONTOLOGY.md](../docs/ontology/ONTOLOGY.md) - Data model specification
