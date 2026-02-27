// Minimal infrastructure for deploying a haymaker workload to Azure Container Apps.
// Consumption tier -- near-zero cost, suitable for development and testing.
//
// Resources created:
//   - Log Analytics workspace (for container logs)
//   - Container Apps Environment (Consumption plan)
//   - Container App (runs the workload container)
//   - Container Registry (stores the workload image)
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

// ---------- Naming ----------
var suffix = uniqueString(resourceGroup().id)
var logAnalyticsName = 'haymaker-logs-${suffix}'
var envName = 'haymaker-env-${environment}'
var appName = 'haymaker-workload-${environment}'

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

// ---------- Container Registry reference ----------
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
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
      registries: [
        {
          server: acr.properties.loginServer
          identity: 'system'
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'workload'
          image: image
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

// ---------- ACR Pull role for the Container App ----------
@description('AcrPull role definition ID')
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, containerApp.id, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------- Outputs ----------
output appName string = containerApp.name
output appFqdn string = containerApp.properties.configuration.?ingress.?fqdn ?? 'no-ingress'
output principalId string = containerApp.identity.principalId
