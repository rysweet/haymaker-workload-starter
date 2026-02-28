#!/bin/sh
# E2E test script for haymaker workload lifecycle.
# Runs inside the container to verify the full CLI flow.
set -e

echo "=== Haymaker E2E Test ==="

echo "--- workload list ---"
haymaker workload list

echo "--- deploy ---"
OUTPUT=$(haymaker deploy my-workload --config item_count=5 --yes 2>&1)
echo "$OUTPUT"
DEPLOYMENT_ID=$(echo "$OUTPUT" | grep -oE 'my-workload-[a-f0-9]+' | head -1)
echo "Deployment ID: $DEPLOYMENT_ID"

echo "--- status ---"
haymaker status "$DEPLOYMENT_ID"

echo "--- logs ---"
haymaker logs "$DEPLOYMENT_ID"

echo "--- stop ---"
haymaker stop "$DEPLOYMENT_ID" --yes

echo "--- start ---"
haymaker start "$DEPLOYMENT_ID"

echo "--- cleanup ---"
haymaker cleanup "$DEPLOYMENT_ID" --yes

echo "=== ALL E2E TESTS PASSED ==="
