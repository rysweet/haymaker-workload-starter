---
layout: default
title: "Tutorial: Build a Goal-Seeking Agent"
nav_order: 2
---

# Tutorial: Build a Goal-Seeking Agent
{: .no_toc }

Build a complete goal-seeking agent workload from scratch, with optional LLM enhancement for adaptive behavior. By the end, you will have a working agent that deploys, executes goals, and reports progress through the haymaker CLI.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## What you will build

A **data-collector** agent that:
- Defines a goal ("collect N data items")
- Executes in phases (initialize, collect, report)
- Tracks progress via status callbacks
- Optionally uses an LLM for adaptive error recovery
- Integrates with the haymaker CLI for lifecycle management

This follows the same pattern used by the [Azure Infrastructure Workload](https://github.com/rysweet/haymaker-azure-workloads) and the [M365 Knowledge Worker Workload](https://github.com/rysweet/haymaker-m365-workloads).

## Prerequisites

- Python 3.11+
- Git
- The [agent-haymaker](https://github.com/rysweet/agent-haymaker) platform installed

## Step 1: Clone and set up

Clone the starter template and install it:

```bash
git clone https://github.com/rysweet/haymaker-workload-starter my-data-collector
cd my-data-collector
pip install -e ".[dev]"
```

Verify the starter workload is registered:

```bash
haymaker workload list
```

You should see:

```
Installed workloads:
  - my-workload
```

Run the existing tests to confirm everything works:

```bash
pytest -q
```

{: .tip }
The starter template has 49 tests at 97% coverage. You will add to these as you build your agent.

## Step 2: Rename the workload

Replace the starter names with your own. Update these files:

**pyproject.toml** -- change the package name and entry point:

```toml
[project]
name = "haymaker-data-collector"

[project.entry-points."agent_haymaker.workloads"]
data-collector = "haymaker_data_collector:DataCollectorWorkload"

[tool.hatch.build.targets.wheel]
packages = ["src/haymaker_data_collector"]
```

**Rename the source directory and update the class name:**

```bash
mv src/haymaker_my_workload src/haymaker_data_collector

# Update class name and workload name in the existing workload.py
sed -i 's/class MyWorkload/class DataCollectorWorkload/' src/haymaker_data_collector/workload.py
sed -i 's/name = "my-workload"/name = "data-collector"/' src/haymaker_data_collector/workload.py
```

**src/haymaker_data_collector/\_\_init\_\_.py:**

```python
"""Data Collector Workload - goal-seeking agent for Agent Haymaker."""

from importlib.metadata import version

from .workload import DataCollectorWorkload

__version__ = version("haymaker-data-collector")

__all__ = ["DataCollectorWorkload"]
```

**workload.yaml:**

```yaml
name: data-collector
version: "0.1.0"
type: runtime
description: "A goal-seeking data collector agent for Agent Haymaker"

package:
  name: haymaker-data-collector
  entrypoint: haymaker_data_collector:DataCollectorWorkload

config_schema:
  goal:
    type: string
    default: "Collect 10 data items"
    description: "The goal for the agent to achieve"
  item_count:
    type: integer
    default: 10
    min: 1
    max: 1000
    description: "Number of items to collect"
  enable_llm:
    type: boolean
    default: false
    description: "Enable LLM for adaptive behavior"
```

Reinstall and verify:

```bash
pip install -e ".[dev]"
haymaker workload list
```

You should now see `data-collector` in the list.

## Step 3: Create the goal-seeking agent

This is the core of the pattern. Create `src/haymaker_data_collector/agent.py`:

```python
"""GoalSeekingAgent - executes goals in phases with status reporting."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class GoalSeekingAgent:
    """Agent that pursues a goal through phased execution.

    The agent lifecycle:
        1. Initialize - set up resources
        2. Execute - work toward the goal in a loop
        3. Report - summarize what was accomplished
        4. Cleanup - release resources

    Status changes are communicated via the on_status_change callback,
    which the workload uses to update DeploymentState.
    """

    def __init__(
        self,
        deployment_id: str,
        goal: str,
        item_count: int = 10,
        on_status_change: Callable[[str, str], None] | None = None,
    ) -> None:
        self.deployment_id = deployment_id
        self.goal = goal
        self.item_count = item_count
        self._on_status_change = on_status_change
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._logs: list[str] = []
        self._items_collected: list[dict[str, Any]] = []

    async def start(self) -> None:
        """Start the agent's execution loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the agent gracefully."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def cleanup(self) -> dict[str, Any]:
        """Release resources and return a summary."""
        await self.stop()
        self._log("Cleaning up resources")
        return {
            "items_collected": len(self._items_collected),
            "goal": self.goal,
            "goal_achieved": len(self._items_collected) >= self.item_count,
        }

    async def get_logs(self, lines: int = 100) -> AsyncIterator[str]:
        """Yield recent log lines."""
        for line in self._logs[-lines:]:
            yield line

    # -- Internal execution --

    async def _run(self) -> None:
        """Main execution loop: initialize -> collect -> report."""
        try:
            await self._phase_initialize()
            await self._phase_collect()
            await self._phase_report()
        except asyncio.CancelledError:
            self._log("Agent cancelled")
            raise
        except Exception as exc:
            self._log(f"Agent failed: {exc}")
            self._update_status("failed", "failed")

    async def _phase_initialize(self) -> None:
        """Phase 1: Set up for data collection."""
        self._update_status("initializing", "running")
        self._log(f"Goal: {self.goal}")
        self._log(f"Target: {self.item_count} items")
        await asyncio.sleep(0.1)  # Simulate setup work
        self._log("Initialization complete")

    async def _phase_collect(self) -> None:
        """Phase 2: Collect data items toward the goal."""
        self._update_status("collecting", "running")
        for i in range(self.item_count):
            if not self._running:
                self._log(f"Stopped at item {i}/{self.item_count}")
                return

            item = await self._collect_one_item(i)
            self._items_collected.append(item)
            self._log(f"Collected item {i + 1}/{self.item_count}: {item['id']}")

        self._log(f"Collection complete: {len(self._items_collected)} items")

    async def _phase_report(self) -> None:
        """Phase 3: Summarize results."""
        self._update_status("reporting", "running")
        achieved = len(self._items_collected) >= self.item_count
        self._log(f"Goal achieved: {achieved}")
        self._log(f"Items collected: {len(self._items_collected)}")
        self._update_status("completed", "completed")

    async def _collect_one_item(self, index: int) -> dict[str, Any]:
        """Collect a single data item.

        Override this method with your real collection logic:
        API calls, database queries, file processing, etc.
        """
        await asyncio.sleep(0.05)  # Simulate work
        return {
            "id": f"item-{index:04d}",
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "data": f"sample-data-{index}",
        }

    def _log(self, message: str) -> None:
        ts = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        self._logs.append(f"[{ts}] {message}")

    def _update_status(self, phase: str, status: str) -> None:
        if self._on_status_change:
            self._on_status_change(phase, status)
```

{: .note }
The `_collect_one_item` method is where you put your real logic. The rest is framework scaffolding.

## Step 4: Add LLM enhancement (optional)

Create `src/haymaker_data_collector/llm_agent.py` to add adaptive behavior:

```python
"""LLMGoalSeekingAgent - agent with LLM-powered adaptive behavior."""

from __future__ import annotations

from typing import Any

from .agent import GoalSeekingAgent


class LLMGoalSeekingAgent(GoalSeekingAgent):
    """Extends GoalSeekingAgent with LLM capabilities.

    When an LLM client is available, the agent can:
    - Recover from collection errors intelligently
    - Evaluate whether the goal has been truly achieved
    - Generate adaptive collection strategies
    """

    def __init__(self, llm_client=None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._llm_client = llm_client

    async def _collect_one_item(self, index: int) -> dict[str, Any]:
        """Collect with LLM-powered error recovery."""
        try:
            return await super()._collect_one_item(index)
        except Exception as exc:
            recovery = await self._handle_error(str(exc), index)
            if recovery:
                self._log(f"LLM suggested recovery: {recovery}")
                return recovery
            raise

    async def _phase_report(self) -> None:
        """Use LLM to evaluate goal achievement."""
        if self._llm_client:
            evaluation = await self._evaluate_goal()
            self._log(f"LLM evaluation: {evaluation}")
        await super()._phase_report()

    async def _handle_error(self, error: str, index: int) -> dict[str, Any] | None:
        """Ask LLM how to recover from a collection error."""
        if not self._llm_client:
            return None

        from agent_haymaker.llm import LLMMessage

        response = await self._llm_client.create_message_async(
            messages=[
                LLMMessage(
                    role="user",
                    content=(
                        f"Error collecting item {index}: {error}\n"
                        f"Goal: {self.goal}\n"
                        "Should I skip this item or retry? "
                        "Reply SKIP or provide alternative data as JSON."
                    ),
                )
            ],
            system="You are a data collection assistant. Be concise.",
            max_tokens=100,
        )

        if "SKIP" in response.content.upper():
            return None
        return {"id": f"item-{index:04d}-recovered", "data": response.content}

    async def _evaluate_goal(self) -> str:
        """Ask LLM to evaluate whether the goal was truly achieved."""
        if not self._llm_client:
            return "No LLM available"

        from agent_haymaker.llm import LLMMessage

        response = await self._llm_client.create_message_async(
            messages=[
                LLMMessage(
                    role="user",
                    content=(
                        f"Goal: {self.goal}\n"
                        f"Items collected: {len(self._items_collected)}\n"
                        f"Target: {self.item_count}\n"
                        "Was the goal achieved? One sentence."
                    ),
                )
            ],
            max_tokens=50,
        )
        return response.content.strip()
```

{: .tip }
The LLM enhancement is completely optional. The base `GoalSeekingAgent` works without it. This layered design means your agent degrades gracefully.

## Step 5: Wire the agent into the workload

Replace `src/haymaker_data_collector/workload.py` with:

```python
"""DataCollectorWorkload - goal-seeking data collection agent."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from agent_haymaker.workloads.base import DeploymentNotFoundError, WorkloadBase
from agent_haymaker.workloads.models import (
    CleanupReport,
    DeploymentConfig,
    DeploymentState,
    DeploymentStatus,
)
from agent_haymaker.workloads.platform import Platform

from .agent import GoalSeekingAgent

_TERMINAL_STATES = frozenset({DeploymentStatus.COMPLETED, DeploymentStatus.FAILED})


class DataCollectorWorkload(WorkloadBase):
    """Workload that manages goal-seeking data collector agents."""

    name = "data-collector"

    def __init__(self, platform: Platform | None = None) -> None:
        super().__init__(platform=platform)
        self._agents: dict[str, GoalSeekingAgent] = {}

    async def deploy(self, config: DeploymentConfig) -> str:
        deployment_id = f"{self.name}-{uuid.uuid4().hex[:8]}"
        goal = config.workload_config.get("goal", "Collect 10 data items")
        item_count = config.workload_config.get("item_count", 10)
        enable_llm = config.workload_config.get("enable_llm", False)

        # Choose agent class
        agent_kwargs: dict[str, Any] = {
            "deployment_id": deployment_id,
            "goal": goal,
            "item_count": item_count,
            "on_status_change": lambda phase, status: asyncio.ensure_future(
                self._on_agent_status(deployment_id, phase, status)
            ),
        }

        if enable_llm:
            from agent_haymaker.llm import LLMConfig, create_llm_client

            from .llm_agent import LLMGoalSeekingAgent

            llm_config = LLMConfig.from_env()
            agent_kwargs["llm_client"] = create_llm_client(llm_config)
            agent = LLMGoalSeekingAgent(**agent_kwargs)
        else:
            agent = GoalSeekingAgent(**agent_kwargs)

        self._agents[deployment_id] = agent

        state = DeploymentState(
            deployment_id=deployment_id,
            workload_name=self.name,
            status=DeploymentStatus.RUNNING,
            phase="initializing",
            started_at=datetime.now(tz=UTC),
            config=config.workload_config,
            metadata={"goal": goal, "item_count": item_count, "items_collected": 0},
        )
        await self.save_state(state)
        await agent.start()
        return deployment_id

    async def get_status(self, deployment_id: str) -> DeploymentState:
        state = await self.load_state(deployment_id)
        if state is None:
            raise DeploymentNotFoundError(f"Deployment {deployment_id} not found")
        # Update metadata from agent if running
        agent = self._agents.get(deployment_id)
        if agent:
            state.metadata["items_collected"] = len(agent._items_collected)
        return state

    async def stop(self, deployment_id: str) -> bool:
        state = await self.get_status(deployment_id)
        if state.status in _TERMINAL_STATES:
            return False
        agent = self._agents.get(deployment_id)
        if agent:
            await agent.stop()
        state.status = DeploymentStatus.STOPPED
        state.phase = "stopped"
        state.stopped_at = datetime.now(tz=UTC)
        await self.save_state(state)
        return True

    async def start(self, deployment_id: str) -> bool:
        state = await self.get_status(deployment_id)
        if state.status != DeploymentStatus.STOPPED:
            return False
        state.status = DeploymentStatus.RUNNING
        state.phase = "running"
        state.stopped_at = None
        await self.save_state(state)
        return True

    async def cleanup(self, deployment_id: str) -> CleanupReport:
        state = await self.get_status(deployment_id)
        if state.status in _TERMINAL_STATES:
            return CleanupReport(
                deployment_id=deployment_id,
                details=[f"Already {state.status}"],
            )
        start_time = time.monotonic()
        agent = self._agents.pop(deployment_id, None)
        result = {}
        if agent:
            result = await agent.cleanup()
        state.status = DeploymentStatus.COMPLETED
        state.phase = "cleaned_up"
        state.completed_at = datetime.now(tz=UTC)
        await self.save_state(state)
        return CleanupReport(
            deployment_id=deployment_id,
            resources_deleted=1,
            details=[f"Agent result: {result}"],
            duration_seconds=time.monotonic() - start_time,
        )

    async def get_logs(
        self, deployment_id: str, follow: bool = False, lines: int = 100
    ) -> AsyncIterator[str]:
        await self.get_status(deployment_id)  # raises if not found
        agent = self._agents.get(deployment_id)
        if agent:
            async for line in agent.get_logs(lines=lines):
                yield line

    async def _on_agent_status(
        self, deployment_id: str, phase: str, status: str
    ) -> None:
        """Callback from agent to update deployment state."""
        state = await self.load_state(deployment_id)
        if state:
            state.phase = phase
            if status == "completed":
                state.status = DeploymentStatus.COMPLETED
                state.completed_at = datetime.now(tz=UTC)
            elif status == "failed":
                state.status = DeploymentStatus.FAILED
            await self.save_state(state)
```

## Step 6: Add tests

Replace `tests/test_workload.py`:

```python
"""Tests for DataCollectorWorkload and GoalSeekingAgent."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_haymaker.workloads.base import DeploymentNotFoundError
from agent_haymaker.workloads.models import (
    DeploymentConfig,
    DeploymentState,
    DeploymentStatus,
)

from haymaker_data_collector import DataCollectorWorkload
from haymaker_data_collector.agent import GoalSeekingAgent


def _mock_platform():
    platform = MagicMock()
    storage: dict[str, DeploymentState] = {}

    async def save(state):
        storage[state.deployment_id] = state

    async def load(deployment_id):
        return storage.get(deployment_id)

    async def list_deps(workload_name):
        return [s for s in storage.values() if s.workload_name == workload_name]

    platform.save_deployment_state = AsyncMock(side_effect=save)
    platform.load_deployment_state = AsyncMock(side_effect=load)
    platform.list_deployments = AsyncMock(side_effect=list_deps)
    platform.get_credential = AsyncMock(return_value=None)
    platform.log = MagicMock()
    platform._storage = storage
    return platform


class TestGoalSeekingAgent:
    async def test_agent_collects_items(self):
        agent = GoalSeekingAgent(
            deployment_id="test-001", goal="Collect 5 items", item_count=5
        )
        await agent.start()
        await asyncio.sleep(1)  # Let agent run
        assert len(agent._items_collected) == 5

    async def test_agent_stop(self):
        agent = GoalSeekingAgent(
            deployment_id="test-002", goal="Collect 100 items", item_count=100
        )
        await agent.start()
        await asyncio.sleep(0.2)
        await agent.stop()
        assert len(agent._items_collected) < 100

    async def test_agent_cleanup(self):
        agent = GoalSeekingAgent(
            deployment_id="test-003", goal="Collect 3 items", item_count=3
        )
        await agent.start()
        await asyncio.sleep(1)
        result = await agent.cleanup()
        assert result["goal_achieved"] is True
        assert result["items_collected"] == 3

    async def test_agent_logs(self):
        agent = GoalSeekingAgent(
            deployment_id="test-004", goal="Collect 2 items", item_count=2
        )
        await agent.start()
        await asyncio.sleep(1)
        logs = [line async for line in agent.get_logs()]
        assert any("Goal:" in line for line in logs)
        assert any("Collected" in line for line in logs)

    async def test_status_callback(self):
        phases = []
        agent = GoalSeekingAgent(
            deployment_id="test-005",
            goal="Test",
            item_count=2,
            on_status_change=lambda p, s: phases.append(p),
        )
        await agent.start()
        await asyncio.sleep(1)
        assert "initializing" in phases
        assert "collecting" in phases
        assert "completed" in phases


class TestDataCollectorWorkload:
    @pytest.fixture()
    def workload(self):
        return DataCollectorWorkload(platform=_mock_platform())

    async def test_deploy(self, workload):
        config = DeploymentConfig(
            workload_name="data-collector",
            workload_config={"item_count": 3},
        )
        dep_id = await workload.deploy(config)
        assert dep_id.startswith("data-collector-")
        state = await workload.get_status(dep_id)
        assert state.status == DeploymentStatus.RUNNING

    async def test_deploy_and_wait(self, workload):
        config = DeploymentConfig(
            workload_name="data-collector",
            workload_config={"item_count": 3},
        )
        dep_id = await workload.deploy(config)
        await asyncio.sleep(1)
        state = await workload.get_status(dep_id)
        assert state.metadata["items_collected"] == 3

    async def test_stop(self, workload):
        config = DeploymentConfig(
            workload_name="data-collector",
            workload_config={"item_count": 100},
        )
        dep_id = await workload.deploy(config)
        await asyncio.sleep(0.2)
        result = await workload.stop(dep_id)
        assert result is True
        state = await workload.get_status(dep_id)
        assert state.status == DeploymentStatus.STOPPED

    async def test_cleanup(self, workload):
        config = DeploymentConfig(
            workload_name="data-collector",
            workload_config={"item_count": 3},
        )
        dep_id = await workload.deploy(config)
        await asyncio.sleep(1)
        report = await workload.cleanup(dep_id)
        assert report.resources_deleted >= 0  # 0 if agent already completed

    async def test_get_logs(self, workload):
        config = DeploymentConfig(
            workload_name="data-collector",
            workload_config={"item_count": 3},
        )
        dep_id = await workload.deploy(config)
        await asyncio.sleep(1)
        logs = [line async for line in workload.get_logs(dep_id)]
        assert len(logs) > 0

    async def test_not_found(self, workload):
        with pytest.raises(DeploymentNotFoundError):
            await workload.get_status("nonexistent")
```

Run the tests:

```bash
pytest -q
```

Expected output:

```
...........                                              [100%]
11 passed in X.XXs
```

## Step 7: Run with the haymaker CLI

Now test the full lifecycle using the CLI:

```bash
# Deploy with default settings
haymaker deploy data-collector --yes

# Check status (use the deployment ID from the output)
haymaker status <deployment-id>

# View logs
haymaker logs <deployment-id>

# Stop and resume
haymaker stop <deployment-id> --yes
haymaker start <deployment-id>

# Clean up
haymaker cleanup <deployment-id> --yes
```

You should see output like:

```
Deployment started: data-collector-a1b2c3d4

Deployment: data-collector-a1b2c3d4
  Workload: data-collector
  Status:   running
  Phase:    collecting
  Started:  2026-02-28 03:15:22.123456+00:00
```

## Step 8: Deploy to Azure

The starter repo includes a deployment pipeline. See the [Deploy to Azure](deploy) guide for details.

```bash
# One-time OIDC setup
./scripts/setup-oidc.sh your-org/my-data-collector

# Deploy
gh workflow run deploy.yml -f environment=dev
```

## Next steps

- **Customize `_collect_one_item`** to call real APIs, query databases, or process files
- **Add scenarios** by creating markdown files that describe different collection strategies
- **Enable LLM** with `--config enable_llm=true` for adaptive error recovery
- **Study the examples**:
  - [Azure Infrastructure Workload](https://github.com/rysweet/haymaker-azure-workloads) -- goal-seeking agents for Azure resource management
  - [M365 Knowledge Worker Workload](https://github.com/rysweet/haymaker-m365-workloads) -- activity simulation with optional LLM content generation
