"""
Configuration management module for the orchestration queue.

This module provides centralized, type-safe configuration management
using Pydantic Settings with:
- Environment variable loading
- Required vs optional field validation
- Custom validators for complex types
- Secret masking for safe logging
- Startup validation with clear error messages

Usage:
    from orchestration_queue.config import get_settings, validate_startup, ConfigurationError

    # At application startup:
    settings = validate_startup()

    # Later in the application:
    settings = get_settings()
    print(settings.github_repository)
    print(settings.sentinel_poll_interval)

    # Access via compatibility wrappers:
    print(settings.github.owner)
    print(settings.github.repo)

Environment Variables:
    See Settings class documentation for all supported variables.
"""

from orchestration_queue.config.exceptions import ConfigurationError
from orchestration_queue.config.settings import (
    AppEnv,
    GitHubConfig,
    NotifierConfig,
    SentinelConfig,
    Settings,
    clear_settings_cache,
    get_settings,
    validate_startup,
)

__all__ = [
    # Main functions
    "get_settings",
    "validate_startup",
    "clear_settings_cache",
    # Exception
    "ConfigurationError",
    # Settings classes
    "Settings",
    "AppEnv",
    # Compatibility wrappers
    "GitHubConfig",
    "SentinelConfig",
    "NotifierConfig",
]
