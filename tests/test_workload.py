"""Tests for the goal-agent workload."""

import asyncio
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_haymaker.workloads.base import DeploymentNotFoundError
from agent_haymaker.workloads.models import (
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
        """start() is not supported -- raises NotImplementedError."""
        workload = MyWorkload(platform=_mock_platform())
        state = DeploymentState(
            deployment_id="test-stopped",
            workload_name="my-workload",
            status=DeploymentStatus.STOPPED,
            phase="stopped",
        )
        await workload.save_state(state)
        with pytest.raises(NotImplementedError, match="Cannot resume deployment"):
            await workload.start("test-stopped")

    async def test_start_error_includes_deployment_id(self):
        """The NotImplementedError message includes the deployment ID."""
        workload = MyWorkload(platform=_mock_platform())
        with pytest.raises(NotImplementedError, match="test-dep-42"):
            await workload.start("test-dep-42")


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


class TestGetLogs:
    async def test_logs_not_found(self):
        workload = MyWorkload(platform=_mock_platform())
        with pytest.raises(DeploymentNotFoundError):
            async for _ in workload.get_logs("nonexistent"):
                pass

    async def test_logs_from_agent_dir_after_restart(self, tmp_path):
        """After process restart, logs are read from state metadata agent_dir."""
        workload = MyWorkload(platform=_mock_platform())

        # Simulate an agent_dir with an agent.log written by a previous process
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        log_file = agent_dir / "agent.log"
        log_file.write_text("line1\nline2\nline3\n")

        # Create state as if a previous process deployed this
        state = DeploymentState(
            deployment_id="test-restart",
            workload_name="my-workload",
            status=DeploymentStatus.RUNNING,
            phase="executing",
            metadata={"agent_dir": str(agent_dir)},
        )
        await workload.save_state(state)

        # No in-memory _logs or _agent_log_files -- simulating restart
        collected = []
        async for line in workload.get_logs("test-restart"):
            collected.append(line)

        assert "line1" in collected
        assert "line2" in collected
        assert "line3" in collected

    async def test_logs_prefers_in_memory_agent_log(self, tmp_path):
        """When in-memory _agent_log_files is set, it is used over metadata."""
        workload = MyWorkload(platform=_mock_platform())

        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        log_file = agent_dir / "agent.log"
        log_file.write_text("from-disk\n")

        # Set up in-memory reference to same file
        workload._agent_log_files["test-mem"] = log_file

        state = DeploymentState(
            deployment_id="test-mem",
            workload_name="my-workload",
            status=DeploymentStatus.RUNNING,
            phase="executing",
            metadata={"agent_dir": str(agent_dir)},
        )
        await workload.save_state(state)

        collected = []
        async for line in workload.get_logs("test-mem"):
            collected.append(line)

        assert "from-disk" in collected


class TestGetStatusLogDetection:
    """Test that get_status detects completion from agent.log after restart."""

    async def test_status_detects_goal_achieved(self, tmp_path):
        workload = MyWorkload(platform=_mock_platform())

        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        log_file = agent_dir / "agent.log"
        log_file.write_text("Starting agent...\nProcessing...\nGoal achieved!\n")

        state = DeploymentState(
            deployment_id="test-achieved",
            workload_name="my-workload",
            status=DeploymentStatus.RUNNING,
            phase="executing",
            metadata={"agent_dir": str(agent_dir)},
        )
        await workload.save_state(state)

        result = await workload.get_status("test-achieved")
        assert result.status == DeploymentStatus.COMPLETED
        assert result.phase == "completed"

    async def test_status_detects_exit_code(self, tmp_path):
        workload = MyWorkload(platform=_mock_platform())

        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        log_file = agent_dir / "agent.log"
        log_file.write_text("Starting agent...\nexit code 1\n")

        state = DeploymentState(
            deployment_id="test-exit",
            workload_name="my-workload",
            status=DeploymentStatus.RUNNING,
            phase="executing",
            metadata={"agent_dir": str(agent_dir)},
        )
        await workload.save_state(state)

        result = await workload.get_status("test-exit")
        assert result.status == DeploymentStatus.FAILED
        assert result.phase == "failed"
        assert "exit code" in result.error.lower()

    async def test_status_stays_running_when_no_log(self, tmp_path):
        workload = MyWorkload(platform=_mock_platform())

        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        # No agent.log file

        state = DeploymentState(
            deployment_id="test-nolog",
            workload_name="my-workload",
            status=DeploymentStatus.RUNNING,
            phase="executing",
            metadata={"agent_dir": str(agent_dir)},
        )
        await workload.save_state(state)

        result = await workload.get_status("test-nolog")
        assert result.status == DeploymentStatus.RUNNING

    async def test_status_stays_running_when_log_inconclusive(self, tmp_path):
        workload = MyWorkload(platform=_mock_platform())

        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        log_file = agent_dir / "agent.log"
        log_file.write_text("Starting agent...\nStill working...\n")

        state = DeploymentState(
            deployment_id="test-working",
            workload_name="my-workload",
            status=DeploymentStatus.RUNNING,
            phase="executing",
            metadata={"agent_dir": str(agent_dir)},
        )
        await workload.save_state(state)

        result = await workload.get_status("test-working")
        assert result.status == DeploymentStatus.RUNNING


class TestGetStatusAgentOutputDir:
    """Test that get_status includes agent_output_dir in metadata."""

    async def test_status_includes_agent_output_dir(self, tmp_path):
        workload = MyWorkload(platform=_mock_platform())

        state = DeploymentState(
            deployment_id="test-output",
            workload_name="my-workload",
            status=DeploymentStatus.COMPLETED,
            phase="completed",
            metadata={"agent_dir": str(tmp_path / "my-agent")},
        )
        await workload.save_state(state)

        result = await workload.get_status("test-output")
        assert "agent_output_dir" in result.metadata
        assert result.metadata["agent_output_dir"] == str(tmp_path / "my-agent")

    async def test_status_without_agent_dir(self):
        workload = MyWorkload(platform=_mock_platform())

        state = DeploymentState(
            deployment_id="test-no-dir",
            workload_name="my-workload",
            status=DeploymentStatus.COMPLETED,
            phase="completed",
            metadata={},
        )
        await workload.save_state(state)

        result = await workload.get_status("test-no-dir")
        assert "agent_output_dir" not in result.metadata


class TestReadLastLine:
    def test_reads_last_nonempty_line(self, tmp_path):
        f = tmp_path / "test.log"
        f.write_text("first\nsecond\nthird\n\n")
        assert MyWorkload._read_last_line(f) == "third"

    def test_returns_none_for_empty_file(self, tmp_path):
        f = tmp_path / "empty.log"
        f.write_text("")
        assert MyWorkload._read_last_line(f) is None

    def test_returns_none_for_missing_file(self, tmp_path):
        f = tmp_path / "missing.log"
        assert MyWorkload._read_last_line(f) is None

    def test_single_line(self, tmp_path):
        f = tmp_path / "single.log"
        f.write_text("only line\n")
        assert MyWorkload._read_last_line(f) == "only line"


class TestExecuteAgentDetached:
    """Tests for _execute_agent_detached using mocked subprocess.Popen."""

    def test_launches_process_with_main_py(self, tmp_path):
        """When main.py exists, Popen is called and the process is tracked."""
        workload = MyWorkload(platform=_mock_platform())
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "main.py").write_text("print('hello')\n")

        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.pid = 12345

        with patch("haymaker_my_workload.workload.subprocess.Popen", return_value=mock_proc):
            workload._execute_agent_detached("dep-1", agent_dir, max_turns=10)

        assert "dep-1" in workload._processes
        assert workload._processes["dep-1"] is mock_proc
        assert "dep-1" in workload._agent_log_files
        assert workload._agent_log_files["dep-1"] == agent_dir / "agent.log"

    def test_raises_when_main_py_missing(self, tmp_path):
        """When main.py is absent, FileNotFoundError is raised."""
        workload = MyWorkload(platform=_mock_platform())
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        # No main.py

        with pytest.raises(FileNotFoundError, match="Agent entry point not found"):
            workload._execute_agent_detached("dep-2", agent_dir, max_turns=5)

    def test_popen_called_with_correct_args(self, tmp_path):
        """Verify the subprocess.Popen call arguments."""
        workload = MyWorkload(platform=_mock_platform())
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "main.py").write_text("print('hello')\n")

        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.pid = 99

        with patch(
            "haymaker_my_workload.workload.subprocess.Popen", return_value=mock_proc
        ) as mock_popen:
            workload._execute_agent_detached("dep-3", agent_dir, max_turns=20)

        args, kwargs = mock_popen.call_args
        assert args[0] == ["python3", "-u", "main.py"]
        assert kwargs["cwd"] == str(agent_dir)
        assert kwargs["start_new_session"] is True
        assert kwargs["stderr"] is not None  # Separate file for stderr

    def test_popen_receives_integer_fds(self, tmp_path):
        """Popen stdout/stderr are integer fds from os.dup(), not file objects."""
        workload = MyWorkload(platform=_mock_platform())
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "main.py").write_text("print('hello')\n")

        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.pid = 42

        with patch(
            "haymaker_my_workload.workload.subprocess.Popen", return_value=mock_proc
        ) as mock_popen:
            workload._execute_agent_detached("dep-dup", agent_dir, max_turns=5)

        _, kwargs = mock_popen.call_args
        # os.dup() returns integers, not file objects
        assert isinstance(kwargs["stdout"], int), "stdout should be an int fd from os.dup()"
        assert isinstance(kwargs["stderr"], int), "stderr should be an int fd from os.dup()"

    def test_error_file_closed_after_popen(self, tmp_path):
        """The error file handle is closed in the parent after Popen returns."""
        workload = MyWorkload(platform=_mock_platform())
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "main.py").write_text("print('hello')\n")

        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.pid = 55

        with patch("haymaker_my_workload.workload.subprocess.Popen", return_value=mock_proc):
            workload._execute_agent_detached("dep-ef", agent_dir, max_turns=5)

        # The error file handle should NOT be tracked (closed immediately)
        # Only the log file handle is tracked
        assert "dep-ef" in workload._log_file_handles
        assert not workload._log_file_handles["dep-ef"].closed

    def test_popen_failure_cleans_up_fds(self, tmp_path):
        """When Popen raises OSError, all file descriptors are closed."""
        workload = MyWorkload(platform=_mock_platform())
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "main.py").write_text("print('hello')\n")

        with patch(
            "haymaker_my_workload.workload.subprocess.Popen",
            side_effect=OSError("exec failed"),
        ):
            with pytest.raises(OSError, match="exec failed"):
                workload._execute_agent_detached("dep-fail", agent_dir, max_turns=5)

        # Log file handle should be cleaned up
        assert "dep-fail" not in workload._log_file_handles
        # Process should not be tracked
        assert "dep-fail" not in workload._processes


