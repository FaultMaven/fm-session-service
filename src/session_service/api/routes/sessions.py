"""Session API routes.

Implements REST API endpoints for session management.
Trust X-User-* headers from API Gateway - no JWT validation needed.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query, status
from fastapi.responses import Response

from session_service.models import (
    SessionCreate,
    SessionUpdate,
    SessionResponse,
    SessionListResponse,
    HeartbeatResponse,
)
from session_service.core import SessionManager
from session_service.infrastructure.redis import get_redis_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


async def get_session_manager() -> SessionManager:
    """Dependency to get SessionManager instance.

    Returns:
        SessionManager: Session manager with Redis client
    """
    redis_client = await get_redis_client()
    return SessionManager(redis_client)


async def get_user_id(
    x_user_id: Optional[str] = Header(None, alias="X-User-ID")
) -> str:
    """Extract user ID from X-User-ID header.

    The API Gateway validates JWT and adds X-User-* headers to requests.
    We trust these headers - no JWT validation needed in this service.

    Args:
        x_user_id: User ID from X-User-ID header

    Returns:
        str: User ID

    Raises:
        HTTPException: If X-User-ID header is missing
    """
    if not x_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-User-ID header is required (should be added by API Gateway)",
        )
    return x_user_id


@router.post("", status_code=status.HTTP_201_CREATED, response_model=SessionResponse)
async def create_session(
    request: SessionCreate,
    user_id: str = Depends(get_user_id),
    session_manager: SessionManager = Depends(get_session_manager),
):
    """Create a new session.

    Requires X-User-ID header from API Gateway.

    Args:
        request: Session creation request
        user_id: User ID from X-User-ID header
        session_manager: Session manager dependency

    Returns:
        SessionResponse: Created session data
    """
    try:
        # Prepare metadata
        metadata = request.metadata or {}
        if request.session_type:
            metadata["session_type"] = request.session_type
        if request.timeout_minutes:
            metadata["timeout_minutes"] = request.timeout_minutes

        # Create session
        session = await session_manager.create_session(
            user_id=user_id,
            client_id=request.client_id,
            metadata=metadata,
        )

        logger.info(
            f"Created session {session.session_id} for user {user_id} "
            f"(client_id={request.client_id})"
        )

        return SessionResponse(
            session_id=session.session_id,
            user_id=session.user_id,
            title=session.title,
            client_id=session.client_id,
            created_at=session.created_at,
            updated_at=session.updated_at,
            last_activity_at=session.last_activity_at,
            status=session.status,
            message_count=len(session.messages),
            metadata=session.metadata,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create session",
        )


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    user_id: str = Depends(get_user_id),
    session_manager: SessionManager = Depends(get_session_manager),
):
    """Get session by ID.

    Requires X-User-ID header from API Gateway.
    Users can only access their own sessions.

    Args:
        session_id: Session identifier
        user_id: User ID from X-User-ID header
        session_manager: Session manager dependency

    Returns:
        SessionResponse: Session data

    Raises:
        HTTPException: If session not found or unauthorized
    """
    try:
        session = await session_manager.get_session(session_id)

        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

        # Authorization check - users can only access their own sessions
        if session.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this session",
            )

        return SessionResponse(
            session_id=session.session_id,
            user_id=session.user_id,
            title=session.title,
            client_id=session.client_id,
            created_at=session.created_at,
            updated_at=session.updated_at,
            last_activity_at=session.last_activity_at,
            status=session.status,
            message_count=len(session.messages),
            metadata=session.metadata,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get session",
        )


@router.put("/{session_id}", response_model=SessionResponse)
async def update_session(
    session_id: str,
    updates: SessionUpdate,
    user_id: str = Depends(get_user_id),
    session_manager: SessionManager = Depends(get_session_manager),
):
    """Update session.

    Requires X-User-ID header from API Gateway.
    Users can only update their own sessions.

    Args:
        session_id: Session identifier
        updates: Session update data
        user_id: User ID from X-User-ID header
        session_manager: Session manager dependency

    Returns:
        SessionResponse: Updated session data

    Raises:
        HTTPException: If session not found or unauthorized
    """
    try:
        # First get session to check ownership
        existing_session = await session_manager.get_session(session_id)

        if not existing_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

        # Authorization check
        if existing_session.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update this session",
            )

        # Update session
        update_dict = updates.model_dump(exclude_none=True)
        session = await session_manager.update_session(session_id, update_dict)

        if not session:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update session",
            )

        logger.info(f"Updated session {session_id} for user {user_id}")

        return SessionResponse(
            session_id=session.session_id,
            user_id=session.user_id,
            title=session.title,
            client_id=session.client_id,
            created_at=session.created_at,
            updated_at=session.updated_at,
            last_activity_at=session.last_activity_at,
            status=session.status,
            message_count=len(session.messages),
            metadata=session.metadata,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update session",
        )


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    user_id: str = Depends(get_user_id),
    session_manager: SessionManager = Depends(get_session_manager),
):
    """Delete session.

    Requires X-User-ID header from API Gateway.
    Users can only delete their own sessions.

    Args:
        session_id: Session identifier
        user_id: User ID from X-User-ID header
        session_manager: Session manager dependency

    Returns:
        None (204 No Content)

    Raises:
        HTTPException: If session not found or unauthorized
    """
    try:
        # First get session to check ownership
        session = await session_manager.get_session(session_id)

        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

        # Authorization check
        if session.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete this session",
            )

        # Delete session
        success = await session_manager.delete_session(session_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete session",
            )

        logger.info(f"Deleted session {session_id} for user {user_id}")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete session",
        )


@router.post("/{session_id}/heartbeat", response_model=HeartbeatResponse)
async def session_heartbeat(
    session_id: str,
    user_id: str = Depends(get_user_id),
    session_manager: SessionManager = Depends(get_session_manager),
):
    """Update session heartbeat (last activity timestamp).

    Requires X-User-ID header from API Gateway.
    Users can only heartbeat their own sessions.

    Args:
        session_id: Session identifier
        user_id: User ID from X-User-ID header
        session_manager: Session manager dependency

    Returns:
        HeartbeatResponse: Updated heartbeat data

    Raises:
        HTTPException: If session not found or unauthorized
    """
    try:
        # First get session to check ownership
        existing_session = await session_manager.get_session(session_id)

        if not existing_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found or expired",
            )

        # Authorization check
        if existing_session.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this session",
            )

        # Update heartbeat
        session = await session_manager.heartbeat(session_id)

        if not session:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update heartbeat",
            )

        logger.debug(f"Heartbeat updated for session {session_id}")

        return HeartbeatResponse(
            session_id=session.session_id,
            last_activity_at=session.last_activity_at,
            status=session.status,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update heartbeat for session {session_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update heartbeat",
        )


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    user_id: str = Depends(get_user_id),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of sessions to return"),
    offset: int = Query(0, ge=0, description="Number of sessions to skip"),
    session_manager: SessionManager = Depends(get_session_manager),
):
    """List user's sessions.

    Requires X-User-ID header from API Gateway.
    Returns only sessions owned by the authenticated user.

    Args:
        user_id: User ID from X-User-ID header
        limit: Maximum number of sessions to return (1-100)
        offset: Number of sessions to skip
        session_manager: Session manager dependency

    Returns:
        SessionListResponse: List of sessions with pagination info
    """
    try:
        # Get user's sessions
        sessions = await session_manager.list_user_sessions(user_id, limit, offset)
        total = await session_manager.count_user_sessions(user_id)

        # Convert to response models
        session_responses = [
            SessionResponse(
                session_id=s.session_id,
                user_id=s.user_id,
                title=s.title,
                client_id=s.client_id,
                created_at=s.created_at,
                updated_at=s.updated_at,
                last_activity_at=s.last_activity_at,
                status=s.status,
                message_count=len(s.messages),
                metadata=s.metadata,
            )
            for s in sessions
        ]

        logger.debug(f"Listed {len(sessions)} sessions for user {user_id} (total: {total})")

        return SessionListResponse(
            sessions=session_responses,
            total=total,
            limit=limit,
            offset=offset,
        )

    except Exception as e:
        logger.error(f"Failed to list sessions for user {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list sessions",
        )


# =============================================================================
# Statistics & Extended Endpoints (Phase 4)
# =============================================================================

@router.get("/{session_id}/cases", summary="Get cases for this session")
async def get_session_cases(
    session_id: str,
    user_id: str = Depends(get_user_id),
    session_manager: SessionManager = Depends(get_session_manager),
):
    """Get all cases associated with this session.
    
    Makes HTTP call to fm-case-service to fetch cases.
    """
    try:
        # Verify session ownership
        session = await session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session {session_id} not found")
        if session.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        
        # TODO: Call fm-case-service via HTTP client to get cases for this session
        # For now, return placeholder
        return {
            "session_id": session_id,
            "cases": [],
            "total": 0
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get cases for session {session_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get cases")


@router.get("/{session_id}/stats", summary="Get session statistics")
async def get_session_stats(
    session_id: str,
    user_id: str = Depends(get_user_id),
    session_manager: SessionManager = Depends(get_session_manager),
):
    """Get detailed statistics for a session."""
    try:
        session = await session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session {session_id} not found")
        if session.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        
        # Calculate stats
        message_count = len(session.messages)
        duration_seconds = None
        if session.created_at and session.last_activity_at:
            delta = session.last_activity_at - session.created_at
            duration_seconds = int(delta.total_seconds())
        
        return {
            "session_id": session_id,
            "message_count": message_count,
            "duration_seconds": duration_seconds,
            "status": session.status,
            "created_at": session.created_at,
            "last_activity_at": session.last_activity_at,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get stats for session {session_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get stats")


# =============================================================================
# Message Management Endpoints (Phase 6.3)
# =============================================================================

@router.post("/{session_id}/messages", summary="Add message to session")
async def add_session_message(
    session_id: str,
    message_data: dict,
    user_id: str = Depends(get_user_id),
    session_manager: SessionManager = Depends(get_session_manager),
):
    """Add a message to the session."""
    try:
        session = await session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session {session_id} not found")
        if session.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        
        # Add message
        message = {
            "role": message_data.get("role", "user"),
            "content": message_data.get("content", ""),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        session.messages.append(message)
        
        # Update session
        await session_manager.update_session(session_id, {"messages": session.messages})
        
        return {"session_id": session_id, "message": message, "total_messages": len(session.messages)}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add message to session {session_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to add message")


@router.get("/{session_id}/messages", summary="Get session messages")
async def get_session_messages(
    session_id: str,
    user_id: str = Depends(get_user_id),
    limit: int = Query(100, ge=1, le=500),
    session_manager: SessionManager = Depends(get_session_manager),
):
    """Get all messages in a session."""
    try:
        session = await session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session {session_id} not found")
        if session.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        
        messages = session.messages[-limit:] if len(session.messages) > limit else session.messages
        
        return {
            "session_id": session_id,
            "messages": messages,
            "total": len(session.messages),
            "returned": len(messages)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get messages for session {session_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get messages")


# =============================================================================
# Search & Archive Endpoints (Phase 6.3)
# =============================================================================

@router.post("/search", summary="Search sessions")
async def search_sessions(
    search_params: dict,
    user_id: str = Depends(get_user_id),
    session_manager: SessionManager = Depends(get_session_manager),
):
    """Search sessions with filters."""
    try:
        # Get all user sessions
        all_sessions = await session_manager.list_user_sessions(user_id, limit=1000, offset=0)
        
        # Apply basic filters
        filtered = all_sessions
        
        if "status" in search_params:
            filtered = [s for s in filtered if s.status == search_params["status"]]
        
        if "query" in search_params:
            query = search_params["query"].lower()
            filtered = [s for s in filtered if query in s.title.lower()]
        
        return {
            "sessions": [
                {
                    "session_id": s.session_id,
                    "title": s.title,
                    "status": s.status,
                    "created_at": s.created_at,
                    "message_count": len(s.messages)
                }
                for s in filtered[:search_params.get("limit", 50)]
            ],
            "total": len(filtered)
        }
    
    except Exception as e:
        logger.error(f"Failed to search sessions: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to search sessions")


@router.post("/{session_id}/archive", summary="Archive session")
async def archive_session(
    session_id: str,
    user_id: str = Depends(get_user_id),
    session_manager: SessionManager = Depends(get_session_manager),
):
    """Archive a session."""
    try:
        session = await session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session {session_id} not found")
        if session.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        
        # Update status to archived
        await session_manager.update_session(session_id, {"status": "archived"})
        
        return {"session_id": session_id, "status": "archived"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to archive session {session_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to archive session")


@router.post("/{session_id}/restore", summary="Restore archived session")
async def restore_session(
    session_id: str,
    user_id: str = Depends(get_user_id),
    session_manager: SessionManager = Depends(get_session_manager),
):
    """Restore an archived session."""
    try:
        session = await session_manager.get_session(session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session {session_id} not found")
        if session.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        
        # Update status back to active
        await session_manager.update_session(session_id, {"status": "active"})
        
        return {"session_id": session_id, "status": "active"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to restore session {session_id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to restore session")
