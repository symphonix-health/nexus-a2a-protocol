param location string = resourceGroup().location
param tags object = {}

param name string
param logAnalyticsWorkspaceId string

@secure()
param appInsightsConnectionString string

resource containerAppEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: reference(logAnalyticsWorkspaceId, '2022-10-01').customerId
        sharedKey: listKeys(logAnalyticsWorkspaceId, '2022-10-01').primarySharedKey
      }
    }
    daprAIConnectionString: appInsightsConnectionString
    zoneRedundant: false
  }
}

output id string = containerAppEnvironment.id
output name string = containerAppEnvironment.name
output defaultDomain string = containerAppEnvironment.properties.defaultDomain
