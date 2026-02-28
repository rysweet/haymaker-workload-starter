---
layout: default
title: Home
nav_order: 1
description: "Build custom AI agent workloads for the Agent Haymaker platform"
permalink: /
---

<div class="hero" markdown="0">
  <h1>Haymaker Workload Starter</h1>
  <p>Build goal-seeking AI agent workloads that deploy, execute, and manage themselves through the haymaker CLI.</p>
  <div class="hero-buttons">
    <a href="/haymaker-workload-starter/tutorial" class="btn btn-primary">Build Your First Agent</a>
    <a href="https://github.com/rysweet/haymaker-workload-starter" class="btn btn-secondary">View on GitHub</a>
  </div>
</div>

<div class="stats fade-in" markdown="0">
  <div class="stat">
    <div class="stat-value">5 min</div>
    <div class="stat-label">To First Deploy</div>
  </div>
  <div class="stat">
    <div class="stat-value">4</div>
    <div class="stat-label">Agent SDKs</div>
  </div>
  <div class="stat">
    <div class="stat-value">21</div>
    <div class="stat-label">Unit Tests</div>
  </div>
  <div class="stat">
    <div class="stat-value">OIDC</div>
    <div class="stat-label">Azure Auth</div>
  </div>
</div>

---

## What is this?

Agent Haymaker is a platform for deploying AI agent workloads that pursue goals autonomously. This repo is a **starter template** -- clone it, build your agent, and deploy to Azure.

Write a goal in markdown. Deploy it. The workload generates and runs the agent automatically:

```bash
# Write your goal
echo '# My Agent
## Goal
Collect system metrics and produce a report.
## Success Criteria
- 10 samples collected
- Report written to output/' > goals/my-agent.md

# Deploy -- the workload generates + runs the agent
haymaker deploy my-workload --config goal_file=goals/my-agent.md --yes
haymaker logs <id> --follow        # watch the agent work
haymaker cleanup <id> --yes        # tear down when done
```

<div class="feature-grid" markdown="0">
  <div class="feature-card">
    <span class="feature-icon">🎯</span>
    <h3>Goal-Seeking Agents</h3>
    <p>Define a goal, implement phases, let the agent execute. Status callbacks keep the platform informed.</p>
  </div>
  <div class="feature-card">
    <span class="feature-icon">🧠</span>
    <h3>LLM + Agent Generator</h3>
    <p>Hand-build agents with optional LLM enhancement, or generate them from natural language goals using <a href="https://rysweet.github.io/amplihack/GOAL_AGENT_GENERATOR_GUIDE/">amplihack</a>.</p>
  </div>
  <div class="feature-card">
    <span class="feature-icon">🔌</span>
    <h3>Plugin Architecture</h3>
    <p>Python entry points for zero-config discovery. Install any workload and the CLI picks it up automatically.</p>
  </div>
  <div class="feature-card">
    <span class="feature-icon">☁️</span>
    <h3>Azure Deploy Pipeline</h3>
    <p>OIDC-authenticated GitHub Actions workflow deploys to Container Apps and runs full E2E verification.</p>
  </div>
</div>

---

## Documentation

<div class="quick-links" markdown="0">
  <a href="/haymaker-workload-starter/tutorial" class="quick-link">
    <span class="icon">📚</span>
    <span>Tutorial: Deploy an Agent</span>
  </a>
  <a href="/haymaker-workload-starter/advanced" class="quick-link">
    <span class="icon">🔧</span>
    <span>Advanced: Custom Agents</span>
  </a>
  <a href="/haymaker-workload-starter/architecture" class="quick-link">
    <span class="icon">🏗️</span>
    <span>Architecture</span>
  </a>
  <a href="/haymaker-workload-starter/deploy" class="quick-link">
    <span class="icon">☁️</span>
    <span>Deploy to Azure</span>
  </a>
</div>

---

## Real workloads built on this pattern

| Workload | What it does | Agent type |
|----------|-------------|------------|
| [Azure Infrastructure](https://github.com/rysweet/haymaker-azure-workloads) | Deploys and manages Azure resources across 50+ scenarios | Goal-seeking + LLM error recovery |
| [M365 Knowledge Worker](https://github.com/rysweet/haymaker-m365-workloads) | Simulates realistic email, Teams, and calendar activity | Activity orchestrator + LLM content generation |
