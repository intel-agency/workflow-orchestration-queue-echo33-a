"""Test configuration startup validation."""

import os
from unittest.mock import patch

import pytest

from orchestration_queue.config import (
    ConfigurationError,
    clear_settings_cache,
    get_settings,
    validate_startup,
)
from orchestration_queue.config.exceptions import (
    format_missing_required,
    format_validation_error,
    mask_value_if_secret,
)


class TestConfigurationError:
    """Tests for ConfigurationError exception."""

    def test_basic_error(self) -> None:
        """Test basic error message."""
        error = ConfigurationError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"

    def test_error_with_field_name(self) -> None:
        """Test error with field name."""
        error = ConfigurationError(
            "Invalid value",
            field_name="github_token",
        )
        assert "Invalid value" in str(error)
        assert "Field: github_token" in str(error)

    def test_error_with_expected_type(self) -> None:
        """Test error with expected type."""
        error = ConfigurationError(
            "Type mismatch",
            field_name="poll_interval",
            expected_type="positive float",
        )
        assert "Type mismatch" in str(error)
        assert "Expected: positive float" in str(error)

    def test_error_with_all_fields(self) -> None:
        """Test error with all fields."""
        error = ConfigurationError(
            "Validation failed",
            field_name="repository",
            expected_type="owner/repo format",
            field_value="invalid",
        )
        assert error.message == "Validation failed"
        assert error.field_name == "repository"
        assert error.expected_type == "owner/repo format"
        assert error.field_value == "invalid"


class TestFormatMissingRequired:
    """Tests for format_missing_required function."""

    def test_format_missing_required(self) -> None:
        """Test formatting of missing required variable."""
        result = format_missing_required("GitHub Token", "GITHUB_TOKEN")

        assert "Missing required configuration: GitHub Token" in result
        assert "GITHUB_TOKEN" in result
        assert "export GITHUB_TOKEN=" in result
        assert ".env file" in result

    def test_format_missing_repository(self) -> None:
        """Test formatting for missing repository."""
        result = format_missing_required("GitHub Repository", "GITHUB_REPOSITORY")

        assert "GitHub Repository" in result
        assert "GITHUB_REPOSITORY" in result


class TestFormatValidationError:
    """Tests for format_validation_error function."""

    def test_format_validation_error(self) -> None:
        """Test formatting of validation error."""
        result = format_validation_error(
            field_name="Poll Interval",
            expected_type="positive number",
            actual_value=-5,
            env_var="SENTINEL_POLL_INTERVAL",
        )

        assert "Invalid configuration for Poll Interval" in result
        assert "Expected: positive number" in result
        assert "SENTINEL_POLL_INTERVAL" in result

    def test_format_validation_error_masks_secrets(self) -> None:
        """Test that validation error masks secrets."""
        result = format_validation_error(
            field_name="GitHub Token",
            expected_type="non-empty string",
            actual_value="ghp_secret123",
            env_var="GITHUB_TOKEN",
        )

        # Token should be masked
        assert "ghp_secret123" not in result
        assert "***MASKED***" in result


class TestMaskValueIfSecret:
    """Tests for mask_value_if_secret function."""

    def test_mask_token(self) -> None:
        """Test masking of token values."""
        result = mask_value_if_secret("ghp_1234567890abcdef", "GITHUB_TOKEN")
        assert "ghp_" in result
        assert "***MASKED***" in result

    def test_no_mask_non_secret(self) -> None:
        """Test non-secret values are not masked."""
        result = mask_value_if_secret("my-repo", "GITHUB_REPOSITORY")
        assert result == "my-repo"

    def test_mask_short_secret(self) -> None:
        """Test masking of short secrets."""
        result = mask_value_if_secret("abc", "WEBHOOK_SECRET")
        # Short secrets are fully masked
        assert "***MASKED***" in result


