"""Goal Agent Workload - generates and runs agents from natural language goals.

Users customize this workload by writing goal prompts in markdown, not Python.
On deploy, the workload uses the amplihack goal agent generator to:
  1. Analyze the goal prompt
  2. Create a phased execution plan
  3. Match skills and SDK tools
  4. Assemble and package a runnable agent
  5. Execute it via AutoMode

Configuration:
    haymaker deploy my-workload --config goal_file=goals/my-goal.md
    haymaker deploy my-workload --config goal_file=goals/my-goal.md sdk=claude
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

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
from agent_haymaker.workloads.platform import Platform

logger = logging.getLogger(__name__)

_TERMINAL_STATES = frozenset({DeploymentStatus.COMPLETED, DeploymentStatus.FAILED})
_MAX_LOG_LINES = 10_000
_DEFAULT_GOAL = """\
# Default Goal

## Goal
Process sample data items and produce a summary report.

## Constraints
- Complete within 5 minutes
- No external API calls required

## Success Criteria
- All items processed
- Summary report generated
"""


class MyWorkload(WorkloadBase):
    """Workload that generates and runs goal-seeking agents from prompts.

    Customize by writing goal markdown files in a goals/ directory.
    Each goal file describes what the agent should accomplish, its
    constraints, and success criteria. The amplihack goal agent
    generator handles the rest.

    Example:
        haymaker deploy my-workload --config goal_file=goals/collect-data.md
        haymaker deploy my-workload --config goal_file=goals/collect-data.md sdk=claude
    """

    name = "my-workload"

    def __init__(self, platform: Platform | None = None) -> None:
        super().__init__(platform=platform)
        self._logs: dict[str, list[str]] = {}
        self._processes: dict[str, object] = {}  # subprocess.Popen instances
        self._agent_log_files: dict[str, Path] = {}  # deployment_id -> log file

    async def deploy(self, config: DeploymentConfig) -> str:
        """Generate an agent from a goal prompt and execute it."""
        deployment_id = f"{self.name}-{uuid.uuid4().hex[:8]}"
        goal_file = config.workload_config.get("goal_file")
        sdk = config.workload_config.get("sdk", "claude")
        enable_memory = config.workload_config.get("enable_memory", False)
        max_turns = config.workload_config.get("max_turns", 15)

        self._logs[deployment_id] = []
        self._append_log(deployment_id, f"Starting deployment {deployment_id}")

        # Resolve or create goal file
        if goal_file:
            goal_path = Path(goal_file)
            if not goal_path.is_absolute():
                goal_path = Path.cwd() / goal_path
            if not goal_path.exists():
                raise ValueError(f"Goal file not found: {goal_path}")
            self._append_log(deployment_id, f"Using goal: {goal_path}")
        else:
            # Use default goal if none specified
            goal_path = Path(f"/tmp/haymaker-{deployment_id}-goal.md")
            goal_path.write_text(_DEFAULT_GOAL)
            self._append_log(deployment_id, "Using default goal (no goal_file specified)")

        # Generate the agent
        self._append_log(deployment_id, "Generating agent from goal prompt...")
        agent_dir = await self._generate_agent(
            deployment_id=deployment_id,
            goal_path=goal_path,
            sdk=sdk,
            enable_memory=enable_memory,
        )
        self._append_log(deployment_id, f"Agent generated in {agent_dir}")

        # Read goal definition for metadata
        goal_text = goal_path.read_text()
        goal_summary = goal_text.split("\n")[0].strip("# ").strip() or "Goal agent"

        # Persist state
        state = DeploymentState(
            deployment_id=deployment_id,
            workload_name=self.name,
            status=DeploymentStatus.RUNNING,
            phase="executing",
            started_at=datetime.now(tz=UTC),
            config=config.workload_config,
            metadata={
                "goal_summary": goal_summary,
                "sdk": sdk,
                "agent_dir": str(agent_dir),
                "max_turns": max_turns,
            },
        )
        await self.save_state(state)

        # Execute agent in background
        # Launch agent as detached subprocess (returns immediately)
        self._execute_agent_detached(deployment_id, agent_dir, max_turns)

        return deployment_id

    async def get_status(self, deployment_id: str) -> DeploymentState:
        state = await self.load_state(deployment_id)
        if state is None:
            raise DeploymentNotFoundError(f"Deployment {deployment_id} not found")

        # Check if detached agent process has finished
        proc = self._processes.get(deployment_id)
        if proc and state.status == DeploymentStatus.RUNNING:
            rc = proc.poll()
            if rc is not None:
                self._processes.pop(deployment_id, None)
                if rc == 0:
                    state.status = DeploymentStatus.COMPLETED
                    state.phase = "completed"
                else:
                    state.status = DeploymentStatus.FAILED
                    state.phase = "failed"
                    state.error = f"Agent exited with code {rc}"
                state.completed_at = datetime.now(tz=UTC)
                await self.save_state(state)

        return state

    async def stop(self, deployment_id: str) -> bool:
        state = await self.get_status(deployment_id)
        if state.status == DeploymentStatus.STOPPED:
            return True
        if state.status not in (DeploymentStatus.RUNNING, DeploymentStatus.PENDING):
            return False

        # Kill the agent process if running
        proc = self._processes.pop(deployment_id, None)
        if proc and proc.poll() is None:
            proc.terminate()
            self._append_log(deployment_id, "Agent process terminated")

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
                details=[f"Already in {state.status} state"],
            )

        start_time = time.monotonic()

        # Kill process if still running
        proc = self._processes.pop(deployment_id, None)
        if proc and proc.poll() is None:
            proc.terminate()

        self._logs.pop(deployment_id, None)

        state.status = DeploymentStatus.COMPLETED
        state.phase = "cleaned_up"
        state.completed_at = datetime.now(tz=UTC)
        await self.save_state(state)

        return CleanupReport(
            deployment_id=deployment_id,
            resources_deleted=1,
            details=[f"Cleaned up deployment {deployment_id}"],
            duration_seconds=time.monotonic() - start_time,
        )

    async def get_logs(
        self, deployment_id: str, follow: bool = False, lines: int = 100
    ) -> AsyncIterator[str]:
        await self.get_status(deployment_id)

        # Yield workload logs (generator pipeline output)
        for line in self._logs.get(deployment_id, [])[-lines:]:
            yield line

        # Also yield from agent log file if it exists
        log_file = self._agent_log_files.get(deployment_id)
        if log_file and log_file.exists():
            with open(log_file) as f:
                file_lines = f.readlines()
            for line in file_lines[-lines:]:
                yield line.rstrip()

    async def validate_config(self, config: DeploymentConfig) -> list[str]:
        errors = []
        wc = config.workload_config
        goal_file = wc.get("goal_file")
        if goal_file:
            p = Path(goal_file)
            if not p.is_absolute():
                p = Path.cwd() / p
            if not p.exists():
                errors.append(f"goal_file not found: {p}")
        sdk = wc.get("sdk", "claude")
        if sdk not in ("claude", "copilot", "microsoft", "mini"):
            errors.append(f"sdk must be one of: claude, copilot, microsoft, mini (got '{sdk}')")
        return errors

    # -- Internal methods --

    async def _generate_agent(
        self,
        deployment_id: str,
        goal_path: Path,
        sdk: str,
        enable_memory: bool,
    ) -> Path:
        """Use the amplihack goal agent generator to create an agent bundle."""
        from amplihack.goal_agent_generator import (
            AgentAssembler,
            GoalAgentPackager,
            ObjectivePlanner,
            PromptAnalyzer,
            SkillSynthesizer,
        )

        analyzer = PromptAnalyzer()
        goal_def = analyzer.analyze(goal_path)
        self._append_log(
            deployment_id,
            f"Goal analyzed: domain={goal_def.domain}, complexity={goal_def.complexity}",
        )

        planner = ObjectivePlanner()
        plan = planner.generate_plan(goal_def)
        self._append_log(
            deployment_id,
            f"Execution plan: {len(plan.phases)} phases, est. {plan.total_estimated_duration}",
        )

        synthesizer = SkillSynthesizer()
        synthesis = synthesizer.synthesize_with_sdk_tools(plan, sdk=sdk)
        skills = synthesis.get("skills", [])
        sdk_tools = synthesis.get("sdk_tools", [])
        self._append_log(
            deployment_id,
            f"Matched {len(skills)} skills, {len(sdk_tools)} SDK tools",
        )

        assembler = AgentAssembler()
        bundle = assembler.assemble(
            goal_def,
            plan,
            skills,
            bundle_name=deployment_id,
            enable_memory=enable_memory,
            sdk=sdk,
            sdk_tools=sdk_tools,
        )

        output_dir = Path(f".haymaker/agents/{deployment_id}")
        packager = GoalAgentPackager(output_dir=output_dir)
        agent_dir = packager.package(bundle)
        self._append_log(deployment_id, "Agent bundle packaged")

        return agent_dir

    def _execute_agent_detached(self, deployment_id: str, agent_dir: Path, max_turns: int) -> None:
        """Launch the agent as a detached subprocess (fire-and-forget).

        Uses subprocess.Popen instead of asyncio so the agent runs
        independently of the event loop. Logs go to a file that
        get_logs() reads. A wrapper script updates deployment state
        when the agent finishes.
        """
        import subprocess

        main_py = agent_dir / "main.py"
        if not main_py.exists():
            self._append_log(deployment_id, f"ERROR: {main_py} not found")
            return

        log_file = agent_dir / "agent.log"
        self._append_log(deployment_id, f"Executing agent (max_turns={max_turns})")
        self._append_log(deployment_id, f"Agent log: {log_file}")

        # Store log file path for get_logs() to read
        self._agent_log_files[deployment_id] = log_file

        # Launch detached -- don't wait for completion
        with open(log_file, "w") as lf:
            proc = subprocess.Popen(
                ["python3", str(main_py)],
                stdout=lf,
                stderr=subprocess.STDOUT,
                cwd=str(agent_dir),
                start_new_session=True,  # Fully detach from parent
            )
        self._processes[deployment_id] = proc
        self._append_log(deployment_id, f"Agent started (pid={proc.pid})")

    def _append_log(self, deployment_id: str, message: str) -> None:
        ts = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {message}"
        buf = self._logs.setdefault(deployment_id, [])
        buf.append(line)
        if len(buf) > _MAX_LOG_LINES:
            del buf[: len(buf) - _MAX_LOG_LINES]
        self.log(message)
