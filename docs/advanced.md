---
layout: default
title: "Advanced: Build a Custom Agent"
nav_order: 5
description: "Build a hand-crafted goal-seeking agent when you need full control"
---

# Advanced: Build a Custom Agent
{: .no_toc }

When you need full control over agent behavior -- custom phases, domain-specific error handling, or integration with systems the generator doesn't know about -- build the agent by hand.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## When to use this approach

| Use the generator (main tutorial) | Build by hand (this page) |
|-----------------------------------|--------------------------|
| Goal can be described in prose | Domain logic is highly specific |
| Standard phases work (plan → implement → test → deploy) | Custom phase ordering or dependencies |
| Agent should explore and adapt | You need deterministic behavior |
| Quick iteration on new goal types | Production workload with strict requirements |

## The pattern

A hand-built agent has two classes:

1. **GoalSeekingAgent** -- manages execution phases, status callbacks, and logging
2. **Workload** -- bridges the agent to the haymaker platform (CLI, state, credentials)

This is the same pattern used by the [Azure Infrastructure Workload](https://github.com/rysweet/haymaker-azure-workloads) and the [M365 Knowledge Worker Workload](https://github.com/rysweet/haymaker-m365-workloads).

See the [Architecture](architecture) page for how these pieces connect.

## Building a custom agent

### 1. Create `agent.py`

```python
"""GoalSeekingAgent - executes goals in phases with status reporting."""

import asyncio
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any


class GoalSeekingAgent:
    def __init__(
        self,
        deployment_id: str,
        goal: str,
        on_status_change: Callable[[str, str], None] | None = None,
    ) -> None:
        self.deployment_id = deployment_id
        self.goal = goal
        self._on_status_change = on_status_change
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._logs: list[str] = []

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def cleanup(self) -> dict[str, Any]:
        await self.stop()
        return {"status": "cleaned"}

    async def get_logs(self, lines: int = 100) -> AsyncIterator[str]:
        for line in self._logs[-lines:]:
            yield line

    async def _run(self) -> None:
        try:
            self._update_status("phase1", "running")
            await self._do_work()
            self._update_status("completed", "completed")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._log(f"Failed: {exc}")
            self._update_status("failed", "failed")

    async def _do_work(self) -> None:
        """Override this with your domain logic."""
        self._log(f"Working on: {self.goal}")
        await asyncio.sleep(1)
        self._log("Done")

    def _log(self, msg: str) -> None:
        ts = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        self._logs.append(f"[{ts}] {msg}")

    def _update_status(self, phase: str, status: str) -> None:
        if self._on_status_change:
            self._on_status_change(phase, status)
```

### 2. Optionally add LLM enhancement

```python
class LLMGoalSeekingAgent(GoalSeekingAgent):
    def __init__(self, llm_client=None, **kwargs):
        super().__init__(**kwargs)
        self._llm_client = llm_client

    async def _do_work(self) -> None:
        result = await super()._do_work()
        if self._llm_client:
            evaluation = await self._llm_client.create_message_async(...)
            self._log(f"LLM evaluation: {evaluation.content}")
```

### 3. Wire into the workload

Override `deploy()` in `workload.py` to create your agent instead of using the generator:

```python
async def deploy(self, config: DeploymentConfig) -> str:
    agent = GoalSeekingAgent(
        deployment_id=deployment_id,
        goal=config.workload_config.get("goal"),
        on_status_change=lambda p, s: asyncio.ensure_future(
            self._on_agent_status(deployment_id, p, s)
        ),
    )
    self._agents[deployment_id] = agent
    await agent.start()
    return deployment_id
```

### 4. Test

```python
async def test_agent_completes():
    agent = GoalSeekingAgent(deployment_id="t1", goal="Test")
    await agent.start()
    await asyncio.sleep(2)
    result = await agent.cleanup()
    assert result["status"] == "cleaned"
```

## Reference implementations

- [Azure Infrastructure Workload](https://github.com/rysweet/haymaker-azure-workloads) -- `GoalSeekingAgent` + `LLMGoalSeekingAgent` for Azure resource management
- [M365 Knowledge Worker](https://github.com/rysweet/haymaker-m365-workloads) -- `ActivityOrchestrator` for simulating office worker patterns
