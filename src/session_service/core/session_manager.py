"""Session Manager - Core business logic for session operations.

This module implements session lifecycle management using Redis as the storage backend.
Based on the FaultMaven monolith SessionService and RedisSessionStore.
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from uuid import uuid4

import redis.asyncio as redis

from session_service.models import SessionData, Message
from session_service.config import get_settings

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages session lifecycle and operations.

    Provides create, read, update, delete operations for sessions
    with Redis-backed storage and TTL management.
    """

    def __init__(self, redis_client: redis.Redis):
        """Initialize SessionManager.

        Args:
            redis_client: Async Redis client instance
        """
        self.redis_client = redis_client
        self.settings = get_settings()
        self.prefix = "session:"
        self.user_index_prefix = "user_sessions:"

    async def create_session(
        self,
        user_id: str,
        client_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SessionData:
        """Create a new session.

        Args:
            user_id: User identifier from X-User-ID header
            client_id: Optional client/device identifier
            metadata: Optional session metadata

        Returns:
            SessionData: Created session

        Raises:
            ValueError: If user_id is empty
        """
        if not user_id or not user_id.strip():
            raise ValueError("user_id is required")

        # Generate session ID
        session_id = str(uuid4())
        now = datetime.now(timezone.utc)

        # Create session data
        session = SessionData(
            session_id=session_id,
            user_id=user_id,
            client_id=client_id,
            created_at=now,
            updated_at=now,
            last_activity_at=now,
            status="active",
            context={},
            messages=[],
            metadata=metadata or {},
        )

        # Store in Redis
        await self._save_session(session)

        # Add to user index
        await self._add_to_user_index(user_id, session_id)

        # Enforce max sessions per user
        await self._enforce_session_limit(user_id)

        logger.info(f"Created session {session_id} for user {user_id}")
        return session

    async def get_session(self, session_id: str) -> Optional[SessionData]:
        """Get session by ID.

        Args:
            session_id: Session identifier

        Returns:
            SessionData if found, None otherwise
        """
        if not session_id or not session_id.strip():
            return None

        key = f"{self.prefix}{session_id}"

        try:
            data = await self.redis_client.get(key)
            if not data:
                return None

            session_dict = json.loads(data)
            return self._dict_to_session(session_dict)

        except Exception as e:
            logger.error(f"Error getting session {session_id}: {e}")
            return None

    async def update_session(
        self, session_id: str, updates: Dict[str, Any]
    ) -> Optional[SessionData]:
        """Update session data.

        Args:
            session_id: Session identifier
            updates: Fields to update

        Returns:
            Updated SessionData if successful, None if session not found
        """
        session = await self.get_session(session_id)
        if not session:
            return None

        # Apply updates
        if "title" in updates:
            session.title = updates["title"]
        if "status" in updates:
            session.status = updates["status"]
        if "context" in updates:
            session.context.update(updates["context"])
        if "metadata" in updates:
            session.metadata.update(updates["metadata"])

        # Update timestamp
        session.updated_at = datetime.now(timezone.utc)

        # Save
        await self._save_session(session)
        logger.debug(f"Updated session {session_id}")

        return session

    async def delete_session(self, session_id: str) -> bool:
        """Delete session.

        Args:
            session_id: Session identifier

        Returns:
            True if deleted, False if not found
        """
        session = await self.get_session(session_id)
        if not session:
            return False

        # Remove from user index
        await self._remove_from_user_index(session.user_id, session_id)

        # Delete session
        key = f"{self.prefix}{session_id}"
        result = await self.redis_client.delete(key)

        logger.info(f"Deleted session {session_id}")
        return result > 0

    async def heartbeat(self, session_id: str) -> Optional[SessionData]:
        """Update session last activity timestamp (heartbeat).

        Args:
            session_id: Session identifier

        Returns:
            Updated SessionData if successful, None if session not found
        """
        session = await self.get_session(session_id)
        if not session:
            return None

        # Update last activity
        session.last_activity_at = datetime.now(timezone.utc)
        session.updated_at = session.last_activity_at

        # Save and extend TTL
        await self._save_session(session)

        logger.debug(f"Heartbeat updated for session {session_id}")
        return session

    async def list_user_sessions(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> List[SessionData]:
        """List sessions for a user.

        Args:
            user_id: User identifier
            limit: Maximum number of sessions to return
            offset: Number of sessions to skip

        Returns:
            List of SessionData objects
        """
        # Get session IDs from user index
        index_key = f"{self.user_index_prefix}{user_id}"
        session_ids = await self.redis_client.smembers(index_key)

        if not session_ids:
            return []

        # Convert to list and apply pagination
        session_ids = list(session_ids)
        paginated_ids = session_ids[offset : offset + limit]

        # Fetch sessions
        sessions = []
        for session_id in paginated_ids:
            session = await self.get_session(session_id)
            if session:
                sessions.append(session)

        return sessions

    async def count_user_sessions(self, user_id: str) -> int:
        """Count total sessions for a user.

        Args:
            user_id: User identifier

        Returns:
            Number of sessions
        """
        index_key = f"{self.user_index_prefix}{user_id}"
        return await self.redis_client.scard(index_key)

    # Private helper methods

    async def _save_session(self, session: SessionData) -> None:
        """Save session to Redis with TTL.

        Args:
            session: Session to save
        """
        key = f"{self.prefix}{session.session_id}"

        # Serialize to JSON
        session_dict = self._session_to_dict(session)
        data = json.dumps(session_dict)

        # Save with TTL
        await self.redis_client.set(
            key, data, ex=self.settings.session_ttl_seconds
        )

    async def _add_to_user_index(self, user_id: str, session_id: str) -> None:
        """Add session to user index.

        Args:
            user_id: User identifier
            session_id: Session identifier
        """
        index_key = f"{self.user_index_prefix}{user_id}"
        await self.redis_client.sadd(index_key, session_id)
        # Set TTL on index as well
        await self.redis_client.expire(index_key, self.settings.session_ttl_seconds)

    async def _remove_from_user_index(self, user_id: str, session_id: str) -> None:
        """Remove session from user index.

        Args:
            user_id: User identifier
            session_id: Session identifier
        """
        index_key = f"{self.user_index_prefix}{user_id}"
        await self.redis_client.srem(index_key, session_id)

    async def _enforce_session_limit(self, user_id: str) -> None:
        """Enforce maximum sessions per user limit.

        Deletes oldest sessions if limit exceeded.

        Args:
            user_id: User identifier
        """
        count = await self.count_user_sessions(user_id)
        if count <= self.settings.max_sessions_per_user:
            return

        # Get all sessions
        sessions = await self.list_user_sessions(user_id, limit=count)

        # Sort by last activity
        sessions.sort(key=lambda s: s.last_activity_at)

        # Delete oldest sessions
        to_delete = count - self.settings.max_sessions_per_user
        for session in sessions[:to_delete]:
            await self.delete_session(session.session_id)
            logger.info(
                f"Deleted session {session.session_id} for user {user_id} (limit enforcement)"
            )

    @staticmethod
    def _session_to_dict(session: SessionData) -> Dict[str, Any]:
        """Convert SessionData to dictionary for JSON serialization.

        Args:
            session: Session to convert

        Returns:
            Dictionary representation
        """
        return {
            "session_id": session.session_id,
            "user_id": session.user_id,
            "title": session.title,
            "client_id": session.client_id,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "last_activity_at": session.last_activity_at.isoformat(),
            "status": session.status,
            "context": session.context,
            "messages": [
                {
                    "message_id": m.message_id,
                    "role": m.role,
                    "content": m.content,
                    "timestamp": m.timestamp.isoformat(),
                    "metadata": m.metadata,
                }
                for m in session.messages
            ],
            "metadata": session.metadata,
        }

    @staticmethod
    def _dict_to_session(data: Dict[str, Any]) -> SessionData:
        """Convert dictionary to SessionData.

        Args:
            data: Dictionary representation

        Returns:
            SessionData object
        """
        # Parse timestamps
        created_at = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        updated_at = datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))
        last_activity_at = datetime.fromisoformat(
            data["last_activity_at"].replace("Z", "+00:00")
        )

        # Parse messages
        messages = [
            Message(
                message_id=m["message_id"],
                role=m["role"],
                content=m["content"],
                timestamp=datetime.fromisoformat(
                    m["timestamp"].replace("Z", "+00:00")
                ),
                metadata=m.get("metadata", {}),
            )
            for m in data.get("messages", [])
        ]

        return SessionData(
            session_id=data["session_id"],
            user_id=data["user_id"],
            title=data.get("title"),
            client_id=data.get("client_id"),
            created_at=created_at,
            updated_at=updated_at,
            last_activity_at=last_activity_at,
            status=data.get("status", "active"),
            context=data.get("context", {}),
            messages=messages,
            metadata=data.get("metadata", {}),
        )