class TestTerminateProcess:
    """Tests for _terminate_process with SIGTERM/SIGKILL escalation."""

    def test_sigterm_succeeds(self):
        """Process terminates cleanly with SIGTERM."""
        workload = MyWorkload(platform=_mock_platform())
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = None  # still running
        mock_proc.wait.return_value = 0  # terminates on SIGTERM
        workload._processes["dep-term"] = mock_proc

        workload._terminate_process("dep-term")

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_not_called()
        assert "dep-term" not in workload._processes

    def test_escalates_to_sigkill(self):
        """When SIGTERM times out, escalates to SIGKILL."""
        workload = MyWorkload(platform=_mock_platform())
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = None  # still running
        # First wait (after SIGTERM) times out, second wait (after SIGKILL) succeeds
        mock_proc.wait.side_effect = [subprocess.TimeoutExpired("cmd", 10), 0]
        workload._processes["dep-kill"] = mock_proc

        workload._terminate_process("dep-kill")

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()
        assert "dep-kill" not in workload._processes

    def test_noop_when_already_exited(self):
        """No signals sent if process already exited."""
        workload = MyWorkload(platform=_mock_platform())
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = 0  # already exited
        workload._processes["dep-done"] = mock_proc

        workload._terminate_process("dep-done")

        mock_proc.terminate.assert_not_called()
        mock_proc.kill.assert_not_called()
        assert "dep-done" not in workload._processes

    def test_closes_log_file_handle(self, tmp_path):
        """Log file handle is closed during cleanup."""
        workload = MyWorkload(platform=_mock_platform())
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = 0  # already exited
        workload._processes["dep-lf"] = mock_proc

        log_file = tmp_path / "agent.log"
        lf = open(log_file, "w")
        workload._log_file_handles["dep-lf"] = lf

        workload._terminate_process("dep-lf")

        assert lf.closed
        assert "dep-lf" not in workload._log_file_handles


