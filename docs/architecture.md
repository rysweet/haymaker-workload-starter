---
layout: default
title: Architecture
nav_order: 3
---

# Architecture
{: .no_toc }

How workloads, agents, and the platform fit together.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## Overview

```
┌─────────────────────────────────────────────────┐
│                  haymaker CLI                     │
│  deploy / status / logs / stop / start / cleanup │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│              WorkloadBase (ABC)                   │
│  deploy() / get_status() / stop() / cleanup()    │
│  get_logs() / start() / validate_config()        │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│           Your Workload (concrete)               │
│  Creates and manages GoalSeekingAgent instances  │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│            GoalSeekingAgent                       │
│  start() / stop() / cleanup() / get_logs()       │
│  Phases: initialize → execute → report           │
│                                                   │
│  ┌─────────────────────────────────────────────┐ │
│  │ Optional: LLMGoalSeekingAgent               │ │
│  │  Error recovery, goal evaluation, adaptive  │ │
│  └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

## Key components

### Platform (`agent-haymaker`)

The platform provides:
- **CLI** (`haymaker` command) with universal lifecycle commands
- **WorkloadBase** abstract class that all workloads inherit from
- **Registry** that discovers installed workloads via Python entry points
- **FilePlatform** for local state persistence (`~/.haymaker/state/`)
- **LLM abstraction** supporting Anthropic, Azure OpenAI, and Azure AI Foundry

### Workload (your code)

A workload is a Python package that:
1. Inherits from `WorkloadBase`
2. Implements 5 required methods (deploy, get_status, stop, cleanup, get_logs)
3. Registers via entry point in `pyproject.toml`
4. Declares a manifest in `workload.yaml`

### Goal-seeking agent (your code)

The agent is a class that:
1. Receives a goal and configuration
2. Executes in phases (initialize, execute, report)
3. Reports status via callbacks
4. Optionally uses LLM for adaptive behavior

## Data flow

```
User runs: haymaker deploy data-collector --config item_count=50
    │
    ▼
CLI parses config into DeploymentConfig
    │
    ▼
Registry finds DataCollectorWorkload via entry point
    │
    ▼
WorkloadBase.deploy() called
    │
    ▼
Your workload creates GoalSeekingAgent
    │
    ▼
Agent starts async task → phases run → status callbacks → state persisted
    │
    ▼
User queries: haymaker status <id> → reads persisted state
```

## State model

```python
class DeploymentState:
    deployment_id: str          # "data-collector-a1b2c3d4"
    workload_name: str          # "data-collector"
    status: DeploymentStatus    # RUNNING, STOPPED, COMPLETED, FAILED
    phase: str                  # "initializing", "collecting", "completed"
    started_at: datetime
    config: dict                # workload-specific settings
    metadata: dict              # runtime metrics
```

Statuses: `PENDING` → `RUNNING` ⇄ `STOPPED` → `CLEANING_UP` → `COMPLETED` / `FAILED`

## LLM integration

The LLM layer is optional and pluggable:

```python
from agent_haymaker.llm import LLMConfig, create_llm_client

config = LLMConfig.from_env()  # reads LLM_PROVIDER, API keys from env
client = create_llm_client(config)  # returns Anthropic, AzureOpenAI, or AzureAIFoundry provider

response = await client.create_message_async(
    messages=[LLMMessage(role="user", content="What should I do next?")],
    system="You are a helpful assistant.",
    max_tokens=200,
)
```

Supported providers:
- **Anthropic** (`ANTHROPIC_API_KEY`)
- **Azure OpenAI** (`AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`)
- **Azure AI Foundry** (`AZURE_AI_ENDPOINT`)
