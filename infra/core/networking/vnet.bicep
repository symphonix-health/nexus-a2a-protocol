param location string = resourceGroup().location
param tags object = {}

param vnetName string
param addressPrefix string
param subnets array

resource vnet 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        addressPrefix
      ]
    }
    subnets: [for subnet in subnets: {
      name: subnet.name
      properties: {
        addressPrefix: subnet.addressPrefix
        delegations: subnet.?delegations ?? []
        serviceEndpoints: subnet.?serviceEndpoints ?? []
        privateEndpointNetworkPolicies: 'Disabled'
        privateLinkServiceNetworkPolicies: 'Enabled'
      }
    }]
  }
}

output id string = vnet.id
output name string = vnet.name
output subnets array = [for (subnet, i) in subnets: {
  id: vnet.properties.subnets[i].id
  name: vnet.properties.subnets[i].name
  addressPrefix: vnet.properties.subnets[i].properties.addressPrefix
}]
