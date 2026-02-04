"""
Contracts module - Pydantic models and event schemas for IntelliFlow OS.

This module defines the shared data contracts used across SupportFlow
and CareFlow applications for audit events, cost tracking, and governance logging.
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

from pydantic import BaseModel, ConfigDict, Field


class AuditEventType(str, Enum):
    """Enumeration of audit event types for governance tracking."""

    # User interactions
    USER_QUERY = "user_query"
    USER_FEEDBACK = "user_feedback"

    # AI operations
    AI_RESPONSE = "ai_response"
    AI_ESCALATION = "ai_escalation"

    # System events
    SYSTEM_ERROR = "system_error"
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"

    # Governance events
    POLICY_CHECK = "policy_check"
    POLICY_VIOLATION = "policy_violation"
    HUMAN_OVERRIDE = "human_override"

    # Data operations
    DATA_ACCESS = "data_access"
    DATA_EXPORT = "data_export"

    # Authentication
    AUTH_LOGIN = "auth_login"
    AUTH_LOGOUT = "auth_logout"
    AUTH_FAILURE = "auth_failure"


class AuditEventSchema(BaseModel):
    """
    Schema for audit events in the IntelliFlow OS governance system.

    This model captures all information needed for compliance auditing
    and governance tracking across both SupportFlow and CareFlow.
    """

    event_id: str = Field(
        ...,
        description="Unique identifier for the audit event"
    )
    event_type: AuditEventType = Field(
        ...,
        description="Type of the audit event"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp when the event occurred"
    )
    component: str = Field(
        ...,
        description="Component or module that generated the event"
    )
    action: str = Field(
        ...,
        description="Specific action that was performed"
    )
    user_id: Optional[str] = Field(
        default=None,
        description="ID of the user associated with the event"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session identifier for tracking user sessions"
    )
    success: bool = Field(
        default=True,
        description="Whether the action completed successfully"
    )
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional event-specific details"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional metadata for extended tracking"
    )

    model_config = ConfigDict(use_enum_values=True)


class CostTrackingSchema(BaseModel):
    """
    Schema for tracking AI model usage costs.

    Captures token usage and cost calculations for budget monitoring
    and cost allocation across the IntelliFlow OS platform.
    """

    event_id: str = Field(
        ...,
        description="Unique identifier linking to the audit event"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC timestamp of the cost event"
    )
    model: str = Field(
        ...,
        description="AI model used (e.g., 'gpt-4o-mini', 'gpt-4o')"
    )
    input_tokens: int = Field(
        ...,
        ge=0,
        description="Number of input/prompt tokens"
    )
    output_tokens: int = Field(
        ...,
        ge=0,
        description="Number of output/completion tokens"
    )
    total_tokens: int = Field(
        ...,
        ge=0,
        description="Total tokens used (input + output)"
    )
    cost_usd: float = Field(
        ...,
        ge=0.0,
        description="Calculated cost in USD"
    )
    component: Optional[str] = Field(
        default=None,
        description="Component that incurred the cost"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session identifier for cost allocation"
    )


class GovernanceLogEntry(BaseModel):
    """
    Schema for governance log entries displayed in the UI.

    This is a simplified view of governance events optimized for
    real-time display in the Streamlit sidebar governance panel.
    """

    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the governance event occurred"
    )
    component: str = Field(
        ...,
        description="Component that generated the log entry"
    )
    action: str = Field(
        ...,
        description="Action that was performed"
    )
    success: bool = Field(
        default=True,
        description="Whether the action was successful"
    )
    details: Optional[str] = Field(
        default=None,
        description="Human-readable details about the event"
    )
