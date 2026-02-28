"""Tests for the goal-agent workload."""

import asyncio
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
    async def test_start_returns_false(self):
        """start() is not supported -- always returns False."""
        workload = MyWorkload(platform=_mock_platform())
        # Manually create a stopped deployment in state
        state = DeploymentState(
            deployment_id="test-stopped",
            workload_name="my-workload",
            status=DeploymentStatus.STOPPED,
            phase="stopped",
        )
        await workload.save_state(state)
        result = await workload.start("test-stopped")
        assert result is False


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
