"""
Unit tests for SentinelOrchestrator implementation.

Tests cover the sentinel orchestrator including polling loop behavior,
jittered exponential backoff, and error handling.
"""

import asyncio
import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestration_queue.orchestrator_sentinel import SentinelOrchestrator


class TestCalculateBackoff:
    """Tests for SentinelOrchestrator._calculate_backoff method."""

    @pytest.fixture
    def mock_settings(self) -> None:
        """Mock settings to avoid config validation errors."""
        with patch("orchestration_queue.orchestrator_sentinel.settings") as mock_settings:
            mock_settings.github_token = "FAKE-GITHUB-TOKEN-FOR-TESTING-00000000"
            mock_settings.github_org = "test-org"
            mock_settings.github_repo = "test-repo"
            mock_settings.sentinel_bot_login = "test-bot"
            mock_settings.poll_interval = 60.0
            mock_settings.heartbeat_interval = 300.0
            mock_settings.subprocess_timeout = 5700.0
            mock_settings.shell_bridge_path = "./scripts/devcontainer-opencode.sh"
            mock_settings.log_level = "INFO"
            mock_settings.backoff_base_seconds = 5.0
            mock_settings.backoff_max_seconds = 300.0
            yield mock_settings

    def test_backoff_increases_on_consecutive_errors(self, mock_settings: None) -> None:
        """Test that backoff increases exponentially with consecutive errors."""
        sentinel = SentinelOrchestrator()

        # Use fixed random to get deterministic jitter
        with patch("random.random", return_value=0.0):
            backoff_0 = sentinel._calculate_backoff(0)
            backoff_1 = sentinel._calculate_backoff(1)
            backoff_2 = sentinel._calculate_backoff(2)
            backoff_3 = sentinel._calculate_backoff(3)

        # Without jitter (random.random() = 0):
        # error 0: 5 * 2^0 = 5
        # error 1: 5 * 2^1 = 10
        # error 2: 5 * 2^2 = 20
        # error 3: 5 * 2^3 = 40
        assert backoff_0 == pytest.approx(5.0, rel=0.01)
        assert backoff_1 == pytest.approx(10.0, rel=0.01)
        assert backoff_2 == pytest.approx(20.0, rel=0.01)
        assert backoff_3 == pytest.approx(40.0, rel=0.01)

    def test_backoff_caps_at_max(self, mock_settings: None) -> None:
        """Test that backoff is capped at 300 seconds (5 minutes)."""
        sentinel = SentinelOrchestrator()

        # With jitter (random.random() = 0.5):
        # error 10: min(5 * 2^10, 300) + jitter = min(5120, 300) + jitter = 300 + jitter
        with patch("random.random", return_value=0.5):
            backoff = sentinel._calculate_backoff(10)

        # Max is 300, with 25% jitter (0.5 * 0.25 = 0.125)
        # 300 + (300 * 0.25 * 0.5) = 300 + 37.5 = 337.5
        assert backoff == pytest.approx(337.5, rel=0.01)
        assert backoff <= 300.0 * 1.25  # Max with max jitter

    def test_backoff_caps_at_max_no_jitter(self, mock_settings: None) -> None:
        """Test that backoff base is capped at 300 even with high error count."""
        sentinel = SentinelOrchestrator()

        # Without jitter, backoff should be exactly 300 at high error counts
        with patch("random.random", return_value=0.0):
            backoff = sentinel._calculate_backoff(100)

        assert backoff == pytest.approx(300.0, rel=0.01)

    def test_jitter_is_applied(self, mock_settings: None) -> None:
        """Test that jitter is applied to backoff values."""
        sentinel = SentinelOrchestrator()

        # Collect multiple backoff values for the same error count
        backoffs = []
        for _ in range(100):
            backoff = sentinel._calculate_backoff(2)
            backoffs.append(backoff)

        # All values should be in range [20, 25] (base 20 + 0-25% jitter)
        # base = 5 * 2^2 = 20
        # max_jitter = 20 * 0.25 = 5
        # range = [20, 25]
        assert all(20.0 <= b <= 25.0 for b in backoffs)

        # Values should vary (jitter is random)
        unique_values = set(backoffs)
        assert len(unique_values) > 1, "Jitter should produce varying values"

    def test_jitter_range(self, mock_settings: None) -> None:
        """Test that jitter adds 0-25% to the backoff value."""
        sentinel = SentinelOrchestrator()

        # Test with random.random() = 0 (no jitter)
        with patch("random.random", return_value=0.0):
            backoff_min = sentinel._calculate_backoff(1)
            assert backoff_min == pytest.approx(10.0, rel=0.01)

        # Test with random.random() = 1 (max jitter = 25%)
        with patch("random.random", return_value=1.0):
            backoff_max = sentinel._calculate_backoff(1)
            # 10 + (10 * 0.25 * 1) = 10 + 2.5 = 12.5
            assert backoff_max == pytest.approx(12.5, rel=0.01)

    def test_first_error_backoff(self, mock_settings: None) -> None:
        """Test backoff for first error is around 5 seconds."""
        sentinel = SentinelOrchestrator()

        # Collect samples to verify range
        backoffs = [sentinel._calculate_backoff(0) for _ in range(50)]

        # First error: base = 5 * 2^0 = 5
        # Range with jitter: [5, 6.25]
        assert all(5.0 <= b <= 6.25 for b in backoffs)


