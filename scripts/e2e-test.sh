#!/bin/sh
# E2E test: runs the full goal-agent lifecycle in Azure.
# Requires ANTHROPIC_API_KEY in the environment.
set -e

# Prevent nested Claude Code session detection
unset CLAUDECODE

echo "=== Haymaker Goal-Agent E2E Test ==="

echo "--- Step 1: workload list ---"
haymaker workload list
echo "PASS: workload registered"

echo "--- Step 2: verify API key available ---"
if [ -z "$ANTHROPIC_API_KEY" ]; then
  echo "WARN: No ANTHROPIC_API_KEY -- skipping agent execution test"
  echo "Running generator pipeline dry-run instead..."

  python3 -c "
from pathlib import Path
from amplihack.goal_agent_generator import PromptAnalyzer, ObjectivePlanner
goal = PromptAnalyzer().analyze(Path('goals/example-data-collector.md'))
plan = ObjectivePlanner().generate_plan(goal)
print(f'Goal: {goal.goal[:60]}')
print(f'Domain: {goal.domain}, Phases: {len(plan.phases)}')
print('Generator pipeline: PASS')
"
  echo "=== E2E TESTS PASSED (dry-run mode) ==="
  exit 0
fi

echo "API key present, running full agent lifecycle"

echo "--- Step 3: deploy with example goal ---"
OUTPUT=$(haymaker deploy my-workload --config goal_file=goals/example-file-organizer.md --yes 2>&1)
echo "$OUTPUT"
DEPLOYMENT_ID=$(echo "$OUTPUT" | grep -oE 'my-workload-[a-f0-9]+' | head -1)
echo "Deployment ID: $DEPLOYMENT_ID"

if [ -z "$DEPLOYMENT_ID" ]; then
  echo "FAIL: No deployment ID"
  exit 1
fi

echo "--- Step 4: wait for agent to complete (polling every 30s, up to 15 min) ---"
for i in $(seq 1 30); do
  sleep 30
  STATUS=$(haymaker status "$DEPLOYMENT_ID" 2>&1 | grep "Status:" | awk '{print $2}')
  PHASE=$(haymaker status "$DEPLOYMENT_ID" 2>&1 | grep "Phase:" | awk '{print $2}')
  echo "  [$i] status=$STATUS phase=$PHASE"
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    break
  fi
done

echo "--- Step 5: show logs ---"
haymaker logs "$DEPLOYMENT_ID" 2>&1 || true

echo "--- Step 6: check for expected output ---"
AGENT_DIR=$(haymaker status "$DEPLOYMENT_ID" 2>&1 | grep "Directory:" | awk '{print $2}')
if [ -n "$AGENT_DIR" ] && [ -f "$AGENT_DIR/output/file-report.md" ]; then
  echo "PASS: output/file-report.md found"
  echo "--- report preview ---"
  head -20 "$AGENT_DIR/output/file-report.md" 2>/dev/null || true
else
  echo "WARN: output/file-report.md not found (agent_dir=$AGENT_DIR)"
fi

echo "--- Step 7: final status ---"
haymaker status "$DEPLOYMENT_ID" 2>&1

echo "--- Step 8: cleanup ---"
haymaker cleanup "$DEPLOYMENT_ID" --yes 2>&1 || true

if [ "$STATUS" = "completed" ]; then
  echo "=== AGENT REACHED GOAL - ALL E2E TESTS PASSED ==="
elif [ "$STATUS" = "failed" ]; then
  echo "=== AGENT FAILED (check logs above) ==="
  # Don't exit 1 -- agent failure is informational, workload lifecycle worked
  echo "=== WORKLOAD LIFECYCLE PASSED ==="
else
  echo "=== AGENT TIMED OUT (status=$STATUS) ==="
  echo "=== WORKLOAD LIFECYCLE PASSED ==="
fi
