"""
Centralized configuration management using Pydantic Settings.

This module provides type-safe configuration with:
- Environment variable loading
- Required vs optional field validation
- Custom validators for complex types
- Secret masking for safe logging
- Startup validation with clear error messages
"""

import logging
from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from orchestration_queue.config.exceptions import ConfigurationError

logger = logging.getLogger(__name__)


class AppEnv(StrEnum):
    """Application environment enumeration."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"

    def is_production(self) -> bool:
        """Check if this is a production environment."""
        return self == AppEnv.PRODUCTION

    def is_development(self) -> bool:
        """Check if this is a development environment."""
        return self == AppEnv.DEVELOPMENT


class Settings(BaseSettings):
    """
    Main application settings combining all configuration sections.

    This class provides a single point of access for all configuration
    through the get_settings() function.

    Environment Variables:
        APP_ENV: Application environment (development/staging/production/testing)
        LOG_LEVEL: Logging level (DEBUG/INFO/WARNING/ERROR/CRITICAL)

    GitHub Configuration:
        GITHUB_TOKEN: GitHub Personal Access Token (required)
        GITHUB_REPOSITORY: Repository in 'owner/repo' format (required)

    Sentinel Configuration:
        SENTINEL_BOT_LOGIN: GitHub username for task claiming
        SENTINEL_POLL_INTERVAL: Seconds between polls (default: 60)
        SENTINEL_HEARTBEAT_INTERVAL: Seconds between heartbeats (default: 300)
        SENTINEL_SUBPROCESS_TIMEOUT: Max subprocess seconds (default: 5700)
        SENTINEL_BACKOFF_BASE_SECONDS: Base backoff (default: 5)
        SENTINEL_BACKOFF_MAX_SECONDS: Max backoff (default: 300)
        SENTINEL_SHELL_BRIDGE_PATH: Path to shell bridge script

    Notifier Configuration:
        NOTIFIER_WEBHOOK_SECRET: Secret for webhook verification
        NOTIFIER_SERVICE_NAME: Service name for logging
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",  # Allow extra fields for compatibility wrappers
        case_sensitive=False,
    )

    # =========================================================================
    # Application-level settings
    # =========================================================================
    app_env: Annotated[
        AppEnv,
        Field(
            default=AppEnv.DEVELOPMENT,
            description="Application environment",
        ),
    ]

    log_level: Annotated[
        str,
        Field(
            default="INFO",
            description="Logging level (DEBUG/INFO/WARNING/ERROR/CRITICAL)",
        ),
    ]

    # =========================================================================
    # GitHub Configuration
    # =========================================================================
    github_token: Annotated[
        str,
        Field(
            default="",
            description="GitHub Personal Access Token with repo scope",
        ),
    ]

    github_repository: Annotated[
        str,
        Field(
            default="",
            description="Repository in 'owner/repo' format",
        ),
    ]

    # =========================================================================
    # Notifier Configuration
    # =========================================================================
    notifier_webhook_secret: Annotated[
        str,
        Field(
            default="",
            description="Secret for verifying GitHub webhook signatures",
        ),
    ]

    notifier_service_name: Annotated[
        str,
        Field(
            default="workflow-orchestration-queue",
            description="Service name for logging and identification",
        ),
    ]

    # =========================================================================
    # Sentinel Configuration
    # =========================================================================
    sentinel_bot_login: Annotated[
        str,
        Field(
            default="",
            description="GitHub username for the sentinel bot (used for task claiming)",
        ),
    ]

    sentinel_poll_interval: Annotated[
        float,
        Field(
            default=60.0,
            ge=1.0,
            le=3600.0,
            description="Seconds between polling cycles",
        ),
    ]

    sentinel_heartbeat_interval: Annotated[
        float,
        Field(
            default=300.0,
            ge=10.0,
            le=3600.0,
            description="Seconds between heartbeat posts",
        ),
    ]

    sentinel_subprocess_timeout: Annotated[
        float,
        Field(
            default=5700.0,
            ge=60.0,
            le=86400.0,
            description="Maximum seconds for subprocess execution (safety net)",
        ),
    ]

    sentinel_backoff_base_seconds: Annotated[
        float,
        Field(
            default=5.0,
            ge=1.0,
            le=60.0,
            description="Base backoff interval for error recovery",
        ),
    ]

    sentinel_backoff_max_seconds: Annotated[
        float,
        Field(
            default=300.0,
            ge=10.0,
            le=3600.0,
            description="Maximum backoff interval (cap)",
        ),
    ]

    sentinel_shell_bridge_path: Annotated[
        str,
        Field(
            default="./scripts/devcontainer-opencode.sh",
            description="Path to the shell bridge script",
        ),
    ]

    # =========================================================================
    # Computed properties for backward compatibility
    # =========================================================================

    @property
    def github_owner(self) -> str:
        """Get the repository owner."""
        if "/" in self.github_repository:
            return self.github_repository.split("/", 1)[0]
        return ""

    @property
    def github_repo(self) -> str:
        """Get the repository name."""
        if "/" in self.github_repository:
            return self.github_repository.split("/", 1)[1]
        return ""

    # =========================================================================
    # Validators
    # =========================================================================

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is a valid Python logging level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        upper_v = v.upper()
        if upper_v not in valid_levels:
            raise ValueError(f"Invalid log level: '{v}'. Must be one of: {', '.join(valid_levels)}")
        return upper_v

    @field_validator("github_repository")
    @classmethod
    def validate_github_repository(cls, v: str) -> str:
        """Validate repository format. Empty string is allowed."""
        if not v:
            return v

        import re

        pattern = r"^([a-zA-Z0-9_-]+)/([a-zA-Z0-9_.-]+)$"
        if not re.match(pattern, v):
            raise ValueError(
                f"Invalid repository format: '{v}'. Expected 'owner/repo' (e.g., 'octocat/Hello-World')"
            )
        return v

    # =========================================================================
    # Helper methods
    # =========================================================================

    def get_masked_token(self) -> str:
        """Return a masked version of the GitHub token for safe logging."""
        if not self.github_token:
            return "***EMPTY***"
        if len(self.github_token) <= 8:
            return "***MASKED***"
        return f"{self.github_token[:4]}...{self.github_token[-4:]}"

    def get_masked_webhook_secret(self) -> str:
        """Return a masked version of the webhook secret for safe logging."""
        if not self.notifier_webhook_secret:
            return "***NOT SET***"
        if len(self.notifier_webhook_secret) <= 8:
            return "***MASKED***"
        return f"{self.notifier_webhook_secret[:4]}...***MASKED***"

    def get_masked_config_summary(self) -> dict[str, Any]:
        """
        Get a summary of the configuration with secrets masked.

        This is safe to log and includes all configuration values
        with sensitive fields masked.

        Returns:
            Dictionary with masked configuration values.
        """
        return {
            "app_env": self.app_env.value,
            "log_level": self.log_level,
            "github": {
                "repository": self.github_repository,
                "owner": self.github_owner,
                "repo": self.github_repo,
                "token": self.get_masked_token(),
            },
            "sentinel": {
                "bot_login": self.sentinel_bot_login or "(not set)",
                "poll_interval": self.sentinel_poll_interval,
                "heartbeat_interval": self.sentinel_heartbeat_interval,
                "subprocess_timeout": self.sentinel_subprocess_timeout,
                "backoff_base_seconds": self.sentinel_backoff_base_seconds,
                "backoff_max_seconds": self.sentinel_backoff_max_seconds,
                "shell_bridge_path": self.sentinel_shell_bridge_path,
            },
            "notifier": {
                "webhook_secret": self.get_masked_webhook_secret(),
                "service_name": self.notifier_service_name,
            },
        }


