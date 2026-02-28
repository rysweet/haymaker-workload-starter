"""Tests for the goal-agent workload."""

import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_haymaker.workloads.base import DeploymentNotFoundError
from agent_haymaker.workloads.models import (
    CleanupReport,
    DeploymentConfig,
    DeploymentState,
    DeploymentStatus,
)

from haymaker_my_workload import MyWorkload


def _mock_platform():
    """Create a mock platform with in-memory state storage."""
    platform = MagicMock()
    storage: dict[str, DeploymentState] = {}

    async def save(state: DeploymentState):
        storage[state.deployment_id] = state

    async def load(deployment_id: str):
        return storage.get(deployment_id)

    async def list_deps(workload_name: str):
        return [s for s in storage.values() if s.workload_name == workload_name]

    platform.save_deployment_state = AsyncMock(side_effect=save)
    platform.load_deployment_state = AsyncMock(side_effect=load)
    platform.list_deployments = AsyncMock(side_effect=list_deps)
    platform.get_credential = AsyncMock(return_value=None)
    platform.log = MagicMock()
    platform._storage = storage
    return platform


def _mock_generator(agent_dir: Path):
    """Mock the amplihack generator pipeline to return a fake agent dir."""
    import uuid

    from amplihack.goal_agent_generator.models import (
        ExecutionPlan,
        GoalAgentBundle,
        GoalDefinition,
        PlanPhase,
    )

    goal_def = GoalDefinition(
        raw_prompt="test goal",
        goal="Test goal",
        domain="testing",
        constraints=[],
        success_criteria=["done"],
        context={},
        complexity="simple",
    )
    plan = ExecutionPlan(
        goal_id=uuid.uuid4(),
        phases=[
            PlanPhase(
                name="test",
                description="test phase",
                required_capabilities=["execution"],
                estimated_duration="1 min",
                dependencies=[],
                success_indicators=["done"],
            )
        ],
        total_estimated_duration="1 min",
        required_skills=[],
        parallel_opportunities=[],
        risk_factors=[],
    )

    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "main.py").write_text(
        "import sys; print('Agent executed successfully'); sys.exit(0)\n"
    )

    mock_analyzer = MagicMock()
    mock_analyzer.analyze.return_value = goal_def
    mock_planner = MagicMock()
    mock_planner.generate_plan.return_value = plan
    mock_synthesizer = MagicMock()
    mock_synthesizer.synthesize_with_sdk_tools.return_value = {
        "skills": [],
        "sdk_tools": [],
    }
    mock_assembler = MagicMock()
    mock_assembler.assemble.return_value = GoalAgentBundle(
        id=uuid.uuid4(),
        name="test",
        version="1.0.0",
        goal_definition=goal_def,
        execution_plan=plan,
        skills=[],
        auto_mode_config={},
        metadata={},
        sdk_tools=[],
        sub_agent_configs=[],
        status="ready",
    )
    mock_packager = MagicMock()
    mock_packager.package.return_value = agent_dir

    return {
        "PromptAnalyzer": lambda: mock_analyzer,
        "ObjectivePlanner": lambda: mock_planner,
        "SkillSynthesizer": lambda: mock_synthesizer,
        "AgentAssembler": lambda: mock_assembler,
        "GoalAgentPackager": lambda output_dir=None: mock_packager,
    }


class TestWorkloadInit:
    def test_name(self):
        assert MyWorkload.name == "my-workload"

    def test_init_without_platform(self):
        wl = MyWorkload()
        assert wl._platform is None


class TestDeploy:
    @pytest.fixture()
    def setup(self, tmp_path):
        workload = MyWorkload(platform=_mock_platform())
        agent_dir = tmp_path / "agent"
        mocks = _mock_generator(agent_dir)
        return workload, mocks

    async def test_deploy_with_default_goal(self, setup):
        workload, mocks = setup
        agent_dir = list(mocks.values())[-1]().package.return_value
        mock_gen = AsyncMock(return_value=agent_dir)
        with patch.object(workload, "_generate_agent", mock_gen):
            config = DeploymentConfig(workload_name="my-workload")
            dep_id = await workload.deploy(config)
            assert dep_id.startswith("my-workload-")
            await asyncio.sleep(0.5)
            state = await workload.get_status(dep_id)
            assert state.status in (DeploymentStatus.RUNNING, DeploymentStatus.COMPLETED)

    async def test_deploy_with_goal_file(self, setup, tmp_path):
        workload, mocks = setup
        goal_file = tmp_path / "goal.md"
        goal_file.write_text("# Test\n## Goal\nDo something\n## Success Criteria\n- Done")

        agent_dir = tmp_path / "agent"
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "main.py").write_text("import sys; print('OK'); sys.exit(0)\n")
        mock_gen = AsyncMock(return_value=agent_dir)
        with patch.object(workload, "_generate_agent", mock_gen):
            config = DeploymentConfig(
                workload_name="my-workload",
                workload_config={"goal_file": str(goal_file)},
            )
            dep_id = await workload.deploy(config)
            assert dep_id.startswith("my-workload-")

    async def test_deploy_rejects_invalid_config(self, setup):
        workload, _ = setup
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"sdk": "invalid"},
        )
        with pytest.raises(ValueError, match="Invalid config"):
            await workload.deploy(config)


