"""
Sentinel orchestrator service (The Brain).

This is the persistent background service responsible for:
- Polling for queued tasks
- Claiming tasks via assign-then-verify
- Executing workflows via shell bridge
- Posting heartbeats for progress visibility
"""

import asyncio
import contextlib
import logging
import random
import signal
import subprocess
from datetime import UTC, datetime

from orchestration_queue.config import ConfigurationError, get_settings, validate_startup
from orchestration_queue.models.work_item import (
    TaskType,
    WorkItem,
    WorkItemStatus,
    scrub_secrets,
)
from orchestration_queue.queue.github_queue import GitHubQueue

logger = logging.getLogger(__name__)

# Get settings and configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


class SentinelOrchestrator:
    """
    Persistent orchestrator service that manages task lifecycle.

    The Sentinel is "The Brain" of the orchestration system:
    - Polls for queued tasks (discovery)
    - Claims tasks atomically (locking)
    - Executes workflows via shell bridge (delegation)
    - Posts heartbeats for visibility (progress)
    """

    def __init__(self) -> None:
        """Initialize the sentinel orchestrator."""
        self._running = False
        self._current_task: WorkItem | None = None
        self._shutdown_event = asyncio.Event()
        self._queue: GitHubQueue | None = None

        # Validate configuration at startup
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate required configuration at startup."""
        try:
            validate_startup()
        except ConfigurationError:
            raise

        if not settings.sentinel.bot_login:
            logger.warning("SENTINEL_BOT_LOGIN not set - distributed locking disabled")

    async def _get_queue(self) -> GitHubQueue:
        """Get or create the GitHub queue instance."""
        if self._queue is None:
            self._queue = GitHubQueue(
                token=settings.github.token,
                org=settings.github.owner,
                repo=settings.github.repo,
                poll_interval=settings.sentinel.poll_interval,
            )
        return self._queue

    async def start(self) -> None:
        """Start the sentinel polling loop."""
        logger.info("Starting Sentinel Orchestrator")
        logger.info("Repository: %s", settings.github.repository)
        logger.info("Poll interval: %.1f seconds", settings.sentinel.poll_interval)

        self._running = True

        # Setup signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._handle_shutdown_signal)

        try:
            await self._run_polling_loop()
        finally:
            await self._cleanup()

    def _handle_shutdown_signal(self) -> None:
        """Handle shutdown signals gracefully."""
        logger.info("Received shutdown signal")
        self._shutdown_event.set()

    def _calculate_backoff(self, consecutive_errors: int) -> float:
        """Calculate backoff with jitter.

        Uses exponential backoff with:
        - Base: configurable via settings.sentinel.backoff_base_seconds
        - Cap: configurable via settings.sentinel.backoff_max_seconds
        - Jitter: +0-25% randomization

        Args:
            consecutive_errors: Number of consecutive failed polls

        Returns:
            Backoff time in seconds with jitter applied
        """
        base = settings.sentinel.backoff_base_seconds
        max_backoff = settings.sentinel.backoff_max_seconds

        # Exponential backoff with cap
        backoff = min(base * (2**consecutive_errors), max_backoff)

        # Add jitter (0-25% additional delay)
        jitter = backoff * 0.25 * random.random()

        return backoff + jitter

    async def _run_polling_loop(self) -> None:
        """Main polling loop for task discovery with jittered exponential backoff."""
        consecutive_errors = 0

        while self._running and not self._shutdown_event.is_set():
            try:
                await self._poll_and_process()

                # Success - reset backoff counter
                if consecutive_errors > 0:
                    logger.info(
                        "Poll recovered after %d error(s), resetting backoff",
                        consecutive_errors,
                    )
                consecutive_errors = 0

            except Exception as e:
                # Calculate backoff BEFORE incrementing to use base on first error
                backoff = self._calculate_backoff(consecutive_errors)
                consecutive_errors += 1
                logger.error(
                    "Error in polling cycle (attempt %d): %s - backing off for %.1fs",
                    consecutive_errors,
                    e,
                    backoff,
                    exc_info=True,
                )

                # Wait with backoff or until shutdown
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=backoff,
                    )
                    break  # Shutdown requested
                except TimeoutError:
                    continue  # Continue polling after backoff

            # Wait for next poll interval or shutdown
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=settings.sentinel.poll_interval,
                )
                break  # Shutdown requested
            except TimeoutError:
                pass  # Continue polling

    async def _poll_and_process(self) -> None:
        """Poll for tasks and process one if available."""
        queue = await self._get_queue()

        logger.debug("Polling for queued tasks...")
        tasks = await queue.fetch_queued_tasks()

        if not tasks:
            logger.debug("No queued tasks found")
            return

        logger.info("Found %d queued task(s)", len(tasks))

        # Process the first available task
        task = tasks[0]

        if not settings.sentinel.bot_login:
            logger.warning("Cannot claim task without SENTINEL_BOT_LOGIN")
            return

        # Try to claim the task
        claimed = await queue.claim_task(task.id, settings.sentinel.bot_login)

        if not claimed:
            logger.info("Failed to claim task #%d (likely claimed by another sentinel)", task.id)
            return

        self._current_task = task

        try:
            await self._execute_task(task)
        finally:
            self._current_task = None

    async def _execute_task(self, task: WorkItem) -> None:
        """
        Execute a claimed task via shell bridge.

        This method:
        1. Posts a start comment
        2. Runs the shell bridge commands
        3. Posts result status
        """
        queue = await self._get_queue()

        start_time = datetime.now(UTC)
        start_message = (
            f"🚀 **Task Started**\n\n"
            f"- **Issue:** #{task.id}\n"
            f"- **Type:** {task.task_type.value}\n"
            f"- **Started:** {start_time.isoformat()}\n"
            f"- **Sentinel:** {settings.sentinel.bot_login}"
        )
        await queue.post_heartbeat(task.id, scrub_secrets(start_message))

        # Start heartbeat task
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(task.id, start_time))

        try:
            # Execute via shell bridge
            result = await self._run_shell_bridge(task)

            # Determine final status
            if result.success:
                status = WorkItemStatus.SUCCESS
                result_message = (
                    f"✅ **Task Completed Successfully**\n\n"
                    f"- **Duration:** {self._format_duration(start_time)}\n"
                    f"- **Artifacts:** See linked PR(s)"
                )
            else:
                status = WorkItemStatus.ERROR
                result_message = (
                    f"❌ **Task Failed**\n\n"
                    f"- **Duration:** {self._format_duration(start_time)}\n"
                    f"- **Exit Code:** {result.returncode}\n"
                    f"- **Error:**\n```\n{scrub_secrets(result.stderr[-1000:])}\n```"
                )

            await queue.update_status(task.id, status, scrub_secrets(result_message))

        except Exception as e:
            logger.error("Task execution failed: %s", e, exc_info=True)
            await queue.update_status(
                task.id,
                WorkItemStatus.INFRA_FAILURE,
                scrub_secrets(f"💥 **Infrastructure Error**\n\n```\n{e}\n```"),
            )

        finally:
            heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat_task

            # Reset environment after task completion (success or failure)
            await self._reset_environment()

    async def _run_shell_bridge(self, task: WorkItem) -> "ShellResult":
        """
        Execute the workflow via shell bridge.

        Shell bridge commands:
        1. up - Provision infrastructure
        2. start - Launch opencode server
        3. prompt - Execute workflow
        4. stop - Cleanup (optional)
        """
        bridge = settings.sentinel.shell_bridge_path
        instruction = self._build_instruction(task)

        # Step 1: Provision
        logger.info("Running shell bridge 'up' for task #%d", task.id)
        up_result = await self._run_command([bridge, "up"])
        if not up_result.success:
            return up_result

        # Step 2: Start server
        logger.info("Running shell bridge 'start' for task #%d", task.id)
        start_result = await self._run_command([bridge, "start"])
        if not start_result.success:
            return start_result

        # Step 3: Execute prompt
        logger.info("Running shell bridge 'prompt' for task #%d", task.id)
        prompt_result = await self._run_command(
            [bridge, "prompt", "-f", "-"],
            input_text=instruction,
        )

        return prompt_result

    def _build_instruction(self, task: WorkItem) -> str:
        """Build the instruction prompt for the task."""
        if task.task_type == TaskType.PLAN:
            return f"""Create an application plan for the following specification:

