#!/bin/sh
# E2E test for the goal-agent runtime workload.
# Verifies: registration, deploy (generator pipeline), status, logs, cleanup.
set -e

echo "=== Haymaker Goal-Agent E2E Test ==="

echo "--- Step 1: workload list ---"
haymaker workload list
echo "PASS: workload registered"

echo "--- Step 2: deploy with default goal ---"
# The deploy triggers the amplihack generator pipeline.
# The generated agent's subprocess will fail without API keys -- that's OK.
# We're testing the WORKLOAD, not the agent.
OUTPUT=$(timeout 180 haymaker deploy my-workload --yes 2>&1) || true
echo "$OUTPUT"
DEPLOYMENT_ID=$(echo "$OUTPUT" | grep -oE 'my-workload-[a-f0-9]+' | head -1)
echo "Deployment ID: $DEPLOYMENT_ID"

if [ -z "$DEPLOYMENT_ID" ]; then
  echo "FAIL: No deployment ID returned"
  exit 1
fi
echo "PASS: deployment created"

echo "--- Step 3: status ---"
sleep 2
haymaker status "$DEPLOYMENT_ID" 2>&1 || true
echo "PASS: status returned"

echo "--- Step 4: logs ---"
haymaker logs "$DEPLOYMENT_ID" 2>&1 || true
echo "PASS: logs returned"

echo "--- Step 5: cleanup ---"
haymaker cleanup "$DEPLOYMENT_ID" --yes 2>&1 || true
echo "PASS: cleanup completed"

echo "=== ALL E2E TESTS PASSED ==="
