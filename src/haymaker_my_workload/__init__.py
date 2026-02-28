"""Goal-seeking agent workload for Agent Haymaker.

Generates and runs autonomous agents from natural language goal prompts
using the amplihack goal agent generator.

Quick start:
    pip install -e ".[dev]"
    haymaker deploy my-workload --config goal_file=goals/example-data-collector.md
"""

from importlib.metadata import version

from .workload import MyWorkload

__version__ = version("haymaker-my-workload")

__all__ = ["MyWorkload"]