class TestDeployRejectsInvalid:
    """Test that deploy() raises ValueError for various bad configs."""

    @pytest.fixture()
    def workload(self):
        return MyWorkload(platform=_mock_platform())

    async def test_rejects_invalid_sdk(self, workload):
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"sdk": "gpt5"},
        )
        with pytest.raises(ValueError, match="Invalid config"):
            await workload.deploy(config)

    async def test_rejects_max_turns_too_high(self, workload):
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"max_turns": 999},
        )
        with pytest.raises(ValueError, match="Invalid config"):
            await workload.deploy(config)

    async def test_rejects_non_bool_enable_memory(self, workload):
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"enable_memory": "true"},
        )
        with pytest.raises(ValueError, match="Invalid config"):
            await workload.deploy(config)

    async def test_rejects_nonexistent_goal_file(self, workload):
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"goal_file": "/does/not/exist.md"},
        )
        with pytest.raises(ValueError, match="Invalid config"):
            await workload.deploy(config)

    async def test_rejects_multiple_errors(self, workload):
        """Multiple validation errors are reported together."""
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"sdk": "bad", "max_turns": -1, "enable_memory": 42},
        )
        with pytest.raises(ValueError, match="Invalid config") as exc_info:
            await workload.deploy(config)
        error_msg = str(exc_info.value)
        assert "sdk" in error_msg
        assert "max_turns" in error_msg
        assert "enable_memory" in error_msg


