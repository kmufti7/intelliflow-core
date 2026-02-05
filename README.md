# IntelliFlow Core

Shared components for the **IntelliFlow OS** platform - a governance-first AI system.

## Overview

IntelliFlow Core provides the foundational building blocks shared between:
- [SupportFlow](https://github.com/kmufti7/intelliflow-supportflow) - Banking AI Assistant
- [CareFlow](https://github.com/kmufti7/intelliflow-careflow) - Healthcare AI Assistant

## What's Included

### Governance UI (`governance_ui.py`)
Streamlit components for real-time governance visualization:
- `init_governance_state()` - Initialize session state for governance logging
- `add_governance_log(component, action, success, details)` - Add governance entries
- `render_governance_panel(title)` - Render sidebar governance panel

### Contracts (`contracts.py`)
Pydantic models for type-safe data contracts:
- `AuditEventType` - Enum of audit event categories
- `AuditEventSchema` - Full audit event model
- `CostTrackingSchema` - AI usage cost tracking
- `GovernanceLogEntry` - Simplified log entry for UI

### Helpers (`helpers.py`)
Pure utility functions (no I/O):
- `generate_event_id(prefix)` - Generate unique event IDs
- `format_timestamp(dt)` - ISO 8601 timestamp formatting
- `format_timestamp_short(dt)` - Short time format (HH:MM:SS)
- `truncate_text(text, max_length)` - Truncate with ellipsis
- `calculate_cost(input_tokens, output_tokens, model)` - Calculate AI costs

## Installation

### From Source (Development)

```bash
git clone https://github.com/kmufti7/intelliflow-core.git
cd intelliflow-core
pip install -e ".[dev]"
```

### As Dependency

Add to your `pyproject.toml`:

```toml
dependencies = [
    "intelliflow-core @ git+https://github.com/kmufti7/intelliflow-core.git",
]
```

Or install directly:

```bash
pip install git+https://github.com/kmufti7/intelliflow-core.git
```

## Usage

### Governance UI in Streamlit

```python
import streamlit as st
from intelliflow_core import (
    init_governance_state,
    add_governance_log,
    render_governance_panel
)

# Initialize at app start
init_governance_state()

# Log governance events throughout your app
add_governance_log(
    component="Auth",
    action="User login",
    success=True,
    details="SSO authentication"
)

# Render in sidebar
render_governance_panel("Audit Trail")
```

### Using Contracts

```python
from intelliflow_core import (
    AuditEventType,
    AuditEventSchema,
    CostTrackingSchema
)

# Create audit event
event = AuditEventSchema(
    event_id="EVT_123ABC",
    event_type=AuditEventType.AI_RESPONSE,
    component="ChatEngine",
    action="Generated response",
    details={"model": "gpt-4o-mini", "tokens": 150}
)

# Track costs
cost = CostTrackingSchema(
    event_id=event.event_id,
    model="gpt-4o-mini",
    input_tokens=100,
    output_tokens=50,
    total_tokens=150,
    cost_usd=0.000045
)
```

### Using Helpers

```python
from intelliflow_core import (
    generate_event_id,
    format_timestamp,
    calculate_cost,
    truncate_text
)

# Generate unique event ID
event_id = generate_event_id("AUDIT")  # "AUDIT_A1B2C3D4E5F6"

# Format timestamps
timestamp = format_timestamp()  # "2024-06-15T14:30:45"

# Calculate AI costs
cost = calculate_cost(1000, 500, "gpt-4o-mini")  # 0.00045

# Truncate long text
summary = truncate_text(long_response, 100)  # "First 97 chars..."
```

## Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v
```

## Requirements

- Python >= 3.9
- pydantic >= 2.0
- streamlit >= 1.28.0

## Disclaimer

This is a **portfolio reference implementation** demonstrating PHI-aware architectural patterns with synthetic data.

- **Not a certified medical device**
- **Not a production HIPAA-compliant system**
- **Demonstrates compliance-informed design patterns for regulated industries**

## License

MIT
