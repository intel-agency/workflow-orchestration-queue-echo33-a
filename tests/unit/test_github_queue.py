"""Unit tests for GitHub webhook signature verification."""

import hashlib
import hmac

from orchestration_queue.queue.github_queue import verify_webhook_signature


class TestVerifyWebhookSignature:
    """Tests for webhook signature verification."""

    def test_valid_signature(self, mock_webhook_secret: str) -> None:
        """Test that valid signatures are accepted."""
        payload = b'{"test": "data"}'
        secret = mock_webhook_secret

        # Compute valid signature
        expected_sig = hmac.new(
            secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        signature = f"sha256={expected_sig}"

        assert verify_webhook_signature(payload, signature, secret) is True

    def test_invalid_signature(self, mock_webhook_secret: str) -> None:
        """Test that invalid signatures are rejected."""
        payload = b'{"test": "data"}'
        secret = mock_webhook_secret
        signature = "sha256=invalid_signature_here"

        assert verify_webhook_signature(payload, signature, secret) is False

    def test_missing_sha256_prefix(self, mock_webhook_secret: str) -> None:
        """Test that signatures without sha256= prefix are rejected."""
        payload = b'{"test": "data"}'
        secret = mock_webhook_secret
        signature = "invalid_signature_without_prefix"

        assert verify_webhook_signature(payload, signature, secret) is False

    def test_empty_signature(self, mock_webhook_secret: str) -> None:
        """Test that empty signatures are rejected."""
        payload = b'{"test": "data"}'
        secret = mock_webhook_secret
        signature = ""

        assert verify_webhook_signature(payload, signature, secret) is False

    def test_wrong_secret(self, mock_webhook_secret: str) -> None:
        """Test that wrong secret produces invalid signature."""
        payload = b'{"test": "data"}'
        correct_secret = mock_webhook_secret
        wrong_secret = "WRONG-SECRET-FOR-TESTING-00000000"

        # Compute signature with correct secret
        expected_sig = hmac.new(
            correct_secret.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        signature = f"sha256={expected_sig}"

        # Verify with wrong secret should fail
        assert verify_webhook_signature(payload, signature, wrong_secret) is False

    def test_tampered_payload(self, mock_webhook_secret: str) -> None:
        """Test that tampered payloads are detected."""
        original_payload = b'{"test": "data"}'
        tampered_payload = b'{"test": "TAMPERED"}'
        secret = mock_webhook_secret

        # Compute signature for original payload
        expected_sig = hmac.new(
            secret.encode("utf-8"),
            original_payload,
            hashlib.sha256,
        ).hexdigest()
        signature = f"sha256={expected_sig}"

        # Verify with tampered payload should fail
        assert verify_webhook_signature(tampered_payload, signature, secret) is False
