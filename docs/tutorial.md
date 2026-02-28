---
layout: default
title: "Tutorial: Build a Goal-Seeking Agent Workload"
nav_order: 2
description: "Create autonomous agents from natural language goals -- no Python required"
---

# Tutorial: Build a Goal-Seeking Agent Workload
{: .no_toc }

Learn how to create autonomous AI agents by writing goal descriptions in markdown. The workload generates, deploys, and manages agents automatically using the [amplihack goal agent generator](https://rysweet.github.io/amplihack/GOAL_AGENT_GENERATOR_GUIDE/).
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## What you will learn

- **How the goal-agent runtime works**: Write a goal in markdown, deploy it, the workload does the rest
- **How to write effective goal prompts**: Structure, constraints, and success criteria that produce good agents
- **How the generator pipeline works**: The 4-stage process that turns prose into running code
- **How to customize for your domain**: SDK selection, memory, and advanced configuration
- **How to deploy to Azure**: OIDC-authenticated pipeline with E2E verification

<div class="concept-box" markdown="1">

#### The key insight

Traditional workloads require you to write Python code for every new agent type. This workload flips that: **you write a markdown file describing what the agent should do, and the workload generates and runs the agent automatically**.

This means a team lead can create new agent types by writing goal prompts -- no coding, no PRs, no deploys. Just:

```bash
haymaker deploy my-workload --config goal_file=goals/my-new-agent.md
```

</div>

## Prerequisites

- Python 3.11+
- Git
- [agent-haymaker](https://github.com/rysweet/agent-haymaker) installed
- [amplihack](https://github.com/rysweet/amplihack) installed (`pip install amplihack`)

---

## Part 1: Set up and run

```bash
git clone https://github.com/rysweet/haymaker-workload-starter my-workload
cd my-workload
pip install -e ".[dev]"
```

The repo comes with example goal prompts in `goals/`. Try deploying one:

```bash
haymaker deploy my-workload --config goal_file=goals/example-data-collector.md --yes
```

Check what happened:

```bash
haymaker status <deployment-id>
haymaker logs <deployment-id>
```

The workload:
1. Read your goal prompt
2. Analyzed it (domain: data-processing, complexity: simple)
3. Generated a phased execution plan
4. Matched skills and SDK tools
5. Packaged a runnable agent
6. Executed it as a subprocess

{: .note }
If no `goal_file` is specified, the workload uses a built-in default goal. Try `haymaker deploy my-workload --yes` to see it.

---

## Part 2: Writing goal prompts

<div class="concept-box" markdown="1">

#### What makes a good goal prompt?

The generator extracts four things from your markdown:
1. **Goal** -- What the agent should accomplish (one clear sentence)
2. **Domain** -- Auto-classified (data-processing, security-analysis, automation, testing, deployment, monitoring, integration, reporting)
3. **Constraints** -- Boundaries the agent must respect
4. **Success criteria** -- How to know the goal is achieved

The more specific your prompt, the better the generated agent.

</div>

### Goal prompt structure

```markdown
# Agent Name

## Goal
One clear sentence describing what the agent should accomplish.

## Constraints
- Time limit, resource limits, API restrictions
- What the agent should NOT do
- Required tools or libraries

## Success Criteria
- Measurable outcome 1
- Measurable outcome 2
- File or artifact that should exist when done
```

### Example: Data Collection

```markdown
# Pricing Data Collector

## Goal
Collect product pricing data from 3 public APIs, normalize the schema,
and produce a consolidated JSON report.

## Constraints
- Rate limit: max 10 requests per second per API
- Use only Python standard library + requests
- Complete within 15 minutes

## Success Criteria
- Data collected from all 3 APIs
- All records normalized to {id, name, price, currency, source}
- Report written to output/pricing-report.json
- No unhandled errors in logs
```

### Example: Security Scan

```markdown
# Repository Security Scanner

## Goal
Scan the current repository for common security issues: hardcoded
secrets, vulnerable dependencies, and insecure configurations.

## Constraints
- Read-only: do not modify any files
- Check .env files, config files, and source code
- Use grep-based pattern matching (no external tools)

## Success Criteria
- All files scanned
- Findings categorized by severity (critical, high, medium, low)
- Report written to output/security-report.md
- Zero false positives for test fixtures
```

### Tips for effective prompts

| Do | Don't |
|----|-------|
| Be specific about output format | Leave output undefined |
| Set time/resource constraints | Assume unlimited resources |
| Define measurable success criteria | Use vague "works correctly" |
| Specify what NOT to do (constraints) | Hope the agent figures it out |
| One goal per prompt | Combine unrelated objectives |

---

## Part 3: How the generator pipeline works

<div class="concept-box" markdown="1">

#### The 4-stage pipeline

When you run `haymaker deploy my-workload --config goal_file=goals/my-goal.md`, the workload calls four amplihack components in sequence:

```
goal.md → PromptAnalyzer → ObjectivePlanner → SkillSynthesizer → AgentAssembler
              ↓                    ↓                  ↓                  ↓
         GoalDefinition     ExecutionPlan      matched skills     agent directory
         (goal, domain,     (3-5 phases,       + SDK tools       (main.py, config,
          constraints,       dependencies,                         skills/, README)
          criteria)          durations)
```

Each stage is deterministic and inspectable. The output of each stage is logged so you can see exactly what the generator decided.

</div>

### Stage 1: Prompt Analysis

`PromptAnalyzer` extracts structured data from your markdown:

| Field | Extracted from | Example |
|-------|---------------|---------|
| `goal` | `## Goal` section | "Collect pricing data..." |
| `domain` | Auto-classified from keywords | `data-processing` |
| `constraints` | `## Constraints` bullet points | `["Rate limit: 10 req/s", ...]` |
| `success_criteria` | `## Success Criteria` bullets | `["Data from 3 APIs", ...]` |
| `complexity` | Estimated from goal scope | `moderate` |

### Stage 2: Objective Planning

`ObjectivePlanner` creates a phased execution plan. The phases depend on the domain:

| Domain | Typical phases |
|--------|---------------|
| data-processing | Collection → Transformation → Analysis → Reporting |
| security-analysis | Reconnaissance → Detection → Assessment → Reporting |
| automation | Setup → Design → Execution → Validation |
| testing | Planning → Implementation → Execution → Analysis |
| deployment | Pre-deploy → Deploy → Verify → Post-deploy |

### Stage 3: Skill Matching

`SkillSynthesizer` finds skills that match the plan's requirements and injects SDK-native tools based on your chosen SDK.

### Stage 4: Assembly & Packaging

`AgentAssembler` produces a self-contained directory:

```
.haymaker/agents/<deployment-id>/
├── main.py          # Entry point (AutoMode execution loop)
├── prompt.md        # Your goal
├── config.json      # Plan, SDK config, max_turns
├── skills/          # Matched skills
└── README.md        # Generated usage docs
```

The workload then runs `python3 main.py` as a subprocess, streaming its stdout to the haymaker logs.

---

## Part 4: Configuration and SDK selection

### Config options

| Option | Default | Description |
|--------|---------|-------------|
| `goal_file` | built-in default | Path to your goal markdown |
| `sdk` | `claude` | Execution SDK (see below) |
| `enable_memory` | `false` | Enable agent learning across runs |
| `max_turns` | `15` | Maximum execution iterations |

### SDK comparison

| SDK | Best for | Auth needed |
|-----|----------|-------------|
| `claude` | General tasks, tool use, reasoning | `ANTHROPIC_API_KEY` |
| `copilot` | Code generation, git, development | GitHub Copilot |
| `microsoft` | Azure workloads, structured workflows | Azure AI credentials |
| `mini` | Lightweight tasks, minimal deps | API key for any LLM |

### Examples

```bash
# Default (Claude SDK, 15 turns)
haymaker deploy my-workload --config goal_file=goals/my-goal.md --yes

# Use Microsoft SDK with memory
haymaker deploy my-workload \
  --config goal_file=goals/azure-task.md \
  --config sdk=microsoft \
  --config enable_memory=true \
  --yes

# Quick task with mini SDK
haymaker deploy my-workload \
  --config goal_file=goals/simple-task.md \
  --config sdk=mini \
  --config max_turns=5 \
  --yes
```

---

## Part 5: Monitoring and lifecycle

The haymaker CLI manages the full lifecycle:

```bash
# Deploy
haymaker deploy my-workload --config goal_file=goals/my-goal.md --yes

# Watch progress
haymaker status <id>          # phase, status, metadata
haymaker logs <id>            # generator logs + agent output
haymaker logs <id> --follow   # stream in real time

# Control
haymaker stop <id> --yes      # kill the agent process
haymaker start <id>           # update state (agent doesn't resume)
haymaker cleanup <id> --yes   # mark complete, release resources
```

What each command does:

| Command | Workload action |
|---------|----------------|
| `deploy` | Generate agent from goal → execute as subprocess |
| `status` | Read persisted state (phase, goal, SDK, agent dir) |
| `logs` | Stream generator logs + agent stdout |
| `stop` | Terminate the agent subprocess |
| `cleanup` | Mark deployment complete |

---

## Part 6: Customizing the workload

### Rename it

Follow the rename guide in the [main README](https://github.com/rysweet/haymaker-workload-starter#customization-guide) to change the workload name, package name, and entry point.

### Add domain-specific goals

Create new `.md` files in `goals/`:

```bash
goals/
├── example-data-collector.md    # Comes with the starter
├── example-file-organizer.md    # Comes with the starter
├── my-api-monitor.md            # Your custom goal
├── my-report-generator.md       # Your custom goal
└── my-security-scanner.md       # Your custom goal
```

Each file is a standalone agent definition. No code changes needed.

### Override the workload for advanced use

For full control, edit `src/haymaker_my_workload/workload.py`:
- Override `_generate_agent()` to customize the pipeline
- Override `_execute_agent()` to change how agents run
- Add pre/post processing around the generator stages

---

## Part 7: Deploy to Azure

See the [Deploy to Azure](deploy) guide. The short version:

```bash
# One-time setup
./scripts/setup-oidc.sh your-org/my-workload

# Deploy
gh workflow run deploy.yml -f environment=dev
```

The Azure pipeline builds a container with the workload + amplihack installed, deploys to Container Apps, and runs a full E2E lifecycle test.

---

## Part 8: Testing

Run the test suite:

```bash
pytest -q
```

The tests mock the amplihack generator pipeline so they run without API keys. To test with the real generator:

```bash
# Requires ANTHROPIC_API_KEY or equivalent
haymaker deploy my-workload --config goal_file=goals/example-data-collector.md --yes
haymaker logs <id>
```

---

## Next steps

- **Write goal prompts** for your domain and deploy them
- **Try different SDKs** to see which works best for your tasks
- **Enable memory** for agents that should learn across runs
- **Study the generator**: [Goal Agent Generator Guide](https://rysweet.github.io/amplihack/GOAL_AGENT_GENERATOR_GUIDE/)
- **Study production workloads**:
  - [Azure Infrastructure](https://github.com/rysweet/haymaker-azure-workloads) -- hand-built agents for Azure resource management
  - [M365 Knowledge Worker](https://github.com/rysweet/haymaker-m365-workloads) -- activity simulation with LLM content generation
