"""
Unit tests for GitHubQueue implementation.

Tests cover the GitHub Issues-based task queue operations including
fetching tasks, claiming tasks, updating status, and posting heartbeats.
"""

import hashlib
import hmac
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from orchestration_queue.models.work_item import TaskType, WorkItem, WorkItemStatus
from orchestration_queue.queue.github_queue import GitHubQueue, verify_webhook_signature


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


def create_mock_response(
    status_code: int,
    json_data: Any = None,
    headers: dict[str, str] | None = None,
) -> MagicMock:
    """Create a mock HTTP response."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = json_data if json_data is not None else {}
    response.headers = headers or {}
    response.raise_for_status = MagicMock()
    if status_code >= 400:
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Error", request=MagicMock(), response=response
        )
    return response


def create_sample_issue(
    number: int = 42,
    title: str = "Test Issue",
    body: str = "Test body",
    labels: list[dict[str, str]] | None = None,
    assignees: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Create a sample GitHub issue response."""
    return {
        "number": number,
        "title": title,
        "body": body,
        "state": "open",
        "user": {"login": "developer"},
        "labels": labels or [{"name": "agent:queued"}],
        "assignees": assignees or [],
        "created_at": "2024-01-15T10:30:00Z",
        "updated_at": "2024-01-15T10:30:00Z",
    }