class TestGetStatus:
    async def test_not_found(self):
        workload = MyWorkload(platform=_mock_platform())
        with pytest.raises(DeploymentNotFoundError):
            await workload.get_status("nonexistent")


class TestStop:
    async def test_stop_not_found(self):
        workload = MyWorkload(platform=_mock_platform())
        with pytest.raises(DeploymentNotFoundError):
            await workload.stop("nonexistent")


class TestStart:
    async def test_start_raises_not_implemented(self):
        """start() raises NotImplementedError -- stopped agents must be redeployed."""
        workload = MyWorkload(platform=_mock_platform())
        state = DeploymentState(
            deployment_id="test-stopped",
            workload_name="my-workload",
            status=DeploymentStatus.STOPPED,
            phase="stopped",
        )
        await workload.save_state(state)
        with pytest.raises(NotImplementedError, match="Cannot resume"):
            await workload.start("test-stopped")


class TestCleanup:
    async def test_cleanup_not_found(self):
        workload = MyWorkload(platform=_mock_platform())
        with pytest.raises(DeploymentNotFoundError):
            await workload.cleanup("nonexistent")


class TestValidateConfig:
    @pytest.fixture()
    def workload(self):
        return MyWorkload(platform=_mock_platform())

    async def test_valid_config(self, workload):
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"sdk": "claude"},
        )
        errors = await workload.validate_config(config)
        assert errors == []

    async def test_invalid_sdk(self, workload):
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"sdk": "invalid"},
        )
        errors = await workload.validate_config(config)
        assert any("sdk" in e for e in errors)

    async def test_missing_goal_file(self, workload):
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"goal_file": "/nonexistent/goal.md"},
        )
        errors = await workload.validate_config(config)
        assert any("not found" in e for e in errors)

    async def test_valid_goal_file(self, workload, tmp_path):
        goal_file = tmp_path / "goal.md"
        goal_file.write_text("# Test goal")
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"goal_file": str(goal_file)},
        )
        errors = await workload.validate_config(config)
        assert errors == []

    async def test_invalid_max_turns(self, workload):
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"max_turns": 0},
        )
        errors = await workload.validate_config(config)
        assert any("max_turns" in e for e in errors)

    async def test_invalid_enable_memory(self, workload):
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"enable_memory": "yes"},
        )
        errors = await workload.validate_config(config)
        assert any("enable_memory" in e for e in errors)


class TestResolveGoalPath:
    def test_rejects_path_traversal(self):
        with pytest.raises(ValueError, match="must not contain"):
            MyWorkload._resolve_goal_path("../../../etc/passwd")

    def test_rejects_non_markdown(self, tmp_path):
        py_file = tmp_path / "goal.py"
        py_file.write_text("not a goal")
        with pytest.raises(ValueError, match="must be a markdown"):
            MyWorkload._resolve_goal_path(str(py_file))

    def test_accepts_md(self, tmp_path):
        md_file = tmp_path / "goal.md"
        md_file.write_text("# Goal")
        result = MyWorkload._resolve_goal_path(str(md_file))
        assert result == md_file.resolve()

    def test_accepts_txt(self, tmp_path):
        txt_file = tmp_path / "goal.txt"
        txt_file.write_text("# Goal")
        result = MyWorkload._resolve_goal_path(str(txt_file))
        assert result == txt_file.resolve()

    def test_rejects_nonexistent(self):
        with pytest.raises(ValueError, match="not found"):
            MyWorkload._resolve_goal_path("/tmp/does-not-exist-abc123.md")


