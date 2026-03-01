# Haymaker Workload Starter

A goal-seeking agent workload for [Agent Haymaker](https://github.com/rysweet/agent-haymaker). Write a goal in markdown, deploy it, the workload generates and runs an autonomous AI agent.

**Docs site:** [rysweet.github.io/haymaker-workload-starter](https://rysweet.github.io/haymaker-workload-starter/)

## Quick Start

```bash
git clone https://github.com/rysweet/haymaker-workload-starter my-workload
cd my-workload

# Install dependencies (not yet on PyPI, install from GitHub first)
pip install "agent-haymaker @ git+https://github.com/rysweet/agent-haymaker.git"
pip install "amplihack @ git+https://github.com/rysweet/amplihack.git"
pip install "amplihack-memory-lib @ git+https://github.com/rysweet/amplihack-memory-lib.git"
pip install -e ".[dev]"

export ANTHROPIC_API_KEY=sk-ant-...  # or configure another SDK

haymaker deploy my-workload \
  --config goal_file=goals/example-file-organizer.md \
  --yes
# => Deployment started: my-workload-a1b2c3d4

haymaker status my-workload-a1b2c3d4
haymaker logs my-workload-a1b2c3d4
haymaker cleanup my-workload-a1b2c3d4 --yes
```

## How It Works

You write a markdown file describing a goal:

```markdown
# File Organization Agent

## Goal
Scan the current working directory for files, classify them by type,
and produce a summary report.

## Constraints
- Read-only: do not move or delete any files

## Success Criteria
- All files scanned and classified
- Report written to output/file-report.md
```

The workload runs the [amplihack goal agent generator](https://rysweet.github.io/amplihack/GOAL_AGENT_GENERATOR_GUIDE/) to analyze the goal, create a phased execution plan, match skills, and assemble a runnable agent. The agent executes autonomously as a background process.

## Project Structure

```
haymaker-workload-starter/
├── goals/                             # Goal prompts (write yours here)
│   ├── example-data-collector.md
│   ├── example-file-organizer.md
│   └── example-with-memory.md
├── src/haymaker_my_workload/
│   ├── __init__.py                    # Public API
│   └── workload.py                    # Goal-agent runtime
├── tests/
│   └── test_workload.py               # 68 tests
├── docs/                              # GitHub Pages docs site
├── infra/main.bicep                   # Azure Container Apps (Bicep)
├── scripts/
│   ├── setup-oidc.sh                  # One-time Azure OIDC setup
│   └── e2e-test.sh                    # E2E verification script
├── Makefile                           # Dev shortcuts (make install, test, lint, deploy)
├── Dockerfile                         # Container image
├── .github/workflows/
│   ├── ci.yml                         # Lint + test
│   ├── deploy.yml                     # Azure deploy pipeline
│   └── pages.yml                      # Docs site deploy
├── pyproject.toml                     # Package config
└── workload.yaml                      # Workload manifest
```

## Configuration

| Option | Default | Description |
|--------|---------|-------------|
| `goal_file` | built-in default | Path to goal markdown |
| `sdk` | `claude` | `claude`, `copilot`, `microsoft`, or `mini` |
| `enable_memory` | `false` | Agent learns across runs |
| `max_turns` | `15` | Maximum agentic iterations (1-100) |

## SDK Options

| SDK | Auth | Best for |
|-----|------|----------|
| `claude` | `ANTHROPIC_API_KEY` | General tasks, deep reasoning |
| `copilot` | `GH_TOKEN` | Code generation, git operations |
| `microsoft` | Azure OpenAI + DefaultAzureCredential | Azure workloads |
| `mini` | Any LLM API key via litellm | Lightweight tasks |

## Documentation

- [Tutorial](https://rysweet.github.io/haymaker-workload-starter/tutorial) -- end-to-end with real results
- [Architecture](https://rysweet.github.io/haymaker-workload-starter/architecture) -- how it all connects
- [Deploy to Azure](https://rysweet.github.io/haymaker-workload-starter/deploy) -- OIDC pipeline
- [Advanced: Custom Agents](https://rysweet.github.io/haymaker-workload-starter/advanced) -- hand-built agents

## Development

```bash
# Install dependencies (not yet on PyPI, install from GitHub first)
pip install "agent-haymaker @ git+https://github.com/rysweet/agent-haymaker.git"
pip install "amplihack @ git+https://github.com/rysweet/amplihack.git"
pip install "amplihack-memory-lib @ git+https://github.com/rysweet/amplihack-memory-lib.git"
pip install -e ".[dev]"

# Or use the Makefile shortcut:
make install

pytest -q               # 68 tests
ruff check src/ tests/  # lint
```

## License

MIT
