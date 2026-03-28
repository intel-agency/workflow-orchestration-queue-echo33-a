"""Test configuration settings module."""

import os
from unittest.mock import patch

import pytest

from orchestration_queue.config import (
    AppEnv,
    ConfigurationError,
    Settings,
    clear_settings_cache,
    get_settings,
    validate_startup,
)


class TestAppEnv:
    """Tests for AppEnv enum."""

    def test_is_production(self) -> None:
        """Test is_production method."""
        assert AppEnv.PRODUCTION.is_production() is True
        assert AppEnv.DEVELOPMENT.is_production() is False
        assert AppEnv.STAGING.is_production() is False

    def test_is_development(self) -> None:
        """Test is_development method."""
        assert AppEnv.DEVELOPMENT.is_development() is True
        assert AppEnv.PRODUCTION.is_development() is False


class TestSettings:
    """Tests for Settings model."""

    def test_default_values(self) -> None:
        """Test default settings values."""
        # Create Settings with explicit empty values to avoid env var interference
        settings = Settings(
            github_token="",
            github_repository="",
        )
        assert settings.app_env == AppEnv.DEVELOPMENT
        assert settings.log_level == "INFO"
        assert settings.github_token == ""
        assert settings.github_repository == ""
        assert settings.sentinel_poll_interval == 60.0
        assert settings.notifier_service_name == "workflow-orchestration-queue"

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        settings = Settings(
            github_token="test-token",
            github_repository="owner/repo",
            sentinel_poll_interval=30.0,
        )
        assert settings.github_token == "test-token"
        assert settings.github_repository == "owner/repo"
        assert settings.sentinel_poll_interval == 30.0

    def test_log_level_validation(self) -> None:
        """Test log level validation."""
        # Valid levels
        settings = Settings(log_level="DEBUG")
        assert settings.log_level == "DEBUG"

        # Invalid level
        with pytest.raises(ValueError, match="Invalid log level"):
            Settings(log_level="INVALID")

    def test_log_level_case_insensitive(self) -> None:
        """Test log level is case insensitive."""
        settings = Settings(log_level="debug")
        assert settings.log_level == "DEBUG"

    def test_repository_validation_valid(self) -> None:
        """Test valid repository format."""
        settings = Settings(github_repository="owner/repo")
        assert settings.github_repository == "owner/repo"
        assert settings.github_owner == "owner"
        assert settings.github_repo == "repo"

    def test_repository_validation_with_hyphens(self) -> None:
        """Test repository with hyphens."""
        settings = Settings(github_repository="my-org/my-repo-name")
        assert settings.github_owner == "my-org"
        assert settings.github_repo == "my-repo-name"

    def test_repository_validation_empty(self) -> None:
        """Test empty repository is allowed."""
        settings = Settings(github_repository="")
        assert settings.github_repository == ""

    def test_repository_validation_invalid(self) -> None:
        """Test invalid repository format raises error."""
        with pytest.raises(ValueError, match="Invalid repository format"):
            Settings(github_repository="invalidformat")

    def test_poll_interval_validation_too_low(self) -> None:
        """Test poll interval validation rejects values below minimum."""
        with pytest.raises(ValueError):
            Settings(sentinel_poll_interval=0.5)

    def test_poll_interval_validation_too_high(self) -> None:
        """Test poll interval validation rejects values above maximum."""
        with pytest.raises(ValueError):
            Settings(sentinel_poll_interval=5000.0)

    def test_get_masked_token_short(self) -> None:
        """Test token masking for short tokens."""
        settings = Settings(github_token="short")
        assert settings.get_masked_token() == "***MASKED***"

    def test_get_masked_token_empty(self) -> None:
        """Test token masking for empty tokens."""
        settings = Settings(github_token="")
        assert settings.get_masked_token() == "***EMPTY***"

    def test_get_masked_token_normal(self) -> None:
        """Test token masking for normal tokens."""
        settings = Settings(github_token="ghp_1234567890abcdef")
        masked = settings.get_masked_token()
        assert masked.startswith("ghp_")
        assert masked.endswith("cdef")

    def test_get_masked_webhook_secret_not_set(self) -> None:
        """Test webhook secret masking when not set."""
        settings = Settings(notifier_webhook_secret="")
        assert settings.get_masked_webhook_secret() == "***NOT SET***"

    def test_get_masked_webhook_secret_short(self) -> None:
        """Test webhook secret masking for short secrets."""
        settings = Settings(notifier_webhook_secret="abc")
        assert settings.get_masked_webhook_secret() == "***MASKED***"

    def test_get_masked_webhook_secret_normal(self) -> None:
        """Test webhook secret masking for normal secrets."""
        settings = Settings(notifier_webhook_secret="abcdefghijklmnop")
        masked = settings.get_masked_webhook_secret()
        assert masked.startswith("abcd")
        assert "***MASKED***" in masked

    def test_get_masked_config_summary(self) -> None:
        """Test masked config summary for safe logging."""
        settings = Settings(
            github_token="ghp_secret_token_12345",
            github_repository="owner/repo",
            notifier_webhook_secret="super_secret_webhook",
        )
        summary = settings.get_masked_config_summary()

        # Check secrets are masked
        assert "ghp_secret_token_12345" not in str(summary)
        assert "super_secret_webhook" not in str(summary)

        # Check non-sensitive data is present
        assert summary["github"]["repository"] == "owner/repo"
        assert summary["github"]["owner"] == "owner"
        assert summary["github"]["repo"] == "repo"

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "owner/repo",
        },
        clear=True,
    )
    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "owner/repo",
        },
        clear=True,
    )
    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "owner/repo",
        },
        clear=True,
    )
    def test_compatibility_wrappers(self) -> None:
        """Test compatibility wrappers work correctly."""
        clear_settings_cache()
        # Use get_settings to get the wrapped instance
        settings = get_settings()
        # Verify wrappers are attached
        assert hasattr(settings, "github")
        assert settings.github.token == "test-token"
        assert settings.github.repository == "owner/repo"
        assert settings.github.owner == "owner"
        assert settings.github.repo == "repo"