class TestExecuteAgentDetached:
    def test_execute_with_main_py(self, tmp_path):
        """_execute_agent_detached launches a subprocess when main.py exists."""
        workload = MyWorkload(platform=_mock_platform())
        workload._logs["dep-1"] = []

        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        main_py = agent_dir / "main.py"
        main_py.write_text("print('hello')\n")

        mock_proc = MagicMock()
        mock_proc.pid = 12345

        with patch("subprocess.Popen", return_value=mock_proc) as mock_popen:
            workload._execute_agent_detached("dep-1", agent_dir, max_turns=10)

        mock_popen.assert_called_once()
        call_args = mock_popen.call_args
        assert call_args[0][0] == ["python3", str(main_py)]
        assert call_args[1]["cwd"] == str(agent_dir)
        assert call_args[1]["start_new_session"] is True
        assert workload._processes["dep-1"] is mock_proc
        assert workload._agent_log_files["dep-1"] == agent_dir / "agent.log"
        assert any("pid=12345" in line for line in workload._logs["dep-1"])

        # Clean up the opened log file handle
        lf = workload._log_file_handles.get("dep-1")
        if lf and not lf.closed:
            lf.close()

    def test_execute_without_main_py(self, tmp_path):
        """_execute_agent_detached raises FileNotFoundError when main.py is missing."""
        workload = MyWorkload(platform=_mock_platform())
        workload._logs["dep-2"] = []

        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()

        with pytest.raises(FileNotFoundError, match="Agent entry point not found"):
            workload._execute_agent_detached("dep-2", agent_dir, max_turns=10)


class TestTerminateProcess:
    def test_terminate_running_process(self):
        """_terminate_process sends SIGTERM to a running process."""
        workload = MyWorkload(platform=_mock_platform())

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still running
        mock_proc.wait.return_value = 0  # terminates cleanly
        workload._processes["dep-1"] = mock_proc

        workload._terminate_process("dep-1")

        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once_with(timeout=10)
        assert "dep-1" not in workload._processes

    def test_terminate_escalates_to_kill(self):
        """_terminate_process escalates to SIGKILL when SIGTERM times out."""
        workload = MyWorkload(platform=_mock_platform())

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="python3", timeout=10),
            0,  # kill succeeds
        ]
        workload._processes["dep-1"] = mock_proc

        workload._terminate_process("dep-1")

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()
        assert "dep-1" not in workload._processes

    def test_terminate_already_exited(self):
        """_terminate_process is a no-op for an already-exited process."""
        workload = MyWorkload(platform=_mock_platform())

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # already exited
        workload._processes["dep-1"] = mock_proc

        workload._terminate_process("dep-1")

        mock_proc.terminate.assert_not_called()
        assert "dep-1" not in workload._processes

    def test_terminate_no_process(self):
        """_terminate_process is safe to call with no tracked process."""
        workload = MyWorkload(platform=_mock_platform())
        workload._terminate_process("nonexistent")  # should not raise


class TestCleanupProcess:
    def test_cleanup_closes_file_handle(self):
        """_cleanup_process closes the log file handle."""
        workload = MyWorkload(platform=_mock_platform())

        mock_handle = MagicMock()
        mock_handle.closed = False
        workload._log_file_handles["dep-1"] = mock_handle
        workload._processes["dep-1"] = MagicMock()

        workload._cleanup_process("dep-1")

        mock_handle.close.assert_called_once()
        assert "dep-1" not in workload._processes
        assert "dep-1" not in workload._log_file_handles

    def test_cleanup_skips_already_closed_handle(self):
        """_cleanup_process does not call close() on an already-closed handle."""
        workload = MyWorkload(platform=_mock_platform())

        mock_handle = MagicMock()
        mock_handle.closed = True
        workload._log_file_handles["dep-1"] = mock_handle

        workload._cleanup_process("dep-1")

        mock_handle.close.assert_not_called()

    def test_cleanup_no_handle(self):
        """_cleanup_process is safe when there is no log file handle."""
        workload = MyWorkload(platform=_mock_platform())
        workload._processes["dep-1"] = MagicMock()

        workload._cleanup_process("dep-1")

        assert "dep-1" not in workload._processes


