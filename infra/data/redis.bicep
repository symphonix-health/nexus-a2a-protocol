param location string = resourceGroup().location
param tags object = {}

param name string

resource redis 'Microsoft.Cache/redis@2023-08-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'Basic'
      family: 'C'
      capacity: 0
    }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    redisConfiguration: {
      'maxmemory-policy': 'allkeys-lru'
    }
    publicNetworkAccess: 'Enabled'
  }
}

output id string = redis.id
output name string = redis.name
output hostName string = redis.properties.hostName
output sslPort int = redis.properties.sslPort