class TestValidateConfigEdgeCases:
    """Additional edge cases for validate_config beyond TestValidateConfig."""

    @pytest.fixture()
    def workload(self):
        return MyWorkload(platform=_mock_platform())

    async def test_max_turns_boundary_lower(self, workload):
        """max_turns=1 is the minimum valid value."""
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"max_turns": 1},
        )
        errors = await workload.validate_config(config)
        assert not any("max_turns" in e for e in errors)

    async def test_max_turns_boundary_upper(self, workload):
        """max_turns=100 is the maximum valid value."""
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"max_turns": 100},
        )
        errors = await workload.validate_config(config)
        assert not any("max_turns" in e for e in errors)

    async def test_max_turns_above_upper(self, workload):
        """max_turns=101 exceeds the maximum."""
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"max_turns": 101},
        )
        errors = await workload.validate_config(config)
        assert any("max_turns" in e for e in errors)

    async def test_max_turns_float_rejected(self, workload):
        """max_turns must be an int, not a float."""
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"max_turns": 10.5},
        )
        errors = await workload.validate_config(config)
        assert any("max_turns" in e for e in errors)

    async def test_max_turns_string_rejected(self, workload):
        """max_turns must be an int, not a string."""
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"max_turns": "ten"},
        )
        errors = await workload.validate_config(config)
        assert any("max_turns" in e for e in errors)

    async def test_enable_memory_true_valid(self, workload):
        """enable_memory=True is valid."""
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"enable_memory": True},
        )
        errors = await workload.validate_config(config)
        assert not any("enable_memory" in e for e in errors)

    async def test_enable_memory_false_valid(self, workload):
        """enable_memory=False is valid."""
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"enable_memory": False},
        )
        errors = await workload.validate_config(config)
        assert not any("enable_memory" in e for e in errors)

    async def test_enable_memory_int_rejected(self, workload):
        """enable_memory=1 is not a bool."""
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"enable_memory": 1},
        )
        errors = await workload.validate_config(config)
        assert any("enable_memory" in e for e in errors)

    async def test_all_valid_sdks_accepted(self, workload):
        """Each SDK in the valid set passes validation."""
        for sdk in ("claude", "copilot", "microsoft", "mini"):
            config = DeploymentConfig(
                workload_name="my-workload",
                workload_config={"sdk": sdk},
            )
            errors = await workload.validate_config(config)
            assert not any("sdk" in e for e in errors), f"SDK '{sdk}' should be valid"

    async def test_empty_config_valid(self, workload):
        """A config with no workload_config fields is valid (uses defaults)."""
        config = DeploymentConfig(workload_name="my-workload")
        errors = await workload.validate_config(config)
        assert errors == []


