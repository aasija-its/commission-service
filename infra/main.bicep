@description('Azure region')
param location string = resourceGroup().location

@description('Container image tag to deploy (e.g. sha-abc1234)')
param imageTag string = 'latest'

@description('Azure SQL server hostname')
param sqlServer string = 'ssr-inc-lgz-sha-uat-wus2.database.windows.net'

@description('Azure SQL database name')
param sqlDatabase string = 'sdb-inc-tms-web-uat-wus2'

@description('Application Insights connection string')
param appInsightsConnectionString string = ''

@description('ACR admin password (injected by pipeline)')
@secure()
param acrPassword string = ''

// ─── References to existing shared resources ──────────────────────────────────
var acrServer  = 'trailermaintenanceacr.azurecr.io'
var envId      = resourceId('Microsoft.App/managedEnvironments', 'trailer-maintenance-env')

// ─── Container App ─────────────────────────────────────────────────────────────
resource commissionApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: 'commission-service'
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: envId
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [
        {
          server:           acrServer
          username:         'trailermaintenanceacr'
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        { name: 'acr-password',   value: acrPassword }
        { name: 'sql-server',     value: sqlServer }
        { name: 'sql-database',   value: sqlDatabase }
      ]
      ingress: {
        external:   true
        targetPort: 8001
        transport:  'http'
        corsPolicy: {
          allowedOrigins: ['*']
          allowedMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
          allowedHeaders: ['*']
        }
      }
    }
    template: {
      containers: [
        {
          name:  'commission-service'
          image: '${acrServer}/commission-service:${imageTag}'
          env: [
            { name: 'SQL_SERVER',             secretRef: 'sql-server' }
            { name: 'SQL_DATABASE',           secretRef: 'sql-database' }
            { name: 'DEFAULT_TRANSPORT_RATE', value: '0.02' }
            { name: 'DEFAULT_PROCUREMENT_RATE', value: '0.05' }
          ]
          resources: {
            cpu:    json('0.5')
            memory: '1Gi'
          }
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/health', port: 8001 }
              initialDelaySeconds: 10
              periodSeconds:       30
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 8001 }
              initialDelaySeconds: 5
              periodSeconds:       10
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
        rules: [
          {
            name: 'http-scaling'
            http: { metadata: { concurrentRequests: '50' } }
          }
        ]
      }
    }
  }
}

output fqdn string = commissionApp.properties.configuration.ingress.fqdn
output appId string = commissionApp.id
