"""Unit tests for SessionManager

Tests core session lifecycle operations with mocked Redis.
No external dependencies - all Redis operations are mocked.
"""

import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from session_service.core.session_manager import SessionManager
from session_service.models.session import SessionData, Message


@pytest.fixture
def mock_redis():
    """Create mock Redis client with async methods"""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.smembers = AsyncMock(return_value=set())
    mock.sadd = AsyncMock(return_value=1)
    mock.srem = AsyncMock(return_value=1)
    mock.scard = AsyncMock(return_value=0)
    mock.expire = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_settings():
    """Create mock settings"""
    settings = MagicMock()
    settings.session_ttl_seconds = 3600  # 1 hour
    settings.max_sessions_per_user = 10
    return settings


@pytest.fixture
def session_manager(mock_redis, mock_settings):
    """Create SessionManager with mocked dependencies"""
    with patch("session_service.core.session_manager.get_settings", return_value=mock_settings):
        manager = SessionManager(mock_redis)
        return manager


@pytest.fixture
def test_session():
    """Create test session data"""
    now = datetime.now(timezone.utc)
    return SessionData(
        session_id=str(uuid4()),
        user_id="user-123",
        title="Test Session",
        client_id="client-abc",
        created_at=now,
        updated_at=now,
        last_activity_at=now,
        status="active",
        context={"key": "value"},
        messages=[],
        metadata={"type": "troubleshooting"},
    )


@pytest.mark.unit
class TestCreateSession:
    """Test session creation"""

    @pytest.mark.asyncio
    async def test_create_session_success(self, session_manager, mock_redis):
        """Happy path: create_session with valid user_id returns SessionData"""
        # Act
        session = await session_manager.create_session(
            user_id="user-123",
            client_id="client-abc",
            metadata={"type": "troubleshooting"},
        )

        # Assert - INTENTIONALLY BROKEN FOR VERIFICATION
        assert session is not None
        assert session.session_id is not None
        assert session.user_id == "WRONG-USER"  # This will fail
        assert session.client_id == "client-abc"
        assert session.status == "active"
        assert session.metadata["type"] == "troubleshooting"
        assert isinstance(session.created_at, datetime)

        # Verify Redis calls
        mock_redis.set.assert_called_once()
        mock_redis.sadd.assert_called_once()
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_session_without_client_id(self, session_manager, mock_redis):
        """Happy path: create_session without client_id succeeds"""
        # Act
        session = await session_manager.create_session(user_id="user-123")

        # Assert
        assert session.client_id is None
        assert session.user_id == "user-123"
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_session_empty_user_id(self, session_manager):
        """Bad input: empty user_id raises ValueError"""
        # Act & Assert
        with pytest.raises(ValueError, match="user_id is required"):
            await session_manager.create_session(user_id="")

    @pytest.mark.asyncio
    async def test_create_session_whitespace_user_id(self, session_manager):
        """Bad input: whitespace-only user_id raises ValueError"""
        # Act & Assert
        with pytest.raises(ValueError, match="user_id is required"):
            await session_manager.create_session(user_id="   ")

    @pytest.mark.asyncio
    async def test_create_session_enforces_max_sessions(self, session_manager, mock_redis):
        """Edge case: creating session enforces max_sessions_per_user limit"""
        # Arrange - simulate 10 existing sessions (at limit)
        mock_redis.scard = AsyncMock(return_value=10)

        # Mock smembers to return session IDs
        existing_session_ids = [f"session-{i}" for i in range(10)]
        mock_redis.smembers = AsyncMock(return_value=existing_session_ids)

        # Mock get_session to return sessions with different timestamps
        sessions_data = []
        for i, sid in enumerate(existing_session_ids):
            session = SessionData(
                session_id=sid,
                user_id="user-123",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                last_activity_at=datetime.now(timezone.utc),
                status="active",
                context={},
                messages=[],
                metadata={},
            )
            sessions_data.append(session)

        # Act
        session = await session_manager.create_session(user_id="user-123")

        # Assert
        assert session is not None
        # Verify _enforce_session_limit was called
        mock_redis.scard.assert_called()