# Compatibility classes for backward compatibility
class GitHubConfig:
    """Compatibility wrapper for GitHub configuration."""

    def __init__(self, settings: Settings):
        self._settings = settings

    @property
    def token(self) -> str:
        return self._settings.github_token

    @property
    def repository(self) -> str:
        return self._settings.github_repository

    @property
    def owner(self) -> str:
        return self._settings.github_owner

    @property
    def repo(self) -> str:
        return self._settings.github_repo

    def get_masked_token(self) -> str:
        return self._settings.get_masked_token()


class SentinelConfig:
    """Compatibility wrapper for Sentinel configuration."""

    def __init__(self, settings: Settings):
        self._settings = settings

    @property
    def bot_login(self) -> str:
        return self._settings.sentinel_bot_login

    @property
    def poll_interval(self) -> float:
        return self._settings.sentinel_poll_interval

    @property
    def heartbeat_interval(self) -> float:
        return self._settings.sentinel_heartbeat_interval

    @property
    def subprocess_timeout(self) -> float:
        return self._settings.sentinel_subprocess_timeout

    @property
    def backoff_base_seconds(self) -> float:
        return self._settings.sentinel_backoff_base_seconds

    @property
    def backoff_max_seconds(self) -> float:
        return self._settings.sentinel_backoff_max_seconds

    @property
    def shell_bridge_path(self) -> str:
        return self._settings.sentinel_shell_bridge_path


