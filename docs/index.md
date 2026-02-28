---
layout: default
title: Home
nav_order: 1
---

# Haymaker Workload Starter

A starter template for building custom [Agent Haymaker](https://github.com/rysweet/agent-haymaker) workloads with goal-seeking agents.

---

## What is this?

Agent Haymaker is a platform for deploying and managing AI agent workloads. This repo is a **starter template** you clone and customize to build your own workload type.

The platform provides universal CLI commands that work with any workload:

```bash
haymaker deploy my-workload     # start
haymaker status <id>            # check state
haymaker logs <id> --follow     # stream logs
haymaker stop <id>              # pause
haymaker start <id>             # resume
haymaker cleanup <id>           # tear down
```

## Get started

{: .note }
New to Agent Haymaker? Start with the tutorial.

| Guide | Description |
|-------|-------------|
| [Tutorial: Build a Goal-Seeking Agent](tutorial) | Step-by-step guide to building a data-collector agent with optional LLM enhancement |
| [Architecture](architecture) | How workloads, agents, and the platform fit together |
| [Deploy to Azure](deploy) | OIDC-authenticated deployment to Azure Container Apps |

## Quick start

```bash
git clone https://github.com/rysweet/haymaker-workload-starter my-workload
cd my-workload
pip install -e ".[dev]"
haymaker workload list
pytest -q
```

## Links

- [Agent Haymaker Platform](https://github.com/rysweet/agent-haymaker)
- [Azure Infrastructure Workload](https://github.com/rysweet/haymaker-azure-workloads) (example)
- [M365 Knowledge Worker Workload](https://github.com/rysweet/haymaker-m365-workloads) (example)