@pytest.mark.unit
class TestGetSession:
    """Test session retrieval"""

    @pytest.mark.asyncio
    async def test_get_session_success(self, session_manager, mock_redis, test_session):
        """Happy path: get_session with valid session_id returns SessionData"""
        # Arrange
        session_dict = SessionManager._session_to_dict(test_session)
        mock_redis.get = AsyncMock(return_value=json.dumps(session_dict))

        # Act
        result = await session_manager.get_session(test_session.session_id)

        # Assert
        assert result is not None
        assert result.session_id == test_session.session_id
        assert result.user_id == test_session.user_id
        assert result.title == test_session.title
        mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, session_manager, mock_redis):
        """Edge case: get_session with non-existent session_id returns None"""
        # Arrange
        mock_redis.get = AsyncMock(return_value=None)

        # Act
        result = await session_manager.get_session("non-existent-id")

        # Assert
        assert result is None
        mock_redis.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_session_empty_id(self, session_manager):
        """Bad input: get_session with empty session_id returns None"""
        # Act
        result = await session_manager.get_session("")

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_get_session_redis_error(self, session_manager, mock_redis):
        """Error handling: get_session handles Redis errors gracefully"""
        # Arrange
        mock_redis.get = AsyncMock(side_effect=Exception("Redis connection failed"))

        # Act
        result = await session_manager.get_session("session-123")

        # Assert
        assert result is None


@pytest.mark.unit
class TestUpdateSession:
    """Test session updates"""

    @pytest.mark.asyncio
    async def test_update_session_title(self, session_manager, mock_redis, test_session):
        """Happy path: update_session with new title succeeds"""
        # Arrange
        session_dict = SessionManager._session_to_dict(test_session)
        mock_redis.get = AsyncMock(return_value=json.dumps(session_dict))

        # Act
        updated = await session_manager.update_session(
            test_session.session_id, {"title": "Updated Title"}
        )

        # Assert
        assert updated is not None
        assert updated.title == "Updated Title"
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_session_status(self, session_manager, mock_redis, test_session):
        """Happy path: update_session can change status"""
        # Arrange
        session_dict = SessionManager._session_to_dict(test_session)
        mock_redis.get = AsyncMock(return_value=json.dumps(session_dict))

        # Act
        updated = await session_manager.update_session(
            test_session.session_id, {"status": "archived"}
        )

        # Assert
        assert updated.status == "archived"

    @pytest.mark.asyncio
    async def test_update_session_not_found(self, session_manager, mock_redis):
        """Edge case: update_session with non-existent session_id returns None"""
        # Arrange
        mock_redis.get = AsyncMock(return_value=None)

        # Act
        result = await session_manager.update_session("non-existent", {"title": "New"})

        # Assert
        assert result is None

    @pytest.mark.asyncio
    async def test_update_session_context(self, session_manager, mock_redis, test_session):
        """Happy path: update_session merges context updates"""
        # Arrange
        session_dict = SessionManager._session_to_dict(test_session)
        mock_redis.get = AsyncMock(return_value=json.dumps(session_dict))

        # Act
        updated = await session_manager.update_session(
            test_session.session_id, {"context": {"new_key": "new_value"}}
        )

        # Assert
        assert "new_key" in updated.context
        assert updated.context["new_key"] == "new_value"
        # Original context should be preserved
        assert updated.context["key"] == "value"


@pytest.mark.unit
class TestDeleteSession:
    """Test session deletion"""

    @pytest.mark.asyncio
    async def test_delete_session_success(self, session_manager, mock_redis, test_session):
        """Happy path: delete_session removes session from Redis"""
        # Arrange
        session_dict = SessionManager._session_to_dict(test_session)
        mock_redis.get = AsyncMock(return_value=json.dumps(session_dict))
        mock_redis.delete = AsyncMock(return_value=1)

        # Act
        result = await session_manager.delete_session(test_session.session_id)

        # Assert
        assert result is True
        mock_redis.delete.assert_called_once()
        mock_redis.srem.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_session_not_found(self, session_manager, mock_redis):
        """Edge case: delete_session with non-existent session_id returns False"""
        # Arrange
        mock_redis.get = AsyncMock(return_value=None)

        # Act
        result = await session_manager.delete_session("non-existent")

        # Assert
        assert result is False


@pytest.mark.unit
class TestHeartbeat:
    """Test session heartbeat updates"""

    @pytest.mark.asyncio
    async def test_heartbeat_success(self, session_manager, mock_redis, test_session):
        """Happy path: heartbeat updates last_activity_at timestamp"""
        # Arrange
        original_time = test_session.last_activity_at
        session_dict = SessionManager._session_to_dict(test_session)
        mock_redis.get = AsyncMock(return_value=json.dumps(session_dict))

        # Act
        updated = await session_manager.heartbeat(test_session.session_id)

        # Assert
        assert updated is not None
        assert updated.last_activity_at >= original_time
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_heartbeat_not_found(self, session_manager, mock_redis):
        """Edge case: heartbeat with non-existent session_id returns None"""
        # Arrange
        mock_redis.get = AsyncMock(return_value=None)

        # Act
        result = await session_manager.heartbeat("non-existent")

        # Assert
        assert result is None


