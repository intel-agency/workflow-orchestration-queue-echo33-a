"""
Custom validators for configuration values.

This module provides validation functions for complex configuration types
like GitHub repository formats, URLs, and positive integers.
"""

import re
from typing import Any

from orchestration_queue.config.exceptions import ConfigurationError


def validate_repository_format(value: str) -> tuple[str, str]:
    """
    Validate and parse a GitHub repository string in 'owner/repo' format.

    Args:
        value: The repository string to validate.

    Returns:
        Tuple of (owner, repo).

    Raises:
        ConfigurationError: If the format is invalid.
    """
    pattern = r"^([a-zA-Z0-9_-]+)/([a-zA-Z0-9_.-]+)$"
    match = re.match(pattern, value)

    if not match:
        raise ConfigurationError(
            f"Invalid repository format: '{value}'",
            field_name="repository",
            expected_type="owner/repo (e.g., 'octocat/Hello-World')",
            field_value=value,
        )

    return match.group(1), match.group(2)


def validate_url(value: str, field_name: str = "url") -> str:
    """
    Validate that a string is a valid URL.

    Args:
        value: The URL string to validate.
        field_name: The field name for error messages.

    Returns:
        The validated URL string.

    Raises:
        ConfigurationError: If the URL format is invalid.
    """
    url_pattern = r"^https?://[^\s/$.?#].[^\s]*$"

    if not re.match(url_pattern, value, re.IGNORECASE):
        raise ConfigurationError(
            f"Invalid URL format: '{value}'",
            field_name=field_name,
            expected_type="Valid HTTP/HTTPS URL",
            field_value=value,
        )

    return value


def validate_positive_int(
    value: int,
    field_name: str,
    min_value: int = 1,
    max_value: int | None = None,
) -> int:
    """
    Validate that an integer is positive and within an optional range.

    Args:
        value: The integer value to validate.
        field_name: The field name for error messages.
        min_value: Minimum allowed value (default: 1).
        max_value: Maximum allowed value (optional).

    Returns:
        The validated integer.

    Raises:
        ConfigurationError: If the value is out of range.
    """
    if value < min_value:
        raise ConfigurationError(
            f"Value {value} is below minimum {min_value}",
            field_name=field_name,
            expected_type=f"Integer >= {min_value}",
            field_value=value,
        )

    if max_value is not None and value > max_value:
        raise ConfigurationError(
            f"Value {value} exceeds maximum {max_value}",
            field_name=field_name,
            expected_type=f"Integer <= {max_value}",
            field_value=value,
        )

    return value


def validate_positive_float(
    value: float,
    field_name: str,
    min_value: float = 0.0,
    max_value: float | None = None,
) -> float:
    """
    Validate that a float is positive and within an optional range.

    Args:
        value: The float value to validate.
        field_name: The field name for error messages.
        min_value: Minimum allowed value (default: 0.0).
        max_value: Maximum allowed value (optional).

    Returns:
        The validated float.

    Raises:
        ConfigurationError: If the value is out of range.
    """
    if value < min_value:
        raise ConfigurationError(
            f"Value {value} is below minimum {min_value}",
            field_name=field_name,
            expected_type=f"Number >= {min_value}",
            field_value=value,
        )

    if max_value is not None and value > max_value:
        raise ConfigurationError(
            f"Value {value} exceeds maximum {max_value}",
            field_name=field_name,
            expected_type=f"Number <= {max_value}",
            field_value=value,
        )

    return value


def mask_secret(value: str, visible_chars: int = 4) -> str:
    """
    Mask a secret value for safe logging.

    Args:
        value: The secret value to mask.
        visible_chars: Number of characters to show at the start.

    Returns:
        Masked string safe for logging.
    """
    if not value:
        return "***EMPTY***"

    if len(value) <= visible_chars:
        return "***MASKED***"

    return f"{value[:visible_chars]}...***MASKED***"


def is_secret_field(field_name: str) -> bool:
    """
    Determine if a field name likely contains a secret.

    Args:
        field_name: The field name to check.

    Returns:
        True if the field appears to be a secret.
    """
    secret_patterns = [
        "token",
        "secret",
        "key",
        "password",
        "credential",
        "api_key",
    ]

    return any(pattern in field_name.lower() for pattern in secret_patterns)


def safe_repr(value: Any, field_name: str) -> str:
    """
    Create a safe string representation of a value, masking secrets.

    Args:
        value: The value to represent.
        field_name: The field name (used to detect secrets).

    Returns:
        Safe string representation.
    """
    if value is None:
        return "None"

    str_value = str(value)

    if is_secret_field(field_name):
        return mask_secret(str_value)

    # Truncate long values
    if len(str_value) > 100:
        return f"{str_value[:100]}..."

    return str_value