class NotifierConfig:
    """Compatibility wrapper for Notifier configuration."""

    def __init__(self, settings: Settings):
        self._settings = settings

    @property
    def webhook_secret(self) -> str:
        return self._settings.notifier_webhook_secret

    @property
    def service_name(self) -> str:
        return self._settings.notifier_service_name

    def get_masked_webhook_secret(self) -> str:
        return self._settings.get_masked_webhook_secret()


@lru_cache
def get_settings() -> Settings:
    """
    Get the cached Settings instance.

    This function returns a singleton Settings instance that is
    loaded once and cached for the lifetime of the application.

    Returns:
        Settings instance with all configuration loaded.

    Raises:
        ConfigurationError: If configuration loading fails.
    """
    try:
        settings = Settings()
        # Attach compatibility wrappers
        settings.github = GitHubConfig(settings)
        settings.sentinel = SentinelConfig(settings)
        settings.notifier = NotifierConfig(settings)
        return settings
    except Exception as e:
        raise ConfigurationError(
            f"Failed to load configuration: {e}",
            field_name=str(e),
        ) from e


def validate_startup() -> Settings:
    """
    Validate all required configuration at startup.

    This function should be called at application startup to ensure
    all required configuration is present and valid. It provides
    clear, actionable error messages for any issues.

    Returns:
        Validated Settings instance.

    Raises:
        ConfigurationError: If required configuration is missing or invalid.
    """
    logger.info("Validating configuration...")

    try:
        settings = get_settings()
    except ConfigurationError:
        raise
    except Exception as e:
        raise ConfigurationError(
            f"Failed to load configuration: {e}",
        ) from e

    # Validate required GitHub configuration
    if not settings.github_token:
        raise ConfigurationError(
            "Missing required GitHub token",
            field_name="github.token",
            expected_type="Non-empty string",
        )

    if not settings.github_repository:
        raise ConfigurationError(
            "Missing required GitHub repository",
            field_name="github.repository",
            expected_type="Repository in 'owner/repo' format (e.g., 'octocat/Hello-World')",
        )

    # Log configuration summary (with secrets masked)
    summary = settings.get_masked_config_summary()
    logger.info("Configuration loaded successfully:")
    for section, values in summary.items():
        if isinstance(values, dict):
            logger.info("  %s:", section.upper())
            for key, value in values.items():
                logger.info("    %s: %s", key, value)
        else:
            logger.info("  %s: %s", section, values)

    return settings


def clear_settings_cache() -> None:
    """
    Clear the settings cache.

    This is primarily useful for testing to ensure fresh settings
    are loaded after environment changes.
    """
    get_settings.cache_clear()
