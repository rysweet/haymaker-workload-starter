#!/bin/sh
# E2E test for the goal-agent runtime workload.
# Runs inside the container to verify the full CLI flow.
set -e

echo "=== Haymaker Goal-Agent E2E Test ==="

echo "--- workload list ---"
haymaker workload list

echo "--- deploy with default goal ---"
OUTPUT=$(haymaker deploy my-workload --yes 2>&1)
echo "$OUTPUT"
DEPLOYMENT_ID=$(echo "$OUTPUT" | grep -oE 'my-workload-[a-f0-9]+' | head -1)
echo "Deployment ID: $DEPLOYMENT_ID"

echo "--- status ---"
sleep 2
haymaker status "$DEPLOYMENT_ID"

echo "--- logs ---"
haymaker logs "$DEPLOYMENT_ID"

echo "--- stop ---"
haymaker stop "$DEPLOYMENT_ID" --yes

echo "--- cleanup ---"
haymaker cleanup "$DEPLOYMENT_ID" --yes

echo "=== ALL E2E TESTS PASSED ==="
