"""Unit tests for GitHub event models."""


from orchestration_queue.models.github_events import (
    GitHubIssueEvent,
    GitHubLabel,
    GitHubUser,
)


class TestGitHubUser:
    """Tests for GitHubUser model."""

    def test_user_creation(self) -> None:
        """Test creating a GitHub user."""
        user = GitHubUser(login="developer", id=12345, type="User")

        assert user.login == "developer"
        assert user.id == 12345
        assert user.type == "User"

    def test_user_default_type(self) -> None:
        """Test default user type."""
        user = GitHubUser(login="bot", id=99999)

        assert user.type == "User"


class TestGitHubLabel:
    """Tests for GitHubLabel model."""

    def test_label_creation(self) -> None:
        """Test creating a GitHub label."""
        label = GitHubLabel(name="bug", color="ff0000")

        assert label.name == "bug"
        assert label.color == "ff0000"


class TestGitHubIssueEvent:
    """Tests for GitHubIssueEvent model."""

    def test_event_from_payload(self, sample_issue_payload: dict) -> None:
        """Test parsing issue event from webhook payload."""
        event = GitHubIssueEvent.model_validate(sample_issue_payload)

        assert event.action == "opened"
        assert event.issue.number == 42
        assert event.issue.title == "Add user authentication"
        assert event.repository.full_name == "intel-agency/workflow-orchestration-queue-echo33-a"
        assert event.sender.login == "developer"

    def test_is_labeled_event(self, sample_labeled_payload: dict) -> None:
        """Test is_labeled_event method."""
        event = GitHubIssueEvent.model_validate(sample_labeled_payload)

        assert event.is_labeled_event() is True
        assert event.label is not None
        assert event.label.name == "implementation:ready"

    def test_is_not_labeled_event(self, sample_issue_payload: dict) -> None:
        """Test that opened events are not labeled events."""
        event = GitHubIssueEvent.model_validate(sample_issue_payload)

        assert event.is_labeled_event() is False

    def test_has_label(self, sample_issue_payload: dict) -> None:
        """Test has_label method."""
        event = GitHubIssueEvent.model_validate(sample_issue_payload)

        assert event.has_label("enhancement") is True
        assert event.has_label("bug") is False

    def test_labeled_event_has_label(self, sample_labeled_payload: dict) -> None:
        """Test has_label on labeled event."""
        event = GitHubIssueEvent.model_validate(sample_labeled_payload)

        assert event.has_label("enhancement") is True
        assert event.has_label("implementation:ready") is True
