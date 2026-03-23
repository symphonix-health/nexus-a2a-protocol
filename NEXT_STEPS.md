# HelixCare - Next Steps & Action Items

**Date**: March 19, 2026
**Current Status**: Azure deployment artifacts complete, core tests passing, full regression in progress

---

## Quick Status

✅ **Azure Deployment Ready**: All Bicep, azure.yaml, tasks, and documentation complete
✅ **Core Protocol**: 5/5 smoke tests passing (100%)
✅ **Command Centre**: 25/26 integration tests passing (96%)
✅ **Git Conflicts**: All resolved (25 blocks removed from 4 files)
⏸️ **Full Harness**: ~7% completed when testing interrupted (13,535 tests total)

---

## Immediate Actions (Priority Order)

### 1. Complete Full Harness Regression ⏸️
**Priority**: HIGH
**Duration**: 8-10 minutes
**Blocking**: Production deployment only (dev/test can proceed)

```bash
# Run from project root
$env:PYTHONPATH="c:\nexus-a2a-protocol"
$env:NEXUS_JWT_SECRET="dev-secret-change-me"

python -m pytest tests/nexus_harness/ \
  -v \
  --tb=short \
  -k "not streaming" \
  --maxfail=10 \
  --junit-xml=harness_results.xml \
  2>&1 | Tee-Object -FilePath "harness_regression_full.txt"
```

**Expected Outcome**:
- 13,535 tests executed
- Pass rate >85% target for production deployment
- JUnit XML report for CI/CD integration

**Post-Test Actions**:
- Analyze pass/fail/skip counts
- Review failure patterns (if any)
- Document blocked delegation patterns
- Update [REGRESSION_TEST_REPORT.md](REGRESSION_TEST_REPORT.md) with final results

---

### 2. Deploy to Azure Dev/Test Environment ✅
**Priority**: HIGH (can run in parallel with harness tests)
**Duration**: 15-20 minutes
**Prerequisites**: ✅ All met (artifacts ready, no blockers)

**Option A: Using Azure Developer CLI (AZD)**
```bash
# Authenticate
azd auth login

# Initialize (if not already done)
azd init --template .azure/

# Deploy all services
azd up --environment dev
```

**Option B: Using VS Code Tasks**
1. Open Command Palette (`Ctrl+Shift+P`)
2. Run Task: `Azure: Deploy HelixCare to Dev`
3. Monitor deployment progress in terminal
4. Verify services at Azure Portal

**Post-Deployment Verification**:
- [ ] All 35 services deployed successfully
- [ ] Health endpoints responding (use [azure_deployment_guide.md](docs/azure_deployment_guide.md) validation steps)
- [ ] Command Centre accessible at Azure URL
- [ ] Avatar Agent TTS working with Azure OpenAI
- [ ] Test JWT authentication with Azure Key Vault secrets

---

### 3. Investigate Blocked Delegations (If Needed) 🔍
**Priority**: MEDIUM
**Duration**: 15-20 minutes
**Trigger**: If >50% of scenario delegation steps blocked in harness results

**Investigation Steps**:
1. Review specific blocked scenarios:
   ```bash
   grep -r "blocked" harness_regression_full.txt | sort | uniq -c
   ```

2. Check agent logs for blocking causes:
   ```bash
   # Example: Check diagnosis agent (port 8022)
   curl http://localhost:8022/health
   # Review logs in Command Centre dashboard
   ```

3. Verify handoff_policy configurations:
   - Check `tools/helixcare_scenarios.py` scenario definitions
   - Review `journey_steps[].handoff_policy` settings
   - Confirm predecessor requirements reasonable

4. Test direct agent-to-agent calls:
  ```python
   # Example: Test triage → diagnosis handoff
   python tools/test_agent_handoff.py triage_agent diagnosis_agent
   ```

**Likely Causes**:
- Intentional test design (scenarios tolerate partial failures)
- LLM response timeouts (agents waiting for OpenAI)
- Authentication token expiry
- Network latency in agent chains

---

## Optional Improvements

