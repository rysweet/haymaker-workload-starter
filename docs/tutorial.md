---
layout: default
title: "Tutorial: Build a Goal-Seeking Agent"
nav_order: 2
description: "Learn the goal-seeking agent pattern by building a data collector from scratch"
---

# Tutorial: Build a Goal-Seeking Agent
{: .no_toc }

Learn how Agent Haymaker workloads work by building one from scratch. You will understand the architecture as you go, not just copy code.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## What you will learn

By the end of this tutorial you will understand:

- **The workload pattern**: Why workloads have exactly 5 methods and what each one is responsible for
- **The goal-seeking agent pattern**: How agents execute in phases, report status via callbacks, and manage their own lifecycle
- **The LLM enhancement layer**: How to add optional intelligence without creating a hard dependency
- **The registration mechanism**: How Python entry points let the platform discover your code automatically
- **The deployment lifecycle**: How `haymaker deploy` → `status` → `logs` → `stop` → `cleanup` maps to your code

<div class="concept-box" markdown="1">

#### The big picture

A haymaker workload is a Python package that teaches the platform how to manage one type of work. Think of it like a driver -- the platform (haymaker CLI) is the operating system, and your workload is the driver that knows how to talk to a specific piece of hardware.

The platform handles: discovery, CLI commands, state persistence, credential management.
Your workload handles: the actual work (deploying agents, collecting data, running scenarios).

</div>

## Prerequisites

