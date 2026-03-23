param location string = resourceGroup().location
param tags object = {}

param name string

resource appConfiguration 'Microsoft.AppConfiguration/configurationStores@2023-03-01' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: 'standard'
  }
  properties: {
    enablePurgeProtection: false
    publicNetworkAccess: 'Enabled'
  }
}

output id string = appConfiguration.id
output name string = appConfiguration.name
output endpoint string = appConfiguration.properties.endpoint