**Issue #{task.id}: {task.title}**

{task.body or "No description provided."}

Create a comprehensive implementation plan following the project conventions."""

        elif task.task_type == TaskType.BUGFIX:
            return f"""Analyze and fix the following bug:

**Issue #{task.id}: {task.title}**

{task.body or "No description provided."}

Investigate the issue, identify the root cause, and implement a fix with tests."""

        else:  # IMPLEMENT
            return f"""Implement the following task:

**Issue #{task.id}: {task.title}**

{task.body or "No description provided."}

Implement the required changes following the project conventions and ensure all tests pass."""

    async def _run_command(
        self,
        args: list[str],
        input_text: str | None = None,
    ) -> "ShellResult":
        """Run a shell command with timeout."""
        logger.debug("Running command: %s", " ".join(args))

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdin=subprocess.PIPE if input_text else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(input_text.encode() if input_text else None),
                    timeout=settings.sentinel.subprocess_timeout,
                )
            except TimeoutError:
                process.kill()
                await process.wait()
                raise

            return ShellResult(
                returncode=process.returncode if process.returncode is not None else 1,
                stdout=stdout.decode("utf-8", errors="replace"),
                stderr=stderr.decode("utf-8", errors="replace"),
            )

        except Exception as e:
            logger.error("Command failed: %s", e)
            return ShellResult(
                returncode=1,
                stdout="",
                stderr=str(e),
            )

    async def _heartbeat_loop(self, task_id: int, start_time: datetime) -> None:
        """Post periodic heartbeat comments."""
        queue = await self._get_queue()

        while True:
            await asyncio.sleep(settings.sentinel.heartbeat_interval)

            elapsed = self._format_duration(start_time)
            message = f"⏱️ **Heartbeat** - Elapsed: {elapsed}"

            try:
                await queue.post_heartbeat(task_id, message)
                logger.debug("Posted heartbeat for task #%d", task_id)
            except Exception as e:
                logger.warning("Failed to post heartbeat: %s", e)

    async def _reset_environment(self) -> bool:
        """
        Reset environment between tasks.

        This method:
        1. Stops the devcontainer via shell bridge stop command
        2. Logs all reset actions for audit trail
        3. Handles failures gracefully (not fatal)

        Returns:
            True if reset completed (even with warnings), False on critical errors
        """
        logger.info("Resetting environment for next task")

        try:
            # Stop container via shell bridge
            bridge = settings.sentinel.shell_bridge_path
            result = await self._run_command([bridge, "stop"])

            if not result.success:
                logger.warning(
                    "Environment reset stop command failed (exit code %d): %s",
                    result.returncode,
                    result.stderr,
                )
                # Continue anyway - not a fatal error
            else:
                logger.info("Environment reset stop command succeeded")

            logger.info("Environment reset complete")
            return True

        except Exception as e:
            logger.error("Environment reset failed with exception: %s", e, exc_info=True)
            return False

    def _format_duration(self, start_time: datetime) -> str:
        """Format elapsed time since start."""
        elapsed = datetime.now(UTC) - start_time
        hours, remainder = divmod(int(elapsed.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    async def _cleanup(self) -> None:
        """Cleanup resources on shutdown."""
        logger.info("Cleaning up sentinel resources")

        if self._queue is not None:
            await self._queue.close()

        self._running = False


class ShellResult:
    """Result of a shell command execution."""

    def __init__(
        self,
        returncode: int,
        stdout: str,
        stderr: str,
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    @property
    def success(self) -> bool:
        """Check if command succeeded."""
        return self.returncode == 0


async def main() -> None:
    """Main entry point for the sentinel service."""
    sentinel = SentinelOrchestrator()
    await sentinel.start()


if __name__ == "__main__":
    asyncio.run(main())
