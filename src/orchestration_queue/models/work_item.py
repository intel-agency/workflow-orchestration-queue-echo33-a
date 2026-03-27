"""
Core data models for workflow orchestration queue.

This module defines the unified WorkItem model and related enums that
represent tasks throughout the orchestration system.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class TaskType(StrEnum):
    """Type of task to be executed by the orchestrator."""

    PLAN = "plan"
    """Create an application plan from a specification."""

    IMPLEMENT = "implement"
    """Implement a planned feature or task."""

    BUGFIX = "bugfix"
    """Fix a bug or issue."""


class WorkItemStatus(StrEnum):
    """
    Status of a work item in the orchestration queue.

    Maps to GitHub labels for state machine tracking.
    """

    QUEUED = "agent:queued"
    """Task validated, awaiting Sentinel pickup."""

    IN_PROGRESS = "agent:in-progress"
    """Sentinel has claimed and is processing the task."""

    RECONCILING = "agent:reconciling"
    """Stale task being recovered."""

    SUCCESS = "agent:success"
    """Terminal: Task completed successfully (PR created, tests passed)."""

    ERROR = "agent:error"
    """Terminal: Technical failure (logs posted to issue)."""

    INFRA_FAILURE = "agent:infra-failure"
    """Terminal: Infrastructure failure (container/build error)."""

    STALLED_BUDGET = "agent:stalled-budget"
    """Terminal: Cost guardrails exceeded (future implementation)."""


class WorkItem(BaseModel):
    """
    Unified work item representing a task in the orchestration queue.

    This is the core data structure that flows through all components
    of the orchestration system.
    """

    id: int = Field(..., description="GitHub issue number")
    title: str = Field(..., description="Issue title")
    body: str | None = Field(None, description="Issue body/description")
    task_type: TaskType = Field(..., description="Type of task to execute")
    status: WorkItemStatus = Field(default=WorkItemStatus.QUEUED, description="Current status")
    repository: str = Field(..., description="Full repository name (owner/repo)")
    author: str = Field(..., description="GitHub username of issue author")
    labels: list[str] = Field(default_factory=list, description="GitHub labels")
    assignees: list[str] = Field(default_factory=list, description="Assigned users")
    created_at: str | None = Field(None, description="ISO 8601 creation timestamp")
    updated_at: str | None = Field(None, description="ISO 8601 update timestamp")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": 42,
                    "title": "Add user authentication",
                    "body": "Implement OAuth2 login flow...",
                    "task_type": "implement",
                    "status": "agent:queued",
                    "repository": "intel-agency/workflow-orchestration-queue-echo33-a",
                    "author": "developer",
                    "labels": ["enhancement", "implementation:ready"],
                    "assignees": [],
                    "created_at": "2024-01-15T10:30:00Z",
                    "updated_at": "2024-01-15T10:30:00Z",
                }
            ]
        }
    }

    def has_label(self, label: str) -> bool:
        """Check if the work item has a specific label."""
        return label in self.labels

    def is_assigned(self) -> bool:
        """Check if the work item is assigned to someone."""
        return len(self.assignees) > 0

    def to_github_labels(self) -> list[str]:
        """Get all labels including status label."""
        # Remove any existing status labels and add current status
        status_labels = {s.value for s in WorkItemStatus}
        filtered_labels = [label for label in self.labels if label not in status_labels]
        return [*filtered_labels, self.status.value]


def scrub_secrets(text: str) -> str:
    """
    Remove sensitive credentials from text before public posting.

    Patterns scrubbed:
    - GitHub PATs: ghp_*, ghs_*, gho_*, github_pat_*
    - API keys: sk-*, Bearer tokens
    - ZhipuAI keys
    - Generic API key patterns

    Args:
        text: Text that may contain sensitive credentials.

    Returns:
        Text with credentials replaced by [REDACTED].
    """
    import re

    patterns = [
        # GitHub Personal Access Tokens
        (r"ghp_[a-zA-Z0-9]{36}", "[REDACTED_GITHUB_PAT]"),
        (r"ghs_[a-zA-Z0-9]{36}", "[REDACTED_GITHUB_SERVER]"),
        (r"gho_[a-zA-Z0-9]{36}", "[REDACTED_GITHUB_OAUTH]"),
        (r"github_pat_[a-zA-Z0-9]{22}_[a-zA-Z0-9]{59}", "[REDACTED_GITHUB_FINE_GRAINED]"),
        # OpenAI-style API keys
        (r"sk-[a-zA-Z0-9]{20,}", "[REDACTED_API_KEY]"),
        (r"sk-proj-[a-zA-Z0-9]{20,}", "[REDACTED_PROJECT_KEY]"),
        # Bearer tokens
        (r"Bearer\s+[a-zA-Z0-9._-]+", "Bearer [REDACTED]"),
        # ZhipuAI keys (format varies)
        (r"zhipu[a-zA-Z0-9._-]*", "[REDACTED_ZHIPU]"),
        # Generic API key patterns in URLs
        (r"api_key=[a-zA-Z0-9_-]+", "api_key=[REDACTED]"),
        (r"apikey=[a-zA-Z0-9_-]+", "apikey=[REDACTED]"),
        # Generic secret patterns
        (r"secret[_-]?key[=:]\s*[a-zA-Z0-9_-]+", "secret_key=[REDACTED]"),
        (r"token[=:]\s*[a-zA-Z0-9._-]+", "token=[REDACTED]"),
    ]

    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    return result
