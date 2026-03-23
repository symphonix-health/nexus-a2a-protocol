param location string = resourceGroup().location
param tags object = {}

param name string
param containerAppEnvironmentId string
param port int
param imageName string
param environmentVariables array = []
param secrets array = []
param minReplicas int = 0
param maxReplicas int = 5
param cpu string = '0.5'
param memory string = '1Gi'
param ingressExternal bool = false

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
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
        external: ingressExternal
        targetPort: port
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
            cpu: json(cpu)
            memory: memory
          }
          env: environmentVariables
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-rule'
            http: {
              metadata: {
                concurrentRequests: '10'
              }
            }
          }
        ]
      }
    }
  }
}

output id string = containerApp.id
output name string = containerApp.name
output fqdn string = containerApp.properties.configuration.ingress.fqdn
output uri string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output principalId string = containerApp.identity.principalId