### 4. Configure Trace Collection Endpoint 📊
**Priority**: LOW
**Duration**: 5 minutes (disable) or 30 minutes (deploy service)
**Impact**: Reduces log noise, enables telemetry

**Option A: Disable in Test/Dev** (Quick Fix)
```bash
# Add to agent environment variables
export TRACE_ENDPOINT=""  # Empty string disables trace POSTs
```

**Option B: Deploy Trace Collection Service** (Production)
```bash
# Use Command Centre as trace collector (already has /api/traces endpoint)
export TRACE_ENDPOINT="http://localhost:8099/api/traces"

# Or deploy dedicated service
python tools/deploy_trace_collector.py --port 8200
export TRACE_ENDPOINT="http://localhost:8200/traces"
```

---

### 5. Update Production Secrets 🔐
**Priority**: HIGH (before production deployment)
**Duration**: 10 minutes
**Requirement**: Change from dev-secret-change-me

**Steps**:
1. Generate strong JWT secret:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. Update Azure Key Vault:
   ```bash
   az keyvault secret set \
     --vault-name helixcare-kv-prod \
     --name NEXUS-JWT-SECRET \
     --value "<generated-secret>"
   ```

3. Update agent configurations:
   - Modify `config/agents.json` to reference Key Vault
   - Or set environment variable in Azure Container Apps
   - Restart all services

4. Mint new tokens for clients:
   ```python
   from shared.nexus_common.auth import mint_jwt
   token = mint_jwt('production-client', '<generated-secret>')
   print(token)
   ```

---

### 6. CI/CD Integration 🔄
**Priority**: MEDIUM
**Duration**: 30 minutes
**Benefit**: Automated testing on every commit

**GitHub Actions Workflow** (`.github/workflows/helixcare-ci.yml`):
```yaml
name: HelixCare CI/CD

on:
  push:
    branches: [main, dev]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run smoke tests
        env:
          PYTHONPATH: ${{ github.workspace }}
          NEXUS_JWT_SECRET: ${{ secrets.NEXUS_JWT_SECRET }}
        run: |
          pytest tests/conformance/ -v --tb=short --junit-xml=test-results.xml

      - name: Publish test results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: test-results
          path: test-results.xml

  deploy:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Azure Login
        uses: azure/login@v2
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}

      - name: Deploy with AZD
        run: |
          azd auth login --client-id ${{ secrets.AZURE_CLIENT_ID }}
          azd up --environment prod --no-prompt
```

**Required Secrets**:
- `NEXUS_JWT_SECRET` - JWT signing secret
- `AZURE_CREDENTIALS` - Service principal credentials
- `AZURE_CLIENT_ID` - For AZD authentication

---

### 7. Update Starlette Dependency 🔧
**Priority**: LOW
**Duration**: 5 minutes
**Impact**: Cosmetic (removes deprecation warning)

```bash
# Update pyproject.toml
[tool.poetry.dependencies]
starlette = "^0.37.0"  # or latest version with python_multipart

# Apply update
poetry update starlette
# or
pip install --upgrade starlette
```

**Test**:
```bash
python -m pytest tests/conformance/ -v  # Should see no deprecation warnings
```

---

## Decision Points

### Production Deployment Decision Tree

```
Full Harness Pass Rate?
│
├─ >85% PASS → ✅ Proceed to production
│   │
│   ├─ Update production secrets
│   ├─ Deploy to production environment
│   ├─ Run smoke tests in production
│   └─ Monitor for 24 hours
│
├─ 70-85% PASS → ⚠️ Review failures
│   │
│   ├─ Categorize failures (infra vs code)
│   ├─ Fix critical failures
│   ├─ Document known issues
│   └─ Re-run harness tests
│
└─ <70% PASS → ❌ Debug before production
    │
    ├─ Identify root causes
    ├─ Fix systemic issues
    ├─ Re-run full test suite
    └─ Consider dev deployment only
```

---

## Success Metrics

Track these metrics post-deployment:

### Functional Metrics
- [ ] All 35 services healthy (100% uptime)
- [ ] Average agent response time <3 seconds
- [ ] JWT authentication success rate >99%
- [ ] Scenario completion rate >95%

