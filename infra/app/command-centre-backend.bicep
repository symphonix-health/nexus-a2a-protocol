param location string = resourceGroup().location
param tags object = {}

param name string
param containerAppEnvironmentId string
param imageName string
param environmentVariables array = []
param secrets array = []

resource commandCentre 'Microsoft.App/containerApps@2024-03-01' = {
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
        targetPort: 8099
        transport: 'http'
        allowInsecure: false
        corsPolicy: {
          allowedOrigins: ['*']
          allowedMethods: ['GET', 'POST', 'OPTIONS']
          allowedHeaders: ['*']
        }
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
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: environmentVariables
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
      }
    }
  }
}

output id string = commandCentre.id
output name string = commandCentre.name
output fqdn string = commandCentre.properties.configuration.ingress.fqdn
output uri string = 'https://${commandCentre.properties.configuration.ingress.fqdn}'
output principalId string = commandCentre.identity.principalId
