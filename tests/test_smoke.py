"""Smoke tests: verify the import chain amplihack -> agent-haymaker -> MyWorkload.

These tests confirm that:
1. amplihack.agent exposes the stable public API (LearningAgent, Memory, etc.)
2. amplihack.goal_agent_generator exposes the generator pipeline
3. MyWorkload imports LearningAgent from amplihack.goal_agent_generator (not a local copy)
4. The dependency chain is enforced: amplihack -> agent-haymaker -> haymaker-my-workload
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# 1. amplihack.agent public API
# ---------------------------------------------------------------------------


def test_amplihack_agent_public_api() -> None:
    """amplihack.agent must expose the stable public API."""
    from amplihack.agent import (
        AgenticLoop,
        CognitiveAdapter,
        GoalAgentGenerator,
        LearningAgent,
        Memory,
        ObjectivePlanner,
        PromptAnalyzer,
    )

    assert LearningAgent is not None
    assert CognitiveAdapter is not None
    assert AgenticLoop is not None
    assert Memory is not None
    assert GoalAgentGenerator is not None
    assert PromptAnalyzer is not None
    assert ObjectivePlanner is not None


def test_learning_agent_is_not_local_copy() -> None:
    """LearningAgent in haymaker-workload-starter must come from the amplihack package."""
    from amplihack.agent import LearningAgent
    from amplihack.agents.goal_seeking import LearningAgent as LearningAgentDirect

    # They must be the same class (no shadowing / local copy)
    assert LearningAgent is LearningAgentDirect


# ---------------------------------------------------------------------------
# 2. amplihack.goal_agent_generator pipeline
# ---------------------------------------------------------------------------


def test_goal_agent_generator_pipeline_importable() -> None:
    """amplihack.goal_agent_generator must export all pipeline components."""
    from amplihack.goal_agent_generator import (
        AgentAssembler,
        GoalAgentPackager,
        ObjectivePlanner,
        PromptAnalyzer,
        SkillSynthesizer,
    )

    assert PromptAnalyzer is not None
    assert ObjectivePlanner is not None
    assert SkillSynthesizer is not None
    assert AgentAssembler is not None
    assert GoalAgentPackager is not None


# ---------------------------------------------------------------------------
# 3. agent-haymaker WorkloadBase
# ---------------------------------------------------------------------------


def test_agent_haymaker_workload_base_importable() -> None:
    """agent-haymaker WorkloadBase must be importable (enforces dep chain)."""
    from agent_haymaker.workloads.base import WorkloadBase
    from agent_haymaker.workloads.models import (
        CleanupReport,
        DeploymentConfig,
        DeploymentState,
    )

    assert WorkloadBase is not None
    assert DeploymentConfig is not None
    assert DeploymentState is not None
    assert CleanupReport is not None


# ---------------------------------------------------------------------------
# 4. MyWorkload inherits WorkloadBase and uses amplihack generator
# ---------------------------------------------------------------------------


def test_my_workload_inherits_workload_base() -> None:
    """MyWorkload must be a concrete subclass of WorkloadBase."""
    from agent_haymaker.workloads.base import WorkloadBase
    from haymaker_my_workload import MyWorkload

    assert issubclass(MyWorkload, WorkloadBase)
    assert MyWorkload.name != "base"


def test_my_workload_uses_amplihack_generator() -> None:
    """MyWorkload._generate_agent must import from amplihack.goal_agent_generator."""
    import inspect

    from haymaker_my_workload.workload import MyWorkload

    source = inspect.getsource(MyWorkload._generate_agent)
    assert "amplihack.goal_agent_generator" in source, (
        "MyWorkload._generate_agent should import from amplihack.goal_agent_generator"
    )


# ---------------------------------------------------------------------------
# 5. amplihack.workloads.hive (HiveMindWorkload)
# ---------------------------------------------------------------------------


def test_hive_mind_workload_importable() -> None:
    """HiveMindWorkload must be importable from amplihack.workloads.hive."""
    try:
        from amplihack.workloads.hive import HiveMindWorkload
        from amplihack.workloads.hive.events import (
            HIVE_AGENT_READY,
            HIVE_FEED_COMPLETE,
            HIVE_LEARN_CONTENT,
            HIVE_QUERY,
            HIVE_QUERY_RESPONSE,
        )

        assert HiveMindWorkload.name == "hive-mind"
        assert HIVE_LEARN_CONTENT == "hive.learn_content"
        assert HIVE_FEED_COMPLETE == "hive.feed_complete"
        assert HIVE_AGENT_READY == "hive.agent_ready"
        assert HIVE_QUERY == "hive.query"
        assert HIVE_QUERY_RESPONSE == "hive.query_response"
    except ImportError as exc:
        pytest.skip(f"agent-haymaker not installed: {exc}")


def test_hive_mind_workload_inherits_workload_base() -> None:
    """HiveMindWorkload must be a subclass of WorkloadBase when agent-haymaker is present."""
    try:
        from agent_haymaker.workloads.base import WorkloadBase
        from amplihack.workloads.hive import HiveMindWorkload

        assert issubclass(HiveMindWorkload, WorkloadBase)
    except ImportError as exc:
        pytest.skip(f"agent-haymaker not installed: {exc}")
