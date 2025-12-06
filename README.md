# fm-session-service

> **Part of [FaultMaven](https://github.com/FaultMaven/faultmaven)** —
> The AI-Powered Troubleshooting Copilot

**FaultMaven Session Management Microservice** - Open source Redis-backed session management for troubleshooting workflows.

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://hub.docker.com/r/faultmaven/fm-session-service)

## Overview

The Session Service manages troubleshooting session lifecycle and conversation state in FaultMaven. Sessions store conversation messages, context, and metadata in Redis for fast access and automatic expiration.

**Features:**
- **Redis-backed Storage**: Fast, persistent session management with automatic TTL
- **Session CRUD**: Create, read, update, and delete sessions
- **Conversation History**: Store and retrieve messages with metadata
- **Heartbeat Tracking**: Automatic session timeout with activity-based renewal
- **User Isolation**: Each user only accesses their own sessions
- **Client Support**: Multi-device session resumption via client_id
- **Flexible Metadata**: Attach custom data to sessions and messages
- **Auto-generated Titles**: Session titles from first message

## Quick Start

### Using Docker (Recommended)

```bash
# Run with Redis
docker run -d -p 6379:6379 redis:7-alpine
docker run -d -p 8002:8002 \
  -e REDIS_URL=redis://host.docker.internal:6379 \
  faultmaven/fm-session-service:latest
```

The service will be available at `http://localhost:8002`.

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

# Start Redis
docker run -d -p 6379:6379 redis:7-alpine

# Run service
export REDIS_URL=redis://localhost:6379
uvicorn session_service.main:app --reload --port 8002
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/sessions` | Create new session |
| GET | `/api/v1/sessions/{session_id}` | Get session details |
| PUT | `/api/v1/sessions/{session_id}` | Update session |
| DELETE | `/api/v1/sessions/{session_id}` | Delete session |
| GET | `/api/v1/sessions` | List user's sessions |
| POST | `/api/v1/sessions/{session_id}/messages` | Add message to session |
| GET | `/api/v1/sessions/{session_id}/messages` | Get session messages |
| POST | `/api/v1/sessions/{session_id}/heartbeat` | Update last activity |
| GET | `/health` | Health check |

## Configuration

Configuration via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `SERVICE_NAME` | Service identifier | `fm-session-service` |
| `ENVIRONMENT` | Deployment environment | `development` |
| `PORT` | Service port | `8002` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379` |
| `SESSION_TTL_MINUTES` | Default session timeout | `180` |
| `MAX_SESSION_TTL_MINUTES` | Maximum session timeout | `480` |
| `CORS_ORIGINS` | Allowed CORS origins | `*` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Session Data Model

```json
{
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "user_id": "user_123",
    "client_id": "chrome_extension_v1",
    "title": "Database connection timeout troubleshooting",
    "status": "active",
    "created_at": "2025-11-15T10:30:00Z",
    "updated_at": "2025-11-15T12:45:00Z",
    "last_activity_at": "2025-11-15T12:45:00Z",
    "messages": [
        {
            "message_id": "msg_001",
            "role": "user",
            "content": "My database keeps timing out",
            "timestamp": "2025-11-15T10:30:00Z",
            "metadata": {}
        },
        {
            "message_id": "msg_002",
            "role": "assistant",
            "content": "Let's investigate the connection timeout...",
            "timestamp": "2025-11-15T10:30:15Z",
            "metadata": {"reasoning": "..."}
        }
    ],
    "context": {
        "blast_radius": "single_database",
        "timeline_start": "2025-11-15T09:00:00Z"
    },
    "metadata": {
        "session_type": "troubleshooting",
        "timeout_minutes": 180
    }
}
```

### Message Roles
- `user` - User-provided messages
- `assistant` - AI agent responses
- `system` - System notifications

### Session Status
- `active` - Session in use
- `archived` - Session archived for reference
- `deleted` - Session marked for deletion

## Authorization

This service uses **trusted header authentication** from the FaultMaven API Gateway:

- `X-User-ID` (required): Identifies the user making the request
- `X-User-Email` (optional): User's email address
- `X-User-Roles` (optional): User's roles

All session operations are scoped to the user specified in `X-User-ID`. Users can only access their own sessions.

**Important**: This service should run behind the [fm-api-gateway](https://github.com/FaultMaven/faultmaven) which handles authentication and sets these headers. Never expose this service directly to the internet.

## Architecture

```
┌─────────────────┐
│  API Gateway    │ (Handles authentication)
└────────┬────────┘
         │ X-User-ID header
         ↓
┌─────────────────┐
│ Session Service │ (Trusts headers)
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│   Redis Store   │ (User-scoped data with TTL)
└─────────────────┘
```

## Session Lifecycle

1. **Creation**: POST /api/v1/sessions → New session with TTL
2. **Activity**: POST /api/v1/sessions/{id}/heartbeat → Refresh TTL
3. **Updates**: PUT /api/v1/sessions/{id} → Modify metadata/context
4. **Messages**: POST /api/v1/sessions/{id}/messages → Add conversation
5. **Retrieval**: GET /api/v1/sessions/{id} → Fetch full session
6. **Expiration**: Auto-delete after TTL (default 180 minutes)
7. **Manual Delete**: DELETE /api/v1/sessions/{id} → Immediate removal

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=session_service

# Run specific test file
pytest tests/test_sessions.py -v
```

## Related Projects

- [faultmaven](https://github.com/FaultMaven/faultmaven) - Main backend with API Gateway
- [faultmaven-copilot](https://github.com/FaultMaven/faultmaven-copilot) - Browser extension UI
- [faultmaven-deploy](https://github.com/FaultMaven/faultmaven-deploy) - Docker Compose deployment

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.

## Contributing

See our [Contributing Guide](https://github.com/FaultMaven/.github/blob/main/CONTRIBUTING.md) for detailed guidelines.

## Support

- **Discussions:** [GitHub Discussions](https://github.com/FaultMaven/faultmaven/discussions)
- **Issues:** [GitHub Issues](https://github.com/FaultMaven/fm-session-service/issues)