class TestPollingLoopBackoff:
    """Tests for backoff behavior in the polling loop."""

    @pytest.fixture
    def mock_settings(self) -> None:
        """Mock settings to avoid config validation errors."""
        with patch("orchestration_queue.orchestrator_sentinel.settings") as mock_settings:
            mock_settings.github_token = "FAKE-GITHUB-TOKEN-FOR-TESTING-00000000"
            mock_settings.github_org = "test-org"
            mock_settings.github_repo = "test-repo"
            mock_settings.sentinel_bot_login = "test-bot"
            mock_settings.poll_interval = 60.0
            mock_settings.heartbeat_interval = 300.0
            mock_settings.subprocess_timeout = 5700.0
            mock_settings.shell_bridge_path = "./scripts/devcontainer-opencode.sh"
            mock_settings.log_level = "INFO"
            mock_settings.backoff_base_seconds = 5.0
            mock_settings.backoff_max_seconds = 300.0
            yield mock_settings

    @pytest.mark.asyncio
    async def test_backoff_resets_on_successful_poll(self, mock_settings: None) -> None:
        """Test that consecutive_errors counter resets after successful poll."""
        sentinel = SentinelOrchestrator()
        sentinel._running = True

        # Track consecutive_errors through multiple poll cycles
        call_count = 0

        async def mock_poll_and_process() -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                sentinel._shutdown_event.set()

        with (
            patch.object(sentinel, "_poll_and_process", side_effect=mock_poll_and_process),
            patch("asyncio.wait_for", side_effect=TimeoutError),
        ):
            await sentinel._run_polling_loop()

        # Verify poll was called 3 times (no errors = no backoff delays)
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_backoff_increases_on_errors(self, mock_settings: None) -> None:
        """Test that backoff increases on consecutive errors."""
        sentinel = SentinelOrchestrator()
        sentinel._running = True

        error_count = 0
        sleep_times: list[float] = []

        async def mock_poll_that_fails() -> None:
            nonlocal error_count
            error_count += 1
            if error_count >= 3:
                sentinel._shutdown_event.set()
            raise RuntimeError("Simulated error")

        async def mock_wait_for(aw, timeout: float) -> None:
            sleep_times.append(timeout)
            raise TimeoutError()

        with (
            patch.object(sentinel, "_poll_and_process", side_effect=mock_poll_that_fails),
            patch("asyncio.wait_for", side_effect=mock_wait_for),
        ):
            await sentinel._run_polling_loop()

        # Verify backoff times increase
        assert len(sleep_times) >= 3
        # Each sleep time should be larger than the previous (exponential)
        # Account for jitter by checking approximate ordering
        assert sleep_times[1] > sleep_times[0]
        assert sleep_times[2] > sleep_times[1]

    @pytest.mark.asyncio
    async def test_backoff_uses_calculate_backoff_method(self, mock_settings: None) -> None:
        """Test that the polling loop uses _calculate_backoff for error delays."""
        sentinel = SentinelOrchestrator()
        sentinel._running = True

        calculated_backoffs: list[tuple[int, float]] = []

        original_calculate = sentinel._calculate_backoff

        def track_calculate(consecutive_errors: int) -> float:
            result = original_calculate(consecutive_errors)
            calculated_backoffs.append((consecutive_errors, result))
            return result

        error_count = 0

        async def mock_poll_that_fails() -> None:
            nonlocal error_count
            error_count += 1
            if error_count >= 3:
                sentinel._shutdown_event.set()
            raise RuntimeError("Simulated error")

        async def mock_wait_for(aw, timeout: float) -> None:
            raise TimeoutError()

        with (
            patch.object(sentinel, "_poll_and_process", side_effect=mock_poll_that_fails),
            patch.object(sentinel, "_calculate_backoff", side_effect=track_calculate),
            patch("asyncio.wait_for", side_effect=mock_wait_for),
        ):
            await sentinel._run_polling_loop()

        # Verify _calculate_backoff was called with increasing error counts
        # Note: consecutive_errors starts at 0, so first error uses backoff(0)
        assert len(calculated_backoffs) >= 3
        assert calculated_backoffs[0][0] == 0  # First error (base backoff)
        assert calculated_backoffs[1][0] == 1  # Second error
        assert calculated_backoffs[2][0] == 2  # Third error


class TestResetEnvironment:
    """Tests for SentinelOrchestrator._reset_environment method."""

    @pytest.fixture
    def mock_settings(self) -> None:
        """Mock settings to avoid config validation errors."""
        with patch("orchestration_queue.orchestrator_sentinel.settings") as mock_settings:
            mock_settings.github_token = "FAKE-GITHUB-TOKEN-FOR-TESTING-00000000"
            mock_settings.github_org = "test-org"
            mock_settings.github_repo = "test-repo"
            mock_settings.sentinel_bot_login = "test-bot"
            mock_settings.poll_interval = 60.0
            mock_settings.heartbeat_interval = 300.0
            mock_settings.subprocess_timeout = 5700.0
            mock_settings.shell_bridge_path = "./scripts/devcontainer-opencode.sh"
            mock_settings.log_level = "INFO"
            mock_settings.backoff_base_seconds = 5.0
            mock_settings.backoff_max_seconds = 300.0
            yield mock_settings

    @pytest.mark.asyncio
    async def test_reset_calls_shell_bridge_stop(self, mock_settings: None) -> None:
        """Test that _reset_environment calls shell bridge stop command."""
        sentinel = SentinelOrchestrator()

        # Mock _run_command to return success
        with patch.object(
            sentinel,
            "_run_command",
            return_value=type(
                "ShellResult",
                (),
                {"success": True, "returncode": 0, "stderr": ""},
            )(),
        ) as mock_run:
            result = await sentinel._reset_environment()

            # Verify stop command was called with correct args
            mock_run.assert_called_once_with(["./scripts/devcontainer-opencode.sh", "stop"])
            assert result is True

    @pytest.mark.asyncio
    async def test_reset_returns_true_on_success(self, mock_settings: None) -> None:
        """Test that _reset_environment returns True on successful stop."""
        sentinel = SentinelOrchestrator()

        with patch.object(
            sentinel,
            "_run_command",
            return_value=type(
                "ShellResult",
                (),
                {"success": True, "returncode": 0, "stderr": ""},
            )(),
        ):
            result = await sentinel._reset_environment()
            assert result is True

    @pytest.mark.asyncio
    async def test_reset_returns_true_on_command_failure(self, mock_settings: None) -> None:
        """Test that _reset_environment returns True even when stop fails (graceful handling)."""
        sentinel = SentinelOrchestrator()

        with patch.object(
            sentinel,
            "_run_command",
            return_value=type(
                "ShellResult",
                (),
                {"success": False, "returncode": 1, "stderr": "Stop failed"},
            )(),
        ):
            result = await sentinel._reset_environment()
            # Should still return True - failure is not fatal
            assert result is True

    @pytest.mark.asyncio
    async def test_reset_returns_false_on_exception(self, mock_settings: None) -> None:
        """Test that _reset_environment returns False on unexpected exception."""
        sentinel = SentinelOrchestrator()

        with patch.object(
            sentinel,
            "_run_command",
            side_effect=RuntimeError("Unexpected error"),
        ):
            result = await sentinel._reset_environment()
            assert result is False

    @pytest.mark.asyncio
    async def test_reset_logs_actions(self, mock_settings: None) -> None:
        """Test that _reset_environment logs all actions for audit trail."""
        sentinel = SentinelOrchestrator()

        with (
            patch.object(
                sentinel,
                "_run_command",
                return_value=type(
                    "ShellResult",
                    (),
                    {"success": True, "returncode": 0, "stderr": ""},
                )(),
            ),
            patch("orchestration_queue.orchestrator_sentinel.logger") as mock_logger,
        ):
            await sentinel._reset_environment()

            # Verify logging calls were made
            log_calls = [str(call) for call in mock_logger.info.call_args_list]
            assert any("Resetting environment" in str(call) for call in log_calls)
            assert any("Environment reset complete" in str(call) for call in log_calls)

    @pytest.mark.asyncio
    async def test_reset_logs_warning_on_failure(self, mock_settings: None) -> None:
        """Test that _reset_environment logs warning when stop command fails."""
        sentinel = SentinelOrchestrator()

        with (
            patch.object(
                sentinel,
                "_run_command",
                return_value=type(
                    "ShellResult",
                    (),
                    {"success": False, "returncode": 1, "stderr": "Container not found"},
                )(),
            ),
            patch("orchestration_queue.orchestrator_sentinel.logger") as mock_logger,
        ):
            await sentinel._reset_environment()

            # Verify warning was logged
            warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
            assert any("stop command failed" in str(call) for call in warning_calls)


