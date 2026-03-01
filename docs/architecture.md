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
│  deploy / status / logs / stop / cleanup         │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│              WorkloadBase (ABC)                   │
│  deploy() / get_status() / stop() / cleanup()    │
│  get_logs() / validate_config()                  │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│         Goal-Agent Runtime (MyWorkload)          │
│  Reads goal prompt → runs amplihack pipeline     │
│  → launches agent as detached subprocess         │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│       amplihack Goal Agent Generator             │
│  PromptAnalyzer → ObjectivePlanner →             │
│  SkillSynthesizer → AgentAssembler →             │
│  GoalAgentPackager                               │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│            AutoMode (agent execution)            │
│  Runs main.py with chosen SDK                    │
│  (claude / copilot / microsoft / mini)           │
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

### Goal agent generator (amplihack)

The workload uses the amplihack pipeline to create agents from goal prompts:
1. **PromptAnalyzer** -- extracts goal, domain, constraints, success criteria
2. **ObjectivePlanner** -- creates a 3-5 phase execution plan
3. **SkillSynthesizer** -- matches skills and SDK tools
4. **AgentAssembler** -- combines into an executable bundle
5. **GoalAgentPackager** -- writes to disk (main.py, config, skills)

The generated agent runs via **AutoMode** with the chosen SDK (claude, copilot, microsoft, mini).

## Data flow

```
User runs: haymaker deploy my-workload --config goal_file=goals/my-goal.md
    │
    ▼
CLI parses config into DeploymentConfig
    │
    ▼
Registry finds MyWorkload via entry point
    │
    ▼
deploy() reads goal prompt, runs amplihack generator pipeline
    │
    ▼
Generator creates agent directory (main.py, config.json, skills/)
    │
    ▼
Workload launches main.py as detached subprocess (PID stored in state)
    │
    ▼
Agent runs autonomously, logs to agent.log (via os.dup'd fd)
    │
    ▼
User queries: haymaker status <id>
    │
    ▼
Status detection (priority order):
  1. In-memory process handle (proc.poll()) — same CLI session
  2. PID liveness (os.kill(pid, 0)) — after CLI restart
  3. agent.log parsing ("goal achieved" / "exit code") — fallback
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
    metadata: dict              # runtime info (agent_dir, agent_pid, sdk, ...)
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
