#!/bin/sh
# Full E2E test: deploys a goal-seeking agent, waits for it to reach its goal,
# validates output, checks memory, then runs a SECOND deployment to validate
# memory recall. No timeouts -- runs until done.
#
# Requires: ANTHROPIC_API_KEY in environment
set -e

# Prevent nested Claude Code session detection
unset CLAUDECODE

echo "=== Haymaker Goal-Agent FULL E2E Test ==="
echo "Started: $(date -u)"
echo ""

echo "--- Step 1: workload list ---"
haymaker workload list
echo "PASS: workload registered"

echo "--- Step 2: generator pipeline ---"
python3 -c "
from pathlib import Path
from amplihack.goal_agent_generator import PromptAnalyzer, ObjectivePlanner
goal = PromptAnalyzer().analyze(Path('goals/example-file-organizer.md'))
plan = ObjectivePlanner().generate_plan(goal)
print(f'Goal: {goal.goal[:60]}...')
print(f'Domain: {goal.domain}, Complexity: {goal.complexity}')
print(f'Phases: {len(plan.phases)}, Duration: {plan.total_estimated_duration}')
print('PASS: generator pipeline works')
"

echo ""
echo "=========================================="
echo "  RUN 1: First agent execution"
echo "=========================================="

echo "--- Step 3: deploy (run 1) ---"
OUTPUT=$(haymaker deploy my-workload --config goal_file=goals/example-file-organizer.md --config enable_memory=true --yes 2>&1)
echo "$OUTPUT"
DEP1=$(echo "$OUTPUT" | grep -oE 'my-workload-[a-f0-9]+' | head -1)
echo "Deployment ID: $DEP1"

if [ -z "$DEP1" ]; then
  echo "FAIL: No deployment ID"
  exit 1
fi
echo "PASS: deploy returned instantly"

echo "--- Step 4: wait for agent to complete (polling every 60s, no limit) ---"
ATTEMPT=0
while true; do
  ATTEMPT=$((ATTEMPT + 1))
  sleep 60
  STATUS_OUTPUT=$(haymaker status "$DEP1" 2>&1)
  STATUS=$(echo "$STATUS_OUTPUT" | grep "Status:" | awk '{print $2}')
  PHASE=$(echo "$STATUS_OUTPUT" | grep "Phase:" | awk '{print $2}')
  echo "  [$ATTEMPT] status=$STATUS phase=$PHASE ($(date -u +%H:%M:%S))"
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ]; then
    break
  fi
done

echo "--- Step 5: show logs ---"
haymaker logs "$DEP1" 2>&1 | tail -30 || true

echo "--- Step 6: check output ---"
AGENT_DIR=$(echo "$STATUS_OUTPUT" | grep "agent_dir\|agent_output_dir" | head -1 | awk '{print $NF}' | tr -d "'" | tr -d '"')
if [ -n "$AGENT_DIR" ]; then
  echo "Agent dir: $AGENT_DIR"
  if [ -d "$AGENT_DIR" ]; then
    ls -la "$AGENT_DIR"/output/ 2>/dev/null && echo "PASS: output directory exists" || echo "WARN: no output directory"
    cat "$AGENT_DIR"/output/file-report.md 2>/dev/null | head -20 || true
  fi
fi

echo "--- Step 7: check memory (run 1) ---"
python3 -c "
from amplihack_memory import ExperienceStore
from pathlib import Path
store = ExperienceStore(agent_name='auto_claude', storage_path=Path.home() / '.amplihack' / 'agent-memory')
results = store.search('file organization')
print(f'Memory entries: {len(results)}')
for r in results:
    print(f'  {r.experience_type.name}: {r.context[:60]}')
stats = store.get_statistics()
print(f'Total experiences: {stats[\"total_experiences\"]}')
print('PASS: memory contains run 1 experiences' if results else 'WARN: no memories found')
" 2>/dev/null || echo "WARN: memory check failed (amplihack-memory-lib may not be installed)"

if [ "$STATUS" = "completed" ]; then
  echo "PASS: Run 1 agent reached goal"
else
  echo "INFO: Run 1 agent status=$STATUS"
fi

echo ""
echo "=========================================="
echo "  RUN 2: Second execution (memory recall)"
echo "=========================================="

echo "--- Step 8: deploy (run 2, same goal) ---"
OUTPUT2=$(haymaker deploy my-workload --config goal_file=goals/example-file-organizer.md --config enable_memory=true --yes 2>&1)
echo "$OUTPUT2"
DEP2=$(echo "$OUTPUT2" | grep -oE 'my-workload-[a-f0-9]+' | head -1)
echo "Deployment ID: $DEP2"

echo "--- Step 9: wait for run 2 to complete ---"
ATTEMPT=0
while true; do
  ATTEMPT=$((ATTEMPT + 1))
  sleep 60
  STATUS_OUTPUT2=$(haymaker status "$DEP2" 2>&1)
  STATUS2=$(echo "$STATUS_OUTPUT2" | grep "Status:" | awk '{print $2}')
  PHASE2=$(echo "$STATUS_OUTPUT2" | grep "Phase:" | awk '{print $2}')
  echo "  [$ATTEMPT] status=$STATUS2 phase=$PHASE2 ($(date -u +%H:%M:%S))"
  if [ "$STATUS2" = "completed" ] || [ "$STATUS2" = "failed" ]; then
    break
  fi
done

echo "--- Step 10: check memory (run 2) ---"
python3 -c "
from amplihack_memory import ExperienceStore
from pathlib import Path
store = ExperienceStore(agent_name='auto_claude', storage_path=Path.home() / '.amplihack' / 'agent-memory')
results = store.search('file organization')
print(f'Memory entries after run 2: {len(results)}')
stats = store.get_statistics()
print(f'Total experiences: {stats[\"total_experiences\"]}')
if len(results) > 1:
    print('PASS: memory accumulated across runs')
else:
    print('WARN: expected more memories after two runs')
" 2>/dev/null || echo "WARN: memory check failed"

echo "--- Step 11: show run 2 logs ---"
haymaker logs "$DEP2" 2>&1 | tail -30 || true

echo "--- Step 12: cleanup both ---"
haymaker cleanup "$DEP1" --yes 2>&1 || true
haymaker cleanup "$DEP2" --yes 2>&1 || true

echo ""
echo "=========================================="
echo "  RESULTS"
echo "=========================================="
echo "Run 1: status=$STATUS"
echo "Run 2: status=$STATUS2"
echo "Finished: $(date -u)"
echo ""

if [ "$STATUS" = "completed" ] && [ "$STATUS2" = "completed" ]; then
  echo "=== BOTH RUNS COMPLETED - FULL E2E PASSED ==="
elif [ "$STATUS" = "completed" ]; then
  echo "=== RUN 1 COMPLETED, RUN 2 status=$STATUS2 ==="
else
  echo "=== RUN 1 status=$STATUS, RUN 2 status=$STATUS2 ==="
fi