class TestValidateStartup:
    """Tests for validate_startup function."""

    def teardown_method(self) -> None:
        """Clear settings cache after each test."""
        clear_settings_cache()

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "valid-token",
            "GITHUB_REPOSITORY": "owner/repo",
        },
        clear=True,
    )
    def test_validate_startup_success(self) -> None:
        """Test successful startup validation."""
        clear_settings_cache()
        settings = validate_startup()

        assert settings is not None
        assert settings.github_token == "valid-token"
        assert settings.github_repository == "owner/repo"

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "",
            "GITHUB_REPOSITORY": "owner/repo",
        },
        clear=True,
    )
    def test_validate_startup_missing_token(self) -> None:
        """Test startup validation fails with missing token."""
        clear_settings_cache()

        with pytest.raises(ConfigurationError) as exc_info:
            validate_startup()

        assert "Missing required GitHub token" in str(exc_info.value)

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "valid-token",
            "GITHUB_REPOSITORY": "",
        },
        clear=True,
    )
    def test_validate_startup_missing_repository(self) -> None:
        """Test startup validation fails with missing repository."""
        clear_settings_cache()

        with pytest.raises(ConfigurationError) as exc_info:
            validate_startup()

        assert "Missing required GitHub repository" in str(exc_info.value)

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "valid-token",
            "GITHUB_REPOSITORY": "invalid-no-slash",
        },
        clear=True,
    )
    def test_validate_startup_invalid_repository_format(self) -> None:
        """Test startup validation fails with invalid repository format."""
        clear_settings_cache()

        # This fails at Settings creation, not validate_startup
        with pytest.raises((ValueError, ConfigurationError)):
            get_settings()

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "valid-token",
            "GITHUB_REPOSITORY": "owner/repo",
            "LOG_LEVEL": "INVALID_LEVEL",
        },
        clear=True,
    )
    def test_validate_startup_invalid_log_level(self) -> None:
        """Test startup validation fails with invalid log level."""
        clear_settings_cache()

        with pytest.raises((ConfigurationError, ValueError)):
            validate_startup()


class TestStartupIntegration:
    """Integration tests for startup validation."""

    def teardown_method(self) -> None:
        """Clear settings cache after each test."""
        clear_settings_cache()

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "ghp_test_token_12345",
            "GITHUB_REPOSITORY": "intel-agency/workflow-orchestration-queue",
            "APP_ENV": "production",
            "LOG_LEVEL": "DEBUG",
            "SENTINEL_BOT_LOGIN": "test-bot",
            "SENTINEL_POLL_INTERVAL": "30.0",
            "NOTIFIER_WEBHOOK_SECRET": "test-secret",
        },
        clear=True,
    )
    def test_full_configuration_loading(self) -> None:
        """Test loading of full configuration from environment."""
        clear_settings_cache()
        settings = validate_startup()

        # GitHub config
        assert settings.github_token == "ghp_test_token_12345"
        assert settings.github_repository == "intel-agency/workflow-orchestration-queue"
        assert settings.github_owner == "intel-agency"
        assert settings.github_repo == "workflow-orchestration-queue"

        # App config
        assert settings.app_env.value == "production"
        assert settings.log_level == "DEBUG"

        # Sentinel config
        assert settings.sentinel_bot_login == "test-bot"
        assert settings.sentinel_poll_interval == 30.0

        # Notifier config
        assert settings.notifier_webhook_secret == "test-secret"

    @patch.dict(
        os.environ,
        {
            "GITHUB_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "owner/repo",
        },
        clear=True,
    )
    def test_masked_config_summary_safe_to_log(self) -> None:
        """Test that masked config summary is safe to log."""
        clear_settings_cache()
        settings = validate_startup()
        summary = settings.get_masked_config_summary()

        # Convert to string to check for secrets
        summary_str = str(summary)

        # Token should be masked
        assert "test-token" not in summary_str

        # Non-sensitive data should be present
        assert "owner/repo" in summary_str