@pytest.mark.unit
class TestListUserSessions:
    """Test listing user sessions"""

    @pytest.mark.asyncio
    async def test_list_user_sessions_success(self, session_manager, mock_redis):
        """Happy path: list_user_sessions returns user's sessions"""
        # Arrange
        session_ids = {"session-1", "session-2", "session-3"}
        mock_redis.smembers = AsyncMock(return_value=session_ids)

        # Mock get_session to return valid sessions
        async def mock_get_session(sid):
            return SessionData(
                session_id=sid,
                user_id="user-123",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                last_activity_at=datetime.now(timezone.utc),
                status="active",
                context={},
                messages=[],
                metadata={},
            )

        session_manager.get_session = mock_get_session

        # Act
        sessions = await session_manager.list_user_sessions("user-123")

        # Assert
        assert len(sessions) == 3
        assert all(s.user_id == "user-123" for s in sessions)

    @pytest.mark.asyncio
    async def test_list_user_sessions_empty(self, session_manager, mock_redis):
        """Edge case: list_user_sessions with no sessions returns empty list"""
        # Arrange
        mock_redis.smembers = AsyncMock(return_value=set())

        # Act
        sessions = await session_manager.list_user_sessions("user-123")

        # Assert
        assert sessions == []

    @pytest.mark.asyncio
    async def test_list_user_sessions_pagination(self, session_manager, mock_redis):
        """Happy path: list_user_sessions respects limit and offset"""
        # Arrange
        session_ids = {f"session-{i}" for i in range(10)}
        mock_redis.smembers = AsyncMock(return_value=session_ids)

        async def mock_get_session(sid):
            return SessionData(
                session_id=sid,
                user_id="user-123",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                last_activity_at=datetime.now(timezone.utc),
                status="active",
                context={},
                messages=[],
                metadata={},
            )

        session_manager.get_session = mock_get_session

        # Act
        sessions = await session_manager.list_user_sessions("user-123", limit=5, offset=2)

        # Assert
        assert len(sessions) == 5


@pytest.mark.unit
class TestCountUserSessions:
    """Test counting user sessions"""

    @pytest.mark.asyncio
    async def test_count_user_sessions(self, session_manager, mock_redis):
        """Happy path: count_user_sessions returns correct count"""
        # Arrange
        mock_redis.scard = AsyncMock(return_value=5)

        # Act
        count = await session_manager.count_user_sessions("user-123")

        # Assert
        assert count == 5
        mock_redis.scard.assert_called_once()


@pytest.mark.unit
class TestSessionSerialization:
    """Test session serialization and deserialization"""

    def test_session_to_dict(self, test_session):
        """Happy path: _session_to_dict serializes SessionData correctly"""
        # Act
        result = SessionManager._session_to_dict(test_session)

        # Assert
        assert result["session_id"] == test_session.session_id
        assert result["user_id"] == test_session.user_id
        assert result["title"] == test_session.title
        assert result["status"] == test_session.status
        assert "created_at" in result
        assert isinstance(result["created_at"], str)

    def test_dict_to_session(self, test_session):
        """Happy path: _dict_to_session deserializes correctly"""
        # Arrange
        session_dict = SessionManager._session_to_dict(test_session)

        # Act
        result = SessionManager._dict_to_session(session_dict)

        # Assert
        assert result.session_id == test_session.session_id
        assert result.user_id == test_session.user_id
        assert result.title == test_session.title
        assert result.status == test_session.status

    def test_session_roundtrip(self, test_session):
        """Regression test: session can be serialized and deserialized without data loss"""
        # Act
        session_dict = SessionManager._session_to_dict(test_session)
        restored = SessionManager._dict_to_session(session_dict)

        # Assert
        assert restored.session_id == test_session.session_id
        assert restored.user_id == test_session.user_id
        assert restored.context == test_session.context
        assert restored.metadata == test_session.metadata

    def test_session_with_messages_serialization(self):
        """Happy path: sessions with messages serialize correctly"""
        # Arrange
        now = datetime.now(timezone.utc)
        message = Message(
            message_id="msg-1",
            role="user",
            content="Test message",
            timestamp=now,
            metadata={"key": "value"},
        )
        session = SessionData(
            session_id=str(uuid4()),
            user_id="user-123",
            created_at=now,
            updated_at=now,
            last_activity_at=now,
            status="active",
            context={},
            messages=[message],
            metadata={},
        )

        # Act
        session_dict = SessionManager._session_to_dict(session)
        restored = SessionManager._dict_to_session(session_dict)

        # Assert
        assert len(restored.messages) == 1
        assert restored.messages[0].message_id == "msg-1"
        assert restored.messages[0].role == "user"
        assert restored.messages[0].content == "Test message"
