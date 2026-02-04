"""
Tests for intelliflow-core contracts and helpers.

This module tests:
- Pydantic schema validation
- Helper function behavior
- Edge cases and error handling
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from intelliflow_core.contracts import (
    AuditEventType,
    AuditEventSchema,
    CostTrackingSchema,
    GovernanceLogEntry,
)
from intelliflow_core.helpers import (
    generate_event_id,
    format_timestamp,
    format_timestamp_short,
    truncate_text,
    calculate_cost,
    MODEL_COSTS,
)


# =============================================================================
# AuditEventType Tests
# =============================================================================

class TestAuditEventType:
    """Tests for AuditEventType enum."""

    def test_event_types_exist(self):
        """Verify all expected event types are defined."""
        expected_types = [
            "USER_QUERY", "USER_FEEDBACK",
            "AI_RESPONSE", "AI_ESCALATION",
            "SYSTEM_ERROR", "SYSTEM_STARTUP", "SYSTEM_SHUTDOWN",
            "POLICY_CHECK", "POLICY_VIOLATION", "HUMAN_OVERRIDE",
            "DATA_ACCESS", "DATA_EXPORT",
            "AUTH_LOGIN", "AUTH_LOGOUT", "AUTH_FAILURE",
        ]
        for event_type in expected_types:
            assert hasattr(AuditEventType, event_type)

    def test_event_type_values_are_strings(self):
        """Verify event type values are lowercase strings."""
        for event_type in AuditEventType:
            assert isinstance(event_type.value, str)
            assert event_type.value == event_type.value.lower()


# =============================================================================
# AuditEventSchema Tests
# =============================================================================

class TestAuditEventSchema:
    """Tests for AuditEventSchema Pydantic model."""

    def test_valid_audit_event(self):
        """Test creating a valid audit event."""
        event = AuditEventSchema(
            event_id="EVT_123ABC",
            event_type=AuditEventType.USER_QUERY,
            component="ChatUI",
            action="User submitted query"
        )
        assert event.event_id == "EVT_123ABC"
        assert event.event_type == "user_query"
        assert event.component == "ChatUI"
        assert event.action == "User submitted query"
        assert event.success is True
        assert event.user_id is None

    def test_audit_event_with_all_fields(self):
        """Test audit event with all optional fields."""
        event = AuditEventSchema(
            event_id="EVT_456DEF",
            event_type=AuditEventType.AI_RESPONSE,
            component="AIEngine",
            action="Generated response",
            user_id="user_001",
            session_id="sess_abc123",
            success=True,
            details={"tokens": 150, "model": "gpt-4o-mini"},
            metadata={"version": "1.0"}
        )
        assert event.user_id == "user_001"
        assert event.session_id == "sess_abc123"
        assert event.details["tokens"] == 150
        assert event.metadata["version"] == "1.0"

    def test_audit_event_missing_required_fields(self):
        """Test that missing required fields raise ValidationError."""
        with pytest.raises(ValidationError):
            AuditEventSchema(
                event_id="EVT_123",
                event_type=AuditEventType.USER_QUERY
                # Missing component and action
            )

    def test_audit_event_default_timestamp(self):
        """Test that timestamp defaults to current UTC time."""
        before = datetime.utcnow()
        event = AuditEventSchema(
            event_id="EVT_789",
            event_type=AuditEventType.SYSTEM_STARTUP,
            component="System",
            action="Application started"
        )
        after = datetime.utcnow()
        assert before <= event.timestamp <= after


# =============================================================================
# CostTrackingSchema Tests
# =============================================================================

class TestCostTrackingSchema:
    """Tests for CostTrackingSchema Pydantic model."""

    def test_valid_cost_tracking(self):
        """Test creating a valid cost tracking entry."""
        cost = CostTrackingSchema(
            event_id="EVT_COST_001",
            model="gpt-4o-mini",
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            cost_usd=0.00045
        )
        assert cost.event_id == "EVT_COST_001"
        assert cost.model == "gpt-4o-mini"
        assert cost.input_tokens == 1000
        assert cost.output_tokens == 500
        assert cost.total_tokens == 1500
        assert cost.cost_usd == 0.00045

    def test_cost_tracking_negative_tokens_rejected(self):
        """Test that negative token counts are rejected."""
        with pytest.raises(ValidationError):
            CostTrackingSchema(
                event_id="EVT_BAD",
                model="gpt-4o-mini",
                input_tokens=-100,
                output_tokens=500,
                total_tokens=400,
                cost_usd=0.0
            )

    def test_cost_tracking_negative_cost_rejected(self):
        """Test that negative costs are rejected."""
        with pytest.raises(ValidationError):
            CostTrackingSchema(
                event_id="EVT_BAD",
                model="gpt-4o-mini",
                input_tokens=100,
                output_tokens=500,
                total_tokens=600,
                cost_usd=-0.001
            )


# =============================================================================
# GovernanceLogEntry Tests
# =============================================================================

class TestGovernanceLogEntry:
    """Tests for GovernanceLogEntry Pydantic model."""

    def test_valid_governance_log_entry(self):
        """Test creating a valid governance log entry."""
        entry = GovernanceLogEntry(
            component="Auth",
            action="User login"
        )
        assert entry.component == "Auth"
        assert entry.action == "User login"
        assert entry.success is True
        assert entry.details is None

    def test_governance_log_entry_with_details(self):
        """Test governance log entry with all fields."""
        entry = GovernanceLogEntry(
            component="PolicyEngine",
            action="Compliance check",
            success=False,
            details="Policy violation: PII detected"
        )
        assert entry.success is False
        assert entry.details == "Policy violation: PII detected"

    def test_governance_log_entry_json_serialization(self):
        """Test that GovernanceLogEntry serializes to JSON correctly."""
        entry = GovernanceLogEntry(
            component="Test",
            action="Serialize"
        )
        json_dict = entry.model_dump()
        assert "timestamp" in json_dict
        assert json_dict["component"] == "Test"


# =============================================================================
# Helper Function Tests
# =============================================================================

class TestGenerateEventId:
    """Tests for generate_event_id helper function."""

    def test_default_prefix(self):
        """Test generate_event_id with default prefix."""
        event_id = generate_event_id()
        assert event_id.startswith("EVT_")
        assert len(event_id) == 16  # EVT_ + 12 chars

    def test_custom_prefix(self):
        """Test generate_event_id with custom prefix."""
        event_id = generate_event_id("AUDIT")
        assert event_id.startswith("AUDIT_")

    def test_uniqueness(self):
        """Test that generated IDs are unique."""
        ids = [generate_event_id() for _ in range(100)]
        assert len(ids) == len(set(ids))

    def test_uppercase_suffix(self):
        """Test that the UUID portion is uppercase."""
        event_id = generate_event_id()
        suffix = event_id.split("_")[1]
        assert suffix == suffix.upper()


class TestFormatTimestamp:
    """Tests for format_timestamp helper function."""

    def test_specific_datetime(self):
        """Test formatting a specific datetime."""
        dt = datetime(2024, 6, 15, 14, 30, 45)
        result = format_timestamp(dt)
        assert result == "2024-06-15T14:30:45"

    def test_none_uses_current_time(self):
        """Test that None defaults to current UTC time."""
        before = datetime.utcnow()
        result = format_timestamp(None)
        after = datetime.utcnow()

        # Parse the result and verify it's within the time window
        parsed = datetime.strptime(result, "%Y-%m-%dT%H:%M:%S")
        assert before.replace(microsecond=0) <= parsed <= after.replace(microsecond=0)


class TestFormatTimestampShort:
    """Tests for format_timestamp_short helper function."""

    def test_specific_datetime(self):
        """Test short formatting of a specific datetime."""
        dt = datetime(2024, 6, 15, 9, 5, 3)
        result = format_timestamp_short(dt)
        assert result == "09:05:03"

    def test_none_uses_current_time(self):
        """Test that None defaults to current UTC time."""
        result = format_timestamp_short(None)
        # Just verify format is correct (HH:MM:SS)
        parts = result.split(":")
        assert len(parts) == 3
        assert all(len(p) == 2 for p in parts)


class TestTruncateText:
    """Tests for truncate_text helper function."""

    def test_short_text_unchanged(self):
        """Test that short text is not truncated."""
        result = truncate_text("Hello", 100)
        assert result == "Hello"

    def test_exact_length_unchanged(self):
        """Test that text at exact length is not truncated."""
        result = truncate_text("Hello", 5)
        assert result == "Hello"

    def test_long_text_truncated(self):
        """Test that long text is truncated with ellipsis."""
        result = truncate_text("Hello World", 8)
        assert result == "Hello..."
        assert len(result) == 8

    def test_very_short_max_length(self):
        """Test truncation with very short max length."""
        result = truncate_text("Hello", 3)
        assert result == "Hel"
        assert len(result) == 3

    def test_empty_string(self):
        """Test truncating an empty string."""
        result = truncate_text("", 100)
        assert result == ""

    def test_default_max_length(self):
        """Test default max_length of 100."""
        text = "x" * 150
        result = truncate_text(text)
        assert len(result) == 100
        assert result.endswith("...")


class TestCalculateCost:
    """Tests for calculate_cost helper function."""

    def test_gpt4o_mini_cost(self):
        """Test cost calculation for gpt-4o-mini."""
        # 1000 input + 500 output
        # Input: (1000/1000) * 0.00015 = 0.00015
        # Output: (500/1000) * 0.0006 = 0.0003
        # Total: 0.00045
        result = calculate_cost(1000, 500, "gpt-4o-mini")
        assert result == 0.00045

    def test_gpt4o_cost(self):
        """Test cost calculation for gpt-4o."""
        # 1000 input + 1000 output
        # Input: (1000/1000) * 0.005 = 0.005
        # Output: (1000/1000) * 0.015 = 0.015
        # Total: 0.02
        result = calculate_cost(1000, 1000, "gpt-4o")
        assert result == 0.02

    def test_unknown_model_returns_zero(self):
        """Test that unknown models return 0.0 cost."""
        result = calculate_cost(1000, 1000, "unknown-model")
        assert result == 0.0

    def test_zero_tokens(self):
        """Test cost calculation with zero tokens."""
        result = calculate_cost(0, 0, "gpt-4o-mini")
        assert result == 0.0

    def test_default_model(self):
        """Test that default model is gpt-4o-mini."""
        result = calculate_cost(1000, 500)
        expected = calculate_cost(1000, 500, "gpt-4o-mini")
        assert result == expected

    def test_all_supported_models(self):
        """Test that all models in MODEL_COSTS work correctly."""
        for model in MODEL_COSTS.keys():
            result = calculate_cost(1000, 1000, model)
            assert isinstance(result, float)
            assert result >= 0
