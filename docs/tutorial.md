---
layout: default
title: "Tutorial: Deploy a Goal-Seeking Agent (Local)"
nav_order: 2
description: "Create and run an autonomous AI agent from a markdown goal prompt"
---

# Tutorial: Deploy a Goal-Seeking Agent
{: .no_toc }

Create an autonomous AI agent by writing a goal in markdown. No Python required. This tutorial walks through a real deployment that was tested end-to-end, with actual logs and output.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## What you will do

1. Write a goal prompt describing what the agent should accomplish
2. Deploy it with one command
3. Watch the agent work autonomously
4. Inspect the results

The entire process from goal to working output took **one command** and the agent completed its goal in **12 turns over ~45 minutes**, scanning 21 files and producing a categorized report.

<div class="concept-box" markdown="1">

#### How this works

You write a markdown file describing a goal. The workload passes it through the [amplihack goal agent generator](https://rysweet.github.io/amplihack/GOAL_AGENT_GENERATOR_GUIDE/) which:

1. **Analyzes** the goal (extracts domain, constraints, success criteria)
2. **Plans** a phased execution (3-5 phases with dependencies)
3. **Matches** skills and SDK tools to the plan
4. **Assembles** a runnable agent with `main.py`, config, and skills
5. **Executes** it via AutoMode (an agentic loop using your chosen SDK)

The platform handles lifecycle management -- you deploy, monitor, stop, and clean up through `haymaker` CLI commands.

</div>

## Prerequisites

- Python 3.11+
- [agent-haymaker](https://github.com/rysweet/agent-haymaker) installed
- [amplihack](https://github.com/rysweet/amplihack) installed
- An API key for your chosen SDK (e.g. `ANTHROPIC_API_KEY` for Claude)

## Step 1: Set up

```bash
git clone https://github.com/rysweet/haymaker-workload-starter my-workload
cd my-workload
pip install -e ".[dev]"
```

Verify the workload is registered:

```bash
haymaker workload list
```

```
Installed workloads:
  - my-workload
```

---

## Step 2: Write a goal prompt

The starter repo comes with example goals in `goals/`. Here is the one we used for our real test run:

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

#### What makes a good goal prompt

The generator extracts four things from your markdown:

| Section | What it does | Example |
|---------|-------------|---------|
| `## Goal` | One clear sentence describing the objective | "Scan files and produce a report" |
| `## Constraints` | Boundaries the agent must respect | "Read-only", "stdlib only" |
| `## Success Criteria` | Measurable outcomes that define "done" | "Report written to output/" |

The **domain** and **complexity** are auto-classified from the goal text. Our file organizer was classified as `reporting` domain, `moderate` complexity.

</div>

---

## Step 3: Deploy

```bash
export ANTHROPIC_API_KEY=sk-ant-...   # your API key

haymaker deploy my-workload \
  --config goal_file=goals/example-file-organizer.md \
  --yes
```

Output:

```
Deployment started: my-workload-9572f94f
```

What happened behind the scenes (from the logs):

```
[2026-02-28 07:29:32] Starting deployment my-workload-9572f94f
[2026-02-28 07:29:32] Using goal: goals/example-file-organizer.md
[2026-02-28 07:29:32] Generating agent from goal prompt...
[2026-02-28 07:29:32] Goal analyzed: domain=reporting, complexity=moderate
[2026-02-28 07:29:32] Execution plan: 4 phases, est. 1 hour 12 minutes
[2026-02-28 07:29:32] Matched 1 skills, 5 SDK tools
[2026-02-28 07:29:32] Agent bundle packaged
[2026-02-28 07:29:32] Executing agent (max_turns=15)
```

The generator analyzed the goal and created a 4-phase execution plan:

| Phase | Est. Duration | What it does |
|-------|--------------|-------------|
| Planning | 15 min | Analyze the goal, design the approach |
| Implementation | 15 min | Write the scanner code |
| Testing | 15 min | Verify the implementation |
| Deployment | 15 min | Run the scanner, generate the report |

---

## Step 4: Monitor

Check status while the agent works:

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

View logs (the agent's stdout streams here):

```bash
haymaker logs my-workload-9572f94f
```

The agent ran for **12 turns** using the Claude SDK. During those turns it:

1. Analyzed the requirements and identified 6 explicit requirements and 6 implicit decisions
2. Wrote `scanner.py` -- a 200-line file scanner with extension-based classification
3. Wrote `test_scanner.py` and ran the tests
4. Executed the scanner against the working directory
5. Self-evaluated against 8 measurable criteria
6. Documented its architectural decisions in code comments

---

## Step 5: Inspect the results

After ~45 minutes the agent completed. Final status:

```
✓ Session transcript exported (85 messages, 44m 42s)
Goal achieved successfully!
Exit code: 0
```

### The generated report

The agent created `output/file-report.md`:

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

## Files by Category

### Code (2 files)
- main.py
- scanner.py

### Docs (8 files)
- README.md
- prompt.md
- requirements.txt
...

### Config (5 files)
- agent_config.json
- .claude/context/execution_plan.json
...

### Data (3 files)
- .claude/runtime/logs/.../auto.jsonl
...

### Other (3 files)
- .claude/runtime/logs/.../auto.log
...
```

### The agent's self-evaluation

The agent evaluated itself against 8 criteria it derived from the goal:

| Criterion | Target | Result |
|-----------|--------|--------|
| **Coverage** | 100% of files scanned | 21/21 |
| **Classification** | Every file categorized | All 21 assigned |
| **Categories** | Only the 5 valid categories | code, docs, config, data, other |
| **Extension-only** | No content inspection | Uses `path.suffix` only |
| **Read-only** | 0 moves, 0 deletes | No mutations |
| **Report location** | `output/file-report.md` | Present |
| **Report format** | Valid Markdown with table | Renders correctly |
| **Counts** | Sum matches total | 2+8+5+3+3 = 21 |

**All 8 criteria passed.**

### What the agent built

The agent wrote code from scratch to achieve its goal:

```
agent-directory/
├── main.py              # Entry point (generated by amplihack)
├── scanner.py           # Written by the agent autonomously (200 lines)
├── test_scanner.py      # Tests written by the agent
├── prompt.md            # Your goal prompt
├── agent_config.json    # Execution plan + metadata
├── output/
│   └── file-report.md   # The deliverable
└── .claude/
    └── runtime/logs/    # Full execution traces (85 messages)
```

The `scanner.py` the agent wrote includes:
- Recursive directory walking with `os.walk`
- Extension-based classification using a comprehensive map (100+ extensions)
- Markdown report renderer with summary table and per-category file lists
- Exclusion of the `output/` directory to prevent circular self-inclusion
- Documented architectural decisions in code comments

---

## Step 6: Clean up

```bash
haymaker cleanup my-workload-9572f94f --yes
```

```
Cleanup complete for my-workload-9572f94f
  Resources deleted: 1
```

---

## Writing your own goals

Create a new `.md` file in `goals/` and deploy it:

```bash
cat > goals/api-health-check.md << 'EOF'
# API Health Monitor

## Goal
Check the health of 3 public APIs (httpbin.org, jsonplaceholder, github status)
and produce a JSON status report.

## Constraints
- Use only Python requests library
- Timeout: 5 seconds per API call
- Complete within 10 minutes

## Success Criteria
- All 3 APIs checked
- Response time recorded for each
- Report written to output/health-report.json
EOF

haymaker deploy my-workload --config goal_file=goals/api-health-check.md --yes
```

### Tips for effective goals

| Do | Don't |
|----|-------|
| Be specific about output format and location | Leave output undefined |
| Set time and resource constraints | Assume unlimited resources |
| Define measurable success criteria | Use vague "works correctly" |
| Specify what NOT to do (constraints) | Hope the agent figures it out |
| One goal per prompt file | Combine unrelated objectives |

---

## Configuration options

| Option | Default | Description |
|--------|---------|-------------|
| `goal_file` | built-in default | Path to your goal markdown |
| `sdk` | `claude` | Execution SDK (see below) |
| `enable_memory` | `false` | Agent learns across runs |
| `max_turns` | `15` | Maximum agentic iterations |

### SDK options

The goal agent generator supports four SDKs. Each uses a different AI backend:

| SDK | Best for | Auth required |
|-----|----------|-------------|
| `claude` | General tasks, tool use, deep reasoning | `ANTHROPIC_API_KEY` |
| `copilot` | Code generation, git operations, dev tasks | `gh copilot` login |
| `microsoft` | Azure workloads, structured workflows | Azure AI Foundry endpoint |
| `mini` | Lightweight tasks, minimal dependencies | Any LLM API key via litellm |

```bash
# Deploy with a specific SDK
haymaker deploy my-workload \
  --config goal_file=goals/my-goal.md \
  --config sdk=copilot \
  --yes
```

---

## Lifecycle reference

| Command | What it does |
|---------|-------------|
| `haymaker deploy my-workload --config goal_file=goals/X.md --yes` | Generate agent + execute |
| `haymaker status <id>` | Check agent progress |
| `haymaker logs <id>` | View generator logs + agent stdout |
| `haymaker stop <id> --yes` | Terminate agent process |
| `haymaker cleanup <id> --yes` | Mark complete, release resources |
| `haymaker list` | Show all deployments |

---

## Next steps

- **Write goals** for your domain and deploy them
- **Try different SDKs** to compare behavior
- **[Deploy to Azure](deploy)** for cloud execution with bigger containers
- **[Build a custom agent](advanced)** when you need full control over the agent code
- **[Goal Agent Generator Guide](https://rysweet.github.io/amplihack/GOAL_AGENT_GENERATOR_GUIDE/)** for the full reference
