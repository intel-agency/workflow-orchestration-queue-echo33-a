"""
Pytest configuration and fixtures for workflow-orchestration-queue tests.
"""

import asyncio
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

# Configure asyncio mode
pytestmark = pytest.mark.asyncio(loop_scope="function")


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_github_token() -> str:
    """Return a mock GitHub token for testing."""
    return "FAKE-GITHUB-TOKEN-FOR-TESTING-00000000"


@pytest.fixture
def mock_webhook_secret() -> str:
    """Return a mock webhook secret for testing."""
    return "FAKE-WEBHOOK-SECRET-FOR-TESTING-00000000"


@pytest.fixture
def sample_issue_payload() -> dict[str, Any]:
    """Return a sample GitHub issue webhook payload."""
    return {
        "action": "opened",
        "issue": {
            "id": 123456789,
            "number": 42,
            "title": "Add user authentication",
            "body": "Implement OAuth2 login flow for the application.\n\n[Application Plan]",
            "state": "open",
            "user": {
                "login": "developer",
                "id": 12345,
                "type": "User",
            },
            "labels": [
                {"name": "enhancement", "color": "a2eeef"},
            ],
            "assignees": [],
            "created_at": "2024-01-15T10:30:00Z",
            "updated_at": "2024-01-15T10:30:00Z",
        },
        "repository": {
            "id": 987654321,
            "name": "workflow-orchestration-queue-echo33-a",
            "full_name": "intel-agency/workflow-orchestration-queue-echo33-a",
            "owner": {
                "login": "intel-agency",
                "id": 11111,
                "type": "Organization",
            },
            "private": False,
        },
        "sender": {
            "login": "developer",
            "id": 12345,
            "type": "User",
        },
    }


@pytest.fixture
def sample_labeled_payload() -> dict[str, Any]:
    """Return a sample GitHub issue labeled webhook payload."""
    return {
        "action": "labeled",
        "issue": {
            "id": 123456789,
            "number": 42,
            "title": "Add user authentication",
            "body": "Implement OAuth2 login flow for the application.",
            "state": "open",
            "user": {
                "login": "developer",
                "id": 12345,
                "type": "User",
            },
            "labels": [
                {"name": "enhancement", "color": "a2eeef"},
                {"name": "implementation:ready", "color": "00ff00"},
            ],
            "assignees": [],
            "created_at": "2024-01-15T10:30:00Z",
            "updated_at": "2024-01-15T10:30:00Z",
        },
        "repository": {
            "id": 987654321,
            "name": "workflow-orchestration-queue-echo33-a",
            "full_name": "intel-agency/workflow-orchestration-queue-echo33-a",
            "owner": {
                "login": "intel-agency",
                "id": 11111,
                "type": "Organization",
            },
            "private": False,
        },
        "sender": {
            "login": "developer",
            "id": 12345,
            "type": "User",
        },
        "label": {
            "name": "implementation:ready",
            "color": "00ff00",
        },
    }


@pytest.fixture
def sample_work_item() -> dict[str, Any]:
    """Return a sample WorkItem for testing."""
    return {
        "id": 42,
        "title": "Add user authentication",
        "body": "Implement OAuth2 login flow for the application.",
        "task_type": "implement",
        "status": "agent:queued",
        "repository": "intel-agency/workflow-orchestration-queue-echo33-a",
        "author": "developer",
        "labels": ["enhancement", "implementation:ready"],
        "assignees": [],
        "created_at": "2024-01-15T10:30:00Z",
        "updated_at": "2024-01-15T10:30:00Z",
    }


@pytest_asyncio.fixture
async def mock_httpx_client() -> AsyncMock:
    """Return a mock httpx.AsyncClient for testing."""
    client = AsyncMock()
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.patch = AsyncMock()
    client.aclose = AsyncMock()
    return client
