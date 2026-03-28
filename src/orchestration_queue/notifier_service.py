"""
FastAPI webhook receiver service (The Ear).

This service provides secure webhook ingestion with HMAC SHA256 verification,
intelligent event triaging, and queue initialization.
"""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from orchestration_queue.config import ConfigurationError, get_settings, validate_startup
from orchestration_queue.models.github_events import GitHubIssueEvent
from orchestration_queue.models.work_item import WorkItemStatus
from orchestration_queue.queue.github_queue import GitHubQueue, verify_webhook_signature

logger = logging.getLogger(__name__)

# Get settings and configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Global queue instance
_queue: GitHubQueue | None = None


async def get_queue() -> GitHubQueue:
    """Get or create the GitHub queue instance."""
    global _queue
    if _queue is None:
        _queue = GitHubQueue(
            token=settings.github_token,
            org=settings.github_owner,
            repo=settings.github_repo,
        )
    return _queue


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Validate configuration at startup
    try:
        validate_startup()
    except ConfigurationError as e:
        logger.error("Configuration validation failed: %s", e)
        raise

    logger.info("Starting %s service", settings.notifier_service_name)

    # Warn if webhook secret not set
    if not settings.notifier_webhook_secret:
        logger.warning("NOTIFIER_WEBHOOK_SECRET not set - webhook verification disabled")

    yield

    # Cleanup
    if _queue is not None:
        await _queue.close()
    logger.info("Shutting down %s service", settings.notifier_service_name)


app = FastAPI(
    title="workflow-orchestration-queue",
    description="Headless agentic orchestration platform webhook receiver",
    version="0.1.0",
    lifespan=lifespan,
)


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    service: str
    version: str


@app.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check endpoint for monitoring.

    Returns basic service status and version information.
    """
    return HealthResponse(
        status="healthy",
        service=settings.notifier.service_name,
        version="0.1.0",
    )


@app.post("/webhooks/github")
async def handle_github_webhook(
    request: Request,
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
    x_github_delivery: str = Header(default=""),
) -> JSONResponse:
    """
    Handle incoming GitHub webhooks.

    This endpoint:
    1. Verifies HMAC SHA256 signature
    2. Parses the event payload
    3. Triages the event type
    4. Queues valid tasks via GitHub API

    Returns:
        202 Accepted if the event is queued
        401 Unauthorized if signature verification fails
        400 Bad Request if payload is invalid
    """
    # Get raw body for signature verification
    payload_bytes = await request.body()

    # Verify webhook signature
    if settings.notifier.webhook_secret and not verify_webhook_signature(
        payload_bytes, x_hub_signature_256, settings.notifier.webhook_secret
    ):
        logger.warning("Invalid webhook signature from delivery %s", x_github_delivery)
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse payload
    try:
        payload = await request.json()
    except Exception as e:
        logger.error("Failed to parse webhook payload: %s", e)
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from e

    # Handle ping events
    if x_github_event == "ping":
        logger.info("Received ping event")
        return JSONResponse(
            status_code=200,
            content={"message": "pong", "zen": payload.get("zen", "")},
        )

    # Handle issues events
    if x_github_event == "issues":
        return await handle_issues_event(payload, x_github_delivery)

    # Log unhandled event types
    logger.info(
        "Received unhandled event type: %s (delivery: %s)",
        x_github_event,
        x_github_delivery,
    )

    return JSONResponse(
        status_code=202,
        content={"message": f"Event {x_github_event} acknowledged but not processed"},
    )


async def handle_issues_event(
    payload: dict[str, Any],
    delivery_id: str,
) -> JSONResponse:
    """
    Process GitHub issues webhook events.

    Validates issue templates and queues tasks for processing.
    """
    try:
        event = GitHubIssueEvent.model_validate(payload)
    except Exception as e:
        logger.error("Failed to parse issues event: %s", e)
        raise HTTPException(status_code=400, detail="Invalid issues event payload") from e

    # Only process opened or labeled events
    if event.action not in ("opened", "labeled"):
        logger.debug(
            "Ignoring issues action: %s (issue #%d)",
            event.action,
            event.issue.number,
        )
        return JSONResponse(
            status_code=202,
            content={"message": f"Action {event.action} acknowledged"},
        )

    # Check for workflow-relevant labels
    is_workflow_label = (
        event.is_labeled_event()
        and event.label is not None
        and (
            event.label.name.startswith("orchestration:")
            or event.label.name == "implementation:ready"
            or event.label.name == "implementation:complete"
        )
    )

    # Check for application plan template
    is_application_plan = event.issue.body is not None and "[Application Plan]" in event.issue.body

    if not (is_workflow_label or is_application_plan):
        logger.debug(
            "Ignoring non-workflow issue #%d (action: %s)",
            event.issue.number,
            event.action,
        )
        return JSONResponse(
            status_code=202,
            content={"message": "Issue does not require orchestration"},
        )

    # Queue the task
    try:
        queue = await get_queue()

        # Determine if we need to add the queued label
        if not event.has_label(WorkItemStatus.QUEUED.value):
            success = await queue.update_status(
                event.issue.number,
                WorkItemStatus.QUEUED,
                message="🎯 Task queued for processing by the orchestration system.",
            )
            if success:
                logger.info(
                    "Queued issue #%d for processing (delivery: %s)",
                    event.issue.number,
                    delivery_id,
                )
            else:
                logger.warning(
                    "Failed to queue issue #%d (delivery: %s)",
                    event.issue.number,
                    delivery_id,
                )
        else:
            logger.info(
                "Issue #%d already queued (delivery: %s)",
                event.issue.number,
                delivery_id,
            )

    except Exception as e:
        logger.error("Failed to queue issue #%d: %s", event.issue.number, e)
        # Return 202 anyway - polling will pick it up
        pass

    return JSONResponse(
        status_code=202,
        content={
            "message": "Event accepted and queued",
            "issue_number": event.issue.number,
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "orchestration_queue.notifier_service:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level=settings.log_level.lower(),
    )