- Python 3.11+
- Git
- [agent-haymaker](https://github.com/rysweet/agent-haymaker) installed (`pip install -e path/to/agent-haymaker`)

---

## Part 1: Understanding the starter template

### Clone and explore

```bash
git clone https://github.com/rysweet/haymaker-workload-starter my-data-collector
cd my-data-collector
pip install -e ".[dev]"
```

Verify the workload is discovered:

```bash
haymaker workload list
```

```
Installed workloads:
  - my-workload
```

{: .note }
How did the platform find your workload? Look at `pyproject.toml` -- the `[project.entry-points."agent_haymaker.workloads"]` section registers a name (`my-workload`) pointing to a Python class. The platform scans all installed packages for this entry point group at startup.

### What the starter gives you

Open `src/haymaker_my_workload/workload.py`. It implements `WorkloadBase` with all 5 required methods. But it is just a skeleton -- it stores state and logs but does no real work. Your job is to replace the internals with a **goal-seeking agent** that actually does something.

Run the existing tests to see the baseline:

```bash
pytest -q
```

All 49 tests should pass. These test the skeleton lifecycle. You will replace them with tests for your agent.

---

## Part 2: Rename and make it yours

Before writing any agent code, rename the package so it has its own identity.

Update `pyproject.toml`:

```toml
[project]
name = "haymaker-data-collector"

[project.entry-points."agent_haymaker.workloads"]
data-collector = "haymaker_data_collector:DataCollectorWorkload"

[tool.hatch.build.targets.wheel]
packages = ["src/haymaker_data_collector"]
```

Rename the source directory and update the class:

```bash
mv src/haymaker_my_workload src/haymaker_data_collector

sed -i 's/class MyWorkload/class DataCollectorWorkload/' src/haymaker_data_collector/workload.py
sed -i 's/name = "my-workload"/name = "data-collector"/' src/haymaker_data_collector/workload.py
```

Update `src/haymaker_data_collector/__init__.py`:

```python
"""Data Collector Workload - goal-seeking agent for Agent Haymaker."""

from importlib.metadata import version
from .workload import DataCollectorWorkload

__version__ = version("haymaker-data-collector")
__all__ = ["DataCollectorWorkload"]
```

Update `workload.yaml` with your workload's config schema:

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

You should see `data-collector` in the list.

---

## Part 3: The goal-seeking agent pattern

<div class="concept-box" markdown="1">

#### Why a separate agent class?

The workload manages *platform integration* (state, CLI, credentials). The agent manages *execution* (phases, goals, progress). Keeping them separate means you can:

- Test the agent without the platform
- Swap agent implementations (basic vs LLM-enhanced)
- Reuse the same agent in different workload configurations

This is the same pattern used by the [Azure Infrastructure Workload](https://github.com/rysweet/haymaker-azure-workloads), where `AzureInfrastructureWorkload` delegates to `GoalSeekingAgent`.

</div>

### The agent contract

Every goal-seeking agent needs four capabilities:

| Method | Purpose | When called |
|--------|---------|------------|
| `start()` | Begin executing the goal | On deploy |
| `stop()` | Pause gracefully (save progress) | On `haymaker stop` |
| `cleanup()` | Release all resources | On `haymaker cleanup` |
| `get_logs()` | Stream execution history | On `haymaker logs` |

The agent also communicates back to the workload via a **status callback**: `on_status_change(phase, status)`. This is how the platform knows what your agent is doing.

### Phase-based execution

Agents work in phases. Each phase represents a logical stage of work:

```
initialize  →  collect  →  report
     ↑                        |
     |     (stop/resume)      |
     +────────────────────────+
```

The phases for our data-collector:

1. **Initialize**: Validate configuration, set up connections
2. **Collect**: The main work loop -- collect items one by one
3. **Report**: Summarize what was accomplished, evaluate the goal

### Build the agent

Create `src/haymaker_data_collector/agent.py`:

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

    The lifecycle:
        1. start() creates an async task that runs _run()
        2. _run() executes phases sequentially: initialize → collect → report
        3. Each phase calls _update_status() to notify the workload
        4. stop() cancels the task; cleanup() stops + releases resources
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
        """Launch the execution loop as a background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Cancel the execution task gracefully."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def cleanup(self) -> dict[str, Any]:
        """Stop and return a summary of what was accomplished."""
        await self.stop()
        self._log("Cleaning up resources")
        return {
            "items_collected": len(self._items_collected),
            "goal": self.goal,
            "goal_achieved": len(self._items_collected) >= self.item_count,
        }

    async def get_logs(self, lines: int = 100) -> AsyncIterator[str]:
        """Yield the most recent log lines."""
        for line in self._logs[-lines:]:
            yield line

    # -- Execution engine --

    async def _run(self) -> None:
        """Sequentially execute all phases."""
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
        self._update_status("initializing", "running")
        self._log(f"Goal: {self.goal}")
        self._log(f"Target: {self.item_count} items")
        await asyncio.sleep(0.1)
        self._log("Initialization complete")

    async def _phase_collect(self) -> None:
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
        self._update_status("reporting", "running")
        achieved = len(self._items_collected) >= self.item_count
        self._log(f"Goal achieved: {achieved}")
        self._update_status("completed", "completed")

    async def _collect_one_item(self, index: int) -> dict[str, Any]:
        """Collect a single data item. Override this with your real logic."""
        await asyncio.sleep(0.05)
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

<div class="concept-box" markdown="1">

#### Key design decisions in this code

**`_collect_one_item` is the extension point.** The framework handles phases, logging, status, and lifecycle. You only need to implement what happens for each item. This is where you would put API calls, database queries, file processing, etc.

**`_running` flag enables cooperative cancellation.** The collect loop checks `self._running` every iteration. When `stop()` sets it to False, the loop exits cleanly at the next item boundary -- no data corruption.

**Status callbacks are fire-and-forget.** The agent calls `_update_status()` but does not wait for it. This decouples the agent from the platform -- the agent runs at full speed and the platform catches up.

</div>

---

## Part 4: Adding LLM intelligence (optional)

<div class="concept-box" markdown="1">

#### The layered enhancement pattern

The base agent works without any LLM. The LLM-enhanced version adds optional intelligence by *overriding specific methods*. This means:

- No LLM? Agent works fine with defaults.
- LLM available? Agent recovers from errors, evaluates goals, adapts behavior.
- LLM fails? Agent falls back to base behavior automatically.

This is exactly how the [Azure workload](https://github.com/rysweet/haymaker-azure-workloads/blob/main/src/haymaker_azure_workloads/llm_agent.py) adds Claude-powered troubleshooting on top of static Azure CLI commands.

</div>

Create `src/haymaker_data_collector/llm_agent.py`:

```python
"""LLMGoalSeekingAgent - adds adaptive LLM behavior to the base agent."""

from __future__ import annotations
from typing import Any
from .agent import GoalSeekingAgent


class LLMGoalSeekingAgent(GoalSeekingAgent):
    """Extends GoalSeekingAgent with LLM-powered error recovery and goal evaluation."""

    def __init__(self, llm_client=None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._llm_client = llm_client

    async def _collect_one_item(self, index: int) -> dict[str, Any]:
        """Override: if collection fails, ask the LLM for recovery advice."""
        try:
            return await super()._collect_one_item(index)
        except Exception as exc:
            recovery = await self._handle_error(str(exc), index)
            if recovery:
                self._log(f"LLM suggested recovery: {recovery}")
                return recovery
            raise

    async def _phase_report(self) -> None:
        """Override: use LLM to evaluate goal achievement before reporting."""
        if self._llm_client:
            evaluation = await self._evaluate_goal()
            self._log(f"LLM evaluation: {evaluation}")
        await super()._phase_report()

    async def _handle_error(self, error: str, index: int) -> dict[str, Any] | None:
        if not self._llm_client:
            return None
        from agent_haymaker.llm import LLMMessage
        response = await self._llm_client.create_message_async(
            messages=[LLMMessage(
                role="user",
                content=f"Error collecting item {index}: {error}\n"
                        f"Goal: {self.goal}\n"
                        "Reply SKIP to skip, or provide alternative data as JSON.",
            )],
            system="You are a data collection assistant. Be concise.",
            max_tokens=100,
        )
        if "SKIP" in response.content.upper():
            return None
        return {"id": f"item-{index:04d}-recovered", "data": response.content}

    async def _evaluate_goal(self) -> str:
        if not self._llm_client:
            return "No LLM available"
        from agent_haymaker.llm import LLMMessage
        response = await self._llm_client.create_message_async(
            messages=[LLMMessage(
                role="user",
                content=f"Goal: {self.goal}\nItems: {len(self._items_collected)}/{self.item_count}\nAchieved? One sentence.",
            )],
            max_tokens=50,
        )
        return response.content.strip()
```

{: .note }
The `from agent_haymaker.llm import ...` is inside the methods, not at module level. This is intentional -- it means the LLM dependencies are only loaded when actually used. Users who don't need LLM don't need to install `anthropic` or `openai`.

---

## Part 5: Wiring the agent into the workload

<div class="concept-box" markdown="1">

#### The workload's job

The workload is the **bridge** between the platform and your agent. It translates CLI commands into agent method calls:

| CLI command | Workload method | What it does to the agent |
|-------------|----------------|--------------------------|
| `haymaker deploy` | `deploy()` | Creates agent, calls `agent.start()` |
| `haymaker status` | `get_status()` | Reads persisted state + live agent metrics |
| `haymaker stop` | `stop()` | Calls `agent.stop()`, persists STOPPED state |
| `haymaker start` | `start()` | Updates state back to RUNNING |
| `haymaker cleanup` | `cleanup()` | Calls `agent.cleanup()`, persists COMPLETED state |
| `haymaker logs` | `get_logs()` | Delegates to `agent.get_logs()` |

The workload also decides **which agent class to use** based on configuration (basic vs LLM-enhanced).

</div>

Replace `src/haymaker_data_collector/workload.py`:

```python
"""DataCollectorWorkload - manages goal-seeking data collector agents."""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from agent_haymaker.workloads.base import DeploymentNotFoundError, WorkloadBase
from agent_haymaker.workloads.models import (
    CleanupReport, DeploymentConfig, DeploymentState, DeploymentStatus,
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

        # Choose agent class based on LLM config
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
            agent_kwargs["llm_client"] = create_llm_client(LLMConfig.from_env())
            agent = LLMGoalSeekingAgent(**agent_kwargs)
        else:
            agent = GoalSeekingAgent(**agent_kwargs)

        self._agents[deployment_id] = agent

        state = DeploymentState(
            deployment_id=deployment_id, workload_name=self.name,
            status=DeploymentStatus.RUNNING, phase="initializing",
            started_at=datetime.now(tz=UTC), config=config.workload_config,
            metadata={"goal": goal, "item_count": item_count, "items_collected": 0},
        )
        await self.save_state(state)
        await agent.start()
        return deployment_id

    async def get_status(self, deployment_id: str) -> DeploymentState:
        state = await self.load_state(deployment_id)
        if state is None:
            raise DeploymentNotFoundError(f"Deployment {deployment_id} not found")
        # Enrich with live agent data
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
            return CleanupReport(deployment_id=deployment_id, details=[f"Already {state.status}"])
        start_time = time.monotonic()
        agent = self._agents.pop(deployment_id, None)
        result = await agent.cleanup() if agent else {}
        state.status = DeploymentStatus.COMPLETED
        state.phase = "cleaned_up"
        state.completed_at = datetime.now(tz=UTC)
        await self.save_state(state)
        return CleanupReport(
            deployment_id=deployment_id, resources_deleted=1,
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

    async def _on_agent_status(self, deployment_id: str, phase: str, status: str) -> None:
        """Callback from agent -- updates persisted deployment state."""
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

Reinstall:

```bash
pip install -e ".[dev]"
```

---

## Part 6: Testing your agent

Replace `tests/test_workload.py` with tests that verify both the agent and the workload:

```python
"""Tests for DataCollectorWorkload and GoalSeekingAgent."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_haymaker.workloads.base import DeploymentNotFoundError
from agent_haymaker.workloads.models import (
    DeploymentConfig, DeploymentState, DeploymentStatus,
)
from haymaker_data_collector import DataCollectorWorkload
from haymaker_data_collector.agent import GoalSeekingAgent


def _mock_platform():
    platform = MagicMock()
    storage: dict[str, DeploymentState] = {}
    async def save(state): storage[state.deployment_id] = state
    async def load(did): return storage.get(did)
    async def list_deps(name): return [s for s in storage.values() if s.workload_name == name]
    platform.save_deployment_state = AsyncMock(side_effect=save)
    platform.load_deployment_state = AsyncMock(side_effect=load)
    platform.list_deployments = AsyncMock(side_effect=list_deps)
    platform.get_credential = AsyncMock(return_value=None)
    platform.log = MagicMock()
    return platform


class TestGoalSeekingAgent:
    async def test_collects_all_items(self):
        agent = GoalSeekingAgent(deployment_id="t1", goal="Collect 5", item_count=5)
        await agent.start()
        await asyncio.sleep(1)
        assert len(agent._items_collected) == 5

    async def test_stop_is_cooperative(self):
        agent = GoalSeekingAgent(deployment_id="t2", goal="Collect 100", item_count=100)
        await agent.start()
        await asyncio.sleep(0.2)
        await agent.stop()
        assert 0 < len(agent._items_collected) < 100

    async def test_cleanup_returns_summary(self):
        agent = GoalSeekingAgent(deployment_id="t3", goal="Collect 3", item_count=3)
        await agent.start()
        await asyncio.sleep(1)
        result = await agent.cleanup()
        assert result["goal_achieved"] is True

    async def test_status_callbacks_fire(self):
        phases = []
        agent = GoalSeekingAgent(
            deployment_id="t4", goal="Test", item_count=2,
            on_status_change=lambda p, s: phases.append(p),
        )
        await agent.start()
        await asyncio.sleep(1)
        assert "initializing" in phases
        assert "collecting" in phases
        assert "completed" in phases

    async def test_logs_contain_progress(self):
        agent = GoalSeekingAgent(deployment_id="t5", goal="Collect 2", item_count=2)
        await agent.start()
        await asyncio.sleep(1)
        logs = [line async for line in agent.get_logs()]
        assert any("Goal:" in l for l in logs)
        assert any("Collected" in l for l in logs)


class TestDataCollectorWorkload:
    @pytest.fixture()
    def workload(self):
        return DataCollectorWorkload(platform=_mock_platform())

    async def test_deploy_returns_id(self, workload):
        config = DeploymentConfig(workload_name="data-collector", workload_config={"item_count": 3})
        dep_id = await workload.deploy(config)
        assert dep_id.startswith("data-collector-")

    async def test_status_reflects_agent_progress(self, workload):
        config = DeploymentConfig(workload_name="data-collector", workload_config={"item_count": 3})
        dep_id = await workload.deploy(config)
        await asyncio.sleep(1)
        state = await workload.get_status(dep_id)
        assert state.metadata["items_collected"] == 3

    async def test_stop_pauses_agent(self, workload):
        config = DeploymentConfig(workload_name="data-collector", workload_config={"item_count": 100})
        dep_id = await workload.deploy(config)
        await asyncio.sleep(0.2)
        await workload.stop(dep_id)
        state = await workload.get_status(dep_id)
        assert state.status == DeploymentStatus.STOPPED

    async def test_cleanup_completes(self, workload):
        config = DeploymentConfig(workload_name="data-collector", workload_config={"item_count": 3})
        dep_id = await workload.deploy(config)
        await asyncio.sleep(1)
        report = await workload.cleanup(dep_id)
        assert report.resources_deleted >= 0

    async def test_logs_stream_from_agent(self, workload):
        config = DeploymentConfig(workload_name="data-collector", workload_config={"item_count": 3})
        dep_id = await workload.deploy(config)
        await asyncio.sleep(1)
        logs = [l async for l in workload.get_logs(dep_id)]
        assert len(logs) > 0

    async def test_not_found_raises(self, workload):
        with pytest.raises(DeploymentNotFoundError):
            await workload.get_status("nonexistent")
```

Run them:

```bash
pytest -q
```

Expected: 11 tests pass.

---

## Part 7: Run with the haymaker CLI

This is the payoff -- your agent runs through the same CLI used by all haymaker workloads:

```bash
# Deploy your agent
haymaker deploy data-collector --config item_count=5 --yes

# Check on it (use the deployment ID from the output)
haymaker status <deployment-id>

# View the agent's log output
haymaker logs <deployment-id>

# Full lifecycle test: stop, resume, cleanup
haymaker stop <deployment-id> --yes
haymaker start <deployment-id>
haymaker cleanup <deployment-id> --yes
```

What each command does under the hood:

| You type | Platform calls | Your code runs |
|----------|---------------|---------------|
| `haymaker deploy data-collector` | `workload.deploy(config)` | Creates `GoalSeekingAgent`, calls `agent.start()` |
| `haymaker status <id>` | `workload.get_status(id)` | Reads persisted state + live `agent._items_collected` |
| `haymaker logs <id>` | `workload.get_logs(id)` | Iterates `agent._logs` |
| `haymaker stop <id>` | `workload.stop(id)` | Sets `agent._running = False`, persists STOPPED |
| `haymaker start <id>` | `workload.start(id)` | Updates persisted state to RUNNING |
| `haymaker cleanup <id>` | `workload.cleanup(id)` | Calls `agent.cleanup()`, persists COMPLETED |

---

## Part 8: Deploy to Azure

See the [Deploy to Azure](deploy) guide for the full OIDC pipeline. The short version:

```bash
./scripts/setup-oidc.sh your-org/my-data-collector
gh workflow run deploy.yml -f environment=dev
```

---

## Part 9: Using the Amplihack Goal Agent Generator

<div class="concept-box" markdown="1">

#### From hand-crafted to generated agents

Parts 3-5 taught you to build agents by hand -- you defined phases, wrote the execution loop, and wired everything together manually. That is the right approach when you need full control over agent behavior.

But for many workloads, you can skip most of that work. The [Amplihack Goal Agent Generator](https://rysweet.github.io/amplihack/GOAL_AGENT_GENERATOR_GUIDE/) creates autonomous agents from a **natural language goal description**. Instead of writing `_collect_one_item()`, you write a markdown prompt describing what the agent should accomplish, and the generator produces a complete, executable agent bundle.

</div>

### How the generator works

The generator is a 4-stage pipeline:

```
prompt.md  →  PromptAnalyzer  →  GoalDefinition
                                       ↓
                                 ObjectivePlanner  →  ExecutionPlan (3-5 phases)
                                       ↓
                                 SkillSynthesizer  →  matched skills + SDK tools
                                       ↓
                                 AgentAssembler    →  GoalAgentBundle
                                       ↓
                                 GoalAgentPackager →  runnable agent directory
```

| Stage | What it does | Output |
|-------|-------------|--------|
| **Analyze** | Extracts goal, domain, constraints, success criteria from markdown | `GoalDefinition` |
| **Plan** | Creates a phased execution plan based on domain templates | `ExecutionPlan` with 3-5 phases |
| **Synthesize** | Matches skills from a library + injects SDK-native tools | Scored skill matches + tool configs |
| **Assemble** | Combines everything into an executable bundle | Agent directory with `main.py` |

### Writing a goal prompt

Create a markdown file describing what your agent should do:

```markdown
# Data Collection Agent

## Goal
Collect product pricing data from 5 e-commerce APIs, normalize the schema,
and produce a consolidated JSON report.

## Constraints
- Rate limit: max 10 requests per second per API
- Must handle API authentication via environment variables
- Timeout: complete within 30 minutes

## Success Criteria
- Data collected from all 5 APIs
- All records normalized to common schema
- Report written to output/pricing-report.json
- No unhandled errors
```

### Generating the agent (CLI)

```bash
# Install amplihack if not already available
pip install amplihack

# Generate the agent
amplihack new \
  --file goals/data-collection.md \
  --name pricing-collector \
  --sdk claude \
  --enable-memory \
  --output ./agents
```

This produces a complete agent directory:

```
agents/pricing-collector/
├── main.py          # Entry point using AutoMode
├── prompt.md        # Your goal definition
├── config.json      # Execution plan, SDK config, max_turns
├── skills/          # Auto-matched skills
├── README.md        # Usage instructions
└── logs/            # Runtime traces (populated during execution)
```

### Generating the agent (Python API)

You can also call the generator from within your workload code:

```python
from amplihack.goal_agent_generator import (
    PromptAnalyzer,
    ObjectivePlanner,
    SkillSynthesizer,
    AgentAssembler,
    GoalAgentPackager,
)
from pathlib import Path

# 1. Analyze the goal
analyzer = PromptAnalyzer()
goal_def = analyzer.analyze(Path("goals/data-collection.md"))
# goal_def.goal = "Collect product pricing data..."
# goal_def.domain = "data-processing"
# goal_def.complexity = "moderate"

# 2. Create execution plan
planner = ObjectivePlanner()
plan = planner.generate_plan(goal_def)
# plan.phases = [Collection, Transformation, Analysis, Reporting]

# 3. Match skills
synthesizer = SkillSynthesizer()
synthesis = synthesizer.synthesize_with_sdk_tools(plan, sdk="claude")

# 4. Assemble + package
assembler = AgentAssembler()
bundle = assembler.assemble(
    goal_def, plan, synthesis["skills"],
    sdk="claude", enable_memory=True,
    sdk_tools=synthesis["sdk_tools"],
)

packager = GoalAgentPackager(output_dir=Path("./agents"))
agent_dir = packager.package(bundle)
```

### SDK options

The generator supports four execution SDKs:

| SDK | Best for | Requires |
|-----|----------|----------|
| `claude` | General agent tasks, tool use, subagent delegation | `ANTHROPIC_API_KEY` |
| `copilot` | Development tasks, code generation, git operations | GitHub Copilot access |
| `microsoft` | Azure workloads, structured workflows, telemetry | Azure AI credentials |
| `mini` | Lightweight tasks, minimal dependencies | `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` |

### Wiring a generated agent into your workload

Here is how your workload's `deploy()` can use the generator instead of a hand-built agent:

```python
async def deploy(self, config: DeploymentConfig) -> str:
    deployment_id = f"{self.name}-{uuid.uuid4().hex[:8]}"
    goal_file = Path(config.workload_config.get("goal_file", "goal.md"))
    sdk = config.workload_config.get("sdk", "claude")

    # Generate the agent from the goal prompt
    from amplihack.goal_agent_generator import (
        PromptAnalyzer, ObjectivePlanner,
        SkillSynthesizer, AgentAssembler, GoalAgentPackager,
    )

    goal_def = PromptAnalyzer().analyze(goal_file)
    plan = ObjectivePlanner().generate_plan(goal_def)
    synthesis = SkillSynthesizer().synthesize_with_sdk_tools(plan, sdk=sdk)
    bundle = AgentAssembler().assemble(
        goal_def, plan, synthesis["skills"],
        sdk=sdk, sdk_tools=synthesis["sdk_tools"],
    )
    agent_dir = GoalAgentPackager(
        output_dir=Path(f".haymaker/agents/{deployment_id}")
    ).package(bundle)

    # Persist state
    state = DeploymentState(
        deployment_id=deployment_id,
        workload_name=self.name,
        status=DeploymentStatus.RUNNING,
        phase="executing",
        started_at=datetime.now(tz=UTC),
        config=config.workload_config,
        metadata={
            "goal": goal_def.goal,
            "domain": goal_def.domain,
            "phases": len(plan.phases),
            "agent_dir": str(agent_dir),
        },
    )
    await self.save_state(state)

    # Execute the generated agent in background
    asyncio.create_task(self._run_generated_agent(agent_dir, deployment_id))
    return deployment_id
```

<div class="concept-box" markdown="1">

#### When to use which approach

| Approach | When to use it |
|----------|---------------|
| **Hand-built agent** (Parts 3-5) | You need precise control over every phase. Your domain logic is custom and specific. |
| **Generated agent** (Part 9) | Your goal can be described in natural language. You want the AI to figure out the phases and tools. |
| **Both** | Hand-build the core agent, use the generator for sub-tasks that benefit from autonomous exploration. |

The Azure Infrastructure Workload uses hand-built agents because it needs precise control over Azure CLI commands. A research or data-collection workload might benefit more from generated agents that can explore and adapt.

</div>

### Further reading

- [Goal Agent Generator Guide](https://rysweet.github.io/amplihack/GOAL_AGENT_GENERATOR_GUIDE/) -- full reference
- [Amplihack Framework](https://github.com/rysweet/amplihack) -- the underlying platform

---

## Next steps

You now have two approaches to building workloads:

- **Hand-crafted agents** (Parts 3-5) for full control
- **Generated agents** (Part 9) for declarative, goal-driven workloads

To go further:

- **Replace `_collect_one_item`** with real API calls, database queries, or file processing
- **Write goal prompts** and use `amplihack new` to generate agents for your domain
- **Add error handling** in the LLM agent for your domain-specific failures
- **Study the production workloads**:
  - [Azure Infrastructure](https://github.com/rysweet/haymaker-azure-workloads) -- goal-seeking agents for Azure resource management
  - [M365 Knowledge Worker](https://github.com/rysweet/haymaker-m365-workloads) -- activity simulation with LLM content generation
