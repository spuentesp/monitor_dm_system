# SYS-1: Start Application — Behavior Specification

> Verifies that actual implementation matches the behavior defined in SYS-1-specification.md

## Scenario 1: Application Startup

**Given** the user runs the `monitor` command
**When** the application starts
**Then** configuration is loaded, DB connections are initialized, and services are verified

### AC-1: Configuration Loading
- [x] Configuration is loaded from environment/config file
- [x] Required environment variables are validated
- [x] Missing required config raises error

### AC-2: Database Connections
- [x] Neo4j connection is established
- [x] MongoDB connection is established
- [x] Qdrant connection is established (if used)

### AC-3: Service Health Verification
- [x] All services are checked for connectivity
- [x] Unhealthy services are reported
- [x] Application can proceed with degraded services (optional)

### AC-4: Main Menu Display
- [x] Main menu is displayed after successful startup
- [x] All menu options are available