class TestResetEnvironmentIntegration:
    """Tests for _reset_environment integration with task execution."""

    @pytest.fixture
    def mock_settings(self) -> None:
        """Mock settings to avoid config validation errors."""
        with patch("orchestration_queue.orchestrator_sentinel.settings") as mock_settings:
            mock_settings.github_token = "FAKE-GITHUB-TOKEN-FOR-TESTING-00000000"
            mock_settings.github_org = "test-org"
            mock_settings.github_repo = "test-repo"
            mock_settings.sentinel_bot_login = "test-bot"
            mock_settings.poll_interval = 60.0
            mock_settings.heartbeat_interval = 300.0
            mock_settings.subprocess_timeout = 5700.0
            mock_settings.shell_bridge_path = "./scripts/devcontainer-opencode.sh"
            mock_settings.log_level = "INFO"
            mock_settings.backoff_base_seconds = 5.0
            mock_settings.backoff_max_seconds = 300.0
            yield mock_settings

    @pytest.mark.asyncio
    async def test_reset_called_after_task_success(self, mock_settings: None) -> None:
        """Test that _reset_environment is called after successful task execution."""
        from unittest.mock import AsyncMock

        from orchestration_queue.models.work_item import TaskType, WorkItem, WorkItemStatus

        sentinel = SentinelOrchestrator()

        # Create a mock task with all required fields
        task = WorkItem(
            id=123,
            title="Test Task",
            body="Test body",
            task_type=TaskType.IMPLEMENT,
            status=WorkItemStatus.QUEUED,
            repository="test-org/test-repo",
            author="test-author",
        )

        # Create mock queue
        mock_queue = AsyncMock()
        mock_queue.post_heartbeat = AsyncMock()
        mock_queue.update_status = AsyncMock()

        with (
            patch.object(sentinel, "_get_queue", return_value=mock_queue),
            patch.object(sentinel, "_run_shell_bridge") as mock_run_bridge,
            patch.object(sentinel, "_reset_environment") as mock_reset,
        ):
            mock_run_bridge.return_value = type(
                "ShellResult",
                (),
                {"success": True, "returncode": 0, "stderr": ""},
            )()

            await sentinel._execute_task(task)

            # Verify reset was called in finally block
            mock_reset.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_called_after_task_failure(self, mock_settings: None) -> None:
        """Test that _reset_environment is called even when task execution fails."""
        from unittest.mock import AsyncMock

        from orchestration_queue.models.work_item import TaskType, WorkItem, WorkItemStatus

        sentinel = SentinelOrchestrator()

        task = WorkItem(
            id=456,
            title="Failing Task",
            body="Test body",
            task_type=TaskType.BUGFIX,
            status=WorkItemStatus.QUEUED,
            repository="test-org/test-repo",
            author="test-author",
        )

        # Create mock queue
        mock_queue = AsyncMock()
        mock_queue.post_heartbeat = AsyncMock()
        mock_queue.update_status = AsyncMock()

        with (
            patch.object(sentinel, "_get_queue", return_value=mock_queue),
            patch.object(sentinel, "_run_shell_bridge") as mock_run_bridge,
            patch.object(sentinel, "_reset_environment") as mock_reset,
        ):
            # Simulate failure
            mock_run_bridge.return_value = type(
                "ShellResult",
                (),
                {"success": False, "returncode": 1, "stderr": "Task failed"},
            )()

            await sentinel._execute_task(task)

            # Verify reset was still called in finally block
            mock_reset.assert_called_once()


class TestShellResult:
    """Tests for the ShellResult class."""

    def test_success_property_true_for_zero_returncode(self) -> None:
        """Test that success is True when returncode is 0."""
        from orchestration_queue.orchestrator_sentinel import ShellResult

        result = ShellResult(returncode=0, stdout="output", stderr="")
        assert result.success is True

    def test_success_property_false_for_nonzero_returncode(self) -> None:
        """Test that success is False when returncode is non-zero."""
        from orchestration_queue.orchestrator_sentinel import ShellResult

        result = ShellResult(returncode=1, stdout="", stderr="error")
        assert result.success is False

    def test_attributes_stored_correctly(self) -> None:
        """Test that all attributes are stored correctly."""
        from orchestration_queue.orchestrator_sentinel import ShellResult

        result = ShellResult(returncode=42, stdout="stdout text", stderr="stderr text")
        assert result.returncode == 42
        assert result.stdout == "stdout text"
        assert result.stderr == "stderr text"


class TestValidateConfig:
    """Tests for SentinelOrchestrator._validate_config method."""

    def test_init_raises_on_missing_token(self) -> None:
        """Test that initialization fails when GITHUB_TOKEN is missing."""
        with patch("orchestration_queue.orchestrator_sentinel.settings") as mock_settings:
            mock_settings.github_token = ""
            mock_settings.github_org = "test-org"
            mock_settings.github_repo = "test-repo"
            mock_settings.sentinel_bot_login = "test-bot"

            with pytest.raises(RuntimeError, match="Missing required configuration.*github_token"):
                SentinelOrchestrator()

    def test_init_raises_on_missing_org(self) -> None:
        """Test that initialization fails when GITHUB_ORG is missing."""
        with patch("orchestration_queue.orchestrator_sentinel.settings") as mock_settings:
            mock_settings.github_token = "FAKE-TOKEN-FOR-TESTING-00000000"
            mock_settings.github_org = ""
            mock_settings.github_repo = "test-repo"
            mock_settings.sentinel_bot_login = "test-bot"

            with pytest.raises(RuntimeError, match="Missing required configuration.*github_org"):
                SentinelOrchestrator()

    def test_init_raises_on_missing_repo(self) -> None:
        """Test that initialization fails when GITHUB_REPO is missing."""
        with patch("orchestration_queue.orchestrator_sentinel.settings") as mock_settings:
            mock_settings.github_token = "FAKE-TOKEN-FOR-TESTING-00000000"
            mock_settings.github_org = "test-org"
            mock_settings.github_repo = ""
            mock_settings.sentinel_bot_login = "test-bot"

            with pytest.raises(RuntimeError, match="Missing required configuration.*github_repo"):
                SentinelOrchestrator()

    def test_init_warns_on_missing_bot_login(self) -> None:
        """Test that initialization warns when SENTINEL_BOT_LOGIN is missing."""
        with (
            patch("orchestration_queue.orchestrator_sentinel.settings") as mock_settings,
            patch("orchestration_queue.orchestrator_sentinel.logger") as mock_logger,
        ):
            mock_settings.github_token = "FAKE-TOKEN-FOR-TESTING-00000000"
            mock_settings.github_org = "test-org"
            mock_settings.github_repo = "test-repo"
            mock_settings.sentinel_bot_login = ""

            SentinelOrchestrator()

            # Verify warning was logged
            mock_logger.warning.assert_called_once()
            assert "SENTINEL_BOT_LOGIN" in str(mock_logger.warning.call_args)

    def test_init_succeeds_with_all_config(self) -> None:
        """Test that initialization succeeds with all required config."""
        with patch("orchestration_queue.orchestrator_sentinel.settings") as mock_settings:
            mock_settings.github_token = "FAKE-TOKEN-FOR-TESTING-00000000"
            mock_settings.github_org = "test-org"
            mock_settings.github_repo = "test-repo"
            mock_settings.sentinel_bot_login = "test-bot"

            sentinel = SentinelOrchestrator()
            assert sentinel._running is False
            assert sentinel._queue is None


