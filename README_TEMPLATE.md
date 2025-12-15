# fm-session-service

<!-- GENERATED:BADGE_LINE -->

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://hub.docker.com/r/faultmaven/fm-session-service)
[![Auto-Docs](https://img.shields.io/badge/docs-auto--generated-success.svg)](.github/workflows/generate-docs.yml)

## Overview

**Session management microservice** - Part of the FaultMaven troubleshooting platform.

The Session Service manages troubleshooting investigation sessions in FaultMaven. Sessions are interactive workspaces where users conduct troubleshooting investigations, chat with AI assistants, and track their problem-solving workflow.

**Key Features:**
- **Session Lifecycle**: Create, retrieve, update, and delete troubleshooting sessions
- **User Isolation**: Each user only sees their own sessions (enforced via X-User-ID header)
- **Message Management**: Add and retrieve conversation messages within sessions
- **Session Statistics**: Track message counts, duration, and activity timestamps
- **Status Tracking**: Monitor session progression (active → in_progress → completed/archived)
- **Case Integration**: Link sessions to cases in fm-case-service for long-term tracking
- **Search & Filter**: Find sessions by status, title, or query parameters
- **Archive/Restore**: Archive inactive sessions and restore them when needed
- **Redis Storage**: Fast, in-memory session data with optional persistence

## Quick Start

### Using Docker (Recommended)

```bash
docker run -p 8001:8001 -e REDIS_URL=redis://redis:6379 faultmaven/fm-session-service:latest
```

The service will be available at `http://localhost:8001`. Requires a Redis instance for session storage.

### Using Docker Compose

See [faultmaven-deploy](https://github.com/FaultMaven/faultmaven-deploy) for complete deployment with all FaultMaven services.

### Development Setup

```bash
# Clone repository
git clone https://github.com/FaultMaven/fm-session-service.git
cd fm-session-service

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .

# Set up Redis (requires Docker)
docker run -d -p 6379:6379 redis:7-alpine

# Run service
uvicorn session_service.main:app --reload --port 8001
```

The service connects to Redis at `redis://localhost:6379` by default (configurable via REDIS_URL).

## API Endpoints

<!-- GENERATED:API_TABLE -->

**OpenAPI Documentation**: See [docs/api/openapi.json](docs/api/openapi.json) or [docs/api/openapi.yaml](docs/api/openapi.yaml) for complete API specification.
<!-- GENERATED:RESPONSE_CODES -->

## Configuration

Configuration via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `SERVICE_NAME` | Service identifier | `fm-session-service` |
| `SERVICE_VERSION` | Service version | `1.0.0` |
| `ENVIRONMENT` | Deployment environment | `development` |
| `HOST` | Service host | `0.0.0.0` |
| `PORT` | Service port | `8001` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379` |
| `DEFAULT_SESSION_TTL` | Session TTL in seconds | `86400` (24 hours) |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated) | `*` |
| `LOG_LEVEL` | Logging level (DEBUG/INFO/WARNING/ERROR) | `INFO` |

Example `.env` file:

```env
ENVIRONMENT=production
PORT=8001
REDIS_URL=redis://redis-cluster:6379/0
DEFAULT_SESSION_TTL=604800
LOG_LEVEL=INFO
CORS_ORIGINS=https://app.faultmaven.com,https://admin.faultmaven.com
```

## Session Data Model

Example Session Object:

```json
{
    "session_id": "session_abc123def456",
    "user_id": "user_123",
    "title": "Investigating database timeout issues",
    "description": "Production RDS experiencing connection timeouts",
    "status": "in_progress",
    "messages": [
        {
            "role": "user",
            "content": "What's causing the database timeouts?",
            "timestamp": "2025-11-15T10:30:00Z"
        },
        {
            "role": "assistant",
            "content": "Let me help investigate...",
            "timestamp": "2025-11-15T10:30:05Z"
        }
    ],
    "metadata": {"environment": "production", "component": "database"},
    "created_at": "2025-11-15T10:30:00Z",
    "last_activity_at": "2025-11-15T10:35:00Z"
}
```

### Status Values
- `active` - Session created, not yet started
- `in_progress` - Investigation actively underway
- `completed` - Investigation finished successfully
- `archived` - Session archived for reference
- `abandoned` - Session abandoned without completion

### Message Structure
Messages follow a chat-like format:
- `role`: Either "user" or "assistant"
- `content`: The message text
- `timestamp`: ISO 8601 timestamp

## Authorization

This service uses **trusted header authentication** from the FaultMaven API Gateway:

**Required Headers:**

- `X-User-ID` (required): Identifies the user making the request

**Optional Headers:**

- `X-User-Email`: User's email address
- `X-User-Roles`: User's roles (comma-separated)

All session operations are scoped to the user specified in `X-User-ID`. Users can only access their own sessions.

**Security Model:**

- ✅ User isolation enforced at storage level (Redis key prefixing)
- ✅ All endpoints validate X-User-ID header presence
- ✅ Cross-user access attempts return 404 (not 403) to prevent enumeration
- ⚠️ Service trusts headers set by upstream gateway

**Important**: This service should run behind the [fm-api-gateway](https://github.com/FaultMaven/faultmaven) which handles authentication and sets these headers. Never expose this service directly to the internet.

## Architecture

```
┌─────────────────────────┐
│  FaultMaven API Gateway │  Handles authentication (Clerk)
│  (Port 8000)            │  Sets X-User-ID header
└───────────┬─────────────┘
            │ Trusted headers (X-User-ID)
            ↓
┌─────────────────────────┐
│  fm-session-service     │  Trusts gateway headers
│  (Port 8001)            │  Enforces user isolation
└───────────┬─────────────┘
            │ Redis commands
            ↓
┌─────────────────────────┐
│  Redis                  │  In-memory session storage
│  (Port 6379)            │  User-scoped keys
└─────────────────────────┘
```

**Related Services:**
- fm-case-service (8003) - Case management
- fm-knowledge-service (8002) - Knowledge base
- fm-evidence-service (8004) - Evidence artifacts

**Storage Details:**

- **Database**: Redis (in-memory key-value store)
- **Connection**: redis-py async client
- **Key Pattern**: `session:{user_id}:{session_id}`
- **Data Format**: JSON serialized session objects
- **TTL**: Configurable per session (default 24 hours)
- **Persistence**: Optional (configure Redis AOF/RDB)

## Testing

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage report
pytest --cov=session_service --cov-report=html --cov-report=term

# Run specific test file
pytest tests/test_sessions.py -v

# Run with debug output
pytest -vv -s
```

**Test Coverage Goals:**

- Unit tests: Core business logic (SessionManager)
- Integration tests: Redis operations
- API tests: Endpoint behavior and validation
- Target coverage: >80%

## Development Workflow

```bash
# Format code with black
black src/ tests/

# Lint with flake8
flake8 src/ tests/

# Type check with mypy
mypy src/

# Run all quality checks
black src/ tests/ && flake8 src/ tests/ && mypy src/ && pytest
```

## Related Projects

- [faultmaven](https://github.com/FaultMaven/faultmaven) - Main backend with API Gateway and orchestration
- [faultmaven-copilot](https://github.com/FaultMaven/faultmaven-copilot) - Browser extension UI for troubleshooting
- [faultmaven-deploy](https://github.com/FaultMaven/faultmaven-deploy) - Docker Compose deployment configurations
- [fm-case-service](https://github.com/FaultMaven/fm-case-service) - Case management
- [fm-knowledge-service](https://github.com/FaultMaven/fm-knowledge-service) - Knowledge base and recommendations
- [fm-evidence-service](https://github.com/FaultMaven/fm-evidence-service) - Evidence artifact storage

## CI/CD

This repository uses **GitHub Actions** for automated documentation generation:

**Trigger**: Every push to `main` or `develop` branches

**Process**:
1. Generate OpenAPI spec (JSON + YAML)
2. Validate documentation completeness (fails if endpoints lack descriptions)
3. Auto-generate this README from code
4. Commit changes back to repository (if on main)

See [.github/workflows/generate-docs.yml](.github/workflows/generate-docs.yml) for implementation details.

**Documentation Guarantee**: This README is always in sync with the actual code. Any endpoint changes automatically trigger documentation updates.

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and quality checks (`pytest && black . && flake8`)
5. Commit with clear messages (`git commit -m 'feat: Add amazing feature'`)
6. Push to your fork (`git push origin feature/amazing-feature`)
7. Open a Pull Request

**Code Style**: Black formatting, flake8 linting, mypy type checking
**Commit Convention**: Conventional Commits (feat/fix/docs/refactor/test/chore)

---

<!-- GENERATED:STATS -->

*This README is automatically updated on every commit to ensure zero documentation drift.*
