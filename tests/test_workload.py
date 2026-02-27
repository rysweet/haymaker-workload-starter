"""Tests for MyWorkload lifecycle methods."""

from unittest.mock import AsyncMock, MagicMock

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
    """Create a mock platform with state storage."""
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


class TestMyWorkloadInit:
    """Test workload initialization and registration."""

    def test_name(self):
        assert MyWorkload.name == "my-workload"

    def test_init_without_platform(self):
        wl = MyWorkload()
        assert wl._platform is None

    def test_init_with_platform(self):
        platform = _mock_platform()
        wl = MyWorkload(platform=platform)
        assert wl._platform is platform


class TestDeploy:
    """Test deploy lifecycle method."""

    @pytest.fixture()
    def workload(self):
        return MyWorkload(platform=_mock_platform())

    async def test_deploy_returns_id(self, workload):
        config = DeploymentConfig(workload_name="my-workload")
        deployment_id = await workload.deploy(config)
        assert deployment_id.startswith("my-workload-")
        assert len(deployment_id) == len("my-workload-") + 8

    async def test_deploy_persists_state(self, workload):
        config = DeploymentConfig(workload_name="my-workload")
        deployment_id = await workload.deploy(config)

        state = await workload.get_status(deployment_id)
        assert state.status == DeploymentStatus.RUNNING
        assert state.phase == "running"
        assert state.started_at is not None

    async def test_deploy_with_custom_config(self, workload):
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"item_count": 50, "mode": "verbose"},
        )
        deployment_id = await workload.deploy(config)
        state = await workload.get_status(deployment_id)
        assert state.config["item_count"] == 50
        assert state.metadata["item_count"] == 50

    async def test_deploy_creates_logs(self, workload):
        config = DeploymentConfig(workload_name="my-workload")
        deployment_id = await workload.deploy(config)
        assert deployment_id in workload._logs
        assert len(workload._logs[deployment_id]) >= 2


class TestGetStatus:
    """Test get_status lifecycle method."""

    @pytest.fixture()
    def workload(self):
        return MyWorkload(platform=_mock_platform())

    async def test_get_status_returns_state(self, workload):
        config = DeploymentConfig(workload_name="my-workload")
        dep_id = await workload.deploy(config)
        state = await workload.get_status(dep_id)
        assert isinstance(state, DeploymentState)
        assert state.deployment_id == dep_id

    async def test_get_status_not_found(self, workload):
        with pytest.raises(DeploymentNotFoundError):
            await workload.get_status("nonexistent-id")


class TestStop:
    """Test stop lifecycle method."""

    @pytest.fixture()
    async def running_deployment(self):
        workload = MyWorkload(platform=_mock_platform())
        config = DeploymentConfig(workload_name="my-workload")
        dep_id = await workload.deploy(config)
        return workload, dep_id

    async def test_stop_sets_stopped(self, running_deployment):
        workload, dep_id = running_deployment
        result = await workload.stop(dep_id)
        assert result is True

        state = await workload.get_status(dep_id)
        assert state.status == DeploymentStatus.STOPPED
        assert state.phase == "stopped"
        assert state.stopped_at is not None

    async def test_stop_idempotent(self, running_deployment):
        workload, dep_id = running_deployment
        await workload.stop(dep_id)
        result = await workload.stop(dep_id)
        assert result is True


class TestCleanup:
    """Test cleanup lifecycle method."""

    @pytest.fixture()
    async def running_deployment(self):
        workload = MyWorkload(platform=_mock_platform())
        config = DeploymentConfig(workload_name="my-workload")
        dep_id = await workload.deploy(config)
        return workload, dep_id

    async def test_cleanup_returns_report(self, running_deployment):
        workload, dep_id = running_deployment
        report = await workload.cleanup(dep_id)
        assert isinstance(report, CleanupReport)
        assert report.deployment_id == dep_id
        assert report.resources_deleted >= 1
        assert report.resources_failed == 0
        assert report.duration_seconds >= 0

    async def test_cleanup_sets_completed(self, running_deployment):
        workload, dep_id = running_deployment
        await workload.cleanup(dep_id)
        state = await workload.get_status(dep_id)
        assert state.status == DeploymentStatus.COMPLETED
        assert state.phase == "cleaned_up"

    async def test_cleanup_removes_logs(self, running_deployment):
        workload, dep_id = running_deployment
        assert dep_id in workload._logs
        await workload.cleanup(dep_id)
        assert dep_id not in workload._logs


