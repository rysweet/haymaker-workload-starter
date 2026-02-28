FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (git needed for pip install from GitHub)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git \
    && rm -rf /var/lib/apt/lists/*

# Install agent-haymaker platform from GitHub (not yet on PyPI)
RUN pip install --no-cache-dir "agent-haymaker @ git+https://github.com/rysweet/agent-haymaker.git"

# Install this workload
COPY . .
RUN pip install --no-cache-dir .

# Verify the workload is registered
RUN haymaker workload list

# Keep container alive so haymaker CLI can be invoked via exec.
# Replace this with your workload's long-running process when ready.
CMD ["sh", "-c", "echo 'Haymaker workload container ready.' && tail -f /dev/null"]
