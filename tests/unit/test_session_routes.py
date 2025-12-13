"""Unit tests for Session API routes

Tests API endpoint logic with mocked SessionManager.
No external dependencies - SessionManager and Redis are mocked.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import ASGITransport, AsyncClient

from session_service.main import app
from session_service.models.session import SessionData


@pytest.fixture
def test_session():
    """Create test session data"""
    now = datetime.now(timezone.utc)
    return SessionData(
        session_id="session-123",
        user_id="user-456",
        title="Test Session",
        client_id="client-abc",
        created_at=now,
        updated_at=now,
        last_activity_at=now,
        status="active",
        context={},
        messages=[],
        metadata={"type": "troubleshooting"},
    )


@pytest.fixture
def mock_session_manager():
    """Create mock SessionManager"""
    mock = AsyncMock()
    mock.create_session = AsyncMock()
    mock.get_session = AsyncMock()
    mock.update_session = AsyncMock()
    mock.delete_session = AsyncMock()
    mock.heartbeat = AsyncMock()
    mock.list_user_sessions = AsyncMock(return_value=[])
    mock.count_user_sessions = AsyncMock(return_value=0)
    return mock


@pytest.fixture
async def client(mock_session_manager):
    """Create test HTTP client with mocked dependencies"""

    async def override_get_session_manager():
        return mock_session_manager

    # Mock Redis client
    async def override_get_redis_client():
        return AsyncMock()

    # Override dependencies
    from session_service.api.routes import sessions

    app.dependency_overrides[sessions.get_session_manager] = override_get_session_manager

    # Also need to mock get_redis_client for health check
    with patch("session_service.infrastructure.redis.get_redis_client", return_value=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

    app.dependency_overrides.clear()


@pytest.mark.unit
class TestCreateSession:
    """Test POST /api/v1/sessions"""

    @pytest.mark.asyncio
    async def test_create_session_success(self, client, mock_session_manager, test_session):
        """Happy path: create session with valid X-User-ID returns 201"""
        # Arrange
        mock_session_manager.create_session.return_value = test_session

        # Act
        response = await client.post(
            "/api/v1/sessions",
            json={"client_id": "client-abc", "session_type": "troubleshooting"},
            headers={"X-User-ID": "user-456"},
        )

        # Assert
        assert response.status_code == 201
        data = response.json()
        assert data["session_id"] == "session-123"
        assert data["user_id"] == "user-456"
        assert data["client_id"] == "client-abc"
        mock_session_manager.create_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_session_without_client_id(
        self, client, mock_session_manager, test_session
    ):
        """Happy path: create session without client_id succeeds"""
        # Arrange
        mock_session_manager.create_session.return_value = test_session

        # Act
        response = await client.post(
            "/api/v1/sessions", json={}, headers={"X-User-ID": "user-456"}
        )

        # Assert
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_session_missing_user_id_header(self, client):
        """Bad input: missing X-User-ID header returns 401"""
        # Act
        response = await client.post("/api/v1/sessions", json={})

        # Assert
        assert response.status_code == 401
        assert "X-User-ID" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_session_value_error(self, client, mock_session_manager):
        """Bad input: ValueError from SessionManager returns 400"""
        # Arrange
        mock_session_manager.create_session.side_effect = ValueError("Invalid input")

        # Act
        response = await client.post(
            "/api/v1/sessions", json={}, headers={"X-User-ID": "user-456"}
        )

        # Assert
        assert response.status_code == 400
        assert "Invalid input" in response.json()["detail"]


@pytest.mark.unit
class TestGetSession:
    """Test GET /api/v1/sessions/{session_id}"""

    @pytest.mark.asyncio
    async def test_get_session_success(self, client, mock_session_manager, test_session):
        """Happy path: get session with valid session_id and matching user returns 200"""
        # Arrange
        mock_session_manager.get_session.return_value = test_session

        # Act
        response = await client.get(
            "/api/v1/sessions/session-123", headers={"X-User-ID": "user-456"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "session-123"
        assert data["user_id"] == "user-456"

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, client, mock_session_manager):
        """Edge case: get session with non-existent session_id returns 404"""
        # Arrange
        mock_session_manager.get_session.return_value = None

        # Act
        response = await client.get(
            "/api/v1/sessions/non-existent", headers={"X-User-ID": "user-456"}
        )

        # Assert
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_session_unauthorized(self, client, mock_session_manager, test_session):
        """Bad permission: accessing another user's session returns 403"""
        # Arrange
        mock_session_manager.get_session.return_value = test_session

        # Act - different user trying to access session
        response = await client.get(
            "/api/v1/sessions/session-123", headers={"X-User-ID": "different-user"}
        )

        # Assert
        assert response.status_code == 403
        assert "Not authorized" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_session_missing_user_id_header(self, client):
        """Bad auth: missing X-User-ID header returns 401"""
        # Act
        response = await client.get("/api/v1/sessions/session-123")

        # Assert
        assert response.status_code == 401