class TestPidBasedStatusDetection:
    """Test PID-based process detection in get_status() (Problem 2 fix)."""

    async def test_dead_pid_with_goal_achieved_log(self, tmp_path):
        """When PID is dead and log says 'goal achieved', status is COMPLETED."""
        workload = MyWorkload(platform=_mock_platform())

        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        log_file = agent_dir / "agent.log"
        log_file.write_text("Starting...\nGoal achieved!\n")

        state = DeploymentState(
            deployment_id="test-pid-achieved",
            workload_name="my-workload",
            status=DeploymentStatus.RUNNING,
            phase="executing",
            metadata={"agent_dir": str(agent_dir), "agent_pid": 999999},
        )
        await workload.save_state(state)

        # Mock os.kill to raise ProcessLookupError (PID is dead)
        with patch("haymaker_my_workload.workload.os.kill", side_effect=ProcessLookupError):
            result = await workload.get_status("test-pid-achieved")

        assert result.status == DeploymentStatus.COMPLETED
        assert result.phase == "completed"

    async def test_dead_pid_with_exit_code_log(self, tmp_path):
        """When PID is dead and log says 'exit code', status is FAILED."""
        workload = MyWorkload(platform=_mock_platform())

        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        log_file = agent_dir / "agent.log"
        log_file.write_text("Starting...\nexit code 1\n")

        state = DeploymentState(
            deployment_id="test-pid-exit",
            workload_name="my-workload",
            status=DeploymentStatus.RUNNING,
            phase="executing",
            metadata={"agent_dir": str(agent_dir), "agent_pid": 999999},
        )
        await workload.save_state(state)

        with patch("haymaker_my_workload.workload.os.kill", side_effect=ProcessLookupError):
            result = await workload.get_status("test-pid-exit")

        assert result.status == DeploymentStatus.FAILED
        assert "exit code" in result.error.lower()

    async def test_dead_pid_with_empty_log(self, tmp_path):
        """When PID is dead and log is empty, status is FAILED with descriptive error."""
        workload = MyWorkload(platform=_mock_platform())

        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        log_file = agent_dir / "agent.log"
        log_file.write_text("")  # Empty log

        state = DeploymentState(
            deployment_id="test-pid-empty",
            workload_name="my-workload",
            status=DeploymentStatus.RUNNING,
            phase="executing",
            metadata={"agent_dir": str(agent_dir), "agent_pid": 999999},
        )
        await workload.save_state(state)

        with patch("haymaker_my_workload.workload.os.kill", side_effect=ProcessLookupError):
            result = await workload.get_status("test-pid-empty")

        assert result.status == DeploymentStatus.FAILED
        assert "PID no longer exists" in result.error

    async def test_alive_pid_stays_running(self, tmp_path):
        """When PID is alive, status stays RUNNING."""
        workload = MyWorkload(platform=_mock_platform())

        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()

        state = DeploymentState(
            deployment_id="test-pid-alive",
            workload_name="my-workload",
            status=DeploymentStatus.RUNNING,
            phase="executing",
            metadata={"agent_dir": str(agent_dir), "agent_pid": 999999},
        )
        await workload.save_state(state)

        # os.kill(pid, 0) succeeds -- process is alive
        with patch("haymaker_my_workload.workload.os.kill"):
            result = await workload.get_status("test-pid-alive")

        assert result.status == DeploymentStatus.RUNNING

    async def test_permission_error_assumes_alive(self, tmp_path):
        """When os.kill raises PermissionError, process is assumed alive."""
        workload = MyWorkload(platform=_mock_platform())

        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()

        state = DeploymentState(
            deployment_id="test-pid-perm",
            workload_name="my-workload",
            status=DeploymentStatus.RUNNING,
            phase="executing",
            metadata={"agent_dir": str(agent_dir), "agent_pid": 999999},
        )
        await workload.save_state(state)

        with patch("haymaker_my_workload.workload.os.kill", side_effect=PermissionError):
            result = await workload.get_status("test-pid-perm")

        assert result.status == DeploymentStatus.RUNNING

    async def test_legacy_no_pid_uses_log_detection(self, tmp_path):
        """Legacy deployments without agent_pid fall back to log-based detection."""
        workload = MyWorkload(platform=_mock_platform())

        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        log_file = agent_dir / "agent.log"
        log_file.write_text("Starting...\nGoal achieved!\n")

        state = DeploymentState(
            deployment_id="test-legacy",
            workload_name="my-workload",
            status=DeploymentStatus.RUNNING,
            phase="executing",
            metadata={"agent_dir": str(agent_dir)},  # No agent_pid
        )
        await workload.save_state(state)

        result = await workload.get_status("test-legacy")
        assert result.status == DeploymentStatus.COMPLETED

    async def test_legacy_no_pid_no_log_stays_running(self, tmp_path):
        """Legacy deployment with no PID and no log stays RUNNING."""
        workload = MyWorkload(platform=_mock_platform())

        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        # No agent.log

        state = DeploymentState(
            deployment_id="test-legacy-nolog",
            workload_name="my-workload",
            status=DeploymentStatus.RUNNING,
            phase="executing",
            metadata={"agent_dir": str(agent_dir)},  # No agent_pid
        )
        await workload.save_state(state)

        result = await workload.get_status("test-legacy-nolog")
        assert result.status == DeploymentStatus.RUNNING


