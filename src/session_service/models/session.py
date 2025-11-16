"""Session data models for fm-session-service.

This module defines the core session data structures based on the
FaultMaven monolith session implementation.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class Message(BaseModel):
    """Message within a session conversation."""

    message_id: str = Field(..., description="Unique message identifier")
    role: str = Field(..., description="Message role (user, assistant, system)")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Message timestamp"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional message metadata"
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + 'Z' if v.tzinfo else v.isoformat()
        }


class SessionData(BaseModel):
    """Session data model - represents a troubleshooting session.

    This model is based on the FaultMaven monolith SessionContext but simplified
    for microservice usage. Sessions track user authentication and conversation state.
    """

    # Core identifiers
    session_id: str = Field(..., description="Unique session identifier (UUID)")
    user_id: str = Field(..., description="User identifier from X-User-ID header")

    # Optional metadata
    title: Optional[str] = Field(None, description="Session title (auto-generated from first message)")
    client_id: Optional[str] = Field(None, description="Client/device identifier for multi-device support")

    # Timestamps
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Session creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last update timestamp"
    )
    last_activity_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last activity timestamp (for heartbeat)"
    )

    # Status
    status: str = Field(default="active", description="Session status (active, archived, deleted)")

    # Session content
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Troubleshooting context and state"
    )
    messages: List[Message] = Field(
        default_factory=list,
        description="Conversation messages"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional session metadata (session_type, timeout_minutes, etc.)"
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + 'Z' if v.tzinfo else v.isoformat()
        }


class SessionCreate(BaseModel):
    """Request model for creating a new session."""

    timeout_minutes: Optional[int] = Field(
        default=180,
        ge=60,
        le=480,
        description="Session timeout in minutes (60-480)"
    )
    session_type: Optional[str] = Field(
        default="troubleshooting",
        description="Type of session"
    )
    client_id: Optional[str] = Field(
        None,
        description="Client/device identifier for session resumption"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional session metadata"
    )


class SessionUpdate(BaseModel):
    """Request model for updating a session."""

    title: Optional[str] = None
    status: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        # Only include fields that are set
        exclude_none = True


class SessionResponse(BaseModel):
    """Response model for session operations."""

    session_id: str
    user_id: str
    title: Optional[str] = None
    client_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    last_activity_at: datetime
    status: str
    message_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + 'Z' if v.tzinfo else v.isoformat()
        }


class SessionListResponse(BaseModel):
    """Response model for listing sessions."""

    sessions: List[SessionResponse]
    total: int
    limit: int
    offset: int


class HeartbeatResponse(BaseModel):
    """Response model for heartbeat endpoint."""

    session_id: str
    last_activity_at: datetime
    status: str
    message: str = "Heartbeat updated"

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() + 'Z' if v.tzinfo else v.isoformat()
        }
