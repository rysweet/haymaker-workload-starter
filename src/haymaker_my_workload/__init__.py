"""Haymaker My Workload - starter template for Agent Haymaker workloads.

This package provides a ready-to-customize workload that inherits from
WorkloadBase and implements all required lifecycle methods.

Quick start:
    pip install -e ".[dev]"
    haymaker workload list          # verify registration
    haymaker deploy my-workload     # deploy
"""

from importlib.metadata import version

from .workload import MyWorkload

__version__ = version("haymaker-my-workload")

__all__ = ["MyWorkload"]
