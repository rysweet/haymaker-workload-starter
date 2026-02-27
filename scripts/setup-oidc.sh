#!/usr/bin/env bash
# setup-oidc.sh -- One-time setup for GitHub Actions OIDC authentication to Azure.
#
# This script:
#   1. Creates an Azure AD app registration + service principal
#   2. Assigns Contributor role on the subscription
#   3. Adds federated credentials so GitHub Actions can authenticate without secrets
#   4. Sets the three required GitHub repository secrets
#
# Prerequisites:
#   - Azure CLI logged in:   az login
#   - GitHub CLI logged in:  gh auth login
#   - jq installed
#
# Usage:
#   ./scripts/setup-oidc.sh <github-org/repo>
#
# Example:
#   ./scripts/setup-oidc.sh rysweet/haymaker-workload-starter

set -euo pipefail

REPO="${1:?Usage: $0 <github-org/repo>}"
SP_NAME="haymaker-starter-deploy"

echo "==> Setting up OIDC for repo: $REPO"

# Get subscription and tenant IDs
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
TENANT_ID=$(az account show --query tenantId -o tsv)
echo "    Subscription: $SUBSCRIPTION_ID"
echo "    Tenant:       $TENANT_ID"

# Create service principal with Contributor role
echo "==> Creating service principal: $SP_NAME"
SP_OUTPUT=$(az ad sp create-for-rbac \
  --name "$SP_NAME" \
  --role Contributor \
  --scopes "/subscriptions/$SUBSCRIPTION_ID" \
  --query "{appId: appId, objectId: servicePrincipalObjectId}" \
  -o json)

CLIENT_ID=$(echo "$SP_OUTPUT" | jq -r '.appId')
echo "    Client ID: $CLIENT_ID"

# Get the app object ID (needed for federated credentials)
APP_OBJECT_ID=$(az ad app show --id "$CLIENT_ID" --query id -o tsv)

# Create federated credential for main branch
echo "==> Adding federated credential for main branch"
az ad app federated-credential create \
  --id "$APP_OBJECT_ID" \
  --parameters "{
    \"name\": \"github-actions-main\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"repo:${REPO}:ref:refs/heads/main\",
    \"audiences\": [\"api://AzureADTokenExchange\"],
    \"description\": \"GitHub Actions deploy from main branch\"
  }" -o none

# Create federated credential for manual workflow dispatch
echo "==> Adding federated credential for environment: dev"
az ad app federated-credential create \
  --id "$APP_OBJECT_ID" \
  --parameters "{
    \"name\": \"github-actions-env-dev\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"repo:${REPO}:environment:dev\",
    \"audiences\": [\"api://AzureADTokenExchange\"],
    \"description\": \"GitHub Actions deploy to dev environment\"
  }" -o none

# Set GitHub secrets
echo "==> Setting GitHub repository secrets"
gh secret set AZURE_CLIENT_ID       --repo "$REPO" --body "$CLIENT_ID"
gh secret set AZURE_TENANT_ID       --repo "$REPO" --body "$TENANT_ID"
gh secret set AZURE_SUBSCRIPTION_ID --repo "$REPO" --body "$SUBSCRIPTION_ID"

echo ""
echo "=== OIDC setup complete ==="
echo ""
echo "Secrets set on $REPO:"
echo "  AZURE_CLIENT_ID       = $CLIENT_ID"
echo "  AZURE_TENANT_ID       = $TENANT_ID"
echo "  AZURE_SUBSCRIPTION_ID = $SUBSCRIPTION_ID"
echo ""
echo "Next steps:"
echo "  1. Trigger a deploy:  gh workflow run deploy.yml -f environment=dev"
echo "  2. Watch the run:     gh run watch"
echo "  3. Clean up after:    az group delete --name haymaker-starter-dev-rg --yes"