class TestGetQueue:
    """Tests for SentinelOrchestrator._get_queue method."""

    @pytest.fixture
    def mock_settings(self) -> None:
        """Mock settings to avoid config validation errors."""
        with patch("orchestration_queue.orchestrator_sentinel.settings") as mock_settings:
            mock_settings.github_token = "FAKE-TOKEN-FOR-TESTING-00000000"
            mock_settings.github_org = "test-org"
            mock_settings.github_repo = "test-repo"
            mock_settings.sentinel_bot_login = "test-bot"
            mock_settings.poll_interval = 60.0
            mock_settings.heartbeat_interval = 300.0
            mock_settings.subprocess_timeout = 5700.0
            mock_settings.shell_bridge_path = "./scripts/devcontainer-opencode.sh"
            mock_settings.log_level = "INFO"
            mock_settings.backoff_base_seconds = 5.0
            mock_settings.backoff_max_seconds = 300.0
            yield mock_settings

    @pytest.mark.asyncio
    async def test_get_queue_creates_queue_lazily(self, mock_settings: None) -> None:
        """Test that _get_queue creates a GitHubQueue on first call."""
        sentinel = SentinelOrchestrator()
        assert sentinel._queue is None

        queue = await sentinel._get_queue()

        assert queue is not None
        assert sentinel._queue is queue

    @pytest.mark.asyncio
    async def test_get_queue_returns_same_instance(self, mock_settings: None) -> None:
        """Test that _get_queue returns the same instance on subsequent calls."""
        sentinel = SentinelOrchestrator()

        queue1 = await sentinel._get_queue()
        queue2 = await sentinel._get_queue()

        assert queue1 is queue2


class TestRunCommand:
    """Tests for SentinelOrchestrator._run_command method (Story 2 & 6)."""

    @pytest.fixture
    def mock_settings(self) -> None:
        """Mock settings to avoid config validation errors."""
        with patch("orchestration_queue.orchestrator_sentinel.settings") as mock_settings:
            mock_settings.github_token = "FAKE-TOKEN-FOR-TESTING-00000000"
            mock_settings.github_org = "test-org"
            mock_settings.github_repo = "test-repo"
            mock_settings.sentinel_bot_login = "test-bot"
            mock_settings.poll_interval = 60.0
            mock_settings.heartbeat_interval = 300.0
            mock_settings.subprocess_timeout = 5700.0
            mock_settings.shell_bridge_path = "./scripts/devcontainer-opencode.sh"
            mock_settings.log_level = "INFO"
            mock_settings.backoff_base_seconds = 5.0
            mock_settings.backoff_max_seconds = 300.0
            yield mock_settings

    @pytest.mark.asyncio
    async def test_run_command_success(self, mock_settings: None) -> None:
        """Test _run_command with successful command execution."""
        sentinel = SentinelOrchestrator()

        # Create mock process with proper attributes
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"stdout output", b""))
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        with (
            patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_process)),
            patch("asyncio.wait_for", AsyncMock(return_value=(b"stdout output", b""))),
        ):
            result = await sentinel._run_command(["echo", "test"])

            assert result.success is True
            assert result.returncode == 0
            assert result.stdout == "stdout output"
            assert result.stderr == ""

    @pytest.mark.asyncio
    async def test_run_command_failure_nonzero_exit(self, mock_settings: None) -> None:
        """Test _run_command with non-zero exit code."""
        sentinel = SentinelOrchestrator()

        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(return_value=(b"", b"error message"))
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        with (
            patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_process)),
            patch("asyncio.wait_for", AsyncMock(return_value=(b"", b"error message"))),
        ):
            result = await sentinel._run_command(["false"])

            assert result.success is False
            assert result.returncode == 1
            assert result.stderr == "error message"

    @pytest.mark.asyncio
    async def test_run_command_with_input_text(self, mock_settings: None) -> None:
        """Test _run_command with stdin input."""
        sentinel = SentinelOrchestrator()

        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(return_value=(b"processed", b""))
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        with (
            patch(
                "asyncio.create_subprocess_exec", AsyncMock(return_value=mock_process)
            ) as mock_create,
            patch("asyncio.wait_for", AsyncMock(return_value=(b"processed", b""))) as mock_wait,
        ):
            result = await sentinel._run_command(["cat"], input_text="test input")

            # Verify create_subprocess_exec was called with stdin=PIPE
            assert mock_create.call_args[1]["stdin"] is not None
            # Verify wait_for was called with communicate coroutine
            assert mock_wait.called
            assert result.success is True

    @pytest.mark.asyncio
    async def test_run_command_timeout_kills_process(self, mock_settings: None) -> None:
        """Test that _run_command kills process on timeout (Story 6)."""
        sentinel = SentinelOrchestrator()

        mock_process = MagicMock()
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()

        with (
            patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_process)),
            patch("asyncio.wait_for", side_effect=TimeoutError),
        ):
            result = await sentinel._run_command(["sleep", "1000"])

            # The outer exception handler catches TimeoutError and returns error result
            assert result.success is False
            assert result.returncode == 1
            # Verify process was killed
            mock_process.kill.assert_called_once()
            mock_process.wait.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_command_timeout_value_is_95_minutes(self, mock_settings: None) -> None:
        """Test that timeout value matches 95 minutes (5700 seconds)."""
        # Verify the settings value
        with patch("orchestration_queue.orchestrator_sentinel.settings") as mock_settings:
            mock_settings.github_token = "FAKE-TOKEN-FOR-TESTING-00000000"
            mock_settings.github_org = "test-org"
            mock_settings.github_repo = "test-repo"
            mock_settings.sentinel_bot_login = "test-bot"
            mock_settings.subprocess_timeout = 5700.0  # 95 minutes = 95 * 60 = 5700

            sentinel = SentinelOrchestrator()
            mock_process = MagicMock()
            mock_process.returncode = 0
            mock_process.kill = MagicMock()
            mock_process.wait = AsyncMock()

            with (
                patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_process)),
                patch("asyncio.wait_for", AsyncMock(return_value=(b"", b""))) as mock_wait_for,
            ):
                await sentinel._run_command(["test"])

                # Verify timeout was passed correctly
                call_kwargs = mock_wait_for.call_args[1]
                assert call_kwargs["timeout"] == 5700.0

    @pytest.mark.asyncio
    async def test_run_command_exception_returns_error_result(self, mock_settings: None) -> None:
        """Test that _run_command returns error ShellResult on exception."""
        sentinel = SentinelOrchestrator()

        with patch("asyncio.create_subprocess_exec", side_effect=OSError("Command not found")):
            result = await sentinel._run_command(["nonexistent"])

            assert result.success is False
            assert result.returncode == 1
            assert result.stdout == ""
            assert "Command not found" in result.stderr


