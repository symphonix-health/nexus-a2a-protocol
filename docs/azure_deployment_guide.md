# HelixCare Azure Deployment Guide

## Overview

This guide provides step-by-step instructions for deploying the HelixCare NEXUS A2A Protocol system to Microsoft Azure. The deployment transforms the localhost development environment (25+ Python agents on ports 8021-8067) into a production-ready, scalable Azure Container Apps architecture.

**Target Architecture:**
- 33 Container Apps (25 agents + 8 interop/infrastructure services)
- Azure Container Apps Environment with VNet integration
- Azure OpenAI Service (GPT-4o-mini + TTS)
- Redis Cache, Blob Storage, App Configuration
- Key Vault for secret management
- Application Insights for distributed tracing
- Static Web App for Command Centre frontend

**Deployment Method:** Azure Developer CLI (AZD) + Bicep Infrastructure-as-Code

---

## Prerequisites

### 1. Required Software

| Tool | Version | Installation |
|------|---------|--------------|
| **Azure CLI** | ≥ 2.57.0 | `winget install Microsoft.AzureCLI` |
| **Azure Developer CLI (AZD)** | ≥ 1.6.0 | `winget install Microsoft.Azd` |
| **Docker Desktop** | ≥ 24.0 | [Download](https://www.docker.com/products/docker-desktop) |
| **Python** | 3.12 | `.venv/Scripts/python.exe` (project venv) |
| **Git** | ≥ 2.40 | `winget install Git.Git` |
| **VS Code** | Latest | `winget install Microsoft.VisualStudioCode` |

Verify installations:
```powershell
az --version
azd version
docker --version
python --version
git --version
```

### 2. Azure Account Setup

1. **Azure Subscription**
   - Active Azure subscription with Owner or Contributor role
   - Sufficient quota for Container Apps (33 instances)
   - Azure OpenAI Service access (requires [application](https://aka.ms/oai/access))

2. **Sign in to Azure**
   ```bash
   az login
   az account show  # Verify correct subscription
   az account set --subscription "Your Subscription Name"  # If needed
   ```

3. **Register Resource Providers**
   ```bash
   az provider register --namespace Microsoft.App
   az provider register --namespace Microsoft.ContainerRegistry
   az provider register --namespace Microsoft.KeyVault
   az provider register --namespace Microsoft.CognitiveServices
   az provider register --namespace Microsoft.Cache
   az provider register --namespace Microsoft.Storage
   az provider register --namespace Microsoft.AppConfiguration
   az provider register --namespace Microsoft.Web

   # Wait for registration (5-10 minutes)
   az provider show --namespace Microsoft.App --query "registrationState"
   ```

### 3. Cost Considerations

**Estimated Monthly Cost (Development Environment):**
- Container Apps: ~$200-300 (33 apps @ 0.5 vCPU/1 GB, scale-to-zero)
- Azure OpenAI: ~$50-150 (usage-based: $0.15/1M input tokens, $0.60/1M output tokens)
- Redis Cache: ~$16 (Basic C0 - 250 MB)
- Blob Storage: ~$5 (Standard ZRS, 10 GB)
- App Configuration: ~$1.20 (Standard tier)
- Key Vault: ~$0.30 (secrets + transactions)
- Application Insights: ~$20 (5 GB ingestion)
- Static Web App: $0 (Free tier)
- **Total: ~$300-500/month**

**Production Environment:**
- Scale resources: 1-10 replicas per agent → ~$1,500-3,000/month
- Premium Redis (P1 - 6 GB): ~$250/month
- See [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/)

### 4. OpenAI Configuration

**Option A: Azure OpenAI (Recommended for Production)**
- Apply for access: https://aka.ms/oai/access
- Wait 1-3 business days for approval
- Deployment will create: `gpt-4o-mini` (100K TPM) + `gpt-4o-mini-tts` (50K TPM)

**Option B: OpenAI Cloud API**
- Get API key from https://platform.openai.com/api-keys
- Set during deployment: `azd env set OPENAI_API_KEY <your-key>`
- Cost: Similar to Azure OpenAI but external billing

---

## Quick Start (5 Minutes)

For experienced users with prerequisites met:

```bash
# Clone and navigate
cd c:\nexus-a2a-protocol

# Initialize AZD environment
azd init --environment helixcare-dev

# Set deployment parameters (if using OpenAI Cloud)
azd env set OPENAI_API_KEY "sk-..."  # Skip if using Azure OpenAI

# Deploy everything (20-30 minutes)
azd up

# Get Command Centre URL
azd env get-values | Select-String "COMMAND_CENTRE_URL"

# Open dashboard
azd env get-values | ConvertFrom-Json | % { Start-Process $_.COMMAND_CENTRE_URL }
```

---

## Detailed Deployment Steps

### Step 1: Prepare Repository

```bash
# Navigate to project root
cd c:\nexus-a2a-protocol

# Ensure clean working directory
git status

# Pull latest changes
git pull origin main

# Activate Python virtual environment
.\.venv\Scripts\Activate.ps1

# Verify dependencies
pip install -r requirements.txt
```

### Step 2: Initialize AZD Environment

```bash
# Initialize with environment name
azd init --environment helixcare-dev

# AZD creates:
# - .azure/helixcare-dev/.env (environment variables)
# - azure.yaml reference to infra/main.bicep
```

**Environment Naming Convention:**
- Development: `helixcare-dev`
- Staging: `helixcare-staging`
- Production: `helixcare-prod`

### Step 3: Configure Deployment Parameters

#### Required Parameters

```bash
# Azure region (choose closest to users)
azd env set AZURE_LOCATION "eastus"  # or "westeurope", "australiaeast"

# Environment name (matches azd init)
azd env set AZURE_ENV_NAME "helixcare-dev"

# Your Azure AD user/service principal ID (for Key Vault access)
$principalId = (az ad signed-in-user show --query id -o tsv)
azd env set AZURE_PRINCIPAL_ID $principalId

# JWT secret for protocol authentication (generate strong secret)
$jwtSecret = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | % {[char]$_})
azd env set NEXUS_JWT_SECRET $jwtSecret
```

#### OpenAI Configuration

**Option A: Use Azure OpenAI**
```bash
azd env set DEPLOY_AZURE_OPENAI "true"
# No API key needed; uses Azure managed identity
```

**Option B: Use OpenAI Cloud**
```bash
azd env set DEPLOY_AZURE_OPENAI "false"
azd env set OPENAI_API_KEY "sk-proj-..."
```

#### Optional Parameters

```bash
# Custom deployments (default: gpt-4o-mini + tts)
azd env set OPENAI_DEPLOYMENTS '[{"name":"gpt-4o-mini","model":"gpt-4o-mini","version":"2024-07-18","capacity":100000},{"name":"gpt-4o-mini-tts","model":"gpt-4o-mini-tts","version":"2024-07-18","capacity":50000}]'

# Video clinician provider (default: local_gpu for Azure)
azd env set VIDEO_CLINICIAN_PROVIDER "local_gpu"

# Avatar session TTL (default: 1800 seconds)
azd env set AVATAR_SESSION_IDLE_TTL "1800"

# Command Centre poll interval (default: 5000 ms)
azd env set UPDATE_INTERVAL_MS "5000"
```

### Step 4: Validate Bicep (Dry-Run)

```bash
# Preview changes without deploying
azd provision --preview

# Review output:
# - Resources to be created
# - Estimated costs
# - Parameter validation
# - Dependency graph
```

**Expected Resources:**
- 1 Resource Group: `rg-helixcare-dev`
- 33 Container Apps: `ca-helixcare-dev-triage-agent`, etc.
- 1 Container App Environment: `cae-helixcare-dev`
- 1 Virtual Network: `vnet-helixcare-dev`
- 1 Key Vault: `kv-helixcare-dev-<hash>`
- 1 Storage Account: `sthelixcaredev<hash>`
- 1 Redis Cache: `redis-helixcare-dev`
- 1 App Configuration: `appcs-helixcare-dev`
- 1 Azure OpenAI: `oai-helixcare-dev` (if enabled)
- 1 Log Analytics Workspace: `log-helixcare-dev`
- 1 Application Insights: `appi-helixcare-dev`
- 1 Static Web App: `stapp-helixcare-dev-command-centre`

### Step 5: Deploy Infrastructure

```bash
# Provision Azure resources (15-20 minutes)
azd provision
```

**Deployment Flow:**
1. Creates resource group
2. Deploys VNet, subnets, NSGs
3. Provisions Key Vault, stores JWT secret
4. Creates Container App Environment with VNet integration
5. Deploys data services (Storage, Redis, App Configuration)
6. Provisions Azure OpenAI (if enabled)
7. Deploys 33 Container Apps (placeholder image)
8. Sets up Application Insights
9. Configures RBAC assignments
10. Outputs connection strings and URLs

**Monitor Progress:**
```bash
# In separate terminal, watch resource group
az resource list --resource-group rg-helixcare-dev --output table --query "[].{Name:name, Type:type, Status:provisioningState}"
```

### Step 6: Build and Deploy Container Images

```bash
# Build Docker images + push to ACR + deploy (30-40 minutes)
azd deploy
```

**Build Process (per agent):**
1. Docker builds multi-stage Python 3.12 image
2. Installs dependencies from `requirements.txt`
3. Copies agent code + shared libs
4. Pushes to Azure Container Registry
5. Updates Container App revision
6. Waits for health check

**Parallel Builds:** AZD builds 5 services concurrently by default.

### Step 7: Verify Deployment

```bash
# Get all outputs
azd env get-values

# Test Command Centre backend
$ccUrl = (azd env get-values | ConvertFrom-Json).COMMAND_CENTRE_URL
curl "$ccUrl/health"

# Test Gateway
$gwUrl = (azd env get-values | ConvertFrom-Json).GATEWAY_URL
curl "$gwUrl/health"

# Test Avatar agent (via Gateway)
curl "$gwUrl/rpc" -X POST -H "Content-Type: application/json" `
  -d '{"jsonrpc":"2.0","method":"clinician_avatar_agent.hello","params":{},"id":1}'
```

### Step 8: Configure Frontend (Static Web App)

```bash
# Deploy Command Centre frontend
cd shared/command-centre
npm install
npm run build

# Deploy to Static Web App
az staticwebapp deploy `
  --name stapp-helixcare-dev-command-centre `
  --resource-group rg-helixcare-dev `
  --app-location "shared/command-centre/app/static" `
  --output-location "shared/command-centre/app/static"

cd ../..
```

### Step 9: Upload Configuration Files

```bash
# Upload agents.json to App Configuration
$appConfigName = (azd env get-values | ConvertFrom-Json).AZURE_APP_CONFIGURATION_NAME
az appconfig kv set `
  --name $appConfigName `
  --key "agents" `
  --value (Get-Content config/agents.json -Raw) `
  --content-type "application/json"

# Upload personas.json
az appconfig kv set `
  --name $appConfigName `
  --key "personas" `
  --value (Get-Content config/personas.json -Raw) `
  --content-type "application/json"

# Upload agent_personas.json
az appconfig kv set `
  --name $appConfigName `
  --key "agent_personas" `
  --value (Get-Content config/agent_personas.json -Raw) `
  --content-type "application/json"
```

### Step 10: Test End-to-End

```bash
# Open Command Centre dashboard
$ccUrl = (azd env get-values | ConvertFrom-Json).COMMAND_CENTRE_URL
Start-Process $ccUrl

# Run scenario via Gateway
python tools/helixcare_scenarios.py `
  --run chest_pain_cardiac `
  --gateway $gwUrl `
  --verbose
```

---

## VS Code Integration

### One-Click Deployment Tasks

VS Code tasks are pre-configured in `.vscode/tasks.json`:

1. **Azure: Validate Bicep (What-If)**
   - Ctrl+Shift+P → "Tasks: Run Task" → "Azure: Validate Bicep"
   - Shows deployment preview without making changes

2. **Azure: Deploy All (Up)**
   - One command: provision + build + deploy
   - Recommended for first deployment

3. **Azure: Deploy Infrastructure**
   - Re-provision Bicep changes only
   - Faster when only updating infrastructure

4. **Azure: Deploy Application**
   - Rebuild images + update Container Apps
   - Use after code changes

5. **Azure: View Agent Logs**
   - Live log streaming from Container Apps
   - Pre-configured for Command Centre, Avatar

6. **Azure: Scale Agent (Interactive)**
   - Adjust min/max replicas
   - Useful for load testing

7. **Azure: Open Command Centre**
   - Retrieves COMMAND_CENTRE_URL and opens browser

8. **Azure: Delete Resources (Down)**
   - Destroys all Azure resources
   - Includes `--purge` for Key Vault

### Custom HelixCare Infrastructure Agent

The project includes a specialized VS Code agent:

**Location:** `.github/agents/helixcare-infra.agent.md`

**Use with:** `@helixcare-infra` in GitHub Copilot chat

**Capabilities:**
- Bicep template generation and validation
- Azure resource troubleshooting
- Cost optimization recommendations
- IAM group → RBAC mapping
- HIPAA/GDPR compliance checks
- Container Apps scaling guidance

**Example:**
```
@helixcare-infra how do I add a new agent to the deployment?
@helixcare-infra optimize Redis costs for staging environment
@helixcare-infra validate HIPAA compliance for audit logs
```

---

## Configuration Reference

### Bicep Parameters

**File:** `infra/main.bicep`

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `environmentName` | string | *(from azd)* | Environment suffix (dev, staging, prod) |
| `location` | string | `eastus` | Azure region |
| `principalId` | string | *(required)* | Your Azure AD user/SP ID for Key Vault access |
| `deployAzureOpenAI` | bool | `true` | Deploy Azure OpenAI vs. use OpenAI Cloud |
| `openAIDeployments` | array | *[gpt-4o-mini, tts]* | Azure OpenAI models to deploy |
| `openAIApiKey` | securestring | `''` | OpenAI Cloud API key (if not using Azure) |
| `jwtSecret` | securestring | *(generated)* | JWT signing secret for nexus:invoke |

### Environment Variables (Container Apps)

All 33 Container Apps inherit these environment variables:

| Variable | Value | Purpose |
|----------|-------|---------|
| `NEXUS_JWT_SECRET` | *Key Vault ref* | Protocol authentication |
| `OPENAI_API_KEY` | *Key Vault ref* | OpenAI Cloud access (if used) |
| `AZURE_OPENAI_ENDPOINT` | *Output* | Azure OpenAI endpoint (if deployed) |
| `AZURE_OPENAI_KEY` | *Key Vault ref* | Azure OpenAI access key |
| `AZURE_OPENAI_DEPLOYMENT` | `gpt-4o-mini` | Default LLM model |
| `AZURE_OPENAI_TTS_DEPLOYMENT` | `gpt-4o-mini-tts` | TTS model for avatar |
| `REDIS_HOST` | *Redis hostname* | Session cache endpoint |
| `REDIS_PASSWORD` | *Key Vault ref* | Redis access key |
| `APPINSIGHTS_INSTRUMENTATIONKEY` | *App Insights key* | Distributed tracing |
| `VIDEO_CLINICIAN_PROVIDER` | `local_gpu` | Avatar engine mode |
| `DID_VERIFY` | `false` | D-ID signature verification |
| `AVATAR_SESSION_IDLE_TTL` | `1800` | Session TTL (seconds) |
| `UPDATE_INTERVAL_MS` | `5000` | Command Centre poll interval |

**Agent-Specific:**
- `PORT`: Container internal port (80)
- `AGENT_ID`: Agent identifier (e.g., `triage_agent`)
- `AGENT_NAME`: Display name from persona
- `IAM_GROUPS`: Comma-separated IAM groups

### Key Vault Secrets

**Naming Convention:** `kv-<env>-<hash>` (e.g., `kv-helixcare-dev-a1b2c3d4`)

| Secret Name | Purpose |
|-------------|---------|
| `jwt-secret` | Protocol JWT HS256 signing key |
| `openai-api-key` | OpenAI Cloud API key (if not Azure) |
| `azure-openai-key` | Azure OpenAI access key (if deployed) |

**Access Policy:** System-assigned Managed Identity per Container App with "Key Vault Secrets User" role.

### App Configuration Keys

**Store Name:** `appcs-<env>`

| Key | Content-Type | Source |
|-----|--------------|--------|
| `agents` | `application/json` | `config/agents.json` |
| `personas` | `application/json` | `config/personas.json` |
| `agent_personas` | `application/json` | `config/agent_personas.json` |

**Access:** Agents query App Configuration at runtime for dynamic persona updates.

---

## Troubleshooting

### Deployment Failures

#### Issue: "Resource provider not registered"
```
Error: The subscription is not registered to use namespace 'Microsoft.App'
```

**Solution:**
```bash
az provider register --namespace Microsoft.App
az provider show --namespace Microsoft.App --query "registrationState"
# Wait until "Registered" (5-10 minutes)
```

#### Issue: "Insufficient quota"
```
Error: Operation could not be completed as it results in exceeding approved quota.
```

**Solution:**
1. Check current usage:
   ```bash
   az vm list-usage --location eastus --output table
   ```
2. Request quota increase:
   - Azure Portal → Subscriptions → Usage + quotas
   - Select "Container Apps" → "Request increase"
   - Specify: 100 vCores for Container Apps Environment

#### Issue: "Azure OpenAI access denied"
```
Error: Azure OpenAI access is restricted. Please apply for access.
```

**Solution:**
1. Apply: https://aka.ms/oai/access
2. Wait 1-3 business days
3. **Or** use OpenAI Cloud:
   ```bash
   azd env set DEPLOY_AZURE_OPENAI "false"
   azd env set OPENAI_API_KEY "sk-..."
   ```

#### Issue: "Key Vault access denied"
```
Error: The user or service principal does not have secrets get permission
```

**Solution:**
```bash
# Verify principalId
$principalId = (az ad signed-in-user show --query id -o tsv)
echo $principalId

# Re-set in AZD
azd env set AZURE_PRINCIPAL_ID $principalId

# Re-deploy
azd provision
```

### Runtime Issues

#### Issue: Agent health checks failing
```
Container App: ca-helixcare-dev-triage-agent
Status: Provisioning
Health: Unhealthy
```

**Diagnosis:**
```bash
# View logs
az containerapp logs show `
  --name ca-helixcare-dev-triage-agent `
  --resource-group rg-helixcare-dev `
  --follow

# Check revision status
az containerapp revision list `
  --name ca-helixcare-dev-triage-agent `
  --resource-group rg-helixcare-dev `
  --output table
```

**Common Causes:**
1. Missing environment variable (check `NEXUS_JWT_SECRET`, `OPENAI_API_KEY`)
2. Key Vault access denied (verify Managed Identity RBAC)
3. Application startup error (check logs for Python exceptions)
4. Port mismatch (ensure `PORT=80` and `targetPort=80`)

#### Issue: "No healthy revision"
```
Error: The container app has no healthy revision.
```

**Solution:**
```bash
# Get latest revision
$revision = (az containerapp revision list `
  --name ca-helixcare-dev-triage-agent `
  --resource-group rg-helixcare-dev `
  --query "[0].name" -o tsv)

# View revision details
az containerapp revision show `
  --name ca-helixcare-dev-triage-agent `
  --resource-group rg-helixcare-dev `
  --revision $revision

# Restart revision
az containerapp revision restart `
  --name ca-helixcare-dev-triage-agent `
  --resource-group rg-helixcare-dev `
  --revision $revision
```

#### Issue: Command Centre not loading agents
```
Dashboard shows: "No agents available"
```

**Diagnosis:**
1. Check Command Centre logs:
   ```bash
   az containerapp logs show `
     --name ca-helixcare-dev-command-centre-backend `
     --resource-group rg-helixcare-dev `
     --follow
   ```
2. Verify agent URLs in App Configuration:
   ```bash
   $appConfigName = (azd env get-values | ConvertFrom-Json).AZURE_APP_CONFIGURATION_NAME
   az appconfig kv list --name $appConfigName --query "[?key=='agents']"
   ```
3. Test direct agent health:
   ```bash
   $agentUrl = "https://ca-helixcare-dev-triage-agent.internal.example.com"
   curl "$agentUrl/health"
   ```

**Solution:**
- Ensure all Container Apps are running (scale > 0)
- Verify internal ingress DNS resolution
- Check Application Insights for connection errors

#### Issue: Avatar TTS not working
```
Browser console: "WebSocket disconnected", "TTS fallback to SpeechSynthesis"
```

**Diagnosis:**
1. Check avatar logs:
   ```bash
   az containerapp logs show `
     --name ca-helixcare-dev-clinician-avatar-agent `
     --resource-group rg-helixcare-dev `
     --follow
   ```
2. Verify OpenAI configuration:
   ```bash
   azd env get-values | Select-String "OPENAI"
   ```
3. Test TTS endpoint:
   ```bash
   $avatarUrl = (azd env get-values | ConvertFrom-Json).GATEWAY_URL
   curl "$avatarUrl/rpc" -X POST -H "Content-Type: application/json" `
     -d '{"jsonrpc":"2.0","method":"clinician_avatar_agent.stream_tts","params":{"text":"Hello"},"id":1}'
   ```

**Solution:**
- Ensure `OPENAI_API_KEY` or `AZURE_OPENAI_KEY` is set
- Verify Key Vault secret reference is correct
- Check OpenAI rate limits (429 errors)

### Networking Issues

#### Issue: "Cannot connect to internal agent URL"
```
Error: Failed to resolve 'ca-helixcare-dev-triage-agent.internal.<env>.azurecontainerapps.io'
```

**Solution:**
- Internal DNS only works **within Container App Environment**
- Command Centre, Gateway, and agents share same environment → should work
- External access: Use Gateway as proxy; agents have `external: false` ingress

#### Issue: "Static Web App not accessing backend"
```
CORS error: 'Access-Control-Allow-Origin' header missing
```

**Solution:**
1. Update Command Centre backend CORS settings:
   ```bash
   az containerapp update `
     --name ca-helixcare-dev-command-centre-backend `
     --resource-group rg-helixcare-dev `
     --set-env-vars "CORS_ORIGINS=https://stapp-helixcare-dev-command-centre.azurestaticapps.net"
   ```
2. Or configure in `main.bicep` (under `commandCentreBackend` module):
   ```bicep
   {
     name: 'CORS_ORIGINS'
     value: staticWebApp.outputs.defaultHostname
   }
   ```

---

## Cost Management

### Cost Optimization Strategies

#### 1. Scale-to-Zero (Development)
```bash
# Set min replicas to 0 for unused agents
az containerapp update `
  --name ca-helixcare-dev-consent-analyser `
  --resource-group rg-helixcare-dev `
  --min-replicas 0 `
  --max-replicas 5
```

**Savings:** ~70% reduction for agents with infrequent use.

#### 2. Downgrade Redis (Staging)
For non-production environments:
```bicep
// infra/data/redis.bicep
sku: {
  name: 'Basic'
  family: 'C'
  capacity: 0  // 250 MB - $16/month vs P1 6 GB - $250/month
}
```

#### 3. Use OpenAI Cloud (Small Deployments)
Azure OpenAI has minimum capacity commitment (10K TPM):
```bash
azd env set DEPLOY_AZURE_OPENAI "false"
azd env set OPENAI_API_KEY "sk-..."
```

**Savings:** Pay-as-you-go for low-traffic scenarios.

#### 4. Reduce Application Insights Retention
```bicep
// infra/core/monitor/app-insights.bicep
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  properties: {
    retentionInDays: 7  // vs 30 default
    //...
  }
}
```

**Savings:** ~60% reduction on ingestion costs for dev/staging.

#### 5. Consolidate Small Agents
Deploy multiple agents in one Container App:
```bash
# Merge agents with < 100 req/day
# E.g., consent_analyser + hitl_ui → consent-verification-app
```

**Savings:** ~30% reduction on idle compute.

### Cost Monitoring

#### View Current Costs
```bash
# Month-to-date total
az costmanagement query `
  --type Usage `
  --dataset-filter "{\"and\":[{\"dimensions\":{\"name\":\"ResourceGroup\",\"operator\":\"In\",\"values\":[\"rg-helixcare-dev\"]}}]}" `
  --timeframe MonthToDate

# By resource type
az costmanagement query `
  --type Usage `
  --dataset-grouping name="ResourceType" type="Dimension" `
  --dataset-filter "{\"and\":[{\"dimensions\":{\"name\":\"ResourceGroup\",\"operator\":\"In\",\"values\":[\"rg-helixcare-dev\"]}}]}" `
  --timeframe MonthToDate
```

#### Set Budget Alert
```bash
az consumption budget create `
  --budget-name "helixcare-dev-monthly" `
  --amount 500 `
  --time-grain Monthly `
  --start-date (Get-Date -Format "yyyy-MM-01") `
  --end-date (Get-Date -Year 2025 -Month 12 -Day 31 -Format "yyyy-MM-dd") `
  --scope "/subscriptions/<subscription-id>/resourceGroups/rg-helixcare-dev" `
  --category Cost `
  --notifications "{
    \"Actual_GreaterThan_80_Percent\": {
      \"enabled\": true,
      \"operator\": \"GreaterThan\",
      \"threshold\": 80,
      \"contactEmails\": [\"admin@example.com\"]
    }
  }"
```

#### Cost Analysis Dashboard
- Azure Portal → Cost Management → Cost analysis
- Filter: Resource group = `rg-helixcare-dev`
- Group by: Resource type, Resource, Tag
- Export: Schedule daily CSV to email

---

## Scaling and Performance

### Horizontal Scaling (Replicas)

#### Auto-Scale Rules (Default)
```bicep
scale: {
  minReplicas: 0
  maxReplicas: 5
  rules: [
    {
      name: 'http-scaling'
      http: {
        metadata: {
          concurrentRequests: '10'
        }
      }
    }
  ]
}
```

#### Manual Scaling (Production)
```bash
# High-traffic agents (Avatar, Command Centre)
az containerapp update `
  --name ca-helixcare-prod-clinician-avatar-agent `
  --resource-group rg-helixcare-prod `
  --min-replicas 3 `
  --max-replicas 20

# Always-on critical services
az containerapp update `
  --name ca-helixcare-prod-command-centre-backend `
  --resource-group rg-helixcare-prod `
  --min-replicas 2 `
  --max-replicas 10
```

#### CPU-Based Scaling
```bicep
scale: {
  minReplicas: 1
  maxReplicas: 10
  rules: [
    {
      name: 'cpu-scaling'
      custom: {
        type: 'cpu'
        metadata: {
          type: 'Utilization'
          value: '70'
        }
      }
    }
  ]
}
```

### Vertical Scaling (Resources)

#### Increase Agent CPU/Memory
```bash
# For memory-intensive agents (Gateway, Diagnosis)
az containerapp update `
  --name ca-helixcare-prod-on-demand-gateway `
  --resource-group rg-helixcare-prod `
  --cpu 4 `
  --memory 8Gi
```

#### Container App Limits
- Max vCPU per container: 4.0
- Max memory per container: 8 Gi
- Max containers per replica: 10
- Max replicas per app: 300

**Note:** For >4 vCPU or >8 GB, use multiple replicas instead.

### Database/Cache Scaling

#### Upgrade Redis for Production
```bicep
// infra/data/redis.bicep (production)
sku: {
  name: 'Premium'
  family: 'P'
  capacity: 1  // 6 GB, 20K ops/sec, data persistence
}
```

#### Blob Storage Performance
```bicep
// infra/data/storage.bicep (production)
sku: {
  name: 'Premium_ZRS'  // vs Standard_ZRS
}
kind: 'BlockBlobStorage'
```

**Impact:** 10x IOPS (100K vs 10K), <10ms latency for audit logs.

### Load Testing

#### Simulate 1000 Concurrent Sessions
```bash
# Install k6 load testing tool
winget install k6.k6

# Run scenario load test
k6 run --vus 1000 --duration 10m tools/k6_avatar_scenario.js
```

#### Monitor Performance
```bash
# Application Insights query (KQL)
az monitor app-insights query `
  --app appi-helixcare-prod `
  --analytics-query "
    requests
    | where timestamp > ago(1h)
    | summarize
        AvgDuration = avg(duration),
        P95Duration = percentile(duration, 95),
        RequestCount = count()
      by name
    | order by AvgDuration desc
  "
```

---

## Security Hardening

### Secrets Management

#### Rotate JWT Secret
```bash
# Generate new secret
$newSecret = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | % {[char]$_})

# Update Key Vault
az keyvault secret set `
  --vault-name kv-helixcare-prod-<hash> `
  --name jwt-secret `
  --value $newSecret

# Restart all agents (triggers secret refresh)
az containerapp revision restart `
  --name ca-helixcare-prod-* `
  --resource-group rg-helixcare-prod
```

#### Rotate OpenAI Key
```bash
# Regenerate key in Azure OpenAI Studio
# Update Key Vault secret
az keyvault secret set `
  --vault-name kv-helixcare-prod-<hash> `
  --name azure-openai-key `
  --value "<new-key>"

# Restart agents
az containerapp list --resource-group rg-helixcare-prod --query "[].name" -o tsv | ForEach-Object {
  az containerapp revision restart --name $_ --resource-group rg-helixcare-prod
}
```

### Network Security

#### Enable VNet Restrictions
```bicep
// infra/core/host/container-app-environment.bicep
properties: {
  vnetConfiguration: {
    infrastructureSubnetId: infrastructureSubnetId
    internal: true  // No public IPs
  }
}
```

**Impact:** Agents only accessible via Gateway; Gateway only via VPN/ExpressRoute.

#### Add Application Gateway (WAF)
```bash
# Deploy WAF in front of Command Centre
az network application-gateway create `
  --name agw-helixcare-prod `
  --resource-group rg-helixcare-prod `
  --vnet-name vnet-helixcare-prod `
  --subnet agw-subnet `
  --sku WAF_v2 `
  --http-settings-port 443 `
  --http-settings-protocol Https `
  --frontend-port 443 `
  --backend-pool-name command-centre-pool
```

**Benefits:** DDoS protection, SSL termination, rate limiting, OWASP Top 10 mitigation.

### Compliance Auditing

#### Enable Diagnostic Logs (HIPAA)
```bash
# Storage account for audit logs
$storageId = (az storage account show --name sthelixcareprod<hash> --resource-group rg-helixcare-prod --query id -o tsv)

# Enable for Key Vault
az monitor diagnostic-settings create `
  --name kv-audit-logs `
  --resource kv-helixcare-prod-<hash> `
  --storage-account $storageId `
  --logs '[{"category":"AuditEvent","enabled":true,"retentionPolicy":{"enabled":true,"days":2555}}]'

# Enable for Container App Environment
az monitor diagnostic-settings create `
  --name cae-audit-logs `
  --resource cae-helixcare-prod `
  --storage-account $storageId `
  --logs '[{"category":"ContainerAppConsoleLogs","enabled":true},{"category":"ContainerAppSystemLogs","enabled":true}]'
```

#### Verify Immutable Storage
```bash
# Check immutable policy (HIPAA requirement)
az storage account immutability-policy show `
  --account-name sthelixcareprod<hash> `
  --resource-group rg-helixcare-prod `
  --container-name audit-logs

# Expected: immutabilityPeriodSinceCreationInDays = 2555 (7 years)
```

---

## Operations Runbook

### Daily Operations

#### Health Check Script
```powershell
# tools/azure_health_check.ps1
$resourceGroup = "rg-helixcare-prod"

# Check all Container Apps status
az containerapp list --resource-group $resourceGroup --query "[].{Name:name, Status:properties.runningStatus, Replicas:properties.template.containers[0].resources.cpu}" --output table

# Check Redis availability
az redis show --name redis-helixcare-prod --resource-group $resourceGroup --query "provisioningState"

# Check Application Insights ingestion
az monitor app-insights metrics show `
  --app appi-helixcare-prod `
  --metric "requests/count" `
  --start-time (Get-Date).AddHours(-1) `
  --end-time (Get-Date)
```

#### Backup Configuration
```bash
# Export agents.json from App Configuration
az appconfig kv export `
  --name appcs-helixcare-prod `
  --destination file `
  --path "backups/agents-$(Get-Date -Format 'yyyy-MM-dd').json" `
  --format json `
  --key "agents"

# Backup Key Vault secrets (names only, not values)
az keyvault secret list --vault-name kv-helixcare-prod-<hash> --query "[].name" -o json > backups/secrets-$(Get-Date -Format 'yyyy-MM-dd').json
```

### Incident Response

#### High CPU Alert
```bash
# Identify culprit
az monitor metrics list `
  --resource ca-helixcare-prod-diagnosis-agent `
  --metric "CpuPercentage" `
  --start-time (Get-Date).AddHours(-1) `
  --interval PT1M

# Scale up
az containerapp update `
  --name ca-helixcare-prod-diagnosis-agent `
  --resource-group rg-helixcare-prod `
  --max-replicas 15

# Scale out (vertical)
az containerapp update `
  --name ca-helixcare-prod-diagnosis-agent `
  --resource-group rg-helixcare-prod `
  --cpu 2 `
  --memory 4Gi
```

#### Memory Leak Alert
```bash
# View memory trends
az monitor metrics list `
  --resource ca-helixcare-prod-avatar-agent `
  --metric "MemoryWorkingSetBytes" `
  --aggregation Average `
  --interval PT5M

# Restart specific revision
$revision = (az containerapp revision list --name ca-helixcare-prod-avatar-agent --resource-group rg-helixcare-prod --query "[0].name" -o tsv)
az containerapp revision restart `
  --name ca-helixcare-prod-avatar-agent `
  --resource-group rg-helixcare-prod `
  --revision $revision
```

#### Database Connection Pool Exhaustion
```bash
# Check Redis connections
az redis show --name redis-helixcare-prod --resource-group rg-helixcare-prod --query "port"

# View active connections (via Log Analytics)
az monitor log-analytics query `
  --workspace appi-helixcare-prod `
  --analytics-query "
    traces
    | where message contains 'Redis'
    | where timestamp > ago(30m)
    | summarize count() by bin(timestamp, 1m)
  "

# Solution: Increase Redis tier or optimize connection pooling
az redis update `
  --name redis-helixcare-prod `
  --resource-group rg-helixcare-prod `
  --sku Premium `
  --vm-size P1
```

### Disaster Recovery

#### Backup Strategy
- **Infrastructure (Bicep)**: Git repository (version control)
- **Configuration (App Config)**: Daily export to Blob Storage
- **Secrets (Key Vault)**: Soft-delete enabled (90 days), backup disabled (security policy)
- **Application Data (Redis)**: Premium tier enables RDB persistence
- **Audit Logs (Blob)**: Immutable storage (2555 days), geo-redundant (ZRS)

#### Recovery Procedure
```bash
# 1. Re-deploy infrastructure
azd provision --environment helixcare-dr

# 2. Restore configuration
az appconfig kv import `
  --name appcs-helixcare-dr `
  --source file `
  --path "backups/agents-2024-02-20.json" `
  --format json

# 3. Restore secrets (manual from secure backup)
az keyvault secret set --vault-name kv-helixcare-dr-<hash> --name jwt-secret --value "<backup>"

# 4. Deploy application
azd deploy --environment helixcare-dr

# 5. Update DNS/Gateway (point to new Command Centre URL)
```

**Recovery Time Objective (RTO):** 1 hour
**Recovery Point Objective (RPO):** 24 hours (daily config backups)

---

## Appendix

### A. Resource Naming Convention

| Resource Type | Abbreviation | Example |
|---------------|--------------|---------|
| Resource Group | `rg` | `rg-helixcare-prod` |
| Container App | `ca` | `ca-helixcare-prod-triage-agent` |
| Container App Environment | `cae` | `cae-helixcare-prod` |
| Virtual Network | `vnet` | `vnet-helixcare-prod` |
| Subnet | `snet` | `snet-helixcare-prod-containerapp` |
| Key Vault | `kv` | `kv-helixcare-prod-a1b2c3d4` |
| Storage Account | `st` | `sthelixcareprodabcd1234` |
| Redis Cache | `redis` | `redis-helixcare-prod` |
| App Configuration | `appcs` | `appcs-helixcare-prod` |
| Azure OpenAI | `oai` | `oai-helixcare-prod` |
| Log Analytics | `log` | `log-helixcare-prod` |
| Application Insights | `appi` | `appi-helixcare-prod` |
| Static Web App | `stapp` | `stapp-helixcare-prod-command-centre` |
| Container Registry | `cr` | `crhelixcareprodabcd1234` |

**Pattern:** `<abbr>-<env>-<resource>[-<hash>]`

### B. Port Mappings (Localhost → Azure)

| Agent | Localhost Port | Azure Internal URL |
|-------|----------------|-------------------|
| Triage Agent | 8021 | `https://ca-<env>-triage-agent.internal.<domain>` |
| Diagnosis Agent | 8022 | `https://ca-<env>-diagnosis-agent.internal.<domain>` |
| Imaging Agent | 8024 | `https://ca-<env>-imaging-agent.internal.<domain>` |
| Pharmacy Agent | 8025 | `https://ca-<env>-pharmacy-agent.internal.<domain>` |
| Avatar Agent | 8039 | `https://ca-<env>-clinician-avatar-agent.internal.<domain>` |
| Command Centre | 8099 | `https://ca-<env>-command-centre-backend.<domain>` (external) |
| Gateway | 8100 | `https://ca-<env>-on-demand-gateway.<domain>` (external) |

**Note:** All agents use internal ingress except Command Centre and Gateway.

### C. IAM Group → RBAC Mapping

**Azure Entra ID Groups:**
- `nexus-clinical-high` → `Contributor` (elevated resource access)
- `nexus-clinical-medium` → `Reader` + custom role (view resources)
- `nexus-operations` → `Monitoring Reader` (metrics, logs)
- `nexus-governance` → `Security Reader` (audit logs, Key Vault metadata)
- `nexus-connector` → Custom role (Read App Config, Read Key Vault secrets)
- `nexus-intelligence` → `Log Analytics Reader` (OpenSearch, Analytics)

**Implementation:** Assign during agent deployment via `roleAssignments` in Bicep.

### D. Useful Links

- **Azure Container Apps Docs:** https://learn.microsoft.com/azure/container-apps/
- **Azure Developer CLI:** https://learn.microsoft.com/azure/developer/azure-developer-cli/
- **Bicep Language Reference:** https://learn.microsoft.com/azure/azure-resource-manager/bicep/
- **Azure OpenAI Service:** https://learn.microsoft.com/azure/ai-services/openai/
- **Application Insights:** https://learn.microsoft.com/azure/azure-monitor/app/app-insights-overview
- **Cost Management:** https://learn.microsoft.com/azure/cost-management-billing/

### E. Support Contacts

- **Azure Support:** https://azure.microsoft.com/support/options/
- **HelixCare Project Issues:** https://github.com/your-org/nexus-a2a-protocol/issues
- **Security Incidents:** security@your-org.com
- **On-Call Rotation:** PagerDuty integration (see `docs/oncall.md`)

---

## Changelog

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2024-02-20 | Initial deployment guide for AZD + Bicep workflow |

---

**Last Updated:** 2024-02-20
**Authors:** HelixCare Infrastructure Team
**License:** Proprietary — Internal Use Only