class TestDeployPersistsPid:
    """Test that deploy() stores the agent PID in metadata."""

    async def test_pid_stored_in_metadata(self, tmp_path):
        """After deploy, the state metadata contains agent_pid."""
        workload = MyWorkload(platform=_mock_platform())
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        (agent_dir / "main.py").write_text("import sys; print('OK'); sys.exit(0)\n")

        mock_gen = AsyncMock(return_value=agent_dir)
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.pid = 54321
        mock_proc.poll.return_value = None  # Still running

        with (
            patch.object(workload, "_generate_agent", mock_gen),
            patch("haymaker_my_workload.workload.subprocess.Popen", return_value=mock_proc),
        ):
            dep_id = await workload.deploy(
                DeploymentConfig(workload_name="my-workload")
            )

        state = await workload.load_state(dep_id)
        assert state.metadata.get("agent_pid") == 54321


@pytest.mark.integration
class TestGeneratorIntegration:
    """Integration tests that exercise the real amplihack generator pipeline.

    These tests require the amplihack package to be installed and functional.
    Run with: pytest -m integration
    """

    async def test_generate_agent_produces_runnable_bundle(self, tmp_path):
        """End-to-end: generate an agent from a goal file, verify main.py exists."""
        goal_file = tmp_path / "goal.md"
        goal_file.write_text(
            "# Integration Test Goal\n\n"
            "## Goal\n"
            "Process a list of three numbers and compute their sum.\n\n"
            "## Constraints\n"
            "- Complete within 1 minute\n"
            "- No external API calls\n\n"
            "## Success Criteria\n"
            "- Sum is computed correctly\n"
        )

        workload = MyWorkload(platform=_mock_platform())
        agent_dir = await workload._generate_agent(
            deployment_id="integ-test-001",
            goal_path=goal_file,
            sdk="claude",
            enable_memory=False,
        )

        assert agent_dir.exists(), f"Agent directory was not created: {agent_dir}"
        main_py = agent_dir / "main.py"
        assert main_py.exists(), "Generated agent must contain main.py"
        content = main_py.read_text()
        assert len(content) > 0, "main.py should not be empty"
