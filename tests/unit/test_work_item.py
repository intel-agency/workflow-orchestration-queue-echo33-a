"""Unit tests for WorkItem model and related functionality."""


from orchestration_queue.models.work_item import (
    TaskType,
    WorkItem,
    WorkItemStatus,
    scrub_secrets,
)


class TestTaskType:
    """Tests for TaskType enum."""

    def test_task_type_values(self) -> None:
        """Test that TaskType has expected values."""
        assert TaskType.PLAN.value == "plan"
        assert TaskType.IMPLEMENT.value == "implement"
        assert TaskType.BUGFIX.value == "bugfix"


class TestWorkItemStatus:
    """Tests for WorkItemStatus enum."""

    def test_status_values(self) -> None:
        """Test that WorkItemStatus has expected values."""
        assert WorkItemStatus.QUEUED.value == "agent:queued"
        assert WorkItemStatus.IN_PROGRESS.value == "agent:in-progress"
        assert WorkItemStatus.SUCCESS.value == "agent:success"
        assert WorkItemStatus.ERROR.value == "agent:error"
        assert WorkItemStatus.INFRA_FAILURE.value == "agent:infra-failure"


class TestWorkItem:
    """Tests for WorkItem model."""

    def test_work_item_creation(self, sample_work_item: dict) -> None:
        """Test creating a WorkItem from dict."""
        item = WorkItem.model_validate(sample_work_item)

        assert item.id == 42
        assert item.title == "Add user authentication"
        assert item.task_type == TaskType.IMPLEMENT
        assert item.status == WorkItemStatus.QUEUED
        assert item.repository == "intel-agency/workflow-orchestration-queue-echo33-a"
        assert item.author == "developer"

    def test_has_label(self, sample_work_item: dict) -> None:
        """Test has_label method."""
        item = WorkItem.model_validate(sample_work_item)

        assert item.has_label("enhancement") is True
        assert item.has_label("bug") is False

    def test_is_assigned(self, sample_work_item: dict) -> None:
        """Test is_assigned method."""
        item = WorkItem.model_validate(sample_work_item)
        assert item.is_assigned() is False

        # Add an assignee
        item.assignees.append("sentinel-bot")
        assert item.is_assigned() is True

    def test_to_github_labels(self, sample_work_item: dict) -> None:
        """Test to_github_labels method."""
        item = WorkItem.model_validate(sample_work_item)
        labels = item.to_github_labels()

        # Should include non-status labels
        assert "enhancement" in labels
        assert "implementation:ready" in labels
        # Should include current status
        assert "agent:queued" in labels


class TestScrubSecrets:
    """Tests for scrub_secrets function."""

    def test_scrub_github_pat(self) -> None:
        """Test scrubbing GitHub PAT patterns."""
        text = "Token: ghp_1234567890abcdefghijklmnopqrstuvwxyz"
        result = scrub_secrets(text)

        assert "ghp_" not in result
        assert "[REDACTED_GITHUB_PAT]" in result

    def test_scrub_openai_key(self) -> None:
        """Test scrubbing OpenAI API key patterns."""
        text = "API_KEY=sk-1234567890abcdefghijklmnopqrst"
        result = scrub_secrets(text)

        assert "sk-" not in result
        assert "[REDACTED_API_KEY]" in result

    def test_scrub_bearer_token(self) -> None:
        """Test scrubbing Bearer token patterns."""
        text = "Authorization: Bearer abc123xyz789"
        result = scrub_secrets(text)

        assert "Bearer abc123xyz789" not in result
        assert "Bearer [REDACTED]" in result

    def test_preserves_normal_text(self) -> None:
        """Test that normal text is preserved."""
        text = "This is a normal log message without secrets."
        result = scrub_secrets(text)

        assert result == text

    def test_handles_empty_string(self) -> None:
        """Test handling empty string."""
        assert scrub_secrets("") == ""

    def test_handles_multiple_secrets(self) -> None:
        """Test handling multiple secrets in one string."""
        # Use realistic token lengths: ghp_ needs exactly 36 chars, sk- needs 20+ chars
        text = (
            "ghp_1234567890abcdefghijklmnopqrstuvwxyz and sk-1234567890abcdefghijklmnop both here"
        )
        result = scrub_secrets(text)

        assert "ghp_1234567890abcdefghijklmnopqrstuvwxyz" not in result
        assert "sk-1234567890abcdefghijklmnop" not in result
        assert "[REDACTED_GITHUB_PAT]" in result
        assert "[REDACTED_API_KEY]" in result
