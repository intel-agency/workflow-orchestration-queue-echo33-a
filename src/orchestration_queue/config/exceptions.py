"""
Configuration exceptions for the orchestration queue.

This module provides custom exceptions and error formatting utilities
for configuration validation failures.
"""

from typing import Any


class ConfigurationError(Exception):
    """
    Exception raised when configuration validation fails.

    This exception provides clear, actionable error messages that help
    developers identify exactly which environment variables are missing
    or invalid.

    Attributes:
        message: Human-readable error message.
        field_name: The name of the problematic field.
        expected_type: The expected type or format.
        field_value: The actual value (masked for secrets).
    """

    def __init__(
        self,
        message: str,
        field_name: str | None = None,
        expected_type: str | None = None,
        field_value: Any = None,
    ) -> None:
        """Initialize the configuration error."""
        super().__init__(message)
        self.message = message
        self.field_name = field_name
        self.expected_type = expected_type
        self.field_value = field_value

    def __str__(self) -> str:
        """Return a formatted error message."""
        parts = [self.message]
        if self.field_name:
            parts.append(f"Field: {self.field_name}")
        if self.expected_type:
            parts.append(f"Expected: {self.expected_type}")
        return "\n".join(parts)


def format_missing_required(field_name: str, env_var: str) -> str:
    """
    Format a clear error message for missing required variables.

    Args:
        field_name: The human-readable field name.
        env_var: The environment variable name.

    Returns:
        Formatted error message with actionable guidance.
    """
    return (
        f"Missing required configuration: {field_name}\n"
        f"  Set the environment variable: {env_var}\n"
        f"  Example: export {env_var}=<your-value>\n"
        f"  Or add to .env file: {env_var}=<your-value>"
    )


def format_validation_error(
    field_name: str,
    expected_type: str,
    actual_value: Any,
    env_var: str,
) -> str:
    """
    Format a clear error message for validation failures.

    Args:
        field_name: The human-readable field name.
        expected_type: Description of expected type or format.
        actual_value: The invalid value (will be masked for secrets).
        env_var: The environment variable name.

    Returns:
        Formatted error message with actionable guidance.
    """
    # Mask the value if it looks like a secret
    display_value = mask_value_if_secret(str(actual_value), env_var)

    return (
        f"Invalid configuration for {field_name}\n"
        f"  Expected: {expected_type}\n"
        f"  Got: {display_value}\n"
        f"  Environment variable: {env_var}\n"
        f"  Please check the value and try again."
    )


def mask_value_if_secret(value: str, env_var: str) -> str:
    """
    Mask a value if it appears to be a secret.

    Args:
        value: The value to potentially mask.
        env_var: The environment variable name (used to detect secrets).

    Returns:
        Masked value if it looks like a secret, otherwise the original.
    """
    secret_patterns = [
        "TOKEN",
        "SECRET",
        "KEY",
        "PASSWORD",
        "CREDENTIAL",
        "API_KEY",
    ]

    is_secret = any(pattern in env_var.upper() for pattern in secret_patterns)

    if is_secret:
        if len(value) <= 4:
            return "***MASKED***"
        # Show first 4 characters and mask the rest
        return f"{value[:4]}...***MASKED***"

    return value
