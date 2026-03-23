param location string = resourceGroup().location
param tags object = {}

param name string
param deployments array = []

resource cognitiveAccount 'Microsoft.CognitiveServices/accounts@2023-10-01-preview' = {
  name: name
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: name
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
    }
  }
}

resource deployment 'Microsoft.CognitiveServices/accounts/deployments@2023-10-01-preview' = [for deployment in deployments: {
  parent: cognitiveAccount
  name: deployment.name
  sku: {
    name: deployment.sku
    capacity: deployment.capacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: deployment.model
      version: deployment.version
    }
  }
}]

output id string = cognitiveAccount.id
output name string = cognitiveAccount.name
output endpoint string = cognitiveAccount.properties.endpoint

@secure()
output key string = cognitiveAccount.listKeys().key1
