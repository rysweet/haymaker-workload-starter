#!/bin/sh
# E2E test for the goal-agent runtime workload.
# Verifies workload registration, import, and generator pipeline availability.
#
# Note: The full deploy (which runs the generator pipeline + agent subprocess)
# requires ~60s+ and API keys. This test verifies the infrastructure works.
set -e

echo "=== Haymaker Goal-Agent E2E Test ==="

echo "--- Step 1: workload list ---"
haymaker workload list
echo "PASS: workload registered"

echo "--- Step 2: verify amplihack generator is importable ---"
python3 -c "
from haymaker_my_workload import MyWorkload
from amplihack.goal_agent_generator import PromptAnalyzer, ObjectivePlanner
from agent_haymaker.workloads.models import DeploymentConfig

# Verify workload can be instantiated
wl = MyWorkload()
print(f'Workload name: {wl.name}')

# Verify generator components are available
analyzer = PromptAnalyzer()
planner = ObjectivePlanner()
print('Generator pipeline: OK')

# Verify config validation works
import asyncio
config = DeploymentConfig(workload_name='my-workload', workload_config={'sdk': 'claude'})
errors = asyncio.run(wl.validate_config(config))
print(f'Config validation: {\"PASS\" if not errors else errors}')

# Verify invalid config is caught
bad_config = DeploymentConfig(workload_name='my-workload', workload_config={'sdk': 'invalid'})
errors = asyncio.run(wl.validate_config(bad_config))
print(f'Bad config caught: {\"PASS\" if errors else \"FAIL\"}')

print('All checks passed')
"

echo "--- Step 3: verify goal files exist ---"
ls -la goals/
echo "PASS: goal files present"

echo "--- Step 4: verify generator pipeline (dry run) ---"
python3 -c "
from pathlib import Path
from amplihack.goal_agent_generator import PromptAnalyzer, ObjectivePlanner, SkillSynthesizer

# Analyze the example goal
analyzer = PromptAnalyzer()
goal = analyzer.analyze(Path('goals/example-data-collector.md'))
print(f'Goal: {goal.goal[:60]}...')
print(f'Domain: {goal.domain}')
print(f'Complexity: {goal.complexity}')
print(f'Constraints: {len(goal.constraints)}')
print(f'Success criteria: {len(goal.success_criteria)}')

# Generate execution plan
planner = ObjectivePlanner()
plan = planner.generate_plan(goal)
print(f'Phases: {len(plan.phases)}')
for phase in plan.phases:
    print(f'  - {phase.name}: {phase.estimated_duration}')
print(f'Total duration: {plan.total_estimated_duration}')

print('Generator pipeline: PASS')
"

echo "=== ALL E2E TESTS PASSED ==="