class TestGetLogs:
    async def test_logs_not_found(self):
        workload = MyWorkload(platform=_mock_platform())
        with pytest.raises(DeploymentNotFoundError):
            async for _ in workload.get_logs("nonexistent"):
                pass

    async def test_logs_from_agent_log_file(self, tmp_path):
        """get_logs() yields lines from the agent.log file on disk."""
        workload = MyWorkload(platform=_mock_platform())

        # Create a deployment in state
        state = DeploymentState(
            deployment_id="dep-log",
            workload_name="my-workload",
            status=DeploymentStatus.COMPLETED,
            phase="completed",
        )
        await workload.save_state(state)

        # Create a log file with content
        log_file = tmp_path / "agent.log"
        log_file.write_text("line 1\nline 2\nline 3\n")
        workload._agent_log_files["dep-log"] = log_file

        lines = []
        async for line in workload.get_logs("dep-log"):
            lines.append(line)

        assert "line 1" in lines
        assert "line 2" in lines
        assert "line 3" in lines

    async def test_logs_from_workload_buffer(self):
        """get_logs() yields lines from the in-memory log buffer."""
        workload = MyWorkload(platform=_mock_platform())

        state = DeploymentState(
            deployment_id="dep-buf",
            workload_name="my-workload",
            status=DeploymentStatus.RUNNING,
            phase="executing",
        )
        await workload.save_state(state)

        workload._logs["dep-buf"] = ["[ts] msg1", "[ts] msg2"]

        lines = []
        async for line in workload.get_logs("dep-buf"):
            lines.append(line)

        assert "[ts] msg1" in lines
        assert "[ts] msg2" in lines


class TestDeployWithMemory:
    async def test_deploy_with_enable_memory_true(self, tmp_path):
        """deploy() passes enable_memory=True through to _generate_agent."""
        workload = MyWorkload(platform=_mock_platform())
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir(parents=True)
        (agent_dir / "main.py").write_text("import sys; sys.exit(0)\n")

        mock_gen = AsyncMock(return_value=agent_dir)
        with patch.object(workload, "_generate_agent", mock_gen):
            config = DeploymentConfig(
                workload_name="my-workload",
                workload_config={"enable_memory": True},
            )
            dep_id = await workload.deploy(config)

        # Verify _generate_agent was called with enable_memory=True
        mock_gen.assert_awaited_once()
        call_kwargs = mock_gen.call_args[1] if mock_gen.call_args[1] else {}
        # Could be positional or keyword -- check the call
        call_args = mock_gen.call_args
        # _generate_agent(deployment_id, goal_path, sdk, enable_memory)
        # enable_memory is the 4th positional arg (index 3) or kwarg
        if call_kwargs.get("enable_memory") is not None:
            assert call_kwargs["enable_memory"] is True
        else:
            # positional: (deployment_id, goal_path, sdk, enable_memory)
            assert call_args[0][3] is True

        assert dep_id.startswith("my-workload-")

        # Clean up any subprocess artifacts
        workload._terminate_process(dep_id)


class TestCleanupDeployment:
    async def test_cleanup_removes_temp_goal_file(self, tmp_path):
        """cleanup() deletes the temporary goal file created during deploy."""
        workload = MyWorkload(platform=_mock_platform())

        # Create a running deployment in state
        state = DeploymentState(
            deployment_id="dep-clean",
            workload_name="my-workload",
            status=DeploymentStatus.RUNNING,
            phase="executing",
        )
        await workload.save_state(state)

        # Create a temp goal file and register it
        temp_goal = tmp_path / "temp-goal.md"
        temp_goal.write_text("# Temp Goal\n")
        workload._temp_goal_files["dep-clean"] = temp_goal
        workload._logs["dep-clean"] = ["[ts] starting"]

        report = await workload.cleanup("dep-clean")

        assert isinstance(report, CleanupReport)
        assert not temp_goal.exists(), "Temp goal file should be deleted"
        assert "dep-clean" not in workload._temp_goal_files

    async def test_cleanup_already_completed(self):
        """cleanup() returns early for already-completed deployments."""
        workload = MyWorkload(platform=_mock_platform())

        state = DeploymentState(
            deployment_id="dep-done",
            workload_name="my-workload",
            status=DeploymentStatus.COMPLETED,
            phase="completed",
        )
        await workload.save_state(state)

        report = await workload.cleanup("dep-done")
        assert any("Already in" in d for d in report.details)


