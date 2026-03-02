FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (git for pip, Node.js for Claude Code CLI)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git ca-certificates gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
       | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" \
       > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI (required by claude-agent-sdk for AutoMode)
RUN npm install -g @anthropic-ai/claude-code \
    && claude --version

# Ensure HOME is set and skip Claude Code onboarding/telemetry in container
ENV HOME=/root
ENV CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

# Install agent-haymaker platform and amplihack from GitHub (not yet on PyPI)
# Install deps sequentially to avoid resolver conflicts
RUN pip install --no-cache-dir "agent-haymaker @ git+https://github.com/rysweet/agent-haymaker.git" && \
    pip install --no-cache-dir "amplihack @ git+https://github.com/rysweet/amplihack.git" && \
    pip install --no-cache-dir --no-deps "amplihack-memory-lib @ git+https://github.com/rysweet/amplihack-memory-lib.git"

# Run amplihack install to set up hooks, agents, and tools at $HOME/.amplihack/
# This creates the directory structure that .claude/settings.json hooks reference.
RUN python -m amplihack install

# Install this workload
COPY . .
# --no-deps because deps were installed above from GitHub (not on PyPI)
RUN pip install --no-cache-dir --no-deps .

# Include E2E test script (used by CI to verify the deployment)
COPY scripts/e2e-test.sh /usr/local/bin/haymaker-e2e-test
RUN chmod +x /usr/local/bin/haymaker-e2e-test

# Verify the workload is registered
RUN haymaker workload list

# Keep container alive so haymaker CLI can be invoked via exec.
# Replace this with your workload's long-running process when ready.
CMD ["sh", "-c", "echo 'Haymaker workload container ready.' && tail -f /dev/null"]