@pytest.mark.unit
class TestUpdateSession:
    """Test PUT /api/v1/sessions/{session_id}"""

    @pytest.mark.asyncio
    async def test_update_session_success(self, client, mock_session_manager, test_session):
        """Happy path: update session with valid data returns 200"""
        # Arrange
        mock_session_manager.get_session.return_value = test_session
        updated_session = test_session.model_copy()
        updated_session.title = "Updated Title"
        mock_session_manager.update_session.return_value = updated_session

        # Act
        response = await client.put(
            "/api/v1/sessions/session-123",
            json={"title": "Updated Title"},
            headers={"X-User-ID": "user-456"},
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"

    @pytest.mark.asyncio
    async def test_update_session_not_found(self, client, mock_session_manager):
        """Edge case: update non-existent session returns 404"""
        # Arrange
        mock_session_manager.get_session.return_value = None

        # Act
        response = await client.put(
            "/api/v1/sessions/non-existent",
            json={"title": "New"},
            headers={"X-User-ID": "user-456"},
        )

        # Assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_session_unauthorized(self, client, mock_session_manager, test_session):
        """Bad permission: updating another user's session returns 403"""
        # Arrange
        mock_session_manager.get_session.return_value = test_session

        # Act
        response = await client.put(
            "/api/v1/sessions/session-123",
            json={"title": "Updated"},
            headers={"X-User-ID": "different-user"},
        )

        # Assert
        assert response.status_code == 403


@pytest.mark.unit
class TestDeleteSession:
    """Test DELETE /api/v1/sessions/{session_id}"""

    @pytest.mark.asyncio
    async def test_delete_session_success(self, client, mock_session_manager, test_session):
        """Happy path: delete session returns 204"""
        # Arrange
        mock_session_manager.get_session.return_value = test_session
        mock_session_manager.delete_session.return_value = True

        # Act
        response = await client.delete(
            "/api/v1/sessions/session-123", headers={"X-User-ID": "user-456"}
        )

        # Assert
        assert response.status_code == 204
        mock_session_manager.delete_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_session_not_found(self, client, mock_session_manager):
        """Edge case: delete non-existent session returns 404"""
        # Arrange
        mock_session_manager.get_session.return_value = None

        # Act
        response = await client.delete(
            "/api/v1/sessions/non-existent", headers={"X-User-ID": "user-456"}
        )

        # Assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_session_unauthorized(self, client, mock_session_manager, test_session):
        """Bad permission: deleting another user's session returns 403"""
        # Arrange
        mock_session_manager.get_session.return_value = test_session

        # Act
        response = await client.delete(
            "/api/v1/sessions/session-123", headers={"X-User-ID": "different-user"}
        )

        # Assert
        assert response.status_code == 403


@pytest.mark.unit
class TestHeartbeat:
    """Test POST /api/v1/sessions/{session_id}/heartbeat"""

    @pytest.mark.asyncio
    async def test_heartbeat_success(self, client, mock_session_manager, test_session):
        """Happy path: heartbeat updates last_activity_at and returns 200"""
        # Arrange
        mock_session_manager.get_session.return_value = test_session
        updated_session = test_session.model_copy()
        updated_session.last_activity_at = datetime.now(timezone.utc)
        mock_session_manager.heartbeat.return_value = updated_session

        # Act
        response = await client.post(
            "/api/v1/sessions/session-123/heartbeat", headers={"X-User-ID": "user-456"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == "session-123"
        assert "last_activity_at" in data

    @pytest.mark.asyncio
    async def test_heartbeat_not_found(self, client, mock_session_manager):
        """Edge case: heartbeat on non-existent session returns 404"""
        # Arrange
        mock_session_manager.get_session.return_value = None

        # Act
        response = await client.post(
            "/api/v1/sessions/non-existent/heartbeat", headers={"X-User-ID": "user-456"}
        )

        # Assert
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_heartbeat_unauthorized(self, client, mock_session_manager, test_session):
        """Bad permission: heartbeat on another user's session returns 403"""
        # Arrange
        mock_session_manager.get_session.return_value = test_session

        # Act
        response = await client.post(
            "/api/v1/sessions/session-123/heartbeat", headers={"X-User-ID": "different-user"}
        )

        # Assert
        assert response.status_code == 403


@pytest.mark.unit
class TestListSessions:
    """Test GET /api/v1/sessions"""

    @pytest.mark.asyncio
    async def test_list_sessions_success(self, client, mock_session_manager, test_session):
        """Happy path: list sessions returns user's sessions"""
        # Arrange
        mock_session_manager.list_user_sessions.return_value = [test_session]
        mock_session_manager.count_user_sessions.return_value = 1

        # Act
        response = await client.get("/api/v1/sessions", headers={"X-User-ID": "user-456"})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["session_id"] == "session-123"

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, client, mock_session_manager):
        """Edge case: list sessions with no sessions returns empty list"""
        # Arrange
        mock_session_manager.list_user_sessions.return_value = []
        mock_session_manager.count_user_sessions.return_value = 0

        # Act
        response = await client.get("/api/v1/sessions", headers={"X-User-ID": "user-456"})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["sessions"] == []

    @pytest.mark.asyncio
    async def test_list_sessions_pagination(self, client, mock_session_manager):
        """Happy path: list sessions respects limit and offset parameters"""
        # Arrange
        mock_session_manager.list_user_sessions.return_value = []
        mock_session_manager.count_user_sessions.return_value = 10

        # Act
        response = await client.get(
            "/api/v1/sessions?limit=5&offset=2", headers={"X-User-ID": "user-456"}
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 5
        assert data["offset"] == 2
        mock_session_manager.list_user_sessions.assert_called_with("user-456", 5, 2)

    @pytest.mark.asyncio
    async def test_list_sessions_missing_user_id_header(self, client):
        """Bad auth: missing X-User-ID header returns 401"""
        # Act
        response = await client.get("/api/v1/sessions")

        # Assert
        assert response.status_code == 401


@pytest.mark.unit
class TestAuthorizationChecks:
    """Test authorization enforcement across endpoints"""

    @pytest.mark.asyncio
    async def test_all_endpoints_require_user_id_header(self, client):
        """Regression test: all protected endpoints require X-User-ID header"""
        # Test all main endpoints without X-User-ID header
        endpoints = [
            ("GET", "/api/v1/sessions"),
            ("POST", "/api/v1/sessions"),
            ("GET", "/api/v1/sessions/test-123"),
            ("PUT", "/api/v1/sessions/test-123"),
            ("DELETE", "/api/v1/sessions/test-123"),
            ("POST", "/api/v1/sessions/test-123/heartbeat"),
        ]

        for method, url in endpoints:
            if method == "GET":
                response = await client.get(url)
            elif method == "POST":
                response = await client.post(url, json={})
            elif method == "PUT":
                response = await client.put(url, json={})
            elif method == "DELETE":
                response = await client.delete(url)

            assert response.status_code == 401, f"{method} {url} should return 401 without X-User-ID"

    @pytest.mark.asyncio
    async def test_user_cannot_access_other_users_sessions(
        self, client, mock_session_manager, test_session
    ):
        """Regression test: users can only access their own sessions"""
        # Arrange - session belongs to user-456
        mock_session_manager.get_session.return_value = test_session

        # Test read access
        response = await client.get(
            "/api/v1/sessions/session-123", headers={"X-User-ID": "different-user"}
        )
        assert response.status_code == 403

        # Test update access
        response = await client.put(
            "/api/v1/sessions/session-123",
            json={"title": "New"},
            headers={"X-User-ID": "different-user"},
        )
        assert response.status_code == 403

        # Test delete access
        response = await client.delete(
            "/api/v1/sessions/session-123", headers={"X-User-ID": "different-user"}
        )
        assert response.status_code == 403

        # Test heartbeat access
        response = await client.post(
            "/api/v1/sessions/session-123/heartbeat", headers={"X-User-ID": "different-user"}
        )
        assert response.status_code == 403
