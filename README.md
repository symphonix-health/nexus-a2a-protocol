# Nexus A2A Protocol (Python SDK + PoC)

This repository contains an initial Python SDK and proof-of-concept for a Nexus Agent-to-Agent (A2A) protocol implementation.

Current scope:
- Protocol data models for messages and tasks
- JSON-RPC envelope helpers aligned with A2A-style methods
- In-memory PoC transport to validate end-to-end task exchange
- Unit test suite

## Quick Start

```powershell
py -3.10 -m venv .venv
. .\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e .[dev]
pytest
```

## Package Layout

- `src/nexus_a2a_protocol/models.py`: core message/task models and validation
- `src/nexus_a2a_protocol/jsonrpc.py`: JSON-RPC request/response builders and envelope validation
- `src/nexus_a2a_protocol/poc.py`: in-memory transport + agent registry PoC
- `tests/`: unit tests for models, JSON-RPC helpers, and PoC flow
- `docs/research.md`: protocol research notes and design decisions

## Initial Example

```python
from nexus_a2a_protocol import AgentCard, InMemoryAgent, InMemoryNexus, new_agent_message

nexus = InMemoryNexus()
nexus.register(InMemoryAgent(AgentCard(agent_id="client"), lambda msg: msg))
nexus.register(
    InMemoryAgent(
        AgentCard(agent_id="echo"),
        lambda msg: new_agent_message(f"echo:{msg.parts[0].text}")
    )
)

task = nexus.send_text_task("client", "echo", "ping")
print(task.status.state)  # completed
print(task.artifacts[-1].parts[0].text)  # echo:ping
```

## REST Client Environment

This repo includes VS Code REST Client setup:
- Workspace environments are in `.vscode/settings.json` under `rest-client.environmentVariables`.
- Sample requests are in `requests/nexus-a2a.http`.

To use:
1. Open `requests/nexus-a2a.http`.
2. In VS Code, choose environment `local`, `dev`, or `prod`.
3. Update `apiToken` and `baseUrl` values in `.vscode/settings.json`.
