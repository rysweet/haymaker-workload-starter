# Haymaker Workload Starter

A starter template for building custom [Agent Haymaker](https://github.com/rysweet/agent-haymaker) workloads. Clone this repo, rename the workload, and implement your domain logic.

## Quick Start

```bash
# 1. Clone and rename
git clone https://github.com/rysweet/haymaker-workload-starter my-workload
cd my-workload

# 2. Install in development mode
pip install -e ".[dev]"

# 3. Verify registration
haymaker workload list
# => my-workload (0.1.0) - A starter workload template for Agent Haymaker

# 4. Run tests
pytest -q

# 5. Deploy
haymaker deploy my-workload --config item_count=25
```

## Project Structure

```
haymaker-workload-starter/
├── pyproject.toml                     # Package config + workload entry point
├── workload.yaml                      # Workload manifest (metadata + config schema)
├── .env.example                       # Credential template
├── .pre-commit-config.yaml            # Code quality hooks
├── .github/workflows/ci.yml           # CI pipeline
├── src/haymaker_my_workload/
│   ├── __init__.py                    # Public API
│   └── workload.py                    # Workload implementation (start here)
└── tests/
    └── test_workload.py               # Full lifecycle tests
```

## How It Works

Agent Haymaker uses a plugin architecture. Your workload is a Python package that:

1. **Inherits from `WorkloadBase`** and implements 5 required methods
2. **Registers via entry point** in `pyproject.toml`
3. **Declares a manifest** in `workload.yaml`

Once installed (`pip install -e .`), the platform discovers your workload automatically and all standard CLI commands work:

```bash
haymaker deploy my-workload           # calls your deploy()
haymaker status <id>                  # calls your get_status()
haymaker logs <id> --follow           # calls your get_logs()
haymaker stop <id>                    # calls your stop()
haymaker start <id>                   # calls your start()
haymaker cleanup <id>                 # calls your cleanup()
```

## Customization Guide

### Step 1: Rename Your Workload

Replace all instances of `my-workload` / `MyWorkload` / `haymaker_my_workload`:

| File | What to change |
|------|---------------|
| `pyproject.toml` | `name`, entry point key + value, `packages` path |
| `workload.yaml` | `name`, `package.name`, `package.entrypoint`, `config_schema` |
| `src/haymaker_my_workload/` | Rename the directory |
| `src/.../workload.py` | `MyWorkload` class name, `name` attribute, `validate_config()` rules |
| `src/.../__init__.py` | Import + `__all__` |
| `tests/test_workload.py` | Import path + validation tests |
| `.env.example` | Credential names (if changed in `workload.yaml`) |

### Step 2: Define Your Config Schema

Edit `workload.yaml` to declare what settings your workload accepts:

```yaml
config_schema:
  target_url:
    type: string
    required: true
    description: "URL to monitor"
  check_interval:
    type: integer
    default: 30
    description: "Seconds between checks"
```

Users pass config via CLI:

```bash
haymaker deploy my-workload --config target_url=https://example.com check_interval=15
```

### Step 3: Implement the Five Required Methods

Edit `src/haymaker_my_workload/workload.py`. Each method has TODO comments showing what to implement:

```python
class MyWorkload(WorkloadBase):
    name = "my-workload"

    async def deploy(self, config: DeploymentConfig) -> str:
        """Provision resources and start your workload."""

    async def get_status(self, deployment_id: str) -> DeploymentState:
        """Return current state (refresh from external sources if needed)."""

    async def stop(self, deployment_id: str) -> bool:
        """Pause execution (must be resumable via start())."""

    async def cleanup(self, deployment_id: str) -> CleanupReport:
        """Delete ALL resources. Destructive and final."""

    async def get_logs(self, deployment_id, follow=False, lines=100) -> AsyncIterator[str]:
        """Stream log lines."""
```

### Step 4: Add Validation (Optional)

Override `validate_config()` to reject bad configs before deployment starts:

```python
async def validate_config(self, config: DeploymentConfig) -> list[str]:
    errors = []
    if "target_url" not in config.workload_config:
        errors.append("target_url is required")
    return errors
```

### Step 5: Declare Credentials (Optional)

If your workload needs secrets (API keys, tokens), declare them in `workload.yaml`:

```yaml
credentials:
  - name: MY_API_KEY
    required: true
```

Access them in your workload:

```python
api_key = await self.get_credential("MY_API_KEY")
```

## Platform Utilities

`WorkloadBase` provides these helpers for free:

| Method | Purpose |
|--------|---------|
| `await self.save_state(state)` | Persist deployment state |
| `await self.load_state(id)` | Load deployment state |
| `await self.get_credential(name)` | Fetch secrets from Key Vault / env |
| `self.log(message, level)` | Unified logging |
| `await self.list_deployments()` | List all deployments for this workload |

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest -q

# Run tests with coverage
pytest --cov --cov-report=term-missing

# Lint
ruff check src/ tests/
ruff format src/ tests/

# Type check
pyright src/

# Install pre-commit hooks
pre-commit install
```

## Adding AI/LLM Capabilities

Install with the `ai` extra for LLM integration:

```bash
pip install -e ".[ai]"
```

Then use the LLM abstraction in your workload:

```python
from agent_haymaker.llm import LLMConfig, create_llm_client

async def deploy(self, config):
    if config.workload_config.get("enable_ai"):
        llm_config = LLMConfig.from_env()
        llm = create_llm_client(llm_config)
        response = await llm.generate("Your prompt here")
```

## Deployment States

Your workload transitions through these states:

```
RUNNING ⇄ STOPPED
   ↓         ↓
CLEANING_UP ──┘
   ├── COMPLETED  (success)
   └── FAILED     (cleanup error)
```

`deploy()` sets the initial state to `RUNNING`. `stop()` only works on `RUNNING`
or `PENDING` deployments. `cleanup()` is destructive and final -- it sets
`COMPLETED` on success or `FAILED` if resource deletion errors occur. Double-cleanup
is a safe no-op. Follow-mode logs automatically exit on `COMPLETED` or `FAILED`.

> **Note:** The `PENDING` state is available but not used by the starter template.
> Add it when your workload has async provisioning needs.

## Testing Your Workload

The included tests cover the full lifecycle. Add tests for your domain logic:

```python
async def test_my_custom_behavior(self):
    workload = MyWorkload(platform=_mock_platform())
    config = DeploymentConfig(
        workload_name="my-workload",
        workload_config={"item_count": 100},
    )
    dep_id = await workload.deploy(config)
    # Assert your domain-specific behavior
```

## License

MIT
