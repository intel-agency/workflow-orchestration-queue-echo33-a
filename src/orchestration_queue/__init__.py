"""
workflow-orchestration-queue: Headless agentic orchestration platform.

This package provides the core components for transforming GitHub Issues
into automated execution orders for AI agents.

Architecture (The Four Pillars):
- The Ear (Notifier): FastAPI webhook receiver with HMAC verification
- The State (Queue): GitHub Issues as distributed state management
- The Brain (Sentinel): Persistent background service for task discovery
- The Hands (Worker): Isolated DevContainer executing AI workflows
"""

__version__ = "0.1.0"
__author__ = "Intel Agency"

from orchestration_queue.models.work_item import TaskType, WorkItem, WorkItemStatus

__all__ = [
    "TaskType",
    "WorkItem",
    "WorkItemStatus",
    "__version__",
]
