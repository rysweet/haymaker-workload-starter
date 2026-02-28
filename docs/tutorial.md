---
layout: default
title: "Tutorial: Deploy a Goal-Seeking Agent"
nav_order: 2
description: "Create and run an autonomous AI agent from a markdown goal prompt -- tested end-to-end with real results"
---

# Tutorial: Deploy a Goal-Seeking Agent
{: .no_toc }

Create an autonomous AI agent by writing a goal in markdown. Choose from 4 SDKs. This tutorial was tested end-to-end with real deployments -- every command, log, and output shown here is from an actual run.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## What you will do

1. Write a goal prompt describing what an agent should accomplish
2. Deploy it with one command (returns in <1 second)
3. Monitor the agent as it works autonomously
4. Inspect the output the agent produced
5. Try different SDKs (Claude, Copilot, Microsoft, Mini)

<div class="concept-box" markdown="1">

#### How this works

You write a markdown file describing a goal. The workload runs the [amplihack goal agent generator](https://rysweet.github.io/amplihack/GOAL_AGENT_GENERATOR_GUIDE/) pipeline:

**PromptAnalyzer** (extracts goal, domain, constraints) --> **ObjectivePlanner** (creates phased plan) --> **SkillSynthesizer** (matches tools) --> **AgentAssembler** (builds executable bundle) --> **AutoMode** (runs the agent)

The `haymaker` CLI manages the lifecycle: deploy, monitor, stop, clean up.

</div>

## Prerequisites

```bash
# Install the platform and workload
pip install agent-haymaker   # or: pip install -e path/to/agent-haymaker
pip install amplihack        # or: pip install -e path/to/amplihack

git clone https://github.com/rysweet/haymaker-workload-starter my-workload
cd my-workload
pip install -e ".[dev]"

# Verify
haymaker workload list
# => Installed workloads:
# =>   - my-workload
```

You also need credentials for at least one SDK:

| SDK | What to set |
|-----|-------------|
| Claude | `export ANTHROPIC_API_KEY=sk-ant-...` |
| Copilot | `export GH_TOKEN=$(gh auth token)` |
| Microsoft | `export AZURE_OPENAI_ENDPOINT=https://your-instance.openai.azure.com/` and `export AZURE_OPENAI_DEPLOYMENT=gpt-5` |
| Mini | `export ANTHROPIC_API_KEY=sk-ant-...` (uses litellm) |

---

## Step 1: Write a goal

Create a markdown file in `goals/`. Here is the one we used:

**`goals/example-file-organizer.md`:**

```markdown
# File Organization Agent

## Goal
Scan the current working directory for files, classify them by type
(code, docs, config, data, other), and produce a summary report.

## Constraints
- Read-only: do not move or delete any files
- Classify by file extension
- Output report to `output/file-report.md`

## Success Criteria
- All files in the directory scanned
- Each file classified into a category
- Markdown report generated with counts per category
```

<div class="concept-box" markdown="1">

#### Goal prompt structure

| Section | Purpose | Example |
|---------|---------|---------|
| `## Goal` | What to accomplish (one sentence) | "Scan files and produce a report" |
| `## Constraints` | Boundaries to respect | "Read-only", "stdlib only" |
| `## Success Criteria` | How to know it's done | "Report at output/file-report.md" |

The domain (reporting, data-processing, security, etc.) and complexity are auto-detected.

</div>

---

## Step 2: Deploy

```bash
haymaker deploy my-workload \
  --config goal_file=goals/example-file-organizer.md \
  --yes
```

```
Deployment started: my-workload-9572f94f
```

Deploy returns in **<1 second**. The agent runs as a detached background process. What happened:

```bash
haymaker logs my-workload-9572f94f
```

```
[2026-02-28 07:29:32] Starting deployment my-workload-9572f94f
[2026-02-28 07:29:32] Using goal: goals/example-file-organizer.md
[2026-02-28 07:29:32] Generating agent from goal prompt...
[2026-02-28 07:29:32] Goal analyzed: domain=reporting, complexity=moderate
[2026-02-28 07:29:32] Execution plan: 4 phases, est. 1 hour 12 minutes
[2026-02-28 07:29:32] Matched 1 skills, 5 SDK tools
[2026-02-28 07:29:32] Agent bundle packaged
[2026-02-28 07:29:32] Executing agent (max_turns=15)
[2026-02-28 07:29:32] Agent started (pid=234959)
```

The generator created this execution plan:

| Phase | Est. Duration | What it does |
|-------|--------------|-------------|
| Planning | 15 min | Analyze goal, design approach |
| Implementation | 15 min | Write the scanner code |
| Testing | 15 min | Verify the implementation |
| Deployment | 15 min | Run scanner, generate report |

---

## Step 3: Monitor

```bash
haymaker status my-workload-9572f94f
```

```
Deployment: my-workload-9572f94f
  Workload: my-workload
  Status:   running
  Phase:    executing
  Started:  2026-02-28 07:29:32.123456+00:00
```

Watch the agent work:

```bash
haymaker logs my-workload-9572f94f
```

The logs show the agent's AutoMode turns. In our test run, the agent used 12 turns over 44 minutes and 42 seconds (85 messages total).

Check status periodically:

```bash
# Poll until done
while true; do
  haymaker status my-workload-9572f94f 2>&1 | grep "Status:"
  sleep 30
done
```

```
  Status:   running
  Status:   running
  ...
  Status:   completed
```

---

## Step 4: Inspect the results

When the agent finishes:

```bash
haymaker status my-workload-9572f94f
```

```
Deployment: my-workload-9572f94f
  Workload: my-workload
  Status:   completed
  Phase:    completed
```

The agent's final log entry:

```
Goal achieved successfully!
Exit code: 0
✓ Session transcript exported (85 messages, 44m 42s)
```

### What the agent produced

The agent **wrote code from scratch** to achieve its goal:

```
.haymaker/agents/my-workload-9572f94f/
├── main.py              # Entry point (generated by amplihack)
├── scanner.py           # Written by the agent (200 lines)
├── test_scanner.py      # Tests written by the agent
├── output/
│   └── file-report.md   # The deliverable
├── prompt.md            # Your goal
├── agent_config.json    # Execution plan
└── agent.log            # Full stdout from the agent
```

### The report

```bash
cat .haymaker/agents/my-workload-9572f94f/*/output/file-report.md
```

```markdown
# File Organization Report
Generated: 2026-02-28T16:11:22Z

## Summary

| Category | Count |
|----------|------:|
| code     |     2 |
| docs     |     8 |
| config   |     5 |
| data     |     3 |
| other    |     3 |
| **Total**|    21 |
```

### The agent's self-evaluation

The agent verified 8 criteria it derived from the goal:

| Criterion | Result |
|-----------|--------|
| 100% of files scanned | 21/21 |
| Every file categorized | All 21 assigned |
| Only 5 valid categories | code, docs, config, data, other |
| Extension-only logic | Uses `path.suffix` only |
| Read-only (no mutations) | 0 moves, 0 deletes |
| Report at `output/file-report.md` | Present |
| Valid Markdown with table | Renders correctly |
| Counts sum to total | 2+8+5+3+3 = 21 |

**All 8 criteria passed. Goal achieved.**

---

## Step 5: Clean up

```bash
haymaker cleanup my-workload-9572f94f --yes
```

```
Cleanup complete for my-workload-9572f94f
  Resources deleted: 1
```

---

## Using different SDKs

The goal agent generator supports 4 SDKs. Each uses a different AI backend:

### Claude SDK (default)

```bash
export ANTHROPIC_API_KEY=sk-ant-...

haymaker deploy my-workload \
  --config goal_file=goals/example-file-organizer.md \
  --config sdk=claude \
  --yes
```

```
Deployment started: my-workload-9572f94f
```

Logs show `[AUTO CLAUDE]` prefix. Uses Claude via the Anthropic SDK.

### GitHub Copilot SDK

```bash
export GH_TOKEN=$(gh auth token)

haymaker deploy my-workload \
  --config goal_file=goals/example-file-organizer.md \
  --config sdk=copilot \
  --yes
```

```
Deployment started: my-workload-579017ad
```

Logs show `[AUTO COPILOT]` prefix. Uses GitHub Copilot. Requires a Copilot subscription on the GitHub account.

**Auth options:** `GH_TOKEN`, `COPILOT_GITHUB_TOKEN`, or `GITHUB_TOKEN` environment variables. The SDK auto-detects the token. You can also use `gh copilot` CLI login (credentials stored in system keychain).

### Microsoft Agent Framework (Azure OpenAI)

```bash
export AZURE_OPENAI_ENDPOINT=https://your-instance.openai.azure.com/
export AZURE_OPENAI_DEPLOYMENT=gpt-5

haymaker deploy my-workload \
  --config goal_file=goals/example-file-organizer.md \
  --config sdk=microsoft \
  --yes
```

```
Deployment started: my-workload-26614651
```

Logs show `[AUTO MICROSOFT]` prefix. Uses Azure OpenAI.

**Auth:** Uses `DefaultAzureCredential` -- no API key needed in Azure. For local dev, run `az login` first. In Azure Container Apps, the system-assigned managed identity handles auth automatically.

**Setup:** You need an Azure OpenAI resource with a model deployed. Set the endpoint and deployment name in environment variables.

### Mini SDK (litellm)

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # or OPENAI_API_KEY

haymaker deploy my-workload \
  --config goal_file=goals/example-file-organizer.md \
  --config sdk=mini \
  --yes
```

```
Deployment started: my-workload-323c3fdb
```

Logs show `[AUTO MINI]` prefix. Lightweight -- uses litellm under the hood, works with any LLM provider.

---

## Deploy to Azure

The repo includes a GitHub Actions pipeline for Azure deployment. See [Deploy to Azure](deploy) for full details.

```bash
# One-time OIDC setup
./scripts/setup-oidc.sh your-org/your-repo

# Deploy
gh workflow run deploy.yml -f environment=dev -f location=eastus
```

The pipeline builds a container, deploys to Azure Container Apps (2 vCPU / 4GB), and runs an E2E lifecycle test:

```
workload registered                    ✅
generator pipeline works               ✅
deploy returned instantly              ✅
agent is running                       ✅
logs accessible                        ✅
cleanup completed                      ✅
ALL E2E TESTS PASSED                   ✅
```

---

## Configuration reference

| Option | Default | Description |
|--------|---------|-------------|
| `goal_file` | built-in default | Path to goal markdown |
| `sdk` | `claude` | `claude`, `copilot`, `microsoft`, or `mini` |
| `enable_memory` | `false` | Agent learns across runs |
| `max_turns` | `15` | Maximum agentic iterations |

## Lifecycle commands

| Command | What it does |
|---------|-------------|
| `haymaker deploy my-workload --config goal_file=goals/X.md --yes` | Generate + run agent |
| `haymaker status <id>` | Check agent progress |
| `haymaker logs <id>` | View generator + agent output |
| `haymaker stop <id> --yes` | Terminate agent process |
| `haymaker cleanup <id> --yes` | Release resources |
| `haymaker list` | Show all deployments |

---

## Writing your own goals

```bash
cat > goals/api-monitor.md << 'EOF'
# API Health Monitor

## Goal
Check health of 3 public APIs and produce a JSON status report.

## Constraints
- Use Python requests library
- 5 second timeout per API
- Complete within 10 minutes

## Success Criteria
- All 3 APIs checked
- Response times recorded
- Report at output/health-report.json
EOF

haymaker deploy my-workload --config goal_file=goals/api-monitor.md --yes
```

### Tips

| Do | Don't |
|----|-------|
| Be specific about output format | Leave output undefined |
| Set constraints | Assume unlimited resources |
| Define measurable success criteria | Use "works correctly" |
| One goal per file | Combine unrelated goals |

---

## Next steps

- [Build a custom agent](advanced) when the generator isn't enough
- [Deploy to Azure](deploy) for cloud execution
- [Architecture](architecture) to understand how it all connects
- [Goal Agent Generator Guide](https://rysweet.github.io/amplihack/GOAL_AGENT_GENERATOR_GUIDE/) for full reference