class TestGetStatusProcessCompletion:
    async def test_status_detects_process_exit_success(self):
        """get_status() detects when the subprocess exits with code 0."""
        workload = MyWorkload(platform=_mock_platform())

        state = DeploymentState(
            deployment_id="dep-proc",
            workload_name="my-workload",
            status=DeploymentStatus.RUNNING,
            phase="executing",
        )
        await workload.save_state(state)

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # exited successfully
        workload._processes["dep-proc"] = mock_proc

        result = await workload.get_status("dep-proc")

        assert result.status == DeploymentStatus.COMPLETED
        assert result.phase == "completed"
        assert result.completed_at is not None

    async def test_status_detects_process_exit_failure(self):
        """get_status() detects when the subprocess exits with non-zero code."""
        workload = MyWorkload(platform=_mock_platform())

        state = DeploymentState(
            deployment_id="dep-fail",
            workload_name="my-workload",
            status=DeploymentStatus.RUNNING,
            phase="executing",
        )
        await workload.save_state(state)

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # exited with error
        workload._processes["dep-fail"] = mock_proc

        result = await workload.get_status("dep-fail")

        assert result.status == DeploymentStatus.FAILED
        assert result.phase == "failed"
        assert "exited with code 1" in result.error


class TestStopDeployment:
    async def test_stop_running_deployment(self, tmp_path):
        """stop() terminates the process and marks state as stopped."""
        workload = MyWorkload(platform=_mock_platform())

        state = DeploymentState(
            deployment_id="dep-stop",
            workload_name="my-workload",
            status=DeploymentStatus.RUNNING,
            phase="executing",
        )
        await workload.save_state(state)

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still running
        mock_proc.wait.return_value = 0
        workload._processes["dep-stop"] = mock_proc

        result = await workload.stop("dep-stop")

        assert result is True
        updated = await workload.load_state("dep-stop")
        assert updated.status == DeploymentStatus.STOPPED

    async def test_stop_completed_deployment(self):
        """stop() returns False for completed deployments."""
        workload = MyWorkload(platform=_mock_platform())

        state = DeploymentState(
            deployment_id="dep-done",
            workload_name="my-workload",
            status=DeploymentStatus.COMPLETED,
            phase="completed",
        )
        await workload.save_state(state)

        result = await workload.stop("dep-done")
        assert result is False


class TestKillAllProcesses:
    def test_kill_all_terminates_tracked_processes(self):
        """_kill_all_processes terminates all tracked agent processes."""
        workload = MyWorkload(platform=_mock_platform())

        proc1 = MagicMock()
        proc1.poll.return_value = None
        proc1.wait.return_value = 0
        proc2 = MagicMock()
        proc2.poll.return_value = None
        proc2.wait.return_value = 0

        workload._processes["a"] = proc1
        workload._processes["b"] = proc2

        workload._kill_all_processes()

        proc1.terminate.assert_called_once()
        proc2.terminate.assert_called_once()


class TestAppendLog:
    def test_append_log_truncates_at_max(self):
        """_append_log truncates the buffer when it exceeds _MAX_LOG_LINES."""
        workload = MyWorkload(platform=_mock_platform())
        workload._logs["dep-1"] = [f"line-{i}" for i in range(10_001)]

        workload._append_log("dep-1", "overflow line")

        assert len(workload._logs["dep-1"]) == 10_000


@pytest.mark.integration
class TestGeneratorIntegration:
    """Integration test that calls the real amplihack generator pipeline.

    Requires amplihack to be installed. Skip with: pytest -m 'not integration'
    """

    async def test_generate_agent_produces_expected_files(self, tmp_path):
        """Call _generate_agent with a real goal and verify output files."""
        workload = MyWorkload(platform=_mock_platform())
        workload._logs["integ-1"] = []

        # Create a minimal goal file
        goal_file = tmp_path / "goal.md"
        goal_file.write_text(
            "# Test Goal\n\n"
            "## Goal\n"
            "Print hello world and exit.\n\n"
            "## Constraints\n"
            "- No external dependencies\n"
            "- Complete in under 1 minute\n\n"
            "## Success Criteria\n"
            "- Printed hello world\n"
        )

        agent_dir = await workload._generate_agent(
            deployment_id="integ-1",
            goal_path=goal_file,
            sdk="claude",
            enable_memory=False,
        )

        assert agent_dir.exists(), f"Agent dir should exist: {agent_dir}"
        assert (agent_dir / "main.py").exists(), "main.py should be generated"
        assert (agent_dir / "agent_config.json").exists(), "agent_config.json should be generated"
        assert (agent_dir / "prompt.md").exists(), "prompt.md should be generated"