class TestGetSettings:
    """Tests for get_settings function."""

    def teardown_method(self) -> None:
        """Clear settings cache after each test."""
        clear_settings_cache()

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "test-owner/test-repo",
        },
        clear=True,
    )
    def test_get_settings_returns_singleton(self) -> None:
        """Test get_settings returns cached singleton."""
        clear_settings_cache()
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "test-owner/test-repo",
        },
        clear=True,
    )
    def test_clear_settings_cache(self) -> None:
        """Test clear_settings_cache creates new instance."""
        clear_settings_cache()
        settings1 = get_settings()
        clear_settings_cache()
        settings2 = get_settings()
        # After clearing cache, should be different object
        assert settings1 is not settings2


class TestValidateStartup:
    """Tests for validate_startup function."""

    def teardown_method(self) -> None:
        """Clear settings cache after each test."""
        clear_settings_cache()

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "test-owner/test-repo",
        },
        clear=True,
    )
    def test_validate_startup_success(self) -> None:
        """Test successful startup validation."""
        clear_settings_cache()
        settings = validate_startup()
        assert settings.github_token == "test-token"
        assert settings.github_repository == "test-owner/test-repo"

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "",
            "GITHUB_REPOSITORY": "test-owner/test-repo",
        },
        clear=True,
    )
    def test_validate_startup_missing_token(self) -> None:
        """Test startup validation fails with missing token."""
        clear_settings_cache()
        with pytest.raises(ConfigurationError, match="Missing required GitHub token"):
            validate_startup()

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "",
        },
        clear=True,
    )
    def test_validate_startup_missing_repository(self) -> None:
        """Test startup validation fails with missing repository."""
        clear_settings_cache()
        with pytest.raises(ConfigurationError, match="Missing required GitHub repository"):
            validate_startup()

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "invalid-format",
        },
        clear=True,
    )
    def test_validate_startup_invalid_repository_format(self) -> None:
        """Test startup validation fails with invalid repository format."""
        clear_settings_cache()
        # This should fail during Settings creation, not validate_startup
        with pytest.raises((ValueError, ConfigurationError)):
            get_settings()


class TestEnvironmentVariablePrefix:
    """Tests for environment variable loading."""

    def teardown_method(self) -> None:
        """Clear settings cache after each test."""
        clear_settings_cache()

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "github-token-value",
            "GITHUB_REPOSITORY": "owner/repo",
            "SENTINEL_BOT_LOGIN": "sentinel-bot",
            "SENTINEL_POLL_INTERVAL": "30.0",
            "NOTIFIER_WEBHOOK_SECRET": "webhook-secret",
        },
        clear=True,
    )
    def test_env_var_loading(self) -> None:
        """Test environment variables are loaded correctly."""
        clear_settings_cache()
        settings = get_settings()

        # GitHub config
        assert settings.github_token == "github-token-value"
        assert settings.github_repository == "owner/repo"

        # Sentinel config
        assert settings.sentinel_bot_login == "sentinel-bot"
        assert settings.sentinel_poll_interval == 30.0

        # Notifier config
        assert settings.notifier_webhook_secret == "webhook-secret"

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "owner/repo",
            "APP_ENV": "production",
            "LOG_LEVEL": "DEBUG",
        },
        clear=True,
    )
    def test_app_level_env_vars(self) -> None:
        """Test application-level environment variables."""
        clear_settings_cache()
        settings = get_settings()

        assert settings.app_env == AppEnv.PRODUCTION
        assert settings.log_level == "DEBUG"
