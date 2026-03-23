targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment (e.g., dev, staging, prod)')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

@description('Id of the user or app to assign application roles')
param principalId string = ''

@description('Whether to deploy Azure OpenAI or use external API')
param deployAzureOpenAI bool = true

@description('Azure OpenAI model deployments')
param openAIDeployments array = [
  {
    name: 'gpt-4o-mini'
    model: 'gpt-4o-mini'
    version: '2024-07-18'
    sku: 'Standard'
    capacity: 50
  }
  {
    name: 'gpt-4o-mini-tts'
    model: 'tts'
    version: '1'
    sku: 'Standard'
    capacity: 1
  }
]

@description('External OpenAI API key (if not using Azure OpenAI)')
@secure()
param openAIApiKey string = ''

@description('JWT secret for agent authentication (required - generate with: openssl rand -hex 32)')
@secure()
param jwtSecret string

@description('Tags to apply to all resources')
param tags object = {
  Environment: environmentName
  Project: 'HelixCare'
  ManagedBy: 'azd'
}

var abbrs = loadJsonContent('./abbreviations.json')
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))

// Organize the resource group
resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: '${abbrs.resourceGroups}${environmentName}-${resourceToken}'
  location: location
  tags: tags
}

// Core infrastructure modules
module monitoring './core/monitor/app-insights.bicep' = {
  scope: rg
  params: {
    location: location
    tags: tags
    logAnalyticsName: '${abbrs.operationalInsightsWorkspaces}${resourceToken}'
    applicationInsightsName: '${abbrs.appInsightsComponents}${resourceToken}'
  }
}

module networking './core/networking/vnet.bicep' = {
  scope: rg
  params: {
    location: location
    tags: tags
    vnetName: '${abbrs.networkVirtualNetworks}${resourceToken}'
    addressPrefix: '10.0.0.0/16'
    subnets: [
      {
        name: 'agents-subnet'
        addressPrefix: '10.0.1.0/24'
      }
      {
        name: 'data-subnet'
        addressPrefix: '10.0.2.0/24'
      }
      {
        name: 'gateway-subnet'
        addressPrefix: '10.0.3.0/24'
      }
      {
        name: 'integration-subnet'
        addressPrefix: '10.0.4.0/24'
      }
    ]
  }
}

module keyVault './core/security/keyvault.bicep' = {
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.keyVaults}${resourceToken}'
    principalId: principalId
  }
}

module storage './data/storage.bicep' = {
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.storageAccounts}${resourceToken}'
  }
}

module redis './data/redis.bicep' = {
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.cacheRedis}${resourceToken}'
  }
}

module appConfiguration './data/app-configuration.bicep' = {
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.appConfigurationStores}${resourceToken}'
  }
}

// Azure OpenAI (optional)
module openai './ai/openai.bicep' = if (deployAzureOpenAI) {
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.cognitiveServicesAccounts}${resourceToken}'
    deployments: openAIDeployments
  }
}

// Container Apps Environment
module containerAppEnvironment './core/host/container-app-environment.bicep' = {
  scope: rg
  params: {
    location: location
    tags: tags
    name: '${abbrs.appManagedEnvironments}${resourceToken}'
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsWorkspaceId
    appInsightsConnectionString: monitoring.outputs.applicationInsightsConnectionString
  }
}

// Load agent configurations
var agentsConfig = loadJsonContent('../config/agents.json')
var personasConfig = loadJsonContent('../config/agent_personas.json')

// Helper to get IAM group for an agent
func getIamGroup(agentId string) string => personasConfig.agents[agentId].?iam.?groups[0] ?? 'nexus-operations'

// Deploy all agents from helixcare group
var helixcareAgents = [
  'imaging_agent'
  'pharmacy_agent'
  'bed_manager_agent'
  'discharge_agent'
  'followup_scheduler'
  'care_coordinator'
  'primary_care_agent'
  'specialty_care_agent'
  'telehealth_agent'
  'home_visit_agent'
  'ccm_agent'
  'clinician_avatar_agent'
]

module helixcareAgentApps './app/container-app.bicep' = [for agentId in helixcareAgents: {
  scope: rg
  params: {
    location: location
    tags: tags
    name: agentId
    containerAppEnvironmentId: containerAppEnvironment.outputs.id
    port: agentsConfig.agents[agentId].port
    imageName: 'helixcare/${agentId}:latest'
    environmentVariables: [
      {
        name: 'NEXUS_JWT_SECRET'
        secretRef: 'jwt-secret'
      }
      {
        name: 'OPENAI_API_KEY'
        secretRef: deployAzureOpenAI ? 'azure-openai-key' : 'openai-api-key'
      }
      {
        name: 'OPENAI_ENDPOINT'
        value: deployAzureOpenAI ? openai.outputs.endpoint : 'https://api.openai.com/v1'
      }
      {
        name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
        value: monitoring.outputs.applicationInsightsConnectionString
      }
      {
        name: 'AGENT_ID'
        value: agentId
      }
      {
        name: 'DID_VERIFY'
        value: 'false'
      }
    ]
    secrets: [
      {
        name: 'jwt-secret'
        keyVaultUrl: '${keyVault.outputs.endpoint}secrets/jwt-secret'
        identity: 'system'
      }
      {
        name: deployAzureOpenAI ? 'azure-openai-key' : 'openai-api-key'
        keyVaultUrl: '${keyVault.outputs.endpoint}secrets/${deployAzureOpenAI ? 'azure-openai-key' : 'openai-api-key'}'
        identity: 'system'
      }
    ]
    minReplicas: 0
    maxReplicas: 5
    cpu: '0.5'
    memory: '1Gi'
  }
}]