class TestRunShellBridge:
    """Tests for SentinelOrchestrator._run_shell_bridge method (Story 2)."""

    @pytest.fixture
    def mock_settings(self) -> None:
        """Mock settings to avoid config validation errors."""
        with patch("orchestration_queue.orchestrator_sentinel.settings") as mock_settings:
            mock_settings.github_token = "FAKE-TOKEN-FOR-TESTING-00000000"
            mock_settings.github_org = "test-org"
            mock_settings.github_repo = "test-repo"
            mock_settings.sentinel_bot_login = "test-bot"
            mock_settings.poll_interval = 60.0
            mock_settings.heartbeat_interval = 300.0
            mock_settings.subprocess_timeout = 5700.0
            mock_settings.shell_bridge_path = "./scripts/devcontainer-opencode.sh"
            mock_settings.log_level = "INFO"
            mock_settings.backoff_base_seconds = 5.0
            mock_settings.backoff_max_seconds = 300.0
            yield mock_settings

    @pytest.mark.asyncio
    async def test_shell_bridge_up_start_prompt_sequence(self, mock_settings: None) -> None:
        """Test shell bridge executes up, start, prompt in sequence."""
        from orchestration_queue.models.work_item import TaskType, WorkItem, WorkItemStatus

        sentinel = SentinelOrchestrator()

        task = WorkItem(
            id=123,
            title="Test Task",
            body="Test body",
            task_type=TaskType.IMPLEMENT,
            status=WorkItemStatus.QUEUED,
            repository="test-org/test-repo",
            author="test-author",
        )

        # Track call sequence
        call_sequence: list[str] = []

        async def mock_run_command(args: list[str], input_text: str | None = None) -> object:
            call_sequence.append(args[1])  # up, start, or prompt
            return type("ShellResult", (), {"success": True, "returncode": 0, "stderr": ""})()

        with patch.object(sentinel, "_run_command", side_effect=mock_run_command):
            result = await sentinel._run_shell_bridge(task)

            assert result.success is True
            assert call_sequence == ["up", "start", "prompt"]

    @pytest.mark.asyncio
    async def test_shell_bridge_fails_on_up(self, mock_settings: None) -> None:
        """Test shell bridge returns failure when 'up' command fails."""
        from orchestration_queue.models.work_item import TaskType, WorkItem, WorkItemStatus

        sentinel = SentinelOrchestrator()

        task = WorkItem(
            id=123,
            title="Test Task",
            body="Test body",
            task_type=TaskType.IMPLEMENT,
            status=WorkItemStatus.QUEUED,
            repository="test-org/test-repo",
            author="test-author",
        )

        async def mock_run_command(args: list[str], input_text: str | None = None) -> object:
            if args[1] == "up":
                return type(
                    "ShellResult", (), {"success": False, "returncode": 1, "stderr": "up failed"}
                )()
            return type("ShellResult", (), {"success": True, "returncode": 0, "stderr": ""})()

        with patch.object(sentinel, "_run_command", side_effect=mock_run_command) as mock_run:
            result = await sentinel._run_shell_bridge(task)

            assert result.success is False
            assert result.returncode == 1
            # Should only call 'up', not 'start' or 'prompt'
            assert mock_run.call_count == 1

    @pytest.mark.asyncio
    async def test_shell_bridge_fails_on_start(self, mock_settings: None) -> None:
        """Test shell bridge returns failure when 'start' command fails."""
        from orchestration_queue.models.work_item import TaskType, WorkItem, WorkItemStatus

        sentinel = SentinelOrchestrator()

        task = WorkItem(
            id=123,
            title="Test Task",
            body="Test body",
            task_type=TaskType.IMPLEMENT,
            status=WorkItemStatus.QUEUED,
            repository="test-org/test-repo",
            author="test-author",
        )

        async def mock_run_command(args: list[str], input_text: str | None = None) -> object:
            if args[1] == "start":
                return type(
                    "ShellResult", (), {"success": False, "returncode": 2, "stderr": "start failed"}
                )()
            return type("ShellResult", (), {"success": True, "returncode": 0, "stderr": ""})()

        with patch.object(sentinel, "_run_command", side_effect=mock_run_command) as mock_run:
            result = await sentinel._run_shell_bridge(task)

            assert result.success is False
            assert result.returncode == 2
            # Should call 'up' and 'start', but not 'prompt'
            assert mock_run.call_count == 2


