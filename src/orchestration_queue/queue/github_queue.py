"""
GitHub Issues-based task queue implementation.

This module provides the ITaskQueue interface and GitHubQueue implementation
for managing tasks via GitHub Issues (the "Markdown as a Database" pattern).
"""

import asyncio
import hashlib
import hmac
import logging
from abc import ABC, abstractmethod

import httpx

from orchestration_queue.models.work_item import (
    TaskType,
    WorkItem,
    WorkItemStatus,
)

logger = logging.getLogger(__name__)


class ITaskQueue(ABC):
    """
    Abstract interface for task queue operations.

    This abstraction allows the orchestrator to work with different
    queue providers (GitHub, Linear, Jira, SQL databases) without
    modification (ADR 09: Provider-Agnostic Interface Layer).
    """

    @abstractmethod
    async def fetch_queued_tasks(self) -> list[WorkItem]:
        """
        Fetch all tasks currently in the queue.

        Returns:
            List of WorkItem objects with QUEUED status.
        """
        pass

    @abstractmethod
    async def claim_task(self, task_id: int, sentinel_id: str) -> bool:
        """
        Atomically claim a task for processing.

        Uses the assign-then-verify pattern for distributed locking:
        1. Assign the task to the sentinel
        2. Re-fetch the task
        3. Verify the sentinel is the only assignee

        Args:
            task_id: The issue number to claim.
            sentinel_id: Identifier of the sentinel claiming the task.

        Returns:
            True if claim was successful, False if already claimed.
        """
        pass

    @abstractmethod
    async def update_status(
        self, task_id: int, status: WorkItemStatus, message: str | None = None
    ) -> bool:
        """
        Update the status of a task.

        Args:
            task_id: The issue number to update.
            status: The new status to set.
            message: Optional message to post as a comment.

        Returns:
            True if update was successful.
        """
        pass

    @abstractmethod
    async def post_heartbeat(self, task_id: int, message: str) -> bool:
        """
        Post a progress heartbeat comment on a task.

        Args:
            task_id: The issue number.
            message: Progress message to post.

        Returns:
            True if heartbeat was posted successfully.
        """
        pass


