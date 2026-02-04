"""
Governance UI module - Streamlit components for governance visualization.

This module provides reusable Streamlit components for displaying
governance logs and audit trails in the IntelliFlow OS applications.
"""

from datetime import datetime
from typing import Optional

import streamlit as st

from intelliflow_core.contracts import GovernanceLogEntry
from intelliflow_core.helpers import format_timestamp_short


def init_governance_state() -> None:
    """
    Initialize the governance state in Streamlit session state.

    This function should be called at the start of your Streamlit app
    to ensure the governance_logs list exists in session state.

    Example:
        >>> import streamlit as st
        >>> init_governance_state()
        >>> "governance_logs" in st.session_state
        True
    """
    if "governance_logs" not in st.session_state:
        st.session_state.governance_logs = []


def add_governance_log(
    component: str,
    action: str,
    success: bool = True,
    details: Optional[str] = None
) -> GovernanceLogEntry:
    """
    Add a new entry to the governance log.

    This function creates a GovernanceLogEntry and appends it to the
    session state governance_logs list. Call init_governance_state()
    before using this function.

    Args:
        component: Name of the component generating the log entry.
        action: Description of the action performed.
        success: Whether the action was successful (default: True).
        details: Optional additional details about the action.

    Returns:
        The created GovernanceLogEntry object.

    Example:
        >>> init_governance_state()
        >>> entry = add_governance_log(
        ...     component="Auth",
        ...     action="User login",
        ...     success=True,
        ...     details="User authenticated via SSO"
        ... )
        >>> entry.component
        'Auth'
    """
    # Ensure governance state is initialized
    init_governance_state()

    entry = GovernanceLogEntry(
        timestamp=datetime.utcnow(),
        component=component,
        action=action,
        success=success,
        details=details
    )

    st.session_state.governance_logs.append(entry)
    return entry


def render_governance_panel(title: str = "Governance Log") -> None:
    """
    Render the governance log panel in the Streamlit sidebar.

    This function displays all governance log entries in a scrollable
    panel within the Streamlit sidebar. Entries are shown in reverse
    chronological order (newest first).

    Args:
        title: Title for the governance panel (default: "Governance Log").

    Example:
        >>> import streamlit as st
        >>> init_governance_state()
        >>> add_governance_log("System", "Startup", True)
        >>> render_governance_panel("Audit Trail")
    """
    # Ensure governance state is initialized
    init_governance_state()

    with st.sidebar:
        st.subheader(title)

        logs = st.session_state.governance_logs

        if not logs:
            st.caption("No governance events recorded yet.")
            return

        # Display logs in reverse chronological order
        st.caption(f"Showing {len(logs)} event(s)")

        # Create a container for the logs with custom styling
        with st.container():
            for entry in reversed(logs):
                _render_log_entry(entry)


def _render_log_entry(entry: GovernanceLogEntry) -> None:
    """
    Render a single governance log entry.

    Internal function used by render_governance_panel to display
    individual log entries with appropriate styling.

    Args:
        entry: The GovernanceLogEntry to render.
    """
    # Determine status indicator
    status_icon = "✅" if entry.success else "❌"

    # Format the timestamp
    time_str = format_timestamp_short(entry.timestamp)

    # Create the log entry display
    with st.container():
        # Header line with time, status, and component
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(
                f"**{entry.component}** · {entry.action}",
                help=entry.details if entry.details else None
            )
        with col2:
            st.caption(f"{status_icon} {time_str}")

        # Show details if present
        if entry.details:
            st.caption(f"↳ {entry.details}")

        st.divider()
