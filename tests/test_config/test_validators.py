"""Test configuration validators module."""

import pytest

from orchestration_queue.config.exceptions import ConfigurationError
from orchestration_queue.config.validators import (
    is_secret_field,
    mask_secret,
    validate_positive_float,
    validate_positive_int,
    validate_repository_format,
    validate_url,
)


class TestValidateRepositoryFormat:
    """Tests for validate_repository_format function."""

    def test_valid_format(self) -> None:
        """Test valid repository format."""
        owner, repo = validate_repository_format("owner/repo")
        assert owner == "owner"
        assert repo == "repo"

    def test_valid_format_with_hyphens(self) -> None:
        """Test valid format with hyphens."""
        owner, repo = validate_repository_format("my-org/my-repo-name")
        assert owner == "my-org"
        assert repo == "my-repo-name"

    def test_valid_format_with_underscores(self) -> None:
        """Test valid format with underscores."""
        owner, repo = validate_repository_format("org_name/repo_name")
        assert owner == "org_name"
        assert repo == "repo_name"

    def test_valid_format_with_dots(self) -> None:
        """Test valid format with dots in repo name."""
        owner, repo = validate_repository_format("org/repo.name")
        assert owner == "org"
        assert repo == "repo.name"

    def test_invalid_format_no_slash(self) -> None:
        """Test invalid format without slash."""
        with pytest.raises(ConfigurationError, match="Invalid repository format"):
            validate_repository_format("invalidformat")

    def test_invalid_format_empty(self) -> None:
        """Test invalid format with empty string."""
        with pytest.raises(ConfigurationError, match="Invalid repository format"):
            validate_repository_format("")

    def test_invalid_format_only_slash(self) -> None:
        """Test invalid format with only slash."""
        with pytest.raises(ConfigurationError, match="Invalid repository format"):
            validate_repository_format("/")

    def test_invalid_format_multiple_slashes(self) -> None:
        """Test invalid format with multiple slashes."""
        with pytest.raises(ConfigurationError, match="Invalid repository format"):
            validate_repository_format("owner/repo/extra")


class TestValidateUrl:
    """Tests for validate_url function."""

    def test_valid_http_url(self) -> None:
        """Test valid HTTP URL."""
        result = validate_url("http://example.com/path")
        assert result == "http://example.com/path"

    def test_valid_https_url(self) -> None:
        """Test valid HTTPS URL."""
        result = validate_url("https://example.com/path?query=1")
        assert result == "https://example.com/path?query=1"

    def test_invalid_url_no_protocol(self) -> None:
        """Test invalid URL without protocol."""
        with pytest.raises(ConfigurationError, match="Invalid URL format"):
            validate_url("example.com")

    def test_invalid_url_empty(self) -> None:
        """Test invalid URL with empty string."""
        with pytest.raises(ConfigurationError, match="Invalid URL format"):
            validate_url("")

    def test_custom_field_name(self) -> None:
        """Test custom field name in error message."""
        with pytest.raises(ConfigurationError):
            validate_url("invalid", field_name="custom_field")


class TestValidatePositiveInt:
    """Tests for validate_positive_int function."""

    def test_valid_positive_int(self) -> None:
        """Test valid positive integer."""
        result = validate_positive_int(10, "test_field")
        assert result == 10

    def test_valid_at_minimum(self) -> None:
        """Test value at minimum."""
        result = validate_positive_int(1, "test_field", min_value=1)
        assert result == 1

    def test_valid_at_maximum(self) -> None:
        """Test value at maximum."""
        result = validate_positive_int(100, "test_field", max_value=100)
        assert result == 100

    def test_invalid_below_minimum(self) -> None:
        """Test value below minimum."""
        with pytest.raises(ConfigurationError, match="below minimum"):
            validate_positive_int(0, "test_field", min_value=1)

    def test_invalid_above_maximum(self) -> None:
        """Test value above maximum."""
        with pytest.raises(ConfigurationError, match="exceeds maximum"):
            validate_positive_int(200, "test_field", max_value=100)


class TestValidatePositiveFloat:
    """Tests for validate_positive_float function."""

    def test_valid_positive_float(self) -> None:
        """Test valid positive float."""
        result = validate_positive_float(10.5, "test_field")
        assert result == 10.5

    def test_valid_at_minimum(self) -> None:
        """Test value at minimum."""
        result = validate_positive_float(0.0, "test_field", min_value=0.0)
        assert result == 0.0

    def test_valid_at_maximum(self) -> None:
        """Test value at maximum."""
        result = validate_positive_float(100.0, "test_field", max_value=100.0)
        assert result == 100.0

    def test_invalid_below_minimum(self) -> None:
        """Test value below minimum."""
        with pytest.raises(ConfigurationError, match="below minimum"):
            validate_positive_float(-1.0, "test_field", min_value=0.0)

    def test_invalid_above_maximum(self) -> None:
        """Test value above maximum."""
        with pytest.raises(ConfigurationError, match="exceeds maximum"):
            validate_positive_float(200.0, "test_field", max_value=100.0)


class TestMaskSecret:
    """Tests for mask_secret function."""

    def test_mask_normal_secret(self) -> None:
        """Test masking a normal secret."""
        result = mask_secret("abcdefghijklmnop")
        assert result.startswith("abcd")
        assert "***MASKED***" in result
        assert "abcdefghijklmnop" not in result

    def test_mask_short_secret(self) -> None:
        """Test masking a short secret."""
        result = mask_secret("abc")
        assert result == "***MASKED***"

    def test_mask_empty_secret(self) -> None:
        """Test masking an empty secret."""
        result = mask_secret("")
        assert result == "***EMPTY***"

    def test_mask_custom_visible_chars(self) -> None:
        """Test masking with custom visible characters."""
        result = mask_secret("abcdefghijklmnop", visible_chars=6)
        assert result.startswith("abcdef")
        assert "***MASKED***" in result


class TestIsSecretField:
    """Tests for is_secret_field function."""

    def test_token_is_secret(self) -> None:
        """Test token field is detected as secret."""
        assert is_secret_field("github_token") is True
        assert is_secret_field("access_token") is True

    def test_secret_is_secret(self) -> None:
        """Test secret field is detected as secret."""
        assert is_secret_field("webhook_secret") is True
        assert is_secret_field("api_secret") is True

    def test_key_is_secret(self) -> None:
        """Test key field is detected as secret."""
        assert is_secret_field("api_key") is True
        assert is_secret_field("encryption_key") is True

    def test_password_is_secret(self) -> None:
        """Test password field is detected as secret."""
        assert is_secret_field("password") is True
        assert is_secret_field("db_password") is True

    def test_non_secret_field(self) -> None:
        """Test non-secret field is not detected as secret."""
        assert is_secret_field("repository") is False
        assert is_secret_field("poll_interval") is False
        assert is_secret_field("service_name") is False
