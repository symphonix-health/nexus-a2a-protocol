param keyVaultName string

@secure()
param jwtSecret string

@secure()
param openAIApiKey string = ''

@secure()
param azureOpenAIKey string = ''

param deployAzureOpenAI bool

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource jwtSecretValue 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'jwt-secret'
  properties: {
    value: jwtSecret
  }
}

resource openaiApiKeyValue 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!deployAzureOpenAI && !empty(openAIApiKey)) {
  parent: keyVault
  name: 'openai-api-key'
  properties: {
    value: openAIApiKey
  }
}

resource azureOpenaiKeyValue 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (deployAzureOpenAI && !empty(azureOpenAIKey)) {
  parent: keyVault
  name: 'azure-openai-key'
  properties: {
    value: azureOpenAIKey
  }
}

output jwtSecretName string = jwtSecretValue.name
