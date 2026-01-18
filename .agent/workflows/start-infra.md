---
description: Start Docker infrastructure services
---

# Start Infrastructure

Starts all database services required for MONITOR development.

## Prerequisites

- Docker and Docker Compose installed
- `.env` file in `infra/` directory (copy from `.env.example` if missing)

## Steps

1. Navigate to the infrastructure directory

2. Check if `.env` file exists, if not, copy from template:
   ```bash
   cd infra
   if [ ! -f .env ]; then cp .env.example .env; echo "Created .env from template - please edit with your passwords"; fi
   ```

// turbo
3. Start all Docker services:
   ```bash
   docker compose up -d
   ```

// turbo
4. Verify all services are running:
   ```bash
   docker compose ps
   ```

5. Wait for services to be fully healthy (may take 30-60 seconds):
   ```bash
   docker compose logs -f
   ```
   Press `Ctrl+C` when you see "Started" messages from all services.

## Expected Services

After successful startup, you should see:
- **Neo4j**: `http://localhost:7474` (browser), `bolt://localhost:7687` (driver)
- **MongoDB**: `mongodb://localhost:27017`
- **Qdrant**: `http://localhost:6333`
- **MinIO**: `http://localhost:9000` (API), `http://localhost:9001` (console)
- **OpenSearch**: `http://localhost:9200` (optional)

## Troubleshooting

If services fail to start:
- Check Docker is running: `docker ps`
- Check logs: `docker compose logs <service-name>`
- Ensure ports are not already in use
- Verify `.env` file has all required variables

## Next Steps

After infrastructure is running:
1. Initialize databases (see `infra/README.md`)
2. Run tests: `/run-tests`
3. Start development work
