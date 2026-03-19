param location string
param tags object = {}

param name string
param sku string = 'Free'

resource staticWebApp 'Microsoft.Web/staticSites@2023-01-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: sku
    tier: sku
  }
  properties: {
    repositoryUrl: ''
    branch: ''
    buildProperties: {
      skipGithubActionWorkflowGeneration: true
    }
  }
}

output id string = staticWebApp.id
output name string = staticWebApp.name
output defaultHostname string = staticWebApp.properties.defaultHostname

@secure()
output deploymentToken string = staticWebApp.listSecrets().properties.apiKey
