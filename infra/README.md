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
# From the repo root:
cp env.example .env
# From this infra/ directory:
cp .env.example .env
```

Edit each `.env` with your passwords and configuration.

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

**Collections** (created lazily by the data-layer on first use; see
`packages/data-layer/src/monitor_data/db/qdrant.py:COLLECTION_CONFIGS`):
- `scenes` - Scene summaries and turn embeddings
- `memories` - Character memory embeddings
- `snippets` - Document snippet embeddings
- `entities` - Entity embeddings
- `knowledge` - Knowledge-pack embeddings

---

### MinIO (Object Storage)

**Ports:**
- `9000`: S3-compatible API
- `9001`: Web Console

**Volumes:**
- `./minio/data`: Object storage

**Default Bucket:**
- `monitor` - All uploads land here (created lazily by `MinIOClient.ensure_bucket()` on first upload).

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

## First Run

Schema bootstrap is **automatic on first DB connect** — no manual Cypher,
MongoDB init scripts, Qdrant REST calls, or MinIO bucket creation is
required. After `make infra-up` (or `docker compose up -d`), run:

```bash
# From the repo root
uv run python -m monitor_cli.main init
```

The wizard prompts for an LLM provider, writes API keys to `.env.tokens`
(mode `0o600`), seeds the `llm_providers` Postgres table with the right
role defaults, and prints a green/red health panel at the end. To verify
afterwards:

```bash
uv run python -m monitor_cli.main doctor --json
```

See the top-level [README.md](../README.md) for the full walkthrough.

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
curl -X PATCH 'http://localhost:6333/collections/scenes' \
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

- [layer1_data.md](../docs/2_architecture/layer1_data.md) - Data layer architecture and API specifications
- [mcp_transport.md](../docs/2_architecture/mcp_transport.md) - MCP tool definitions
- [Ontology](../docs/4_ontology/_index.md) - Data model specification