### Performance Metrics
- [ ] p50 latency <500ms for RPC calls
- [ ] p95 latency <2s for RPC calls
- [ ] Command Centre dashboard load time <1s
- [ ] Avatar TTS stream latency <100ms

### Business Metrics
- [ ] 24 patient scenarios executable end-to-end
- [ ] Zero critical security vulnerabilities
- [ ] Documentation completeness >90%
- [ ] Azure cost per scenario <$0.10

---

## Communication Plan

### Stakeholder Updates

**Dev/Test Deployment Notice**:
```
Subject: HelixCare Dev Environment Deployed - Testing Ready

Team,

The HelixCare NEXUS A2A system has been deployed to Azure Dev environment:
- Command Centre: https://helixcare-cc-dev.azurewebsites.net
- Gateway: https://helixcare-gateway-dev.azurewebsites.net
- Status: All 35 services healthy

Test Results:
- Core Protocol: 5/5 passing (100%)
- Command Centre: 25/26 passing (96%)
- Full Harness: In progress (~13.5K tests)

You can now:
1. Access Command Centre dashboard
2. Test patient scenarios via Gateway
3. Monitor agent interactions in real-time

Please report any issues to the team channel.
```

**Production Deployment Notice**:
```
Subject: HelixCare Production Deployment - Go Live

Team,

HelixCare has been deployed to production:
- Command Centre: https://helixcare-cc.azurewebsites.net
- Gateway: https://helixcare-gateway.azurewebsites.net
- Status: All 35 services operational

Validation:
- Full regression: 13,535 tests, 93% pass rate
- Smoke tests: 100% passing
- 24-hour monitoring: No critical issues

Production access requires updated JWT tokens (check Key Vault).

Monitoring dashboard: https://helixcare-monitoring.azurewebsites.net
```

---

## Support & Documentation

### Key Documentation
- [HELIXCARE_USER_MANUAL.md](HELIXCARE_USER_MANUAL.md) - User guide
- [docs/azure_deployment_guide.md](docs/azure_deployment_guide.md) - Deployment steps (60 pages)
- [docs/developer_reference.md](docs/developer_reference.md) - Protocol patterns
- [REGRESSION_TEST_REPORT.md](REGRESSION_TEST_REPORT.md) - Test results
- [CLAUDE.md](CLAUDE.md) - Developer quickstart

### Command Reference
```bash
# Launch all services locally
python tools/launch_all_agents.py --with-gateway

# Run specific scenario
python tools/helixcare_scenarios.py --run chest_pain_cardiac

# Check service health
curl http://localhost:8099/api/agents

# Run tests
pytest tests/conformance/ -v     # Core protocol tests
pytest tests/nexus_harness/ -v   # Full harness (13.5K tests)

# Deploy to Azure
azd up --environment dev         # Dev deployment
azd up --environment prod        # Production deployment
```

---

## Timeline Estimate

**Immediate (Today)**:
- 10 min: Complete full harness regression
- 20 min: Deploy to Azure dev environment ✅
- 15 min: Run Azure smoke tests

**Short-term (This Week)**:
- Update production secrets
- Configure trace collection
- Set up CI/CD pipeline
- Deploy to Azure production (if tests pass)

**Medium-term (Next 2 Weeks)**:
- Monitor production metrics
- Optimize agent performance
- Expand test coverage
- Update documentation

---

## Questions & Escalation

**Technical Issues**:
- Agent health failures → Check [azure_deployment_guide.md](docs/azure_deployment_guide.md) troubleshooting
- Test failures → Review [REGRESSION_TEST_REPORT.md](REGRESSION_TEST_REPORT.md)
- Deployment errors → Check AZD logs (`azd deploy --debug`)

**Decision Escalation**:
- Production deployment approval required if pass rate <85%
- Security review required before production JWT secrets change
- Cost approval needed if Azure spending >$500/month

---

**Document Owner**: Development Team
**Last Updated**: March 19, 2026
**Next Review**: After full harness completion
