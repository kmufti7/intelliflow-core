"""
Helpers module - Pure utility functions for IntelliFlow OS.

This module contains pure functions with no I/O operations, suitable for
use in both synchronous and asynchronous contexts across the platform.
"""

import uuid
from datetime import datetime
from typing import Optional


# Cost per 1K tokens for various models (USD)
MODEL_COSTS = {
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
}


def generate_event_id(prefix: str = "EVT") -> str:
    """
    Generate a unique event identifier.

    Args:
        prefix: Prefix for the event ID (default: "EVT")

    Returns:
        A unique identifier string in the format "{prefix}_{uuid}"

    Example:
        >>> event_id = generate_event_id("AUDIT")
        >>> event_id.startswith("AUDIT_")
        True
    """
    unique_part = uuid.uuid4().hex[:12].upper()
    return f"{prefix}_{unique_part}"


def format_timestamp(dt: Optional[datetime] = None) -> str:
    """
    Format a datetime object to ISO 8601 format string.

    Args:
        dt: Datetime object to format. If None, uses current UTC time.

    Returns:
        ISO 8601 formatted timestamp string.

    Example:
        >>> from datetime import datetime
        >>> dt = datetime(2024, 1, 15, 10, 30, 0)
        >>> format_timestamp(dt)
        '2024-01-15T10:30:00'
    """
    if dt is None:
        dt = datetime.utcnow()
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def format_timestamp_short(dt: Optional[datetime] = None) -> str:
    """
    Format a datetime object to a short, human-readable format.

    Args:
        dt: Datetime object to format. If None, uses current UTC time.

    Returns:
        Short formatted timestamp string (HH:MM:SS).

    Example:
        >>> from datetime import datetime
        >>> dt = datetime(2024, 1, 15, 10, 30, 45)
        >>> format_timestamp_short(dt)
        '10:30:45'
    """
    if dt is None:
        dt = datetime.utcnow()
    return dt.strftime("%H:%M:%S")


def truncate_text(text: str, max_length: int = 100) -> str:
    """
    Truncate text to a maximum length, adding ellipsis if truncated.

    Args:
        text: The text to truncate.
        max_length: Maximum length of the output string (default: 100).

    Returns:
        Truncated text with ellipsis if it exceeded max_length.

    Example:
        >>> truncate_text("Hello World", 5)
        'He...'
        >>> truncate_text("Hi", 100)
        'Hi'
    """
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    if max_length <= 3:
        return text[:max_length]
    return text[:max_length - 3] + "..."


def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    model: str = "gpt-4o-mini"
) -> float:
    """
    Calculate the cost of an AI model call based on token usage.

    Args:
        input_tokens: Number of input/prompt tokens.
        output_tokens: Number of output/completion tokens.
        model: Model name (default: "gpt-4o-mini").

    Returns:
        Calculated cost in USD, rounded to 6 decimal places.
        Returns 0.0 if model is not found in cost table.

    Example:
        >>> calculate_cost(1000, 500, "gpt-4o-mini")
        0.00045
    """
    if model not in MODEL_COSTS:
        return 0.0

    costs = MODEL_COSTS[model]
    input_cost = (input_tokens / 1000) * costs["input"]
    output_cost = (output_tokens / 1000) * costs["output"]

    return round(input_cost + output_cost, 6)
