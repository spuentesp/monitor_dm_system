---
description: "Details the docker-compose environment."
tags: [infrastructure, docker, databases]
layer: 0
---

# Database Cluster

MONITOR relies heavily on containerized infrastructure for local development and eventual cloud deployment.

## The Docker Compose Stack
Running `./dev.sh` spins up `infra/docker-compose.yml`, which includes:
- **Neo4j** (Port 7687)
- **MongoDB** (Port 27017)
- **Qdrant** (Port 6333)
- **MinIO** (Port 9000, 9001)

## Environment Variables
The `.env` file (copied from `env.example`) dictates credentials for these databases. The Data Layer dynamically loads these upon initialization.

## See Also
- [Infrastructure Index](./_index.md)
- [Layer 1: Data](../2_architecture/layer1_data.md)