class GitHubQueue(ITaskQueue):
    """
    GitHub Issues-based task queue implementation.

    Uses GitHub Issues as the persistence layer for task state,
    leveraging labels for status tracking and assignees for locking.
    """

    API_BASE = "https://api.github.com"

    def __init__(
        self,
        token: str,
        org: str,
        repo: str,
        *,
        http_client: httpx.AsyncClient | None = None,
        poll_interval: float = 60.0,
        max_retries: int = 3,
    ):
        """
        Initialize the GitHub queue.

        Args:
            token: GitHub Personal Access Token with repo scope.
            org: GitHub organization or user name.
            repo: Repository name.
            http_client: Optional pre-configured HTTP client.
            poll_interval: Seconds between polling cycles.
            max_retries: Maximum retry attempts for rate limits.
        """
        self.token = token
        self.org = org
        self.repo = repo
        self.poll_interval = poll_interval
        self.max_retries = max_retries
        self._client = http_client
        self._owns_client = http_client is None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.API_BASE,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "workflow-orchestration-queue/0.1.0",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client if we own it."""
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _get_issue_url(self, issue_number: int | None = None) -> str:
        """Build the GitHub API URL for issues."""
        base = f"/repos/{self.org}/{self.repo}/issues"
        if issue_number is not None:
            return f"{base}/{issue_number}"
        return base

    async def _handle_rate_limit(self, response: httpx.Response) -> None:
        """Handle rate limiting with exponential backoff."""
        if response.status_code in (403, 429):
            retry_after = response.headers.get("Retry-After", "60")
            wait_time = float(retry_after)
            logger.warning("Rate limited, waiting %.1f seconds before retry", wait_time)
            await asyncio.sleep(wait_time)

    async def fetch_queued_tasks(self) -> list[WorkItem]:
        """
        Fetch all issues with the agent:queued label.

        Returns:
            List of WorkItem objects ready for processing.
        """
        client = await self._get_client()

        for _attempt in range(self.max_retries):
            response = await client.get(
                self._get_issue_url(),
                params={
                    "state": "open",
                    "labels": WorkItemStatus.QUEUED.value,
                    "sort": "created",
                    "direction": "asc",
                },
            )

            if response.status_code in (403, 429):
                await self._handle_rate_limit(response)
                continue

            response.raise_for_status()
            issues = response.json()

            work_items = []
            for issue in issues:
                # Determine task type from labels
                task_type = self._determine_task_type(issue.get("labels", []))

                work_item = WorkItem(
                    id=issue["number"],
                    title=issue["title"],
                    body=issue.get("body"),
                    task_type=task_type,
                    status=WorkItemStatus.QUEUED,
                    repository=f"{self.org}/{self.repo}",
                    author=issue["user"]["login"],
                    labels=[label["name"] for label in issue.get("labels", [])],
                    assignees=[assignee["login"] for assignee in issue.get("assignees", [])],
                    created_at=issue.get("created_at"),
                    updated_at=issue.get("updated_at"),
                )
                work_items.append(work_item)

            return work_items

        return []

    def _determine_task_type(self, labels: list[dict]) -> TaskType:
        """Determine task type from issue labels."""
        label_names = {label.get("name", "") for label in labels}

        if "task:plan" in label_names or "type:plan" in label_names:
            return TaskType.PLAN
        if "task:bugfix" in label_names or "type:bug" in label_names:
            return TaskType.BUGFIX

        # Default to implement for most tasks
        return TaskType.IMPLEMENT

    async def claim_task(self, task_id: int, sentinel_id: str) -> bool:
        """
        Claim a task using the assign-then-verify pattern.

        1. Assign the issue to the sentinel
        2. Re-fetch the issue
        3. Verify the sentinel is the only assignee

        Args:
            task_id: Issue number to claim.
            sentinel_id: Sentinel's GitHub username.

        Returns:
            True if claim was successful, False otherwise.
        """
        client = await self._get_client()
        issue_url = self._get_issue_url(task_id)

        # Step 1: Assign to sentinel
        for _attempt in range(self.max_retries):
            assign_response = await client.post(
                f"{issue_url}/assignees",
                json={"assignees": [sentinel_id]},
            )

            if assign_response.status_code in (403, 429):
                await self._handle_rate_limit(assign_response)
                continue

            if assign_response.status_code not in (200, 201):
                logger.warning(
                    "Failed to assign issue %d: status %d",
                    task_id,
                    assign_response.status_code,
                )
                return False
            break

        # Step 2: Re-fetch to verify
        await asyncio.sleep(0.5)  # Brief delay for eventual consistency

        for _attempt in range(self.max_retries):
            verify_response = await client.get(issue_url)

            if verify_response.status_code in (403, 429):
                await self._handle_rate_limit(verify_response)
                continue

            verify_response.raise_for_status()
            issue = verify_response.json()

            # Step 3: Verify sentinel is the only assignee
            assignees = [a["login"] for a in issue.get("assignees", [])]

            if assignees == [sentinel_id]:
                # Update status to in-progress
                await self.update_status(task_id, WorkItemStatus.IN_PROGRESS)
                logger.info("Successfully claimed issue %d", task_id)
                return True

            logger.warning(
                "Claim failed for issue %d: assignees=%s, expected=[%s]",
                task_id,
                assignees,
                sentinel_id,
            )
            return False

        return False

    async def update_status(
        self, task_id: int, status: WorkItemStatus, message: str | None = None
    ) -> bool:
        """
        Update issue status by managing labels.

        Args:
            task_id: Issue number.
            status: New status to set.
            message: Optional comment to post.

        Returns:
            True if update was successful.
        """
        client = await self._get_client()
        issue_url = self._get_issue_url(task_id)

        # Get current labels
        for _attempt in range(self.max_retries):
            get_response = await client.get(issue_url)

            if get_response.status_code in (403, 429):
                await self._handle_rate_limit(get_response)
                continue

            get_response.raise_for_status()
            issue = get_response.json()
            break
        else:
            return False

        # Filter out old status labels and add new one
        status_labels = {s.value for s in WorkItemStatus}
        current_labels = [label["name"] for label in issue.get("labels", [])]
        filtered_labels = [lbl for lbl in current_labels if lbl not in status_labels]
        new_labels = [*filtered_labels, status.value]

        # Update labels
        for _attempt in range(self.max_retries):
            update_response = await client.patch(
                issue_url,
                json={"labels": new_labels},
            )

            if update_response.status_code in (403, 429):
                await self._handle_rate_limit(update_response)
                continue

            if update_response.status_code not in (200, 201):
                logger.warning(
                    "Failed to update issue %d status: %d",
                    task_id,
                    update_response.status_code,
                )
                return False
            break

        # Post comment if provided
        if message:
            await self.post_heartbeat(task_id, message)

        logger.info("Updated issue %d status to %s", task_id, status.value)
        return True

    async def post_heartbeat(self, task_id: int, message: str) -> bool:
        """
        Post a progress comment on the issue.

        Args:
            task_id: Issue number.
            message: Progress message.

        Returns:
            True if comment was posted successfully.
        """
        client = await self._get_client()
        issue_url = self._get_issue_url(task_id)

        for _attempt in range(self.max_retries):
            response = await client.post(
                f"{issue_url}/comments",
                json={"body": message},
            )

            if response.status_code in (403, 429):
                await self._handle_rate_limit(response)
                continue

            if response.status_code not in (200, 201):
                logger.warning(
                    "Failed to post heartbeat on issue %d: status %d",
                    task_id,
                    response.status_code,
                )
                return False

            logger.debug("Posted heartbeat on issue %d", task_id)
            return True

        return False


def verify_webhook_signature(
    payload: bytes,
    signature: str,
    secret: str,
) -> bool:
    """
    Verify GitHub webhook HMAC signature.

    Args:
        payload: Raw request body bytes.
        signature: X-Hub-Signature-256 header value.
        secret: Webhook secret.

    Returns:
        True if signature is valid.
    """
    if not signature.startswith("sha256="):
        return False

    expected_sig = signature[7:]  # Remove 'sha256=' prefix

    computed_sig = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_sig, computed_sig)