class TestGetLogs:
    """Test get_logs lifecycle method."""

    @pytest.fixture()
    async def running_deployment(self):
        workload = MyWorkload(platform=_mock_platform())
        config = DeploymentConfig(workload_name="my-workload")
        dep_id = await workload.deploy(config)
        return workload, dep_id

    async def test_get_logs_returns_lines(self, running_deployment):
        workload, dep_id = running_deployment
        lines = []
        async for line in workload.get_logs(dep_id):
            lines.append(line)
        assert len(lines) >= 2
        assert any("starting" in line for line in lines)

    async def test_get_logs_not_found(self):
        workload = MyWorkload(platform=_mock_platform())
        with pytest.raises(DeploymentNotFoundError):
            async for _ in workload.get_logs("nonexistent"):
                pass

    async def test_get_logs_respects_lines_limit(self, running_deployment):
        workload, dep_id = running_deployment
        # Add extra logs
        for i in range(10):
            workload._append_log(dep_id, f"extra log {i}")

        lines = []
        async for line in workload.get_logs(dep_id, lines=3):
            lines.append(line)
        assert len(lines) == 3


class TestStart:
    """Test start (resume) method."""

    @pytest.fixture()
    async def stopped_deployment(self):
        workload = MyWorkload(platform=_mock_platform())
        config = DeploymentConfig(workload_name="my-workload")
        dep_id = await workload.deploy(config)
        await workload.stop(dep_id)
        return workload, dep_id

    async def test_start_resumes_stopped(self, stopped_deployment):
        workload, dep_id = stopped_deployment
        result = await workload.start(dep_id)
        assert result is True

        state = await workload.get_status(dep_id)
        assert state.status == DeploymentStatus.RUNNING

    async def test_start_fails_if_not_stopped(self):
        workload = MyWorkload(platform=_mock_platform())
        config = DeploymentConfig(workload_name="my-workload")
        dep_id = await workload.deploy(config)
        result = await workload.start(dep_id)
        assert result is False


class TestValidateConfig:
    """Test config validation."""

    @pytest.fixture()
    def workload(self):
        return MyWorkload(platform=_mock_platform())

    async def test_valid_config(self, workload):
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"item_count": 10, "interval_seconds": 60, "mode": "normal"},
        )
        errors = await workload.validate_config(config)
        assert errors == []

    async def test_default_config_valid(self, workload):
        config = DeploymentConfig(workload_name="my-workload")
        errors = await workload.validate_config(config)
        assert errors == []

    async def test_invalid_item_count(self, workload):
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"item_count": -1},
        )
        errors = await workload.validate_config(config)
        assert any("item_count" in e for e in errors)

    async def test_invalid_interval(self, workload):
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"interval_seconds": 1},
        )
        errors = await workload.validate_config(config)
        assert any("interval_seconds" in e for e in errors)

    async def test_invalid_mode(self, workload):
        config = DeploymentConfig(
            workload_name="my-workload",
            workload_config={"mode": "turbo"},
        )
        errors = await workload.validate_config(config)
        assert any("mode" in e for e in errors)


class TestListDeployments:
    """Test list_deployments using platform storage."""

    async def test_list_empty(self):
        workload = MyWorkload(platform=_mock_platform())
        result = await workload.list_deployments()
        assert result == []

    async def test_list_after_deploy(self):
        workload = MyWorkload(platform=_mock_platform())
        config = DeploymentConfig(workload_name="my-workload")
        await workload.deploy(config)
        result = await workload.list_deployments()
        assert len(result) == 1

    async def test_list_without_platform(self):
        workload = MyWorkload()
        result = await workload.list_deployments()
        assert result == []
