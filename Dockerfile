FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (git needed for pip install from GitHub)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git \
    && rm -rf /var/lib/apt/lists/*

# Install agent-haymaker platform and amplihack from GitHub (not yet on PyPI)
# Install deps sequentially to avoid resolver conflicts
RUN pip install --no-cache-dir "agent-haymaker @ git+https://github.com/rysweet/agent-haymaker.git" && \
    pip install --no-cache-dir "amplihack @ git+https://github.com/rysweet/amplihack.git" && \
    pip install --no-cache-dir --no-deps "amplihack-memory-lib @ git+https://github.com/rysweet/amplihack-memory-lib.git"

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
