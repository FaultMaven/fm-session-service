# Session Service Extraction Map

## Source Files (from FaultMaven monolith)

| Monolith File | Destination | Action |
|---------------|-------------|--------|
| faultmaven/models/session.py | src/session_service/domain/models/session.py | Extract session models |
| faultmaven/services/domain/session_service.py | src/session_service/domain/services/session_service.py | Extract business logic |
| faultmaven/api/v1/routes/session.py | src/session_service/api/routes/sessions.py | Extract API endpoints |
| faultmaven/infrastructure/persistence/redis_session_store.py | src/session_service/infrastructure/persistence/redis_store.py | Extract Redis storage |
| faultmaven/infrastructure/persistence/redis_session_manager.py | src/session_service/infrastructure/persistence/manager.py | Extract session manager |

## Database Tables (exclusive ownership)

| Table Name | Source Schema | Action |
|------------|---------------|--------|
| None | N/A | Redis-only service (no PostgreSQL) |

## Redis Namespaces

| Namespace | Purpose |
|-----------|---------|
| session:{session_id} | Session state storage |
| session:user:{user_id} | User sessions index |
| session:org:{org_id} | Organization sessions index |

## Events Published

| Event Name | AsyncAPI Schema | Trigger |
|------------|-----------------|---------|
| session.created.v1 | contracts/asyncapi/session-events.yaml | POST /v1/sessions |
| session.updated.v1 | contracts/asyncapi/session-events.yaml | PUT /v1/sessions/{id} |
| session.expired.v1 | contracts/asyncapi/session-events.yaml | Session TTL expiration |
| session.deleted.v1 | contracts/asyncapi/session-events.yaml | DELETE /v1/sessions/{id} |

## Events Consumed

| Event Name | Source Service | Action |
|------------|----------------|--------|
| auth.user.deleted.v1 | Auth Service | Delete all user sessions |
| case.deleted.v1 | Case Service | Update session state |

## API Dependencies

| Dependency | Purpose | Fallback Strategy |
|------------|---------|-------------------|
| Auth Service | Validate user tokens | Circuit breaker (deny if down) |

## Migration Checklist

- [ ] Extract domain models (Session, SessionMessage, SessionContext)
- [ ] Extract business logic (SessionService with lifecycle management)
- [ ] Extract API routes (CRUD + session analytics)
- [ ] Extract Redis storage layer
- [ ] Implement event publishing (outbox pattern)
- [ ] Implement event consumption (inbox pattern)
- [ ] Add circuit breakers for auth dependency
- [ ] Write unit tests (80%+ coverage)
- [ ] Write integration tests (Redis)
- [ ] Write contract tests (provider verification)