// Deploy ED triage group agents
var edTriageAgents = [
  'triage_agent'
  'diagnosis_agent'
  'openhie_mediator'
]

module edTriageAgentApps './app/container-app.bicep' = [for agentId in edTriageAgents: {
  scope: rg
  params: {
    location: location
    tags: tags
    name: agentId
    containerAppEnvironmentId: containerAppEnvironment.outputs.id
    port: agentsConfig.agents[agentId].port
    imageName: 'ed-triage/${agentId}:latest'
    environmentVariables: [
      {
        name: 'NEXUS_JWT_SECRET'
        secretRef: 'jwt-secret'
      }
      {
        name: 'OPENAI_API_KEY'
        secretRef: deployAzureOpenAI ? 'azure-openai-key' : 'openai-api-key'
      }
      {
        name: 'OPENAI_ENDPOINT'
        value: deployAzureOpenAI ? openai.outputs.endpoint : 'https://api.openai.com/v1'
      }
      {
        name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
        value: monitoring.outputs.applicationInsightsConnectionString
      }
      {
        name: 'AGENT_ID'
        value: agentId
      }
      {
        name: 'DID_VERIFY'
        value: 'false'
      }
    ]
    secrets: [
      {
        name: 'jwt-secret'
        keyVaultUrl: '${keyVault.outputs.endpoint}secrets/jwt-secret'
        identity: 'system'
      }
      {
        name: deployAzureOpenAI ? 'azure-openai-key' : 'openai-api-key'
        keyVaultUrl: '${keyVault.outputs.endpoint}secrets/${deployAzureOpenAI ? 'azure-openai-key' : 'openai-api-key'}'
        identity: 'system'
      }
    ]
    minReplicas: 0
    maxReplicas: 10
    cpu: '0.5'
    memory: '1Gi'
  }
}]

// Command Centre Backend
module commandCentreBackend './app/command-centre-backend.bicep' = {
  scope: rg
  params: {
    location: location
    tags: tags
    name: 'command-centre'
    containerAppEnvironmentId: containerAppEnvironment.outputs.id
    imageName: 'helixcare/command-centre:latest'
    environmentVariables: [
      {
        name: 'NEXUS_JWT_SECRET'
        secretRef: 'jwt-secret'
      }
      {
        name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
        value: monitoring.outputs.applicationInsightsConnectionString
      }
      {
        name: 'UPDATE_INTERVAL_MS'
        value: '5000'
      }
      {
        name: 'CC_POLL_CONCURRENCY'
        value: '6'
      }
      {
        name: 'CC_WS_MAX_CLIENTS'
        value: '20'
      }
    ]
    secrets: [
      {
        name: 'jwt-secret'
        keyVaultUrl: '${keyVault.outputs.endpoint}secrets/jwt-secret'
        identity: 'system'
      }
    ]
  }
}

// On-Demand Gateway
module gateway './app/gateway.bicep' = {
  scope: rg
  params: {
    location: location
    tags: tags
    name: 'on-demand-gateway'
    containerAppEnvironmentId: containerAppEnvironment.outputs.id
    imageName: 'helixcare/gateway:latest'
    environmentVariables: [
      {
        name: 'NEXUS_JWT_SECRET'
        secretRef: 'jwt-secret'
      }
      {
        name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
        value: monitoring.outputs.applicationInsightsConnectionString
      }
    ]
    secrets: [
      {
        name: 'jwt-secret'
        keyVaultUrl: '${keyVault.outputs.endpoint}secrets/jwt-secret'
        identity: 'system'
      }
    ]
  }
}

// Static Web App (Command Centre Frontend)
module staticWebApp './app/static-web-app.bicep' = {
  scope: rg
  params: {
    location: location
    tags: tags
    name: 'helixcare-cc-${resourceToken}'
    sku: 'Free'
  }
}

// Store secrets in Key Vault
module keyVaultSecrets './core/security/keyvault-secrets.bicep' = {
 scope: rg
  params: {
    keyVaultName: keyVault.outputs.name
    jwtSecret: jwtSecret
    openAIApiKey: openAIApiKey
    azureOpenAIKey: deployAzureOpenAI ? (openai.?outputs.?key ?? '') : ''
    deployAzureOpenAI: deployAzureOpenAI
  }
}

// Outputs for azd
output AZURE_LOCATION string = location
output AZURE_TENANT_ID string = tenant().tenantId
output AZURE_RESOURCE_GROUP string = rg.name

output APPLICATIONINSIGHTS_CONNECTION_STRING string = monitoring.outputs.applicationInsightsConnectionString
output AZURE_KEY_VAULT_ENDPOINT string = keyVault.outputs.endpoint
output AZURE_KEY_VAULT_NAME string = keyVault.outputs.name

output COMMAND_CENTRE_URL string = commandCentreBackend.outputs.uri
output GATEWAY_URL string = gateway.outputs.uri
output STATIC_WEB_APP_URL string = staticWebApp.outputs.defaultHostname

output AZURE_OPENAI_ENDPOINT string = deployAzureOpenAI ? (openai.?outputs.?endpoint ?? '') : ''
output AZURE_OPENAI_DEPLOYED bool = deployAzureOpenAI
