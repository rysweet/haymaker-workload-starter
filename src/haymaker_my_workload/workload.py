"""MyWorkload - starter workload implementation.

This module demonstrates the full workload lifecycle by implementing all
required abstract methods from WorkloadBase. Customize this for your domain.

The five required methods:
    deploy()     - Start a new deployment
    get_status() - Return current state
    stop()       - Pause execution
    cleanup()    - Destroy all resources
    get_logs()   - Stream log output
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from agent_haymaker.workloads.base import (
    DeploymentNotFoundError,
    WorkloadBase,
)
from agent_haymaker.workloads.models import (
    CleanupReport,
    DeploymentConfig,
    DeploymentState,
    DeploymentStatus,
)

logger = logging.getLogger(__name__)

# Terminal states where no further lifecycle transitions are allowed
_TERMINAL_STATES = frozenset({DeploymentStatus.COMPLETED, DeploymentStatus.FAILED})
# States that can be stopped
_STOPPABLE_STATES = frozenset({DeploymentStatus.RUNNING, DeploymentStatus.PENDING})
# Max log lines per deployment to prevent unbounded memory growth
_MAX_LOG_LINES = 10_000


class MyWorkload(WorkloadBase):
    """Starter workload template.

    Rename this class and the ``name`` attribute to match your workload.
    Then implement the five required methods with your domain logic.

    Example registration in pyproject.toml:
        [project.entry-points."agent_haymaker.workloads"]
        my-workload = "haymaker_my_workload:MyWorkload"
    """

    # Unique workload name - used by CLI: haymaker deploy <name>
    name = "my-workload"

    def __init__(self, platform=None):
        super().__init__(platform=platform)
        # In-memory log buffer (replace with your logging backend).
        # Capped at _MAX_LOG_LINES per deployment to prevent unbounded growth.
        self._logs: dict[str, list[str]] = {}

    # =========================================================================
    # REQUIRED: Implement these five methods
    # =========================================================================

    async def deploy(self, config: DeploymentConfig) -> str:
        """Start a new deployment.

        This is called when a user runs:
            haymaker deploy my-workload --config item_count=50

        TODO: Replace with your deployment logic:
            1. Parse workload_config for your settings
            2. Provision resources (VMs, users, APIs, etc.)
            3. Start your workload's main loop
            4. Return a unique deployment_id
        """
        # Validate before deploying
        errors = await self.validate_config(config)
        if errors:
            raise ValueError(f"Invalid config: {'; '.join(errors)}")

        deployment_id = f"{self.name}-{uuid.uuid4().hex[:8]}"

        # Read workload-specific config with defaults
        item_count = config.workload_config.get("item_count", 10)
        interval = config.workload_config.get("interval_seconds", 60)
        mode = config.workload_config.get("mode", "normal")

        self.log(f"Deploying with item_count={item_count}, interval={interval}s, mode={mode}")

        # Initialize log buffer for this deployment
        self._logs[deployment_id] = []
        self._append_log(deployment_id, f"Deployment {deployment_id} starting")

        # Create and persist initial state
        state = DeploymentState(
            deployment_id=deployment_id,
            workload_name=self.name,
            status=DeploymentStatus.RUNNING,
            phase="initializing",
            started_at=datetime.now(tz=UTC),
            config=config.workload_config,
            metadata={"item_count": item_count, "items_processed": 0},
        )
        await self.save_state(state)

        self._append_log(deployment_id, "Initialization complete, workload running")

        # TODO: Start your background task here. For example:
        #   asyncio.create_task(self._run_loop(deployment_id, item_count, interval))

        # Update phase
        state.phase = "running"
        await self.save_state(state)

        return deployment_id

    async def get_status(self, deployment_id: str) -> DeploymentState:
        """Return current deployment state.

        Called by: haymaker status <deployment-id>

        TODO: If your workload has external state (cloud resources, APIs),
        you may want to refresh the state here before returning it.
        """
        state = await self.load_state(deployment_id)
        if state is None:
            raise DeploymentNotFoundError(f"Deployment {deployment_id} not found")
        return state

    async def stop(self, deployment_id: str) -> bool:
        """Pause a running deployment.

        Called by: haymaker stop <deployment-id>

        The deployment should be resumable via start(). If your workload
        cannot pause, you can stop background tasks and record progress
        so start() can pick up where it left off.

        TODO: Cancel background tasks, close connections, save checkpoint.
        """
        state = await self.get_status(deployment_id)
        if state.status == DeploymentStatus.STOPPED:
            return True
        if state.status not in _STOPPABLE_STATES:
            self.log(f"Cannot stop deployment in {state.status} state")
            return False

        self._append_log(deployment_id, "Stopping deployment")

        state.status = DeploymentStatus.STOPPED
        state.phase = "stopped"
        state.stopped_at = datetime.now(tz=UTC)
        await self.save_state(state)

        self._append_log(deployment_id, "Deployment stopped")
        return True

    async def cleanup(self, deployment_id: str) -> CleanupReport:
        """Remove all resources created by this deployment.

        Called by: haymaker cleanup <deployment-id>

        This is destructive - the deployment cannot resume after cleanup.

        TODO: Delete cloud resources, remove users, tear down infrastructure.
        Track what was deleted and any errors in the CleanupReport.
        """
        state = await self.get_status(deployment_id)
        self._append_log(deployment_id, "Starting cleanup")

        state.status = DeploymentStatus.CLEANING_UP
        state.phase = "cleanup"
        await self.save_state(state)

        deleted = 0
        errors: list[str] = []
        details: list[str] = []
        start_time = time.monotonic()

        # TODO: Delete your resources here. Example:
        # try:
        #     await self._delete_resources(deployment_id)
        #     deleted += 1
        #     details.append("Deleted resource group")
        # except Exception as e:
        #     errors.append(f"Failed to delete resource group: {e}")

        details.append(f"Cleaned up deployment {deployment_id}")
        deleted += 1

        # Clean up local state
        self._logs.pop(deployment_id, None)

        state.status = DeploymentStatus.COMPLETED
        state.phase = "cleaned_up"
        state.completed_at = datetime.now(tz=UTC)
        await self.save_state(state)

        elapsed = time.monotonic() - start_time
        return CleanupReport(
            deployment_id=deployment_id,
            resources_deleted=deleted,
            resources_failed=len(errors),
            details=details,
            errors=errors,
            duration_seconds=elapsed,
        )

    async def get_logs(
        self, deployment_id: str, follow: bool = False, lines: int = 100
    ) -> AsyncIterator[str]:
        """Stream logs for a deployment.

        Called by: haymaker logs <deployment-id> [--follow]

        TODO: Replace the in-memory log buffer with your logging backend
        (file, cloud logging, database, etc.).
        """
        await self.get_status(deployment_id)  # Raises if not found

        log_lines = self._logs.get(deployment_id, [])

        # Yield historical lines
        for line in log_lines[-lines:]:
            yield line

        # If following, poll for new lines until deployment reaches a terminal state
        if follow:
            seen = len(log_lines)
            while True:
                state = await self.load_state(deployment_id)
                if state is None or state.status in _TERMINAL_STATES:
                    # Yield any remaining lines before exiting
                    current = self._logs.get(deployment_id, [])
                    if len(current) > seen:
                        for line in current[seen:]:
                            yield line
                    break
                current = self._logs.get(deployment_id, [])
                if len(current) > seen:
                    for line in current[seen:]:
                        yield line
                    seen = len(current)
                await asyncio.sleep(1)

    # =========================================================================
    # OPTIONAL: Override these for enhanced functionality
    # =========================================================================

    async def start(self, deployment_id: str) -> bool:
        """Resume a stopped deployment.

        Called by: haymaker start <deployment-id>

        TODO: Reload checkpoint and restart background tasks.
        """
        state = await self.get_status(deployment_id)
        if state.status != DeploymentStatus.STOPPED:
            self.log(f"Cannot start deployment in {state.status} state")
            return False

        self._append_log(deployment_id, "Resuming deployment")

        state.status = DeploymentStatus.RUNNING
        state.phase = "running"
        state.stopped_at = None
        await self.save_state(state)

        self._append_log(deployment_id, "Deployment resumed")
        return True

    async def validate_config(self, config: DeploymentConfig) -> list[str]:
        """Validate config before deploy.

        Return a list of error messages. Empty list means valid.

        TODO: Add your validation rules here. Keep these in sync with
        the config_schema in workload.yaml.
        """
        errors = []
        wc = config.workload_config

        item_count = wc.get("item_count", 10)
        if isinstance(item_count, bool) or not isinstance(item_count, int) or item_count < 1:
            errors.append("item_count must be a positive integer")
        elif item_count > 1000:
            errors.append("item_count must be <= 1000")

        interval = wc.get("interval_seconds", 60)
        if isinstance(interval, bool) or not isinstance(interval, int) or interval < 10:
            errors.append("interval_seconds must be an integer >= 10")

        mode = wc.get("mode", "normal")
        if mode not in ("normal", "verbose", "dry-run"):
            errors.append(f"mode must be one of: normal, verbose, dry-run (got '{mode}')")

        return errors

    # =========================================================================
    # Private helpers
    # =========================================================================

    def _append_log(self, deployment_id: str, message: str) -> None:
        """Append a timestamped message to the deployment's log buffer."""
        ts = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {message}"
        buf = self._logs.setdefault(deployment_id, [])
        buf.append(line)
        if len(buf) > _MAX_LOG_LINES:
            del buf[: len(buf) - _MAX_LOG_LINES]
        self.log(message)
