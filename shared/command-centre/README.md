# NEXUS-A2A Command Centre

Real-time monitoring dashboard for NEXUS-A2A agent networks. Provides visual topology, performance heatmaps, and event streaming for distributed agent systems.

## Features

- **🗺️ Network Topology Visualization**: Interactive SVG graph showing agent relationships with real-time status
- **🔥 Performance Heatmaps**: Color-coded metrics for throughput, latency, error rates, and activity
- **📊 Event Timeline**: Live stream of task lifecycle events with semantic coloring
- **📈 Performance Charts**: System throughput, latency distribution, load balance, and error budget gauges
- **🎨 Colorblind-Safe Palette**: WCAG AA compliant with perceptually uniform gradients
- **⚡ WebSocket Streaming**: Sub-second event delivery via Redis pub/sub

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Agent 1   │────▶│    Redis    │◀────│   Agent N   │
│  (FastAPI)  │     │  (Pub/Sub)  │     │  (FastAPI)  │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   Command   │
                    │   Centre    │
                    └─────────────┘
                           │
                           ▼
                   ┌───────────────┐
                   │  Dashboard UI │
                   │ (HTML/CSS/JS) │
                   └───────────────┘
```

## Quick Start

### 1. Add to docker-compose.yml

```yaml
services:
  command-centre:
    build:
      context: ../../
      dockerfile: shared/command-centre/Dockerfile
    environment:
      - REDIS_URL=redis://redis:6379
      - AGENT_URLS=http://agent1:8021,http://agent2:8022,http://agent3:8023
      - UPDATE_INTERVAL_MS=2000
    ports:
      - "8099:8099"
    depends_on:
      - redis
```

### 2. Start the Stack

```bash
cd demos/ed-triage
docker-compose up
```

### 3. Access Dashboard

Navigate to [http://localhost:8099](http://localhost:8099)

## Color Semantics

### Status Colors
- 🟢 **Green (#10b981)**: Healthy (< 5% error rate, < 5s latency)
- 🟡 **Amber (#f59e0b)**: Degraded (5-10% errors or > 5s latency)
- 🔴 **Red (#ef4444)**: Unhealthy (> 10% error rate)
- ⚪ **Gray (#6b7280)**: Unknown/Unreachable

### Task State Colors
- 🔵 **Blue (#3b82f6)**: Accepted
- 🟣 **Violet (#8b5cf6)**: Working
- 🟢 **Green (#10b981)**: Final (Success)
- 🔴 **Red (#dc2626)**: Error
- ⚫ **Slate (#64748b)**: Cancelled

### Heatmap Gradients

#### Latency (0-5000ms)
```
Cool (Fast) ──────────────────────────────▶ Hot (Slow)
#ecfdf5 → #6ee7b7 → #10b981 → #047857 → #064e3b
```

#### Throughput (0-100 tasks/min)
```
Low ─────────────────────────────────────▶ High
#eff6ff → #93c5fd → #3b82f6 → #1d4ed8 → #1e3a8a
```

#### Error Rate (0-100%)
```
None ────────────────────────────────────▶ Critical
#fef2f2 → #fecaca → #f87171 → #dc2626 → #991b1b
```

## Dashboard Components

### 1. Network Topology (Top Panel)
- **Nodes**: Agent circles sized by throughput, colored by health
- **Edges**: RPC dependencies with flow animations
- **Interactions**: Hover for metrics, click for details

### 2. Metrics Heatmap (Middle Panel)
Multi-dimensional grid showing:
- **Row 1**: Throughput (tasks/min)
- **Row 2**: Latency (avg + P95)
- **Row 3**: Error Rate (%)
- **Row 4**: Status
- **Row 5**: Last Activity (temporal fade)

### 3. Event Timeline (Right Sidebar)
- Real-time log of task lifecycle events
- Filterable by state (accepted/working/final/error)
- Color-coded duration indicators
- Expandable JSON payloads

### 4. Performance Charts (Bottom, Collapsible)
- **System Throughput**: Area chart (60s window)
- **Latency Distribution**: Stacked P50/P95/P99
- **Agent Load Balance**: Horizontal bar chart
- **Error Budget Gauge**: Radial SLO indicator

## API Endpoints

### `GET /health`
Health check for the command centre itself.

```json
{
  "status": "healthy",
  "name": "command-centre",
  "timestamp": "2026-02-08T10:30:00Z",
  "monitored_agents": 3
}
```

### `GET /api/agents`
Current state of all monitored agents.

```json
[
  {
    "name": "triage-agent",
    "url": "http://triage-agent:8021",
    "status": "healthy",
    "health_score": 0.95,
    "metrics": {
      "tasks_accepted": 245,
      "tasks_completed": 238,
      "tasks_errored": 7,
      "avg_latency_ms": 1250,
      "p95_latency_ms": 2100,
      "last_task_ms": 1050
    },
    "dependencies": ["diagnosis-agent"],
    "card": {...},
    "last_seen": "2026-02-08T10:30:05Z"
  }
]
```

### `GET /api/topology`
Network topology graph data (nodes + edges).

### `WS /api/events`
WebSocket stream of real-time events.

**Message format:**
```json
{
  "type": "task.event",
  "payload": {
    "agent": "triage-agent",
    "task_id": "task-abc123",
    "event": "nexus.task.final",
    "data": {...},
    "timestamp": "2026-02-08T10:30:05Z",
    "duration_ms": 1250
  },
  "timestamp": "2026-02-08T10:30:05Z"
}
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL for pub/sub |
| `AGENT_URLS` | `""` | Comma-separated agent base URLs |
| `UPDATE_INTERVAL_MS` | `2000` | Agent health polling interval |

