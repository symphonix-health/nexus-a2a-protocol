/**
 * NEXUS-A2A Command Centre Dashboard
 * Main application logic for real-time monitoring
 */

// State Management
const state = {
    agents: [],
    events: [],
    ws: null,
    connected: false,
    charts: null,
    filters: {
        accepted: true,
        working: true,
        final: true,
        error: true,
    },
};

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    initializeWebSocket();
    initializeFilters();
    initializeToggleButtons();
});

// ── WebSocket Connection ──────────────────────────────────────────────
function initializeWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/api/events`;

    state.ws = new WebSocket(wsUrl);

    state.ws.onopen = () => {
        state.connected = true;
        updateConnectionStatus(true);
        showToast('Connected to Command Centre', 'success');
    };

    state.ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        handleWebSocketMessage(message);
    };

    state.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        showToast('Connection error', 'error');
    };

    state.ws.onclose = () => {
        state.connected = false;
        updateConnectionStatus(false);
        showToast('Disconnected from Command Centre', 'warning');

        // Attempt reconnection
        setTimeout(initializeWebSocket, 5000);
    };
}

function handleWebSocketMessage(message) {
    switch (message.type) {
        case 'agents.snapshot':
            state.agents = message.payload;
            renderTopology();
            renderHeatmap();
            break;

        case 'task.event':
            addEvent(message.payload);
            updateHeatmapMetrics(message.payload);
            break;

        default:
            console.warn('Unknown message type:', message.type);
    }
}

// ── Connection Status ─────────────────────────────────────────────────
function updateConnectionStatus(connected) {
    const dot = document.getElementById('connection-status');
    const text = document.getElementById('connection-text');

    if (connected) {
        dot.classList.add('connected');
        dot.classList.remove('disconnected');
        text.textContent = 'Connected';
    } else {
        dot.classList.remove('connected');
        dot.classList.add('disconnected');
        text.textContent = 'Disconnected';
    }
}

// ── Topology Visualization ────────────────────────────────────────────
function renderTopology() {
    const svg = document.getElementById('topology-svg');
    svg.innerHTML = ''; // Clear previous

    if (state.agents.length === 0) return;

    const width = svg.clientWidth;
    const height = 400;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) / 3;

    // Calculate positions in a circle
    const angleStep = (2 * Math.PI) / state.agents.length;
    const positions = state.agents.map((agent, i) => ({
        agent,
        x: centerX + radius * Math.cos(i * angleStep - Math.PI / 2),
        y: centerY + radius * Math.sin(i * angleStep - Math.PI / 2),
    }));

    // Draw edges (dependencies)
    state.agents.forEach((agent) => {
        const sourcePos = positions.find(p => p.agent.name === agent.name);
        agent.dependencies.forEach((depName) => {
            const targetPos = positions.find(p => p.agent.name === depName);
            if (sourcePos && targetPos) {
                drawEdge(svg, sourcePos.x, sourcePos.y, targetPos.x, targetPos.y);
            }
        });
    });

    // Draw nodes
    positions.forEach(({ agent, x, y }) => {
        drawNode(svg, agent, x, y);
    });
}

function drawEdge(svg, x1, y1, x2, y2) {
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', x1);
    line.setAttribute('y1', y1);
    line.setAttribute('x2', x2);
    line.setAttribute('y2', y2);
    line.classList.add('edge-line');
    svg.appendChild(line);
}

function drawNode(svg, agent, x, y) {
    // Node circle with status color
    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('cx', x);
    circle.setAttribute('cy', y);

    // Size based on throughput
    const tasks = agent.metrics?.tasks_completed || 0;
    const nodeRadius = Math.max(15, Math.min(30, 15 + tasks / 10));
    circle.setAttribute('r', nodeRadius);

    // Color based on status
    const statusColor = getStatusColor(agent.status);
    circle.setAttribute('fill', statusColor);
    circle.setAttribute('stroke', statusColor);
    circle.setAttribute('fill-opacity', '0.8');
    circle.classList.add('node-circle');

    // Tooltip on hover
    circle.setAttribute('title', `${agent.name}\nStatus: ${agent.status}\nLatency: ${agent.metrics?.avg_latency_ms || 0}ms`);

    svg.appendChild(circle);

    // Label
    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', x);
    text.setAttribute('y', y + nodeRadius + 15);
    text.textContent = agent.name;
    text.classList.add('node-text');
    svg.appendChild(text);
}

// ── Heatmap Rendering ─────────────────────────────────────────────────
function renderHeatmap() {
    const table = document.getElementById('heatmap-table');

    // Clear existing agent columns
    const thead = table.querySelector('thead tr');
    while (thead.children.length > 1) {
        thead.removeChild(thead.lastChild);
    }

    // Add agent column headers
    state.agents.forEach(agent => {
        const th = document.createElement('th');
        th.textContent = agent.name;
        th.style.minWidth = '120px';
        thead.appendChild(th);
    });

    // Update metric rows
    const tbody = table.querySelector('tbody');
    tbody.querySelectorAll('tr').forEach(row => {
        const metric = row.dataset.metric;

        // Remove existing cells (except label)
        while (row.children.length > 1) {
            row.removeChild(row.lastChild);
        }

        // Add cells for each agent
        state.agents.forEach(agent => {
            const td = document.createElement('td');
            td.classList.add('heatmap-cell');
            updateHeatmapCell(td, agent, metric);
            row.appendChild(td);
        });
    });
}

function updateHeatmapCell(td, agent, metric) {
    const metrics = agent.metrics || {};

    switch (metric) {
        case 'throughput': {
            const completed = metrics.tasks_completed || 0;
            const throughputColor = getThroughputColor(completed / 5); // Normalize to tasks/min
            td.style.backgroundColor = throughputColor;
            td.innerHTML = `<div class="value">${completed}</div><div class="label">tasks</div>`;
            break;
        }

        case 'latency': {
            const latency = metrics.avg_latency_ms || 0;
            const latencyColor = getLatencyColor(latency);
            td.style.backgroundColor = latencyColor;
            td.innerHTML = `<div class="value">${Math.round(latency)}</div><div class="label">ms</div>`;
            break;
        }

        case 'error-rate': {
            const total = (metrics.tasks_completed || 0) + (metrics.tasks_errored || 0);
            const errorRate = total > 0 ? (metrics.tasks_errored || 0) / total : 0;
            const errorColor = getErrorRateColor(errorRate);
            td.style.backgroundColor = errorColor;
            td.innerHTML = `<div class="value">${(errorRate * 100).toFixed(1)}%</div>`;
            break;
        }

        case 'status': {
            const statusColor = getStatusColor(agent.status);
            td.style.backgroundColor = statusColor;
            td.innerHTML = `<div class="value">${agent.status}</div>`;
            break;
        }

        case 'last-activity': {
            const lastSeen = new Date(agent.last_seen);
            const ageMs = Date.now() - lastSeen.getTime();
            const ageSec = Math.floor(ageMs / 1000);
            const opacity = getPulseOpacity(ageMs, 30000); // 30s fade
            td.style.backgroundColor = `rgba(59, 130, 246, ${opacity})`;
            td.innerHTML = `<div class="value">${ageSec}s</div><div class="label">ago</div>`;
            break;
        }
    }
}

function updateHeatmapMetrics(event) {
    // Update agent metrics based on incoming events
    const agentName = event.agent;
    const agent = state.agents.find(a => a.name === agentName);

    if (agent && event.duration_ms) {
        // Update would happen here in real implementation
        // For now, metrics come from polling
    }
}

// ── Timeline Events ───────────────────────────────────────────────────
function addEvent(event) {
    state.events.unshift(event);

    // Keep only last 100 events
    if (state.events.length > 100) {
        state.events = state.events.slice(0, 100);
    }

    renderTimeline();
}

function renderTimeline() {
    const container = document.getElementById('timeline-container');

    // Filter events based on active filters
    const filteredEvents = state.events.filter(event => {
        const eventType = event.event.split('.').pop(); // Extract last part
        return state.filters[eventType];
    });

    // Render (showing most recent first)
    container.innerHTML = filteredEvents.slice(0, 50).map(event => {
        const timestamp = new Date(event.timestamp).toLocaleTimeString();
        const eventType = event.event.split('.').pop();
        const stateColor = getTaskColor(eventType);
        const durationMs = event.duration_ms || 0;
        const durationSec = (durationMs / 1000).toFixed(2);

        // Duration color
        let durationColor = '#10b981'; // green
        if (durationMs > 10000) durationColor = '#dc2626'; // red
        else if (durationMs > 3000) durationColor = '#f59e0b'; // amber
        else if (durationMs > 1000) durationColor = '#fbbf24'; // yellow

        return `
            <div class="timeline-event" style="border-left-color: ${stateColor}">
                <div class="timestamp">[${timestamp}]</div>
                <div class="agent-name">${event.agent}</div>
                <div class="task-id">${event.task_id}</div>
                <span class="state-badge" style="background-color: ${stateColor}">${eventType}</span>
                ${durationMs > 0 ? `<div class="duration" style="color: ${durationColor}">${durationSec}s</div>` : ''}
            </div>
        `;
    }).join('');
}

// ── Filters & Controls ────────────────────────────────────────────────
function initializeFilters() {
    document.querySelectorAll('.timeline-filters input').forEach(input => {
        input.addEventListener('change', (e) => {
            const filter = e.target.dataset.filter;
            state.filters[filter] = e.target.checked;
            renderTimeline();
        });
    });
}

// ── Performance Charts ────────────────────────────────────────────────
function initializeCharts() {
    const throughputCtx = document.getElementById('throughput-chart');
    const latencyCtx = document.getElementById('latency-chart');
    const loadCtx = document.getElementById('load-chart');
    const errorCtx = document.getElementById('error-gauge');

    state.charts = {
        throughput: new Chart(throughputCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Total Tasks',
                    data: [],
                    borderColor: COLORS.ui.accent,
                    backgroundColor: COLORS.ui.accent + '20',
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: { beginAtZero: true }
                }
            }
        }),

        latency: new Chart(latencyCtx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Avg Latency (ms)',
                    data: [],
                    backgroundColor: COLORS.status.degraded + '80'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: { beginAtZero: true }
                }
            }
        }),

        load: new Chart(loadCtx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Tasks Completed',
                    data: [],
                    backgroundColor: COLORS.status.healthy + '80'
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    x: { beginAtZero: true }
                }
            }
        }),

        errorGauge: new Chart(errorCtx, {
            type: 'doughnut',
            data: {
                labels: ['Success', 'Errors'],
                datasets: [{
                    data: [100, 0],
                    backgroundColor: [COLORS.status.healthy + '80', COLORS.status.unhealthy + '80']
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'bottom' }
                }
            }
        })
    };
}

function updatePerformanceCharts() {
    if (!state.charts) return;

    // Throughput: sum all agent tasks
    const totalTasks = state.agents.reduce((sum, agent) =>
        sum + (agent.metrics?.tasks_completed || 0), 0);

    const now = new Date().toLocaleTimeString();
    const throughputChart = state.charts.throughput;
    throughputChart.data.labels.push(now);
    throughputChart.data.datasets[0].data.push(totalTasks);

    // Keep last 20 data points
    if (throughputChart.data.labels.length > 20) {
        throughputChart.data.labels.shift();
        throughputChart.data.datasets[0].data.shift();
    }
    throughputChart.update('none');

    // Latency: show avg latency per agent
    const latencyChart = state.charts.latency;
    latencyChart.data.labels = state.agents.map(a => a.name);
    latencyChart.data.datasets[0].data = state.agents.map(a =>
        Math.round(a.metrics?.avg_latency_ms || 0));
    latencyChart.update('none');

    // Load balance: tasks per agent
    const loadChart = state.charts.load;
    loadChart.data.labels = state.agents.map(a => a.name);
    loadChart.data.datasets[0].data = state.agents.map(a =>
        a.metrics?.tasks_completed || 0);
    loadChart.update('none');

    // Error gauge: total error rate
    const totalCompleted = state.agents.reduce((sum, a) =>
        sum + (a.metrics?.tasks_completed || 0), 0);
    const totalErrored = state.agents.reduce((sum, a) =>
        sum + (a.metrics?.tasks_errored || 0), 0);
    const total = totalCompleted + totalErrored;

    const errorChart = state.charts.errorGauge;
    if (total > 0) {
        errorChart.data.datasets[0].data = [totalCompleted, totalErrored];
    } else {
        errorChart.data.datasets[0].data = [100, 0];
    }
    errorChart.update('none');
}

function initializeToggleButtons() {
    const toggleBtn = document.getElementById('toggle-performance');
    const panel = document.querySelector('.performance-panel');

    toggleBtn.addEventListener('click', () => {
        panel.classList.toggle('collapsed');
        toggleBtn.textContent = panel.classList.contains('collapsed') ? '▼' : '▲';

        // Initialize charts on first open
        if (!state.charts && !panel.classList.contains('collapsed')) {
            setTimeout(() => {
                initializeCharts();
                updatePerformanceCharts();
            }, 100);
        }
    });
}

// ── Toast Notifications ───────────────────────────────────────────────
function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => container.removeChild(toast), 300);
    }, 3000);
}

// ── Periodic Updates ──────────────────────────────────────────────────
// Poll for agent updates every 2 seconds (in addition to WebSocket events)
setInterval(async () => {
    if (!state.connected) return;

    try {
        const response = await fetch('/api/agents');
        if (response.ok) {
            state.agents = await response.json();
            renderTopology();
            renderHeatmap();

            // Update charts if they're initialized
            if (state.charts) {
                updatePerformanceCharts();
            }
        }
    } catch (error) {
        console.error('Failed to poll agents:', error);
    }
}, 2000);
