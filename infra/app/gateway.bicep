param location string = resourceGroup().location
param tags object = {}

param name string
param containerAppEnvironmentId string
param imageName string
param environmentVariables array = []
param secrets array = []

resource gateway 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppEnvironmentId
    configuration: {
      ingress: {
        external: true
        targetPort: 8100
        transport: 'http'
        allowInsecure: false
      }
      secrets: [for secret in secrets: {
        name: secret.name
        keyVaultUrl: secret.?keyVaultUrl
        identity: secret.?identity == 'system' ? 'system' : null
      }]
    }
    template: {
      containers: [
        {
          name: name
          image: imageName
          resources: {
            cpu: json('2.0')
            memory: '4Gi'
          }
          env: environmentVariables
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 10
        rules: [
          {
            name: 'http-rule'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
    }
  }
}

output id string = gateway.id
output name string = gateway.name
output fqdn string = gateway.properties.configuration.ingress.fqdn
output uri string = 'https://${gateway.properties.configuration.ingress.fqdn}'
output principalId string = gateway.identity.principalId
