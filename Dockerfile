FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install agent-haymaker platform + this workload
COPY . .
RUN pip install --no-cache-dir agent-haymaker>=0.1.0 && \
    pip install --no-cache-dir .

# Verify the workload is registered
RUN haymaker workload list

# Keep container alive so haymaker CLI can be invoked via exec.
# Replace this with your workload's long-running process when ready.
CMD ["sh", "-c", "echo 'Haymaker workload container ready.' && tail -f /dev/null"]
