// Minimal infrastructure for deploying a haymaker workload to Azure Container Apps.
// Consumption tier -- near-zero cost, suitable for development and testing.
//
// Resources created:
//   - Container Registry (Basic, admin-enabled for image pull)
//   - Log Analytics workspace (for container logs)
//   - Container Apps Environment (Consumption plan)
//   - Container App (runs the workload container)
//
// Usage:
//   az deployment group create \
//     --resource-group <rg> \
//     --template-file infra/main.bicep \
//     --parameters image=<acr>.azurecr.io/<image>:<tag> acrName=<acr>

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Container image to deploy (e.g. myacr.azurecr.io/my-workload:latest)')
param image string

@description('Name of the Azure Container Registry')
param acrName string

@description('Environment label')
@allowed(['dev', 'staging', 'prod'])
param environment string = 'dev'

@description('Anthropic API key for Claude SDK agents')
@secure()
param anthropicApiKey string = ''

@description('Azure OpenAI endpoint (for microsoft SDK with DefaultAzureCredential)')
param azureOpenAiEndpoint string = ''

@description('Azure OpenAI deployment name')
param azureOpenAiDeployment string = ''

// ---------- Naming ----------
var suffix = uniqueString(resourceGroup().id)
var logAnalyticsName = 'haymaker-logs-${suffix}'
var envName = 'haymaker-env-${environment}'
var appName = 'haymaker-workload-${environment}'

// ---------- Container Registry (admin-enabled for Container Apps pull) ----------
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

// ---------- Log Analytics ----------
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// ---------- Container Apps Environment (Consumption) ----------
resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// ---------- Container App ----------
resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      secrets: [
        {
          name: 'acr-password'
          value: acr.listCredentials().passwords[0].value
        }
        {
          name: 'anthropic-api-key'
          value: anthropicApiKey
        }
      ]
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.listCredentials().username
          passwordSecretRef: 'acr-password'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'workload'
          image: image
          resources: {
            cpu: json('2')
            memory: '4Gi'
          }
          env: [
            {
              name: 'ANTHROPIC_API_KEY'
              secretRef: 'anthropic-api-key'
            }
            {
              name: 'CLAUDECODE'
              value: ''
            }
            {
              name: 'AZURE_OPENAI_ENDPOINT'
              value: azureOpenAiEndpoint
            }
            {
              name: 'AZURE_OPENAI_DEPLOYMENT'
              value: azureOpenAiDeployment
            }
            {
              name: 'LLM_PROVIDER'
              value: 'anthropic'
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

// ---------- Outputs ----------
output appName string = containerApp.name
output appFqdn string = containerApp.properties.configuration.?ingress.?fqdn ?? 'no-ingress'
output principalId string = containerApp.identity.principalId
