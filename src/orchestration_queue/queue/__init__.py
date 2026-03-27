"""Queue package for workflow orchestration."""

from orchestration_queue.queue.github_queue import GitHubQueue, ITaskQueue

__all__ = [
    "GitHubQueue",
    "ITaskQueue",
]