### Adding Agents

1. Add agent URL to `AGENT_URLS` environment variable
2. Ensure agent has:
   - `GET /.well-known/agent-card.json` (discovery)
   - `GET /health` (health check with metrics)
3. Configure agent to publish events to Redis:
   ```python
   bus = TaskEventBus(agent_name="my-agent", redis_url="redis://redis:6379")
   ```

## Development

### Local Development

```bash
cd shared/command-centre

# Install dependencies
pip install -r requirements.txt

# Set environment
export REDIS_URL=redis://localhost:6379
export AGENT_URLS=http://localhost:8021,http://localhost:8022

# Run server
python -m uvicorn app.main:app --reload --port 8099
```

### Testing

```bash
# Run test suite
pytest tests/nexus_harness/test_command_centre.py -v

# Test matrix validation
python -m json.tool nexus-a2a/artefacts/matrices/nexus_command_centre_matrix.json
```

## Accessibility

- **WCAG AA Compliant**: All color combinations meet contrast ratios
- **Colorblind Safe**: Uses redundant encoding (color + patterns)
- **Keyboard Navigation**: Full support for keyboard-only users
- **Screen Reader**: ARIA labels on all interactive elements

## Troubleshooting

### Dashboard shows "Disconnected"
- Check WebSocket connection: `ws://localhost:8099/api/events`
- Verify Redis is running: `redis-cli ping`
- Check browser console for errors

### Agents not appearing
- Confirm `AGENT_URLS` environment variable is set
- Verify agents are reachable from command-centre container
- Check agent health endpoints return 200: `curl http://agent:8021/health`

### No events in timeline
- Verify agents are publishing to Redis channel `nexus:events`
- Check Redis pub/sub: `redis-cli SUBSCRIBE nexus:events`
- Ensure agents have Redis client configured

### Heatmap shows stale data
- Check `UPDATE_INTERVAL_MS` (default 2s)
- Verify agent `/health` endpoints return updated metrics
- Browser cache: Hard refresh (Ctrl+Shift+R)

## License

See [LICENSE](../../LICENSE) for details.
