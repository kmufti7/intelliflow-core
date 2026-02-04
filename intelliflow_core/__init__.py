"""
IntelliFlow Core - Shared components for IntelliFlow OS platform.

This package provides governance UI components, contracts (Pydantic models),
and helper utilities shared between SupportFlow and CareFlow applications.
"""

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
)
from intelliflow_core.governance_ui import (
    init_governance_state,
    add_governance_log,
    render_governance_panel,
)

__version__ = "0.1.0"

__all__ = [
    # Contracts
    "AuditEventType",
    "AuditEventSchema",
    "CostTrackingSchema",
    "GovernanceLogEntry",
    # Helpers
    "generate_event_id",
    "format_timestamp",
    "format_timestamp_short",
    "truncate_text",
    "calculate_cost",
    # Governance UI
    "init_governance_state",
    "add_governance_log",
    "render_governance_panel",
]