class TestBuildInstruction:
    """Tests for SentinelOrchestrator._build_instruction method."""

    @pytest.fixture
    def mock_settings(self) -> None:
        """Mock settings to avoid config validation errors."""
        with patch("orchestration_queue.orchestrator_sentinel.settings") as mock_settings:
            mock_settings.github_token = "FAKE-TOKEN-FOR-TESTING-00000000"
            mock_settings.github_org = "test-org"
            mock_settings.github_repo = "test-repo"
            mock_settings.sentinel_bot_login = "test-bot"
            mock_settings.poll_interval = 60.0
            mock_settings.heartbeat_interval = 300.0
            mock_settings.subprocess_timeout = 5700.0
            mock_settings.shell_bridge_path = "./scripts/devcontainer-opencode.sh"
            mock_settings.log_level = "INFO"
            mock_settings.backoff_base_seconds = 5.0
            mock_settings.backoff_max_seconds = 300.0
            yield mock_settings

    def test_build_instruction_plan_task(self, mock_settings: None) -> None:
        """Test instruction building for PLAN task type."""
        from orchestration_queue.models.work_item import TaskType, WorkItem, WorkItemStatus

        sentinel = SentinelOrchestrator()

        task = WorkItem(
            id=42,
            title="Create new feature",
            body="Implement user authentication",
            task_type=TaskType.PLAN,
            status=WorkItemStatus.QUEUED,
            repository="test-org/test-repo",
            author="test-author",
        )

        instruction = sentinel._build_instruction(task)

        assert "Create an application plan" in instruction
        assert "#42" in instruction
        assert "Create new feature" in instruction
        assert "Implement user authentication" in instruction

    def test_build_instruction_bugfix_task(self, mock_settings: None) -> None:
        """Test instruction building for BUGFIX task type."""
        from orchestration_queue.models.work_item import TaskType, WorkItem, WorkItemStatus

        sentinel = SentinelOrchestrator()

        task = WorkItem(
            id=99,
            title="Fix login crash",
            body="App crashes on login",
            task_type=TaskType.BUGFIX,
            status=WorkItemStatus.QUEUED,
            repository="test-org/test-repo",
            author="test-author",
        )

        instruction = sentinel._build_instruction(task)

        assert "Analyze and fix" in instruction
        assert "#99" in instruction
        assert "Fix login crash" in instruction
        assert "App crashes on login" in instruction

    def test_build_instruction_implement_task(self, mock_settings: None) -> None:
        """Test instruction building for IMPLEMENT task type."""
        from orchestration_queue.models.work_item import TaskType, WorkItem, WorkItemStatus

        sentinel = SentinelOrchestrator()

        task = WorkItem(
            id=101,
            title="Add API endpoint",
            body="Create REST API for users",
            task_type=TaskType.IMPLEMENT,
            status=WorkItemStatus.QUEUED,
            repository="test-org/test-repo",
            author="test-author",
        )

        instruction = sentinel._build_instruction(task)

        assert "Implement the following task" in instruction
        assert "#101" in instruction
        assert "Add API endpoint" in instruction
        assert "Create REST API for users" in instruction

    def test_build_instruction_with_no_body(self, mock_settings: None) -> None:
        """Test instruction building when body is None."""
        from orchestration_queue.models.work_item import TaskType, WorkItem, WorkItemStatus

        sentinel = SentinelOrchestrator()

        task = WorkItem(
            id=1,
            title="Empty task",
            body=None,
            task_type=TaskType.IMPLEMENT,
            status=WorkItemStatus.QUEUED,
            repository="test-org/test-repo",
            author="test-author",
        )

        instruction = sentinel._build_instruction(task)

        assert "No description provided" in instruction


class TestHeartbeatLoop:
    """Tests for SentinelOrchestrator._heartbeat_loop method (Story 3)."""

    @pytest.fixture
    def mock_settings(self) -> None:
        """Mock settings to avoid config validation errors."""
        with patch("orchestration_queue.orchestrator_sentinel.settings") as mock_settings:
            mock_settings.github_token = "FAKE-TOKEN-FOR-TESTING-00000000"
            mock_settings.github_org = "test-org"
            mock_settings.github_repo = "test-repo"
            mock_settings.sentinel_bot_login = "test-bot"
            mock_settings.poll_interval = 60.0
            mock_settings.heartbeat_interval = 300.0
            mock_settings.subprocess_timeout = 5700.0
            mock_settings.shell_bridge_path = "./scripts/devcontainer-opencode.sh"
            mock_settings.log_level = "INFO"
            mock_settings.backoff_base_seconds = 5.0
            mock_settings.backoff_max_seconds = 300.0
            yield mock_settings

    @pytest.mark.asyncio
    async def test_heartbeat_posts_at_interval(self, mock_settings: None) -> None:
        """Test that heartbeat posts comments at the configured interval."""
        from datetime import UTC, datetime

        sentinel = SentinelOrchestrator()

        mock_queue = AsyncMock()
        mock_queue.post_heartbeat = AsyncMock()

        sleep_count = 0

        async def mock_sleep(interval: float) -> None:
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 3:
                raise asyncio.CancelledError()

        with (
            patch.object(sentinel, "_get_queue", return_value=mock_queue),
            patch("asyncio.sleep", side_effect=mock_sleep),
            contextlib.suppress(asyncio.CancelledError),
        ):
            await sentinel._heartbeat_loop(42, datetime.now(UTC))

        # Verify heartbeat was posted on each sleep cycle
        assert mock_queue.post_heartbeat.call_count >= 2

    @pytest.mark.asyncio
    async def test_heartbeat_continues_on_failure(self, mock_settings: None) -> None:
        """Test that heartbeat loop continues even when posting fails."""
        from datetime import UTC, datetime

        sentinel = SentinelOrchestrator()

        mock_queue = AsyncMock()
        # First call fails, second succeeds
        mock_queue.post_heartbeat = AsyncMock(
            side_effect=[
                Exception("Network error"),
                None,
                asyncio.CancelledError(),
            ]
        )

        sleep_count = 0

        async def mock_sleep(interval: float) -> None:
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 3:
                raise asyncio.CancelledError()

        with (
            patch.object(sentinel, "_get_queue", return_value=mock_queue),
            patch("asyncio.sleep", side_effect=mock_sleep),
            contextlib.suppress(asyncio.CancelledError),
        ):
            await sentinel._heartbeat_loop(42, datetime.now(UTC))

        # Should have attempted multiple posts despite failure
        assert mock_queue.post_heartbeat.call_count >= 2

    @pytest.mark.asyncio
    async def test_heartbeat_cancellation(self, mock_settings: None) -> None:
        """Test that heartbeat loop can be cancelled."""
        from datetime import UTC, datetime

        sentinel = SentinelOrchestrator()

        mock_queue = AsyncMock()
        mock_queue.post_heartbeat = AsyncMock()

        async def mock_sleep(interval: float) -> None:
            raise asyncio.CancelledError()

        with (
            patch.object(sentinel, "_get_queue", return_value=mock_queue),
            patch("asyncio.sleep", side_effect=mock_sleep),
            pytest.raises(asyncio.CancelledError),
        ):
            await sentinel._heartbeat_loop(42, datetime.now(UTC))


