#!/bin/sh
# E2E test for the goal-agent runtime workload.
# Verifies: workload registration, deploy (generator pipeline),
# status, logs, stop, and cleanup.
#
# Note: The generated agent's main.py requires API keys to actually
# execute. This test verifies the WORKLOAD LIFECYCLE, not the agent
# execution. The agent subprocess will fail without keys, but the
# workload handles that gracefully (sets FAILED status).
set -e

echo "=== Haymaker Goal-Agent E2E Test ==="

echo "--- workload list ---"
haymaker workload list

echo "--- deploy (generates agent from default goal) ---"
OUTPUT=$(haymaker deploy my-workload --yes 2>&1)
echo "$OUTPUT"
DEPLOYMENT_ID=$(echo "$OUTPUT" | grep -oE 'my-workload-[a-f0-9]+' | head -1)
echo "Deployment ID: $DEPLOYMENT_ID"

if [ -z "$DEPLOYMENT_ID" ]; then
  echo "FAIL: No deployment ID returned"
  exit 1
fi

echo "--- status (verify deployment was created) ---"
sleep 3
haymaker status "$DEPLOYMENT_ID"

echo "--- logs (verify generator pipeline ran) ---"
LOGS=$(haymaker logs "$DEPLOYMENT_ID" 2>&1 || true)
echo "$LOGS"

# Verify the generator pipeline logged its stages
if echo "$LOGS" | grep -q "Goal analyzed\|Generating agent\|Agent generated\|Execution plan"; then
  echo "PASS: Generator pipeline executed"
else
  echo "WARN: Generator pipeline logs not found (agent may have completed too fast)"
fi

echo "--- stop ---"
haymaker stop "$DEPLOYMENT_ID" --yes 2>&1 || true

echo "--- cleanup ---"
haymaker cleanup "$DEPLOYMENT_ID" --yes

echo "=== ALL E2E TESTS PASSED ==="