class TestFetchQueuedTasks:
    """Tests for GitHubQueue.fetch_queued_tasks method."""

    @pytest.mark.asyncio
    async def test_fetch_queued_tasks_success(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test successful fetch of queued issues."""
        issues = [
            create_sample_issue(number=1, title="First task"),
            create_sample_issue(number=2, title="Second task"),
        ]
        mock_httpx_client.get.return_value = create_mock_response(200, issues)

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
        )

        result = await queue.fetch_queued_tasks()

        assert len(result) == 2
        assert all(isinstance(item, WorkItem) for item in result)
        assert result[0].id == 1
        assert result[0].title == "First task"
        assert result[0].status == WorkItemStatus.QUEUED
        assert result[1].id == 2
        assert result[1].title == "Second task"

    @pytest.mark.asyncio
    async def test_fetch_queued_tasks_empty(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test handling of empty results."""
        mock_httpx_client.get.return_value = create_mock_response(200, [])

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
        )

        result = await queue.fetch_queued_tasks()

        assert result == []
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_fetch_queued_tasks_rate_limit_then_success(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test rate limit handling with retry."""
        issues = [create_sample_issue(number=1)]
        rate_limit_response = create_mock_response(
            403, {"message": "rate limited"}, {"Retry-After": "1"}
        )
        success_response = create_mock_response(200, issues)

        mock_httpx_client.get.side_effect = [rate_limit_response, success_response]

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
            max_retries=3,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await queue.fetch_queued_tasks()

        assert len(result) == 1
        assert result[0].id == 1

    @pytest.mark.asyncio
    async def test_fetch_queued_tasks_rate_limit_exhausted(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test rate limit handling when all retries exhausted."""
        rate_limit_response = create_mock_response(
            429, {"message": "rate limited"}, {"Retry-After": "1"}
        )
        mock_httpx_client.get.return_value = rate_limit_response

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
            max_retries=2,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await queue.fetch_queued_tasks()

        assert result == []

    @pytest.mark.asyncio
    async def test_fetch_queued_tasks_maps_task_type_plan(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test mapping of GitHub issue to WorkItem with PLAN task type."""
        issues = [
            create_sample_issue(
                number=1,
                labels=[{"name": "agent:queued"}, {"name": "task:plan"}],
            )
        ]
        mock_httpx_client.get.return_value = create_mock_response(200, issues)

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
        )

        result = await queue.fetch_queued_tasks()

        assert len(result) == 1
        assert result[0].task_type == TaskType.PLAN

    @pytest.mark.asyncio
    async def test_fetch_queued_tasks_maps_task_type_bugfix(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test mapping of GitHub issue to WorkItem with BUGFIX task type."""
        issues = [
            create_sample_issue(
                number=1,
                labels=[{"name": "agent:queued"}, {"name": "task:bugfix"}],
            )
        ]
        mock_httpx_client.get.return_value = create_mock_response(200, issues)

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
        )

        result = await queue.fetch_queued_tasks()

        assert len(result) == 1
        assert result[0].task_type == TaskType.BUGFIX

    @pytest.mark.asyncio
    async def test_fetch_queued_tasks_maps_task_type_implement_default(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test mapping defaults to IMPLEMENT when no type label."""
        issues = [
            create_sample_issue(
                number=1,
                labels=[{"name": "agent:queued"}],
            )
        ]
        mock_httpx_client.get.return_value = create_mock_response(200, issues)

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
        )

        result = await queue.fetch_queued_tasks()

        assert len(result) == 1
        assert result[0].task_type == TaskType.IMPLEMENT

    @pytest.mark.asyncio
    async def test_fetch_queued_tasks_with_assignees(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test that assignees are properly mapped."""
        issues = [
            create_sample_issue(
                number=1,
                assignees=[{"login": "user1"}, {"login": "user2"}],
            )
        ]
        mock_httpx_client.get.return_value = create_mock_response(200, issues)

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
        )

        result = await queue.fetch_queued_tasks()

        assert len(result) == 1
        assert result[0].assignees == ["user1", "user2"]


class TestClaimTask:
    """Tests for GitHubQueue.claim_task method."""

    @pytest.mark.asyncio
    async def test_claim_task_success(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test successful claim with assign-then-verify pattern."""
        sentinel_id = "sentinel-bot"

        # Assign response
        assign_response = create_mock_response(201, {"assignees": [{"login": sentinel_id}]})
        # Verify response - sentinel is the only assignee
        verify_response = create_mock_response(
            200,
            create_sample_issue(
                number=42,
                assignees=[{"login": sentinel_id}],
            ),
        )
        # update_status calls
        get_labels_response = create_mock_response(
            200,
            create_sample_issue(
                number=42,
                labels=[{"name": "agent:queued"}],
            ),
        )
        patch_response = create_mock_response(200, {"labels": [{"name": "agent:in-progress"}]})

        mock_httpx_client.post.side_effect = [assign_response]
        mock_httpx_client.get.side_effect = [verify_response, get_labels_response]
        mock_httpx_client.patch.return_value = patch_response

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await queue.claim_task(42, sentinel_id)

        assert result is True

    @pytest.mark.asyncio
    async def test_claim_task_already_assigned(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test claim failure when already assigned to someone else."""
        sentinel_id = "sentinel-bot"
        other_user = "other-user"

        # Assign response - succeeds but...
        assign_response = create_mock_response(201, {"assignees": [{"login": other_user}]})
        # Verify response - shows different assignee (race condition)
        verify_response = create_mock_response(
            200,
            create_sample_issue(
                number=42,
                assignees=[{"login": other_user}],
            ),
        )

        mock_httpx_client.post.return_value = assign_response
        mock_httpx_client.get.return_value = verify_response

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await queue.claim_task(42, sentinel_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_claim_task_assign_fails(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test claim failure when assignment returns non-200 status."""
        sentinel_id = "sentinel-bot"

        # Assign response - fails
        assign_response = create_mock_response(422, {"message": "Validation failed"})

        mock_httpx_client.post.return_value = assign_response

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
        )

        result = await queue.claim_task(42, sentinel_id)

        assert result is False

    @pytest.mark.asyncio
    async def test_claim_task_rate_limit_on_assign(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test rate limit handling during assign."""
        sentinel_id = "sentinel-bot"

        # First assign attempt rate limited, second succeeds
        rate_limit_response = create_mock_response(
            403, {"message": "rate limited"}, {"Retry-After": "1"}
        )
        assign_response = create_mock_response(201, {"assignees": [{"login": sentinel_id}]})
        verify_response = create_mock_response(
            200,
            create_sample_issue(
                number=42,
                assignees=[{"login": sentinel_id}],
            ),
        )
        get_labels_response = create_mock_response(
            200,
            create_sample_issue(number=42, labels=[{"name": "agent:queued"}]),
        )
        patch_response = create_mock_response(200, {"labels": [{"name": "agent:in-progress"}]})

        mock_httpx_client.post.side_effect = [rate_limit_response, assign_response]
        mock_httpx_client.get.side_effect = [verify_response, get_labels_response]
        mock_httpx_client.patch.return_value = patch_response

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
            max_retries=3,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await queue.claim_task(42, sentinel_id)

        assert result is True

    @pytest.mark.asyncio
    async def test_claim_task_rate_limit_on_verify(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test rate limit handling during verify."""
        sentinel_id = "sentinel-bot"

        assign_response = create_mock_response(201, {"assignees": [{"login": sentinel_id}]})
        # First verify rate limited, second succeeds
        rate_limit_response = create_mock_response(
            429, {"message": "rate limited"}, {"Retry-After": "1"}
        )
        verify_response = create_mock_response(
            200,
            create_sample_issue(
                number=42,
                assignees=[{"login": sentinel_id}],
            ),
        )
        get_labels_response = create_mock_response(
            200,
            create_sample_issue(number=42, labels=[{"name": "agent:queued"}]),
        )
        patch_response = create_mock_response(200, {"labels": [{"name": "agent:in-progress"}]})

        mock_httpx_client.post.return_value = assign_response
        mock_httpx_client.get.side_effect = [
            rate_limit_response,
            verify_response,
            get_labels_response,
        ]
        mock_httpx_client.patch.return_value = patch_response

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
            max_retries=3,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await queue.claim_task(42, sentinel_id)

        assert result is True

    @pytest.mark.asyncio
    async def test_claim_task_no_assignees(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test claim fails when issue has no assignees after assignment."""
        sentinel_id = "sentinel-bot"

        assign_response = create_mock_response(201, {})
        # Verify shows no assignees (assignment didn't stick)
        verify_response = create_mock_response(
            200,
            create_sample_issue(number=42, assignees=[]),
        )

        mock_httpx_client.post.return_value = assign_response
        mock_httpx_client.get.return_value = verify_response

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await queue.claim_task(42, sentinel_id)

        assert result is False


class TestUpdateStatus:
    """Tests for GitHubQueue.update_status method."""

    @pytest.mark.asyncio
    async def test_update_status_success(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test label transition from one status to another."""
        # Get current labels
        get_response = create_mock_response(
            200,
            create_sample_issue(
                number=42,
                labels=[{"name": "agent:queued"}, {"name": "enhancement"}],
            ),
        )
        # Patch labels
        patch_response = create_mock_response(
            200,
            {"labels": [{"name": "agent:in-progress"}, {"name": "enhancement"}]},
        )

        mock_httpx_client.get.return_value = get_response
        mock_httpx_client.patch.return_value = patch_response

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
        )

        result = await queue.update_status(42, WorkItemStatus.IN_PROGRESS)

        assert result is True
        # Verify the patch was called with correct labels
        call_args = mock_httpx_client.patch.call_args
        assert "labels" in call_args[1]["json"]
        labels = call_args[1]["json"]["labels"]
        assert "agent:in-progress" in labels
        assert "enhancement" in labels
        assert "agent:queued" not in labels

    @pytest.mark.asyncio
    async def test_update_status_with_message(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test posting comment with status update."""
        # Get current labels
        get_response = create_mock_response(
            200,
            create_sample_issue(number=42, labels=[{"name": "agent:queued"}]),
        )
        # Patch labels
        patch_response = create_mock_response(200, {"labels": [{"name": "agent:in-progress"}]})
        # Post comment
        comment_response = create_mock_response(201, {"id": 1})

        mock_httpx_client.get.return_value = get_response
        mock_httpx_client.patch.return_value = patch_response
        mock_httpx_client.post.return_value = comment_response

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
        )

        result = await queue.update_status(42, WorkItemStatus.IN_PROGRESS, "Starting work!")

        assert result is True
        # Verify comment was posted
        mock_httpx_client.post.assert_called_once()
        call_args = mock_httpx_client.post.call_args
        assert "comments" in call_args[0][0]
        assert call_args[1]["json"]["body"] == "Starting work!"

    @pytest.mark.asyncio
    async def test_update_status_rate_limit_on_get(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test rate limit handling during GET."""
        rate_limit_response = create_mock_response(
            403, {"message": "rate limited"}, {"Retry-After": "1"}
        )
        get_response = create_mock_response(
            200,
            create_sample_issue(number=42, labels=[{"name": "agent:queued"}]),
        )
        patch_response = create_mock_response(200, {"labels": [{"name": "agent:in-progress"}]})

        mock_httpx_client.get.side_effect = [rate_limit_response, get_response]
        mock_httpx_client.patch.return_value = patch_response

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
            max_retries=3,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await queue.update_status(42, WorkItemStatus.IN_PROGRESS)

        assert result is True

    @pytest.mark.asyncio
    async def test_update_status_rate_limit_on_patch(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test rate limit handling during PATCH."""
        get_response = create_mock_response(
            200,
            create_sample_issue(number=42, labels=[{"name": "agent:queued"}]),
        )
        rate_limit_response = create_mock_response(
            429, {"message": "rate limited"}, {"Retry-After": "1"}
        )
        patch_response = create_mock_response(200, {"labels": [{"name": "agent:in-progress"}]})

        mock_httpx_client.get.return_value = get_response
        mock_httpx_client.patch.side_effect = [rate_limit_response, patch_response]

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
            max_retries=3,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await queue.update_status(42, WorkItemStatus.IN_PROGRESS)

        assert result is True

    @pytest.mark.asyncio
    async def test_update_status_patch_fails(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test failed update returns False."""
        get_response = create_mock_response(
            200,
            create_sample_issue(number=42, labels=[{"name": "agent:queued"}]),
        )
        # Patch fails
        patch_response = create_mock_response(422, {"message": "Validation failed"})

        mock_httpx_client.get.return_value = get_response
        mock_httpx_client.patch.return_value = patch_response

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
        )

        result = await queue.update_status(42, WorkItemStatus.IN_PROGRESS)

        assert result is False

    @pytest.mark.asyncio
    async def test_update_status_get_rate_limit_exhausted(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test rate limit exhausted during GET returns False."""
        rate_limit_response = create_mock_response(
            403, {"message": "rate limited"}, {"Retry-After": "1"}
        )

        mock_httpx_client.get.return_value = rate_limit_response

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
            max_retries=2,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await queue.update_status(42, WorkItemStatus.IN_PROGRESS)

        assert result is False


class TestPostHeartbeat:
    """Tests for GitHubQueue.post_heartbeat method."""

    @pytest.mark.asyncio
    async def test_post_heartbeat_success(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test successful comment posting."""
        comment_response = create_mock_response(201, {"id": 123})

        mock_httpx_client.post.return_value = comment_response

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
        )

        result = await queue.post_heartbeat(42, "Progress update: 50% complete")

        assert result is True
        mock_httpx_client.post.assert_called_once()
        call_args = mock_httpx_client.post.call_args
        assert "comments" in call_args[0][0]
        assert call_args[1]["json"]["body"] == "Progress update: 50% complete"

    @pytest.mark.asyncio
    async def test_post_heartbeat_rate_limit_then_success(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test rate limit handling with retry."""
        rate_limit_response = create_mock_response(
            403, {"message": "rate limited"}, {"Retry-After": "1"}
        )
        success_response = create_mock_response(201, {"id": 123})

        mock_httpx_client.post.side_effect = [rate_limit_response, success_response]

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
            max_retries=3,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await queue.post_heartbeat(42, "Progress update")

        assert result is True

    @pytest.mark.asyncio
    async def test_post_heartbeat_rate_limit_exhausted(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test rate limit exhausted returns False."""
        rate_limit_response = create_mock_response(
            429, {"message": "rate limited"}, {"Retry-After": "1"}
        )

        mock_httpx_client.post.return_value = rate_limit_response

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
            max_retries=2,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await queue.post_heartbeat(42, "Progress update")

        assert result is False

    @pytest.mark.asyncio
    async def test_post_heartbeat_fails(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test failed post returns False."""
        fail_response = create_mock_response(404, {"message": "Not found"})

        mock_httpx_client.post.return_value = fail_response

        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
        )

        result = await queue.post_heartbeat(42, "Progress update")

        assert result is False


class TestGitHubQueueHelpers:
    """Tests for GitHubQueue helper methods."""

    @pytest.mark.asyncio
    async def test_close_owned_client(
        self, mock_github_token: str, mock_httpx_client: AsyncMock
    ) -> None:
        """Test close() does nothing when client is provided."""
        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
            http_client=mock_httpx_client,
        )

        await queue.close()

        # Should not close the provided client
        mock_httpx_client.aclose.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_issue_url(self, mock_github_token: str) -> None:
        """Test URL building for issues."""
        queue = GitHubQueue(
            token=mock_github_token,
            org="my-org",
            repo="my-repo",
        )

        assert queue._get_issue_url() == "/repos/my-org/my-repo/issues"
        assert queue._get_issue_url(42) == "/repos/my-org/my-repo/issues/42"

    def test_determine_task_type_with_plan_label(self, mock_github_token: str) -> None:
        """Test task type determination with plan label."""
        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
        )

        labels = [{"name": "task:plan"}, {"name": "agent:queued"}]
        assert queue._determine_task_type(labels) == TaskType.PLAN

    def test_determine_task_type_with_bug_label(self, mock_github_token: str) -> None:
        """Test task type determination with bug label."""
        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
        )

        labels = [{"name": "type:bug"}, {"name": "agent:queued"}]
        assert queue._determine_task_type(labels) == TaskType.BUGFIX

    def test_determine_task_type_default(self, mock_github_token: str) -> None:
        """Test task type defaults to IMPLEMENT."""
        queue = GitHubQueue(
            token=mock_github_token,
            org="test-org",
            repo="test-repo",
        )

        labels = [{"name": "enhancement"}, {"name": "agent:queued"}]
        assert queue._determine_task_type(labels) == TaskType.IMPLEMENT
