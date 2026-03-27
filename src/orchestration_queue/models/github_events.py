"""
GitHub webhook event models for the orchestration queue.

Pydantic models for parsing and validating GitHub webhook payloads.
"""

from typing import Any

from pydantic import BaseModel, Field


class GitHubUser(BaseModel):
    """GitHub user information."""

    login: str = Field(..., description="Username")
    id: int = Field(..., description="User ID")
    type: str = Field(default="User", description="User type (User, Bot, Organization)")


class GitHubLabel(BaseModel):
    """GitHub label information."""

    name: str = Field(..., description="Label name")
    color: str | None = Field(None, description="Label color (hex)")


class GitHubRepository(BaseModel):
    """GitHub repository information."""

    id: int = Field(..., description="Repository ID")
    name: str = Field(..., description="Repository name")
    full_name: str = Field(..., description="Full name (owner/repo)")
    owner: GitHubUser = Field(..., description="Repository owner")
    private: bool = Field(default=False, description="Whether repository is private")


class GitHubIssue(BaseModel):
    """GitHub issue information."""

    id: int = Field(..., description="Issue ID")
    number: int = Field(..., description="Issue number")
    title: str = Field(..., description="Issue title")
    body: str | None = Field(None, description="Issue body")
    state: str = Field(..., description="Issue state (open, closed)")
    user: GitHubUser = Field(..., description="Issue author")
    labels: list[GitHubLabel] = Field(default_factory=list, description="Issue labels")
    assignees: list[GitHubUser] = Field(default_factory=list, description="Assignees")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")


class GitHubIssueEvent(BaseModel):
    """
    GitHub issues webhook event payload.

    Triggered when an issue is opened, edited, closed, reopened,
    labeled, unlabeled, assigned, or unassigned.
    """

    action: str = Field(..., description="Event action (opened, labeled, etc.)")
    issue: GitHubIssue = Field(..., description="Issue that triggered the event")
    repository: GitHubRepository = Field(..., description="Repository containing the issue")
    sender: GitHubUser = Field(..., description="User who triggered the event")
    label: GitHubLabel | None = Field(None, description="Label (for labeled/unlabeled events)")

    def is_labeled_event(self) -> bool:
        """Check if this is a label event."""
        return self.action == "labeled" and self.label is not None

    def has_label(self, label_name: str) -> bool:
        """Check if the issue has a specific label."""
        return any(label.name == label_name for label in self.issue.labels)


class GitHubWebhookPayload(BaseModel):
    """
    Generic GitHub webhook payload wrapper.

    Used for initial parsing before determining the event type.
    """

    zen: str | None = Field(None, description="Zen message (ping events only)")
    hook_id: int | None = Field(None, description="Hook ID (ping events only)")
    action: str | None = Field(None, description="Event action")
    repository: GitHubRepository | None = Field(None, description="Repository")
    sender: GitHubUser | None = Field(None, description="Sender")

    # Raw payload for debugging
    raw_payload: dict[str, Any] | None = Field(default=None, exclude=True)

    def is_ping(self) -> bool:
        """Check if this is a ping event."""
        return self.zen is not None

    def is_issues_event(self) -> bool:
        """Check if this is an issues event."""
        return self.action is not None and hasattr(self, "issue")