class TestGracefulShutdown:
    """Tests for graceful shutdown handling (Story 4)."""

    @pytest.fixture
    def mock_settings(self) -> None:
        """Mock settings to avoid config validation errors."""
        with patch("orchestration_queue.orchestrator_sentinel.settings") as mock_settings:
            mock_settings.github_token = "FAKE-TOKEN-FOR-TESTING-00000000"
            mock_settings.github_org = "test-org"
            mock_settings.github_repo = "test-repo"
            mock_settings.sentinel_bot_login = "test-bot"
            mock_settings.poll_interval = 60.0
            mock_settings.heartbeat_interval = 300.0
            mock_settings.subprocess_timeout = 5700.0
            mock_settings.shell_bridge_path = "./scripts/devcontainer-opencode.sh"
            mock_settings.log_level = "INFO"
            mock_settings.backoff_base_seconds = 5.0
            mock_settings.backoff_max_seconds = 300.0
            yield mock_settings

    def test_handle_shutdown_signal_sets_event(self, mock_settings: None) -> None:
        """Test that _handle_shutdown_signal sets the shutdown event."""
        sentinel = SentinelOrchestrator()
        assert not sentinel._shutdown_event.is_set()

        sentinel._handle_shutdown_signal()

        assert sentinel._shutdown_event.is_set()

    @pytest.mark.asyncio
    async def test_run_polling_loop_exits_on_shutdown(self, mock_settings: None) -> None:
        """Test that _run_polling_loop exits when shutdown signal is received."""
        sentinel = SentinelOrchestrator()
        sentinel._running = True
        sentinel._shutdown_event.set()  # Set shutdown before loop starts

        poll_count = 0

        async def mock_poll() -> None:
            nonlocal poll_count
            poll_count += 1

        with patch.object(sentinel, "_poll_and_process", side_effect=mock_poll):
            await sentinel._run_polling_loop()

        # Should not have polled because shutdown was already set
        assert poll_count == 0

    @pytest.mark.asyncio
    async def test_cleanup_closes_queue(self, mock_settings: None) -> None:
        """Test that _cleanup closes the queue if it exists."""
        sentinel = SentinelOrchestrator()

        mock_queue = AsyncMock()
        sentinel._queue = mock_queue
        sentinel._running = True

        await sentinel._cleanup()

        mock_queue.close.assert_called_once()
        assert sentinel._running is False

    @pytest.mark.asyncio
    async def test_cleanup_handles_no_queue(self, mock_settings: None) -> None:
        """Test that _cleanup handles case where queue is None."""
        sentinel = SentinelOrchestrator()
        sentinel._queue = None
        sentinel._running = True

        # Should not raise
        await sentinel._cleanup()

        assert sentinel._running is False

    @pytest.mark.asyncio
    async def test_start_registers_signal_handlers(self, mock_settings: None) -> None:
        """Test that start() registers SIGTERM and SIGINT handlers."""
        import signal

        sentinel = SentinelOrchestrator()

        mock_loop = MagicMock()
        mock_loop.add_signal_handler = MagicMock()

        registered_handlers: list[int] = []

        def track_handler(sig: int, handler: object) -> None:
            registered_handlers.append(sig)

        mock_loop.add_signal_handler.side_effect = track_handler

        async def mock_polling_loop() -> None:
            sentinel._shutdown_event.set()

        async def mock_cleanup() -> None:
            pass

        with (
            patch("asyncio.get_event_loop", return_value=mock_loop),
            patch.object(sentinel, "_run_polling_loop", side_effect=mock_polling_loop),
            patch.object(sentinel, "_cleanup", side_effect=mock_cleanup),
        ):
            await sentinel.start()

        # Verify both signals were registered
        assert signal.SIGTERM in registered_handlers
        assert signal.SIGINT in registered_handlers


class TestFormatDuration:
    """Tests for SentinelOrchestrator._format_duration method."""

    @pytest.fixture
    def mock_settings(self) -> None:
        """Mock settings to avoid config validation errors."""
        with patch("orchestration_queue.orchestrator_sentinel.settings") as mock_settings:
            mock_settings.github_token = "FAKE-TOKEN-FOR-TESTING-00000000"
            mock_settings.github_org = "test-org"
            mock_settings.github_repo = "test-repo"
            mock_settings.sentinel_bot_login = "test-bot"
            mock_settings.poll_interval = 60.0
            mock_settings.heartbeat_interval = 300.0
            mock_settings.subprocess_timeout = 5700.0
            mock_settings.shell_bridge_path = "./scripts/devcontainer-opencode.sh"
            mock_settings.log_level = "INFO"
            mock_settings.backoff_base_seconds = 5.0
            mock_settings.backoff_max_seconds = 300.0
            yield mock_settings

    def test_format_duration_seconds_only(self, mock_settings: None) -> None:
        """Test formatting duration less than a minute."""
        from datetime import UTC, datetime, timedelta

        sentinel = SentinelOrchestrator()

        # Use a fixed "now" and calculate start_time 30 seconds ago
        now = datetime.now(UTC)
        start_time = now - timedelta(seconds=30)

        with patch("orchestration_queue.orchestrator_sentinel.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.side_effect = lambda *args, **kwargs: datetime(
                *args, **kwargs
            )  # Pass through constructor

            result = sentinel._format_duration(start_time)

            assert "s" in result
            assert "m" not in result

    def test_format_duration_minutes_and_seconds(self, mock_settings: None) -> None:
        """Test formatting duration with minutes."""
        from datetime import UTC, datetime, timedelta

        sentinel = SentinelOrchestrator()

        now = datetime.now(UTC)
        start_time = now - timedelta(minutes=5, seconds=30)

        result = sentinel._format_duration(start_time)

        assert "m" in result
        assert "s" in result

    def test_format_duration_hours_and_minutes(self, mock_settings: None) -> None:
        """Test formatting duration with hours."""
        from datetime import UTC, datetime, timedelta

        sentinel = SentinelOrchestrator()

        now = datetime.now(UTC)
        start_time = now - timedelta(hours=2, minutes=30)

        result = sentinel._format_duration(start_time)

        assert "h" in result
        assert "m" in result


class TestExecuteTask:
    """Tests for task execution flow."""

    @pytest.fixture
    def mock_settings(self) -> None:
        """Mock settings to avoid config validation errors."""
        with patch("orchestration_queue.orchestrator_sentinel.settings") as mock_settings:
            mock_settings.github_token = "FAKE-TOKEN-FOR-TESTING-00000000"
            mock_settings.github_org = "test-org"
            mock_settings.github_repo = "test-repo"
            mock_settings.sentinel_bot_login = "test-bot"
            mock_settings.poll_interval = 60.0
            mock_settings.heartbeat_interval = 300.0
            mock_settings.subprocess_timeout = 5700.0
            mock_settings.shell_bridge_path = "./scripts/devcontainer-opencode.sh"
            mock_settings.log_level = "INFO"
            mock_settings.backoff_base_seconds = 5.0
            mock_settings.backoff_max_seconds = 300.0
            yield mock_settings

    @pytest.mark.asyncio
    async def test_execute_task_handles_infra_failure(self, mock_settings: None) -> None:
        """Test that _execute_task handles exceptions as INFRA_FAILURE."""
        from orchestration_queue.models.work_item import TaskType, WorkItem, WorkItemStatus

        sentinel = SentinelOrchestrator()

        task = WorkItem(
            id=123,
            title="Test Task",
            body="Test body",
            task_type=TaskType.IMPLEMENT,
            status=WorkItemStatus.QUEUED,
            repository="test-org/test-repo",
            author="test-author",
        )

        mock_queue = AsyncMock()
        mock_queue.post_heartbeat = AsyncMock()
        mock_queue.update_status = AsyncMock()

        with (
            patch.object(sentinel, "_get_queue", return_value=mock_queue),
            patch.object(
                sentinel, "_run_shell_bridge", side_effect=RuntimeError("Infrastructure error")
            ),
            patch.object(sentinel, "_reset_environment"),
        ):
            await sentinel._execute_task(task)

            # Verify INFRA_FAILURE status was posted
            call_args = mock_queue.update_status.call_args
            assert call_args[0][1] == WorkItemStatus.INFRA_FAILURE
            assert "Infrastructure Error" in call_args[0][2]


