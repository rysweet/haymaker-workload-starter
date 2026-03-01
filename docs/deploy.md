---
layout: default
title: Deploy to Azure
nav_order: 4
---

# Deploy to Azure
{: .no_toc }

Deploy your workload to Azure Container Apps using GitHub Actions with OIDC authentication.
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>Table of contents</summary>
  {: .text-delta }
1. TOC
{:toc}
</details>

---

## Prerequisites

- Azure subscription
- Azure CLI: `az login`
- GitHub CLI: `gh auth login`

## One-time OIDC setup

Run the setup script to create a service principal with federated credentials:

```bash
./scripts/setup-oidc.sh your-org/your-repo
```

This creates three repository secrets (no passwords stored):

| Secret | Purpose |
|--------|---------|
| `AZURE_CLIENT_ID` | Service principal app ID |
| `AZURE_TENANT_ID` | Azure AD tenant |
| `AZURE_SUBSCRIPTION_ID` | Target subscription |

## Deploy

Trigger manually from GitHub Actions:

```bash
gh workflow run deploy.yml -f environment=dev -f location=eastus
gh run watch
```

The workflow runs three jobs:

1. **build** -- Docker image built and pushed to Azure Container Registry
2. **deploy** -- Bicep template deploys Container Apps (Consumption tier)
3. **verify** -- Full haymaker CLI E2E test inside the container

## What gets deployed

| Resource | SKU | Cost |
|----------|-----|------|
| Container Registry | Basic | ~$5/mo |
| Container Apps Environment | Dedicated (D4 profile) | ~$0 when scaled to 0 |
| Container App | 4 vCPU, 16 GiB (D4) | ~$0.30/hr when active |
| Log Analytics | Per-GB | ~$0 at this scale |

## E2E verification

The verify job runs the full haymaker lifecycle inside the deployed container:

```
haymaker workload list     → workload registered
haymaker deploy            → agent starts (returns instantly)
haymaker status <id>       → running
haymaker logs <id>         → log output
haymaker cleanup <id>      → torn down
```

## Clean up

Delete the resource group when done:

```bash
az group delete --name haymaker-starter-dev-rg --yes --no-wait
```

## How OIDC works

```
GitHub Actions  ──OIDC token──>  Azure AD  ──validates──>  grants access
                                     │
                     federated credential matches:
                     repo:org/repo:ref:refs/heads/main
```

No service principal passwords are stored in GitHub. Azure trusts GitHub's OIDC tokens based on the federated credential configuration created by the setup script.

### Long-running E2E and token refresh

OIDC tokens expire after 5 minutes, but the E2E verification job polls for up to 80 minutes. The polling loop automatically requests fresh tokens from GitHub's OIDC provider every ~4 minutes using `ACTIONS_ID_TOKEN_REQUEST_URL` and re-authenticates with `az login --service-principal --federated-token`. If token refresh fails, the loop continues gracefully.