class TestPollAndProcess:
    """Tests for _poll_and_process task claiming and execution flow."""

    @pytest.fixture
    def mock_settings(self) -> None:
        """Mock settings to avoid config validation errors."""
        with patch("orchestration_queue.orchestrator_sentinel.settings") as mock_settings:
            mock_settings.github_token = "FAKE-TOKEN-FOR-TESTING-00000000"
            mock_settings.github_org = "test-org"
            mock_settings.github_repo = "test-repo"
            mock_settings.sentinel_bot_login = "test-bot"
            mock_settings.poll_interval = 60.0
            mock_settings.heartbeat_interval = 300.0
            mock_settings.subprocess_timeout = 5700.0
            mock_settings.shell_bridge_path = "./scripts/devcontainer-opencode.sh"
            mock_settings.log_level = "INFO"
            mock_settings.backoff_base_seconds = 5.0
            mock_settings.backoff_max_seconds = 300.0
            yield mock_settings

    @pytest.mark.asyncio
    async def test_poll_finds_and_claims_task(self, mock_settings: None) -> None:
        """Test that _poll_and_process finds and claims a task."""
        from orchestration_queue.models.work_item import TaskType, WorkItem, WorkItemStatus

        sentinel = SentinelOrchestrator()

        task = WorkItem(
            id=42,
            title="Test Task",
            body="Test body",
            task_type=TaskType.IMPLEMENT,
            status=WorkItemStatus.QUEUED,
            repository="test-org/test-repo",
            author="test-author",
        )

        mock_queue = AsyncMock()
        mock_queue.fetch_queued_tasks = AsyncMock(return_value=[task])
        mock_queue.claim_task = AsyncMock(return_value=True)
        mock_queue.post_heartbeat = AsyncMock()
        mock_queue.update_status = AsyncMock()

        with (
            patch.object(sentinel, "_reset_environment"),
            patch.object(sentinel, "_get_queue", return_value=mock_queue),
            patch.object(sentinel, "_execute_task") as mock_execute,
        ):
            await sentinel._poll_and_process()

            # Verify task was claimed
            mock_queue.claim_task.assert_called_once_with(42, "test-bot")
            # Verify execute was called with the task
            mock_execute.assert_called_once_with(task)

    @pytest.mark.asyncio
    async def test_poll_claim_fails(self, mock_settings: None) -> None:
        """Test that _poll_and_process handles claim failure gracefully."""
        from orchestration_queue.models.work_item import TaskType, WorkItem, WorkItemStatus

        sentinel = SentinelOrchestrator()

        task = WorkItem(
            id=42,
            title="Test Task",
            body="Test body",
            task_type=TaskType.IMPLEMENT,
            status=WorkItemStatus.QUEUED,
            repository="test-org/test-repo",
            author="test-author",
        )

        mock_queue = AsyncMock()
        mock_queue.fetch_queued_tasks = AsyncMock(return_value=[task])
        mock_queue.claim_task = AsyncMock(return_value=False)  # Claim fails

        with (
            patch.object(sentinel, "_reset_environment"),
            patch.object(sentinel, "_get_queue", return_value=mock_queue),
            patch.object(sentinel, "_execute_task") as mock_execute,
        ):
            await sentinel._poll_and_process()

            # Verify execute was NOT called when claim fails
            mock_execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_poll_no_bot_login_configured(self) -> None:
        """Test that _poll_and_process warns when no bot login is configured."""
        from orchestration_queue.models.work_item import TaskType, WorkItem, WorkItemStatus

        with patch("orchestration_queue.orchestrator_sentinel.settings") as mock_settings:
            mock_settings.github_token = "FAKE-TOKEN-FOR-TESTING-00000000"
            mock_settings.github_org = "test-org"
            mock_settings.github_repo = "test-repo"
            mock_settings.sentinel_bot_login = ""  # Empty bot login
            mock_settings.poll_interval = 60.0
            mock_settings.heartbeat_interval = 300.0
            mock_settings.subprocess_timeout = 5700.0
            mock_settings.shell_bridge_path = "./scripts/devcontainer-opencode.sh"
            mock_settings.log_level = "INFO"

            sentinel = SentinelOrchestrator()

            task = WorkItem(
                id=42,
                title="Test Task",
                body="Test body",
                task_type=TaskType.IMPLEMENT,
                status=WorkItemStatus.QUEUED,
                repository="test-org/test-repo",
                author="test-author",
            )

            mock_queue = AsyncMock()
            mock_queue.fetch_queued_tasks = AsyncMock(return_value=[task])

            with (
                patch.object(sentinel, "_reset_environment"),
                patch.object(sentinel, "_get_queue", return_value=mock_queue),
                patch.object(sentinel, "_execute_task") as mock_execute,
                patch("orchestration_queue.orchestrator_sentinel.logger") as mock_logger,
            ):
                await sentinel._poll_and_process()

                # Verify warning was logged
                warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
                assert any("SENTINEL_BOT_LOGIN" in str(call) for call in warning_calls)
                # Verify execute was NOT called
                mock_execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_poll_logs_found_tasks(self, mock_settings: None) -> None:
        """Test that _poll_and_process logs when tasks are found."""
        from orchestration_queue.models.work_item import TaskType, WorkItem, WorkItemStatus

        sentinel = SentinelOrchestrator()

        task = WorkItem(
            id=42,
            title="Test Task",
            body="Test body",
            task_type=TaskType.IMPLEMENT,
            status=WorkItemStatus.QUEUED,
            repository="test-org/test-repo",
            author="test-author",
        )

        mock_queue = AsyncMock()
        mock_queue.fetch_queued_tasks = AsyncMock(return_value=[task])
        mock_queue.claim_task = AsyncMock(return_value=False)  # Claim fails so we don't execute

        with (
            patch.object(sentinel, "_reset_environment"),
            patch.object(sentinel, "_get_queue", return_value=mock_queue),
            patch("orchestration_queue.orchestrator_sentinel.logger") as mock_logger,
        ):
            await sentinel._poll_and_process()

            # Verify info log about found tasks
            info_calls = [str(call) for call in mock_logger.info.call_args_list]
            assert any("queued task" in str(call) for call in info_calls)
