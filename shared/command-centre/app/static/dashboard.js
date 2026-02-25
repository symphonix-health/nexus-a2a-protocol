/**
 * NEXUS-A2A Command Centre Dashboard
 * Main application logic for real-time monitoring
 */

// State Management
const state = {
    agents: [],
    events: [],
    scenarios: {},
    scenarioCatalog: [],
    ws: null,
    connected: false,
    charts: null,
    flowSource: 'idle',
    lastRealFlowEventAt: 0,
    syntheticFlowInterval: null,
    syntheticCursor: 0,
    syntheticScenarios: [
        { id: 'VISIT-DEMO-1001', steps: ['triage', 'diagnosis', 'imaging', 'discharge'], index: 0 },
        { id: 'VISIT-DEMO-1002', steps: ['triage', 'diagnosis', 'pharmacy', 'followup'], index: 0 },
        { id: 'VISIT-DEMO-1003', steps: ['triage', 'diagnosis', 'bed', 'coordinator'], index: 0 },
    ],
    filters: {
        accepted: true,
        working: true,
        final: true,
        error: true,
    },
    timelinePaused: false,
    timelineBufferedCount: 0,
    timelineFrozenEvents: null,
    traceRuns: [],
    selectedTraceId: null,
    observerActions: {},
    observerAudit: [],
    flowFilters: {
        hideSynthetic: false,
        severity: 'all',
        needsAction: false,
    },
    alertFeed: [],
    alertHistory: {},
};

const FLOW_STALE_MS = 30000;
const FLOW_EXPIRE_MS = 10 * 60 * 1000;
const FLOW_SYNTHETIC_DELAY_MS = 8000;
const FLOW_LIVE_STALE_MS = 15000;
const FLOW_RETRY_BLOCK_THRESHOLD = 2;
const FLOW_ALERT_DEDUP_MS = 60 * 1000;
const FLOW_ALERT_HISTORY_RETENTION_MS = 30 * 60 * 1000;
const FLOW_SLA_DEFAULT_MS = 45 * 1000;
const FLOW_SLA_URGENT_MS = 30 * 1000;
const FLOW_SLA_CRITICAL_MS = 20 * 1000;
const FLOW_OBSERVER_STORAGE_KEY = 'command-centre.flow-observer-actions.v1';
const FLOW_ALERT_WEBHOOK_KEY = 'command-centre.flow-alert-webhook-url';
const TOPOLOGY_HINT_DISMISSED_KEY = 'command-centre.topology-hint-dismissed';
const FLOW_OBSERVER_ACTION_RETENTION_MS = 2 * FLOW_EXPIRE_MS;
const FLOW_OBSERVER_AUDIT_MAX = 400;
const TRACE_RUN_MAX = 200;

const topologyView = {
    scale: 1,
    minScale: 0.65,
    maxScale: 2.8,
    panX: 0,
    panY: 0,
    dragging: false,
    lastPointer: null,
    initialized: false,
};

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    initializeTopologyHint();
    initializeTopologyInteractions();
    initializeWebSocket();
    initializePerformanceCharts();
    loadScenarioCatalog();
    initializeScenarioFlowBoard();
    initializeJourneyPopover();
    initializeFilters();
    initializeToggleButtons();
    loadTraceRuns();
    initializeTracePanel();
    initializeLiveAvatarPanel();
});

function initializeLiveAvatarPanel() {
    const frame = document.getElementById('live-avatar-frame');
    const refreshBtn = document.getElementById('live-avatar-refresh');
    if (!frame) return;

    const avatarUrl = `${window.location.protocol}//${window.location.hostname}:8039/avatar?live=1&readonly=1`;
    frame.src = avatarUrl;

    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            frame.src = `${avatarUrl}&r=${Date.now()}`;
            showToast('Live avatar panel refreshed', 'success');
        });
    }
}

const popoverState = {
    element: null,
    activeTarget: null,
};

function initializeTopologyHint() {
    const hint = document.getElementById('topology-hint');
    const dismissBtn = document.getElementById('dismiss-topology-hint');
    if (!hint || !dismissBtn) return;

    if (isTopologyHintDismissed()) {
        hint.classList.add('is-hidden');
    }

    dismissBtn.addEventListener('click', () => {
        hint.classList.add('is-hidden');
        setTopologyHintDismissed(true);
    });
}

function isTopologyHintDismissed() {
    try {
        return window.localStorage.getItem(TOPOLOGY_HINT_DISMISSED_KEY) === 'true';
    } catch (error) {
        return false;
    }
}

function setTopologyHintDismissed(value) {
    try {
        if (value) {
            window.localStorage.setItem(TOPOLOGY_HINT_DISMISSED_KEY, 'true');
        } else {
            window.localStorage.removeItem(TOPOLOGY_HINT_DISMISSED_KEY);
        }
    } catch (error) {
        // Ignore storage failures (e.g., restricted mode)
    }
}

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
        try {
            const message = JSON.parse(event.data);
            handleWebSocketMessage(message);
        } catch (error) {
            console.warn('Dropped malformed WebSocket JSON payload:', error);
        }
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
            updatePerformanceCharts();
            break;

        case 'task.event':
            addEvent(message.payload);
            updateHeatmapMetrics(message.payload);
            ingestScenarioEvent(message.payload, false);
            updatePerformanceCharts();
            break;

        case 'trace.run':
            handleTraceRunEvent(message.payload);
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

    const width = svg.clientWidth || svg.parentElement?.clientWidth || 900;
    const dynamicHeight = Math.max(300, Math.min(560, 280 + Math.max(0, state.agents.length - 6) * 22));
    const height = dynamicHeight;
    svg.setAttribute('height', String(height));
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);

    const centerX = width / 2;
    const centerY = height / 2;
    const labelPadding = 90;
    const radius = Math.max(70, Math.min(width, height) / 2 - labelPadding);
    const denseMode = state.agents.length > 15;

    const viewport = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    viewport.setAttribute('id', 'topology-viewport');
    svg.appendChild(viewport);

    // Calculate positions in a circle
    const angleStep = (2 * Math.PI) / state.agents.length;
    const positions = state.agents.map((agent, i) => ({
        agent,
        x: centerX + radius * Math.cos(i * angleStep - Math.PI / 2),
        y: centerY + radius * Math.sin(i * angleStep - Math.PI / 2),
    }));

    // Draw dependency edges between agents (outer ring)
    state.agents.forEach((agent) => {
        const sourcePos = positions.find(p => p.agent.name === agent.name);
        agent.dependencies.forEach((depName) => {
            const targetPos = positions.find(p => p.agent.name === depName);
            if (sourcePos && targetPos) {
                drawEdge(viewport, sourcePos.x, sourcePos.y, targetPos.x, targetPos.y, 'edge-line edge-agent');
            }
        });
    });

    // Draw animated hub links to show nexus-a2a-protocol as the communication centre.
    positions.forEach(({ x, y }) => {
        drawEdge(viewport, centerX, centerY, x, y, 'edge-line edge-hub-link');
    });

    drawHubNode(viewport, centerX, centerY);

    // Draw nodes
    const placedLabels = [];
    positions.forEach(({ agent, x, y }) => {
        drawNode(viewport, agent, x, y, centerX, centerY, {
            denseMode,
            placedLabels,
        });
    });

    applyTopologyTransform();
}

function initializeTopologyInteractions() {
    const svg = document.getElementById('topology-svg');
    if (!svg || topologyView.initialized) return;

    topologyView.initialized = true;

    svg.addEventListener('wheel', (event) => {
        event.preventDefault();

        const point = getSvgPoint(svg, event.clientX, event.clientY);
        if (!point) return;

        const zoomFactor = event.deltaY > 0 ? 0.92 : 1.08;
        const nextScale = clamp(topologyView.scale * zoomFactor, topologyView.minScale, topologyView.maxScale);

        if (nextScale === topologyView.scale) return;

        const worldX = (point.x - topologyView.panX) / topologyView.scale;
        const worldY = (point.y - topologyView.panY) / topologyView.scale;

        topologyView.scale = nextScale;
        topologyView.panX = point.x - worldX * nextScale;
        topologyView.panY = point.y - worldY * nextScale;

        applyTopologyTransform();
    }, { passive: false });

    svg.addEventListener('pointerdown', (event) => {
        topologyView.dragging = true;
        topologyView.lastPointer = getSvgPoint(svg, event.clientX, event.clientY);
        svg.classList.add('is-panning');
    });

    window.addEventListener('pointermove', (event) => {
        if (!topologyView.dragging) return;

        const point = getSvgPoint(svg, event.clientX, event.clientY);
        if (!point || !topologyView.lastPointer) return;

        topologyView.panX += point.x - topologyView.lastPointer.x;
        topologyView.panY += point.y - topologyView.lastPointer.y;
        topologyView.lastPointer = point;

        applyTopologyTransform();
    });

    window.addEventListener('pointerup', () => {
        topologyView.dragging = false;
        topologyView.lastPointer = null;
        svg.classList.remove('is-panning');
    });

    svg.addEventListener('dblclick', () => {
        topologyView.scale = 1;
        topologyView.panX = 0;
        topologyView.panY = 0;
        applyTopologyTransform();
    });
}

function applyTopologyTransform() {
    const viewport = document.getElementById('topology-viewport');
    if (!viewport) return;

    viewport.setAttribute(
        'transform',
        `translate(${topologyView.panX.toFixed(2)} ${topologyView.panY.toFixed(2)}) scale(${topologyView.scale.toFixed(3)})`
    );
}

function getSvgPoint(svg, clientX, clientY) {
    if (!svg.getScreenCTM()) return null;

    const point = svg.createSVGPoint();
    point.x = clientX;
    point.y = clientY;
    return point.matrixTransform(svg.getScreenCTM().inverse());
}

function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
}

function drawEdge(svg, x1, y1, x2, y2, className = 'edge-line') {
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', x1);
    line.setAttribute('y1', y1);
    line.setAttribute('x2', x2);
    line.setAttribute('y2', y2);
    className.split(' ').filter(Boolean).forEach((name) => line.classList.add(name));
    svg.appendChild(line);
}

function drawHubNode(svg, x, y) {
    const ringOuter = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    ringOuter.setAttribute('cx', x);
    ringOuter.setAttribute('cy', y);
    ringOuter.setAttribute('r', '36');
    ringOuter.classList.add('hub-ring', 'hub-ring-outer');
    svg.appendChild(ringOuter);

    const ringInner = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    ringInner.setAttribute('cx', x);
    ringInner.setAttribute('cy', y);
    ringInner.setAttribute('r', '28');
    ringInner.classList.add('hub-ring', 'hub-ring-inner');
    svg.appendChild(ringInner);

    const hub = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    hub.setAttribute('cx', x);
    hub.setAttribute('cy', y);
    hub.setAttribute('r', '20');
    hub.classList.add('hub-node');
    hub.setAttribute('title', 'nexus-a2a-protocol\nCommunication hub for agent-to-agent routing');
    svg.appendChild(hub);

    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.setAttribute('x', String(x));
    label.setAttribute('y', String(y + 44));
    label.setAttribute('text-anchor', 'middle');
    label.textContent = 'nexus-a2a-protocol';
    label.classList.add('hub-label');
    svg.appendChild(label);
}

function drawNode(svg, agent, x, y, centerX, centerY, options = {}) {
    // Node circle with status color
    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('cx', x);
    circle.setAttribute('cy', y);

    // Size based on throughput
    const tasks = agent.metrics?.tasks_completed || 0;
    const nodeRadius = Math.max(12, Math.min(22, 12 + tasks / 20));
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
    const dx = x - centerX;
    const dy = y - centerY;
    const magnitude = Math.hypot(dx, dy) || 1;
    const ux = dx / magnitude;
    const uy = dy / magnitude;
    const labelOffset = nodeRadius + 16;

    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    let labelX = x + ux * labelOffset;
    let labelY = y + uy * labelOffset;
    const label = truncateTopologyLabel(agent.name, 22);
    const denseMode = Boolean(options.denseMode);

    let anchor = 'middle';
    if (ux > 0.3) {
        anchor = 'start';
    } else if (ux < -0.3) {
        anchor = 'end';
    }

    if (denseMode) {
        const resolved = resolveLabelPositionWithJitter(label, labelX, labelY, anchor, options.placedLabels || []);
        labelX = resolved.x;
        labelY = resolved.y;
        anchor = resolved.anchor;
        options.placedLabels?.push(getLabelBounds(label, labelX, labelY, anchor));
    }

    text.setAttribute('x', String(labelX));
    text.setAttribute('y', String(labelY));
    text.setAttribute('text-anchor', anchor);
    text.setAttribute('dominant-baseline', 'middle');
    text.textContent = label;
    text.classList.add('node-text');
    svg.appendChild(text);
}

function truncateTopologyLabel(value, maxLen = 22) {
    const label = String(value || 'unknown-agent');
    if (label.length <= maxLen) return label;
    return `${label.slice(0, maxLen - 1)}…`;
}

function resolveLabelPositionWithJitter(label, x, y, anchor, placedLabels) {
    const offsets = [
        [0, 0],
        [10, 0],
        [-10, 0],
        [0, 10],
        [0, -10],
        [14, 10],
        [-14, 10],
        [14, -10],
        [-14, -10],
        [20, 0],
        [-20, 0],
        [0, 18],
        [0, -18],
    ];

    for (const [dx, dy] of offsets) {
        const candidate = getLabelBounds(label, x + dx, y + dy, anchor);
        const collides = placedLabels.some((existing) => boundsOverlap(candidate, existing, 3));
        if (!collides) {
            return { x: x + dx, y: y + dy, anchor };
        }
    }

    return { x, y, anchor };
}

function getLabelBounds(label, x, y, anchor) {
    const width = Math.max(32, label.length * 6.8);
    const halfHeight = 7;

    let left = x - width / 2;
    let right = x + width / 2;

    if (anchor === 'start') {
        left = x;
        right = x + width;
    } else if (anchor === 'end') {
        left = x - width;
        right = x;
    }

    return {
        left,
        right,
        top: y - halfHeight,
        bottom: y + halfHeight,
    };
}

function boundsOverlap(a, b, padding = 0) {
    return !(
        a.right + padding < b.left ||
        a.left - padding > b.right ||
        a.bottom + padding < b.top ||
        a.top - padding > b.bottom
    );
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
    if (!event || !event.agent) return;

    const agentName = String(event.agent);
    let agent = state.agents.find(a => a.name === agentName);

    // Create optimistic local entry so charts/tables can update immediately
    // between backend poll cycles.
    if (!agent) {
        agent = {
            name: agentName,
            status: 'healthy',
            metrics: {},
            dependencies: [],
            last_seen: new Date().toISOString(),
        };
        state.agents.push(agent);
    }

    agent.metrics = agent.metrics || {};
    const metrics = agent.metrics;
    const phase = String(event.event || '').split('.').pop();
    const duration = Number(event.duration_ms || 0);

    if (phase === 'accepted') {
        metrics.tasks_accepted = (metrics.tasks_accepted || 0) + 1;
    }

    if (phase === 'final') {
        const prevCompleted = Number(metrics.tasks_completed || 0);
        const prevLatency = Number(metrics.avg_latency_ms || 0);
        metrics.tasks_completed = prevCompleted + 1;

        if (duration > 0) {
            metrics.avg_latency_ms = (
                (prevLatency * prevCompleted + duration) / metrics.tasks_completed
            );
        }
    }

    if (phase === 'error') {
        metrics.tasks_errored = (metrics.tasks_errored || 0) + 1;
        if (duration > 0 && !metrics.avg_latency_ms) {
            metrics.avg_latency_ms = duration;
        }
    }

    agent.last_seen = event.timestamp || new Date().toISOString();

    renderHeatmap();
    updatePerformanceCharts();
}

// ── Scenario Flow Board ───────────────────────────────────────────────
function initializeScenarioFlowBoard() {
    loadObserverActions();
    initializeFlowBoardControls();
    initializeFlowBoardInteractions();
    renderScenarioFlowBoard();

    setInterval(() => {
        pruneStaleScenarios();
        maybeStartSyntheticFlow();
        renderScenarioFlowBoard();
    }, 5000);

    setTimeout(() => {
        maybeStartSyntheticFlow();
    }, FLOW_SYNTHETIC_DELAY_MS);
}

function initializeFlowBoardControls() {
    const hideSynthetic = document.getElementById('flow-hide-synthetic');
    const severityFilter = document.getElementById('flow-risk-filter');
    const needsAction = document.getElementById('flow-needs-action');

    if (hideSynthetic) {
        hideSynthetic.checked = state.flowFilters.hideSynthetic;
        hideSynthetic.addEventListener('change', (event) => {
            state.flowFilters.hideSynthetic = event.target.checked;
            renderScenarioFlowBoard();
        });
    }

    if (severityFilter) {
        severityFilter.value = state.flowFilters.severity;
        severityFilter.addEventListener('change', (event) => {
            state.flowFilters.severity = event.target.value;
            renderScenarioFlowBoard();
        });
    }

    if (needsAction) {
        needsAction.checked = state.flowFilters.needsAction;
        needsAction.addEventListener('change', (event) => {
            state.flowFilters.needsAction = event.target.checked;
            renderScenarioFlowBoard();
        });
    }
}

function initializeFlowBoardInteractions() {
    const panel = document.querySelector('.scenario-flow-panel');
    if (!panel) return;

    panel.addEventListener('click', (event) => {
        const actionBtn = event.target.closest('button[data-flow-action]');
        if (actionBtn) {
            event.stopPropagation();
            const scenarioId = actionBtn.dataset.scenarioId;
            const action = actionBtn.dataset.flowAction;
            if (!scenarioId || !action) return;

            if (action === 'ack') {
                ackScenario(scenarioId);
            } else if (action === 'escalate') {
                escalateScenario(scenarioId);
            }

            renderScenarioFlowBoard();
            return;
        }

        const card = event.target.closest('.flow-card[data-scenario-id]');
        if (!card) return;

        const interactive = event.target.closest('button, select, input, label');
        if (interactive) return;

        const scenario = state.scenarios[card.dataset.scenarioId];
        if (scenario) {
            drillThroughScenarioTrace(scenario);
        }
    });

    panel.addEventListener('change', (event) => {
        const assigneeSelect = event.target.closest('select[data-flow-action="assign"]');
        if (!assigneeSelect) return;

        const scenarioId = assigneeSelect.dataset.scenarioId;
        if (!scenarioId) return;

        assignScenario(scenarioId, assigneeSelect.value || '');
        renderScenarioFlowBoard();
    });
}

async function loadScenarioCatalog() {
    try {
        const response = await fetch('/api/scenario-catalog');
        if (!response.ok) {
            return;
        }

        const payload = await response.json();
        if (!Array.isArray(payload)) {
            return;
        }

        state.scenarioCatalog = payload;
        renderScenarioFlowBoard();
    } catch (error) {
        console.warn('Scenario catalog unavailable:', error);
    }
}

function ingestScenarioEvent(event, isSynthetic = false) {
    if (!event || !event.task_id || !event.event) return;

    const phase = normalizeFlowPhase(event.event);
    if (!phase) return;

    if (!isSynthetic) {
        state.lastRealFlowEventAt = Date.now();
        if (state.flowSource !== 'live') {
            state.flowSource = 'live';
            stopSyntheticFlow();
            removeSyntheticScenarios();
        }
    }

    const scenarioId = deriveScenarioId(event.task_id);
    const now = Date.now();
    const current = state.scenarios[scenarioId] || {
        id: scenarioId,
        journeyLabel: resolveScenarioLabel(event.task_id, scenarioId),
        journeyDescription: resolveScenarioDescription(event.task_id),
        taskId: event.task_id,
        step: deriveStepName(event.task_id, event.agent),
        phase,
        status: 'active',
        agent: event.agent || 'unknown-agent',
        firstSeenAt: now,
        updatedAt: now,
        completedAt: null,
        isSynthetic,
        totalDurationMs: 0,
        retryCount: 0,
        requiresHitl: inferRequiresHitl(event.task_id),
        waitingOn: event.waiting_on || null,
        lane: 'in-progress',
        laneEnteredAt: now,
    };

    current.taskId = event.task_id;
    current.journeyLabel = resolveScenarioLabel(event.task_id, scenarioId);
    current.journeyDescription = resolveScenarioDescription(event.task_id);
    current.step = deriveStepName(event.task_id, event.agent);
    current.phase = phase;
    current.agent = event.agent || current.agent;
    current.updatedAt = now;
    current.isSynthetic = isSynthetic;
    current.totalDurationMs += event.duration_ms || 0;
    current.retryCount = Math.max(current.retryCount, Number(event.retry_count || 0));
    current.requiresHitl = Boolean(event.requires_hitl ?? current.requiresHitl ?? inferRequiresHitl(event.task_id));
    current.waitingOn = event.waiting_on || current.waitingOn || null;

    if (phase === 'final') {
        current.status = 'completed';
        current.completedAt = now;
    } else if (phase === 'error') {
        current.status = 'active';
        current.retryCount = Math.max(current.retryCount, FLOW_RETRY_BLOCK_THRESHOLD);
    } else {
        current.status = 'active';
    }

    const risk = evaluateScenarioRisk(current, now);
    const nextLane = getFlowLane(current, risk, now);
    if (current.lane !== nextLane) {
        current.lane = nextLane;
        current.laneEnteredAt = now;
    }

    state.scenarios[scenarioId] = current;
    renderScenarioFlowBoard();
}

function inferRequiresHitl(taskId) {
    const value = String(taskId || '').toLowerCase();
    return value.includes('hitl') || value.includes('approval') || value.includes('consent');
}

function normalizeFlowPhase(eventName) {
    if (typeof eventName !== 'string') return null;
    const phase = eventName.split('.').pop();
    if (['accepted', 'working', 'final', 'error'].includes(phase)) {
        return phase;
    }
    return null;
}

function deriveScenarioId(taskId) {
    if (!taskId || typeof taskId !== 'string') return 'unknown-scenario';
    const parts = taskId.split('-').filter(Boolean);

    if (parts.length >= 3 && parts[0].toUpperCase() === 'VISIT') {
        return `${parts[0]}-${parts[1]}`;
    }

    if (parts.length >= 3 && parts[0].toUpperCase() === 'PAT') {
        return `${parts[0]}-${parts[1]}`;
    }

    if (parts.length >= 2) {
        return `${parts[0]}-${parts[1]}`;
    }

    return parts[0] || taskId;
}

function deriveStepName(taskId, agentName) {
    if (taskId && taskId.includes('-')) {
        return taskId.split('-').pop();
    }
    return agentName || 'unknown-step';
}

function resolveScenarioLabel(taskId, scenarioId) {
    const match = findBestScenarioMatch(taskId);
    if (match) {
        return match.display_name || humanizeScenarioId(match.name || '');
    }
    return humanizeScenarioId(scenarioId);
}

function resolveScenarioDescription(taskId) {
    const match = findBestScenarioMatch(taskId);
    if (match && match.description) {
        return String(match.description);
    }
    return 'Scenario description unavailable';
}

function findBestScenarioMatch(taskId) {
    const normalizedTaskId = String(taskId || '').toLowerCase();

    if (state.scenarioCatalog.length > 0 && normalizedTaskId) {
        let bestMatch = null;

        state.scenarioCatalog.forEach((entry) => {
            const prefixes = Array.isArray(entry.task_id_prefixes) ? entry.task_id_prefixes : [];
            prefixes.forEach((prefix) => {
                const normalizedPrefix = String(prefix || '').toLowerCase().trim();
                if (!normalizedPrefix) return;

                if (matchesTaskIdPrefix(normalizedTaskId, normalizedPrefix)) {
                    if (!bestMatch || normalizedPrefix.length > bestMatch.prefixLength) {
                        bestMatch = {
                            entry,
                            prefixLength: normalizedPrefix.length,
                        };
                    }
                }
            });
        });

        if (bestMatch) {
            return bestMatch.entry;
        }
    }

    return null;
}

function matchesTaskIdPrefix(taskId, prefix) {
    return taskId.includes(`-${prefix}-`) || taskId.endsWith(`-${prefix}`) || taskId.includes(prefix);
}

function humanizeScenarioId(value) {
    if (!value) return 'Unknown Journey';
    return String(value)
        .replace(/^VISIT-[^-]+-?/i, '')
        .replace(/_/g, ' ')
        .replace(/-/g, ' ')
        .replace(/\b\w/g, (char) => char.toUpperCase())
        .trim() || value;
}

function getFlowLane(scenario, risk, now = Date.now()) {
    if (scenario.status === 'completed') {
        return 'completed';
    }

    const ageMs = now - scenario.updatedAt;
    if (scenario.requiresHitl && !isScenarioAcknowledged(scenario.id)) {
        return 'queued';
    }

    if (
        scenario.phase === 'error' ||
        scenario.retryCount >= FLOW_RETRY_BLOCK_THRESHOLD ||
        ageMs > FLOW_STALE_MS ||
        risk.slaBreached
    ) {
        return 'blocked';
    }

    return 'in-progress';
}

function renderScenarioFlowBoard() {
    const laneQueued = document.getElementById('flow-lane-queued');
    const laneInProgress = document.getElementById('flow-lane-in-progress');
    const laneBlocked = document.getElementById('flow-lane-blocked');
    const laneCompleted = document.getElementById('flow-lane-completed');

    if (!laneQueued || !laneInProgress || !laneBlocked || !laneCompleted) return;

    const now = Date.now();

    const scenarios = Object.values(state.scenarios)
        .map((scenario) => {
            const risk = evaluateScenarioRisk(scenario, now);
            const lane = getFlowLane(scenario, risk, now);

            if (scenario.lane !== lane) {
                scenario.lane = lane;
                scenario.laneEnteredAt = now;
            }

            return {
                ...scenario,
                lane,
                risk,
                observer: getObserverAction(scenario.id),
            };
        })
        .filter((scenario) => applyFlowFilters(scenario))
        .sort((a, b) => {
            if (b.risk.score !== a.risk.score) return b.risk.score - a.risk.score;
            return b.updatedAt - a.updatedAt;
        })
        .slice(0, 24);

    const lanes = {
        queued: [],
        'in-progress': [],
        blocked: [],
        completed: [],
    };

    scenarios.forEach((scenario) => {
        lanes[scenario.lane].push(scenario);
    });

    updateFlowSummaryCounts(lanes, scenarios);
    updateFlowKpis(scenarios);
    updateFlowSourceBadge();
    refreshFlowAlerts(scenarios, now);
    renderFlowAlertFeed();

    renderFlowLane(laneQueued, lanes.queued, 'No queued/HITL journeys', 'queued');
    renderFlowLane(laneInProgress, lanes['in-progress'], 'No journeys in progress', 'in-progress');
    renderFlowLane(laneBlocked, lanes.blocked, 'No blocked journeys', 'blocked');
    renderFlowLane(laneCompleted, lanes.completed, 'No completed journeys yet');
}

function applyFlowFilters(scenario) {
    if (state.flowFilters.hideSynthetic && scenario.isSynthetic) {
        return false;
    }

    if (state.flowFilters.needsAction && !scenarioNeedsObserverAction(scenario)) {
        return false;
    }

    if (state.flowFilters.severity === 'all') return true;
    const rank = severityRank(scenario.risk.severity);
    if (state.flowFilters.severity === 'medium') return rank >= severityRank('medium');
    if (state.flowFilters.severity === 'high') return rank >= severityRank('high');
    if (state.flowFilters.severity === 'critical') return rank >= severityRank('critical');
    return true;
}

function renderFlowLane(container, scenarios, emptyMessage, laneName = '') {
    container.innerHTML = '';

    if (scenarios.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'flow-empty';
        empty.textContent = emptyMessage;
        container.appendChild(empty);
        return;
    }

    scenarios.forEach((scenario) => {
        const card = document.createElement('article');
        card.className = `flow-card ${scenario.isSynthetic ? 'synthetic' : ''} lane-${laneName}`;
        card.dataset.scenarioId = scenario.id;

        const ageSeconds = Math.max(0, Math.floor((Date.now() - scenario.updatedAt) / 1000));
        const durationSeconds = Math.max(0, Math.floor((scenario.updatedAt - scenario.firstSeenAt) / 1000));
        const laneAgeSeconds = Math.max(0, Math.floor((Date.now() - (scenario.laneEnteredAt || scenario.updatedAt)) / 1000));

        const journeyLabel = escapeHtml(scenario.journeyLabel || 'Unknown Journey');
        const journeyDescription = escapeHtmlAttribute(
            scenario.journeyDescription || 'Scenario description unavailable'
        );
        const scenarioId = escapeHtml(scenario.id || 'unknown-scenario');
        const agentName = escapeHtml(scenario.agent || 'unknown-agent');
        const stepName = escapeHtml(scenario.step || 'unknown-step');
        const phase = escapeHtml(scenario.phase || 'working');
        const severity = escapeHtml(scenario.risk.severity || 'low');
        const riskScore = Number(scenario.risk.score || 0);
        const whyBadges = (scenario.risk.reasons || [])
            .slice(0, 3)
            .map((reason) => `<span class="flow-why-badge">${escapeHtml(reason)}</span>`)
            .join('');

        const observer = scenario.observer || getObserverAction(scenario.id);
        const ackText = observer.ackAt
            ? `Acked ${formatAgeSeconds(Math.max(0, Math.floor((Date.now() - observer.ackAt) / 1000)))} ago`
            : 'Unacknowledged';
        const escalationText = observer.escalatedAt
            ? `Escalated ${formatAgeSeconds(Math.max(0, Math.floor((Date.now() - observer.escalatedAt) / 1000)))} ago`
            : 'Not escalated';

        card.innerHTML = `
            <div class="journey-label" data-description="${journeyDescription}" tabindex="0" aria-describedby="journey-popover">${journeyLabel}</div>
            <div class="scenario-id">${scenarioId}</div>
            <div class="meta">
                <span>${agentName}</span>
                <span>${ageSeconds}s ago</span>
            </div>
            <span class="phase-badge phase-${phase}">${phase}</span>
            <span class="risk-badge risk-${severity}">Risk ${severity.toUpperCase()} · ${riskScore}</span>
            <div class="flow-why-row">${whyBadges || '<span class="flow-why-badge">No active risk signals</span>'}</div>
            <div class="meta">
                <span>Step: ${stepName}</span>
                <span>Elapsed: ${durationSeconds}s</span>
            </div>
            <div class="meta">
                <span>Lane age: ${laneAgeSeconds}s</span>
                <span>SLA: ${scenario.risk.slaBreached ? 'Breached' : 'Within target'}</span>
            </div>
            <div class="observer-controls">
                <button type="button" class="flow-action-btn" data-flow-action="ack" data-scenario-id="${scenarioId}">
                    ${observer.ackAt ? 'Re-ack' : 'Acknowledge'}
                </button>
                <button type="button" class="flow-action-btn warn" data-flow-action="escalate" data-scenario-id="${scenarioId}">
                    ${observer.escalated ? 'Escalated' : 'Escalate'}
                </button>
                <select class="flow-assign-select" data-flow-action="assign" data-scenario-id="${scenarioId}" aria-label="Assign observer">
                    <option value="" ${observer.assignee ? '' : 'selected'}>Unassigned</option>
                    <option value="ops-nurse" ${observer.assignee === 'ops-nurse' ? 'selected' : ''}>Ops nurse</option>
                    <option value="flow-lead" ${observer.assignee === 'flow-lead' ? 'selected' : ''}>Flow lead</option>
                    <option value="incident-commander" ${observer.assignee === 'incident-commander' ? 'selected' : ''}>Incident commander</option>
                </select>
            </div>
            <div class="meta observer-state">
                <span>${escapeHtml(ackText)}</span>
                <span>${escapeHtml(escalationText)}</span>
            </div>
        `;

        container.appendChild(card);
    });
}

function updateFlowSummaryCounts(lanes, scenarios) {
    document.getElementById('flow-in-progress-count').textContent = lanes['in-progress'].length;
    document.getElementById('flow-queued-count').textContent = lanes.queued.length;
    document.getElementById('flow-blocked-count').textContent = lanes.blocked.length;
    document.getElementById('flow-completed-count').textContent = lanes.completed.length;
    const criticalCount = scenarios.filter((scenario) => scenario.risk.severity === 'critical').length;
    document.getElementById('flow-critical-count').textContent = criticalCount;
}

function updateFlowKpis(scenarios) {
    const blockedAgesSec = scenarios
        .filter((scenario) => scenario.lane === 'blocked')
        .map((scenario) => Math.max(0, (Date.now() - scenario.updatedAt) / 1000));
    const p95RiskAge = percentile(blockedAgesSec, 95);

    const active = scenarios.filter((scenario) => scenario.status !== 'completed');
    const breached = active.filter((scenario) => scenario.risk.slaBreached).length;
    const breachRate = active.length > 0 ? (breached / active.length) * 100 : 0;

    const ackDurations = Object.entries(state.observerActions)
        .map(([scenarioId, action]) => {
            const scenario = state.scenarios[scenarioId];
            if (!scenario || !action?.ackAt) return null;
            return Math.max(0, (action.ackAt - scenario.firstSeenAt) / 1000);
        })
        .filter((value) => Number.isFinite(value));
    const meanAckSeconds = ackDurations.length
        ? ackDurations.reduce((sum, value) => sum + value, 0) / ackDurations.length
        : NaN;

    const escalations = Object.values(state.observerActions).filter((action) => action.escalated).length;

    document.getElementById('flow-kpi-p95-risk-age').textContent = Number.isFinite(p95RiskAge)
        ? `${Math.round(p95RiskAge)}s`
        : '--';
    document.getElementById('flow-kpi-sla-breach-rate').textContent = `${breachRate.toFixed(1)}%`;
    document.getElementById('flow-kpi-mean-ack-seconds').textContent = Number.isFinite(meanAckSeconds)
        ? `${Math.round(meanAckSeconds)}s`
        : '--';
    document.getElementById('flow-kpi-escalations').textContent = String(escalations);
}

function percentile(values, p) {
    if (!Array.isArray(values) || values.length === 0) return NaN;
    const sorted = [...values].sort((a, b) => a - b);
    const index = Math.ceil((p / 100) * sorted.length) - 1;
    return sorted[Math.max(0, Math.min(sorted.length - 1, index))];
}

function evaluateScenarioRisk(scenario, now = Date.now()) {
    const elapsedMs = Math.max(0, scenario.updatedAt - scenario.firstSeenAt);
    const ageMs = Math.max(0, now - scenario.updatedAt);
    const retryCount = Number(scenario.retryCount || 0);
    const slaTargetMs = deriveScenarioSlaTargetMs(scenario);
    const slaOverrunMs = Math.max(0, elapsedMs - slaTargetMs);
    const slaBreached = slaOverrunMs > 0;

    const reasons = [];
    let score = 0;

    if (slaBreached) {
        score += Math.min(30, 10 + Math.round(slaOverrunMs / 1000));
        reasons.push(`SLA +${Math.round(slaOverrunMs / 1000)}s`);
    }
    if (ageMs > FLOW_STALE_MS) {
        score += 20;
        reasons.push(`Stale update ${Math.round(ageMs / 1000)}s`);
    }
    if (retryCount > 0) {
        score += Math.min(20, retryCount * 6);
        reasons.push(`${retryCount} retries`);
    }
    if (scenario.phase === 'error') {
        score += 30;
        reasons.push('Error state');
    }
    if (scenario.requiresHitl && !isScenarioAcknowledged(scenario.id)) {
        score += 15;
        reasons.push('Awaiting HITL/observer');
    }
    if (scenario.waitingOn) {
        score += 10;
        reasons.push(`Waiting on ${scenario.waitingOn}`);
    }
    if (reasons.length === 0) {
        reasons.push('Nominal progression');
    }

    return {
        score: Math.max(0, Math.min(100, score)),
        severity: riskSeverityFromScore(score),
        reasons,
        elapsedMs,
        ageMs,
        slaTargetMs,
        slaOverrunMs,
        slaBreached,
    };
}

function deriveScenarioSlaTargetMs(scenario) {
    const text = `${scenario.journeyLabel || ''} ${scenario.journeyDescription || ''} ${scenario.taskId || ''}`.toLowerCase();
    if (text.includes('critical') || text.includes('stroke') || text.includes('sepsis') || text.includes('cardiac')) {
        return FLOW_SLA_CRITICAL_MS;
    }
    if (text.includes('urgent') || text.includes('triage') || text.includes('high')) {
        return FLOW_SLA_URGENT_MS;
    }
    return FLOW_SLA_DEFAULT_MS;
}

function riskSeverityFromScore(score) {
    if (score >= 75) return 'critical';
    if (score >= 50) return 'high';
    if (score >= 25) return 'medium';
    return 'low';
}

function severityRank(severity) {
    if (severity === 'critical') return 4;
    if (severity === 'high') return 3;
    if (severity === 'medium') return 2;
    return 1;
}

function scenarioNeedsObserverAction(scenario) {
    const observer = scenario.observer || getObserverAction(scenario.id);
    if (!observer.ackAt) return true;
    if (scenario.lane === 'blocked' && !observer.escalated) return true;
    if (!observer.assignee && scenario.risk.severity !== 'low') return true;
    return false;
}

function getObserverAction(scenarioId) {
    return state.observerActions[scenarioId] || {
        ackAt: null,
        escalated: false,
        escalatedAt: null,
        assignee: '',
    };
}

function setObserverAction(scenarioId, patch) {
    const current = getObserverAction(scenarioId);
    state.observerActions[scenarioId] = {
        ...current,
        ...patch,
    };
    persistObserverActions();
}

function isScenarioAcknowledged(scenarioId) {
    return Boolean(getObserverAction(scenarioId).ackAt);
}

function ackScenario(scenarioId) {
    const now = Date.now();
    setObserverAction(scenarioId, { ackAt: now });
    state.observerAudit.unshift({ type: 'ack', scenarioId, timestamp: now });
    if (state.observerAudit.length > FLOW_OBSERVER_AUDIT_MAX) {
        state.observerAudit = state.observerAudit.slice(0, FLOW_OBSERVER_AUDIT_MAX);
    }
}

function escalateScenario(scenarioId) {
    const now = Date.now();
    const scenario = state.scenarios[scenarioId];
    const risk = scenario ? evaluateScenarioRisk(scenario, now) : { severity: 'high', score: 60 };

    setObserverAction(scenarioId, { escalated: true, escalatedAt: now });
    state.observerAudit.unshift({ type: 'escalate', scenarioId, timestamp: now });
    if (state.observerAudit.length > FLOW_OBSERVER_AUDIT_MAX) {
        state.observerAudit = state.observerAudit.slice(0, FLOW_OBSERVER_AUDIT_MAX);
    }

    triggerFlowAlert({
        kind: 'observer-escalation',
        scenarioId,
        message: `Observer escalation raised for ${scenarioId}`,
        severity: risk.severity,
        score: risk.score,
        timestamp: now,
    });
}

function assignScenario(scenarioId, assignee) {
    const now = Date.now();
    setObserverAction(scenarioId, { assignee, assignAt: now });
    state.observerAudit.unshift({ type: 'assign', scenarioId, assignee, timestamp: now });
    if (state.observerAudit.length > FLOW_OBSERVER_AUDIT_MAX) {
        state.observerAudit = state.observerAudit.slice(0, FLOW_OBSERVER_AUDIT_MAX);
    }
}

function loadObserverActions() {
    try {
        const raw = window.localStorage.getItem(FLOW_OBSERVER_STORAGE_KEY);
        if (!raw) return;
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === 'object') {
            state.observerActions = parsed;
        }
    } catch (error) {
        console.warn('Unable to load observer actions; clearing corrupted local state:', error);
        try {
            window.localStorage.removeItem(FLOW_OBSERVER_STORAGE_KEY);
        } catch (storageError) {
            // Ignore storage permission errors.
        }
        state.observerActions = {};
    }
}

function persistObserverActions() {
    try {
        window.localStorage.setItem(FLOW_OBSERVER_STORAGE_KEY, JSON.stringify(state.observerActions));
    } catch (error) {
        console.warn('Unable to persist observer actions:', error);
    }
}

function refreshFlowAlerts(scenarios, now = Date.now()) {
    pruneAlertHistory(now);

    scenarios.forEach((scenario) => {
        const shouldAlert = scenario.lane === 'blocked' || scenario.risk.severity === 'critical';
        if (!shouldAlert) return;

        const dedupKey = `${scenario.id}:${scenario.lane}:${scenario.risk.severity}`;
        const lastAlertAt = state.alertHistory[dedupKey] || 0;
        if (now - lastAlertAt < FLOW_ALERT_DEDUP_MS) return;

        state.alertHistory[dedupKey] = now;
        triggerFlowAlert({
            kind: scenario.lane === 'blocked' ? 'blocked-journey' : 'critical-risk',
            scenarioId: scenario.id,
            message: `${scenario.journeyLabel} is ${scenario.lane === 'blocked' ? 'blocked' : 'critical risk'}`,
            severity: scenario.risk.severity,
            score: scenario.risk.score,
            timestamp: now,
        });
    });
}

function pruneAlertHistory(now = Date.now()) {
    Object.keys(state.alertHistory).forEach((dedupKey) => {
        const timestamp = Number(state.alertHistory[dedupKey] || 0);
        if (!Number.isFinite(timestamp) || now - timestamp > FLOW_ALERT_HISTORY_RETENTION_MS) {
            delete state.alertHistory[dedupKey];
        }
    });
}

function pruneObserverState(now = Date.now()) {
    const activeScenarioIds = new Set(Object.keys(state.scenarios));
    let changed = false;

    Object.entries(state.observerActions).forEach(([scenarioId, action]) => {
        const ackAt = Number(action?.ackAt || 0);
        const escalatedAt = Number(action?.escalatedAt || 0);
        const assignAt = Number(action?.assignAt || 0);
        const lastActionAt = Math.max(ackAt, escalatedAt, assignAt);
        const stale = !activeScenarioIds.has(scenarioId)
            && lastActionAt > 0
            && now - lastActionAt > FLOW_OBSERVER_ACTION_RETENTION_MS;

        if (stale) {
            delete state.observerActions[scenarioId];
            changed = true;
        }
    });

    if (state.observerAudit.length > FLOW_OBSERVER_AUDIT_MAX) {
        state.observerAudit = state.observerAudit.slice(0, FLOW_OBSERVER_AUDIT_MAX);
    }

    if (changed) {
        persistObserverActions();
    }
}

function triggerFlowAlert(alert) {
    state.alertFeed.unshift(alert);
    state.alertFeed = state.alertFeed.slice(0, 30);
    emitAlertHook(alert);

    if (alert.severity === 'critical' || alert.kind === 'observer-escalation') {
        showToast(alert.message, 'warning');
    }
}

function emitAlertHook(alert) {
    try {
        window.dispatchEvent(new CustomEvent('command-centre-flow-alert', { detail: alert }));
    } catch (error) {
        console.warn('Failed to dispatch flow alert event:', error);
    }

    try {
        const webhookUrl = window.localStorage.getItem(FLOW_ALERT_WEBHOOK_KEY);
        if (!webhookUrl) return;
        fetch(webhookUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(alert),
            keepalive: true,
        }).catch(() => {});
    } catch (error) {
        // Ignore storage/network config issues.
    }
}

function renderFlowAlertFeed() {
    const feed = document.getElementById('flow-alert-feed');
    if (!feed) return;

    if (!state.alertFeed.length) {
        feed.innerHTML = '<div class="flow-empty">No active flow alerts.</div>';
        return;
    }

    feed.innerHTML = state.alertFeed.slice(0, 8).map((alert) => {
        const ageSec = Math.max(0, Math.floor((Date.now() - alert.timestamp) / 1000));
        return `
            <div class="flow-alert-item severity-${escapeHtml(alert.severity)}">
                <div class="flow-alert-title">${escapeHtml(alert.message)}</div>
                <div class="flow-alert-meta">
                    <span>${escapeHtml(alert.kind)}</span>
                    <span>Score ${Number(alert.score || 0)}</span>
                    <span>${ageSec}s ago</span>
                </div>
            </div>
        `;
    }).join('');
}

function drillThroughScenarioTrace(scenario) {
    const scenarioToken = String(scenario.id || '').toLowerCase();
    const labelToken = String(scenario.journeyLabel || '').toLowerCase();

    const match = state.traceRuns.find((run) => {
        const name = String(run.scenario_name || '').toLowerCase();
        const visit = String(run.visit_id || '').toLowerCase();
        const traceId = String(run.trace_id || '').toLowerCase();
        return (
            (scenarioToken && (name.includes(scenarioToken) || visit.includes(scenarioToken) || traceId.includes(scenarioToken))) ||
            (labelToken && name.includes(labelToken.replace(/\s+/g, '_')))
        );
    });

    if (!match) {
        showToast(`No matching trace run for ${scenario.id}`, 'warning');
        return;
    }

    selectTraceRun(match.trace_id);
    showToast(`Focused trace ${match.trace_id}`, 'success');
}

function formatAgeSeconds(seconds) {
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const rem = seconds % 60;
    return `${minutes}m ${rem}s`;
}

function initializeJourneyPopover() {
    const popover = document.createElement('div');
    popover.id = 'journey-popover';
    popover.className = 'journey-popover hidden';
    popover.setAttribute('role', 'tooltip');
    document.body.appendChild(popover);
    popoverState.element = popover;

    document.addEventListener('mouseover', (event) => {
        const target = event.target.closest('.journey-label[data-description]');
        if (!target) return;
        showJourneyPopover(target);
    });

    document.addEventListener('mouseout', (event) => {
        if (!popoverState.activeTarget) return;

        const leavingTarget = event.target.closest('.journey-label[data-description]');
        const enteringTarget = event.relatedTarget && event.relatedTarget.closest
            ? event.relatedTarget.closest('.journey-label[data-description]')
            : null;

        if (leavingTarget && leavingTarget === popoverState.activeTarget && !enteringTarget) {
            hideJourneyPopover();
        }
    });

    document.addEventListener('focusin', (event) => {
        const target = event.target.closest('.journey-label[data-description]');
        if (!target) return;
        showJourneyPopover(target);
    });

    document.addEventListener('focusout', (event) => {
        const target = event.target.closest('.journey-label[data-description]');
        if (!target) return;
        hideJourneyPopover();
    });

    document.addEventListener('scroll', () => {
        if (popoverState.activeTarget) {
            positionJourneyPopover(popoverState.activeTarget);
        }
    }, true);

    window.addEventListener('resize', () => {
        if (popoverState.activeTarget) {
            positionJourneyPopover(popoverState.activeTarget);
        }
    });
}

function showJourneyPopover(target) {
    if (!popoverState.element) return;

    const description = target.dataset.description || 'Scenario description unavailable';
    popoverState.element.textContent = description;
    popoverState.element.classList.remove('hidden');
    popoverState.activeTarget = target;
    positionJourneyPopover(target);
}

function hideJourneyPopover() {
    if (!popoverState.element) return;
    popoverState.element.classList.add('hidden');
    popoverState.activeTarget = null;
}

function positionJourneyPopover(target) {
    if (!popoverState.element || !target) return;

    const rect = target.getBoundingClientRect();
    const popover = popoverState.element;
    const margin = 10;

    popover.style.left = '0px';
    popover.style.top = '0px';

    const popoverWidth = popover.offsetWidth;
    const popoverHeight = popover.offsetHeight;

    let left = rect.left + window.scrollX;
    let top = rect.bottom + window.scrollY + margin;

    const maxLeft = window.scrollX + window.innerWidth - popoverWidth - margin;
    left = Math.max(window.scrollX + margin, Math.min(left, maxLeft));

    const wouldOverflowBottom = top + popoverHeight > window.scrollY + window.innerHeight - margin;
    if (wouldOverflowBottom) {
        top = rect.top + window.scrollY - popoverHeight - margin;
    }

    popover.style.left = `${left}px`;
    popover.style.top = `${Math.max(window.scrollY + margin, top)}px`;
}

function updateFlowSummaryCounts(lanes, scenarios = []) {
    document.getElementById('flow-in-progress-count').textContent = lanes['in-progress']?.length || 0;
    document.getElementById('flow-queued-count').textContent = lanes.queued?.length || 0;
    document.getElementById('flow-blocked-count').textContent = lanes.blocked?.length || 0;
    document.getElementById('flow-completed-count').textContent = lanes.completed?.length || 0;
    const criticalCount = scenarios.filter((scenario) => scenario.risk?.severity === 'critical').length;
    document.getElementById('flow-critical-count').textContent = criticalCount;
}

function updateFlowSourceBadge() {
    const badge = document.getElementById('flow-board-source');
    const freshness = document.getElementById('flow-live-freshness');
    const warning = document.getElementById('flow-live-stale-warning');
    if (!badge) return;

    badge.classList.remove('idle', 'live', 'synthetic', 'stale');
    badge.classList.add(state.flowSource);

    const liveAgeMs = state.lastRealFlowEventAt > 0 ? Date.now() - state.lastRealFlowEventAt : Infinity;
    const liveAgeSec = Number.isFinite(liveAgeMs) ? Math.floor(liveAgeMs / 1000) : null;
    const liveIsStale = state.flowSource === 'live' && Number.isFinite(liveAgeMs) && liveAgeMs > FLOW_LIVE_STALE_MS;

    if (warning) {
        warning.classList.toggle('hidden', !liveIsStale);
    }

    if (state.flowSource === 'live') {
        badge.textContent = liveIsStale ? 'Live feed stale' : 'Live journey events';
        if (liveIsStale) {
            badge.classList.add('stale');
        }
    } else if (state.flowSource === 'synthetic') {
        badge.textContent = 'Demo mode (synthetic)';
    } else {
        badge.textContent = 'Waiting for events';
    }

    if (freshness) {
        if (state.flowSource === 'synthetic') {
            freshness.textContent = 'Synthetic heartbeat active';
        } else if (!Number.isFinite(liveAgeMs)) {
            freshness.textContent = 'No live heartbeat';
        } else {
            freshness.textContent = `Last live event ${liveAgeSec}s ago`;
        }
    }
}

function maybeStartSyntheticFlow() {
    const noLiveTraffic = Date.now() - state.lastRealFlowEventAt > FLOW_SYNTHETIC_DELAY_MS;
    if (!noLiveTraffic || state.syntheticFlowInterval || state.flowSource === 'live') {
        return;
    }

    state.flowSource = 'synthetic';
    state.syntheticFlowInterval = setInterval(() => {
        emitSyntheticFlowEvent();
    }, 2500);

    emitSyntheticFlowEvent();
}

function stopSyntheticFlow() {
    if (state.syntheticFlowInterval) {
        clearInterval(state.syntheticFlowInterval);
        state.syntheticFlowInterval = null;
    }
}

function removeSyntheticScenarios() {
    Object.keys(state.scenarios).forEach((id) => {
        if (state.scenarios[id].isSynthetic) {
            delete state.scenarios[id];
        }
    });
}

function emitSyntheticFlowEvent() {
    const index = state.syntheticCursor % state.syntheticScenarios.length;
    const scenario = state.syntheticScenarios[index];
    state.syntheticCursor += 1;

    const stepName = scenario.steps[scenario.index];
    let phase = 'working';
    if (scenario.index === 0) phase = 'accepted';
    if (scenario.index === scenario.steps.length - 1) phase = 'final';

    const payload = {
        agent: `${stepName}-agent`,
        task_id: `${scenario.id}-${stepName}`,
        event: `nexus.task.${phase}`,
        timestamp: new Date().toISOString(),
        duration_ms: Math.floor(Math.random() * 1200) + 300,
    };

    addEvent(payload);
    ingestScenarioEvent(payload, true);

    if (phase === 'final') {
        scenario.index = 0;
    } else {
        scenario.index += 1;
    }
}

function pruneStaleScenarios() {
    const now = Date.now();
    Object.keys(state.scenarios).forEach((id) => {
        if (now - state.scenarios[id].updatedAt > FLOW_EXPIRE_MS) {
            delete state.scenarios[id];
        }
    });
    pruneObserverState(now);
}

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function escapeHtmlAttribute(value) {
    return escapeHtml(value).replace(/\n/g, ' ');
}

// ── Timeline Events ───────────────────────────────────────────────────
function addEvent(event) {
    state.events.unshift(event);

    // Keep only last 100 events
    if (state.events.length > 100) {
        state.events = state.events.slice(0, 100);
    }

    if (state.timelinePaused) {
        state.timelineBufferedCount += 1;
        updateTimelineOps();
        return;
    }

    renderTimeline();
}

function renderTimeline() {
    const container = document.getElementById('timeline-container');
    if (!container) return;

    // Filter events based on active filters
    const filteredEvents = getFilteredTimelineEvents(getTimelineSourceEvents());

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

    updateTimelineOps(filteredEvents.length);
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

    initializeTimelineOperations();
}

function initializeTimelineOperations() {
    const pauseBtn = document.getElementById('timeline-pause-btn');
    const clearBtn = document.getElementById('timeline-clear-btn');
    const jumpBtn = document.getElementById('timeline-jump-btn');
    const timelineContainer = document.getElementById('timeline-container');

    if (pauseBtn) {
        pauseBtn.addEventListener('click', () => {
            state.timelinePaused = !state.timelinePaused;

            if (!state.timelinePaused) {
                state.timelineBufferedCount = 0;
                state.timelineFrozenEvents = null;
                renderTimeline();
                showToast('Timeline resumed', 'success');
            } else {
                state.timelineFrozenEvents = [...state.events];
                renderTimeline();
                showToast('Timeline paused (events continue buffering)', 'warning');
            }
        });
    }

    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            state.events = [];
            state.timelineBufferedCount = 0;
            state.timelineFrozenEvents = state.timelinePaused ? [] : null;
            renderTimeline();
            showToast('Timeline cleared', 'success');
        });
    }

    if (jumpBtn) {
        jumpBtn.addEventListener('click', () => {
            jumpTimelineToLatest();
        });
    }

    if (timelineContainer) {
        timelineContainer.addEventListener('scroll', () => {
            updateTimelineJumpButton();
        }, { passive: true });
    }

    updateTimelineOps();
}

function getTimelineSourceEvents() {
    if (state.timelinePaused && Array.isArray(state.timelineFrozenEvents)) {
        return state.timelineFrozenEvents;
    }
    return state.events;
}

function getFilteredTimelineEvents(events = state.events) {
    return events.filter((event) => {
        const eventType = event.event.split('.').pop();
        return state.filters[eventType];
    });
}

function updateTimelineOps(filteredCount = null) {
    const countEl = document.getElementById('timeline-event-count');
    const streamStateEl = document.getElementById('timeline-stream-state');
    const pauseBtn = document.getElementById('timeline-pause-btn');

    const visibleCount = Number.isFinite(filteredCount)
        ? filteredCount
        : getFilteredTimelineEvents(getTimelineSourceEvents()).length;
    const totalCount = state.events.length;

    if (countEl) {
        const baseLabel = `${visibleCount} visible · ${totalCount} total`;
        countEl.textContent = state.timelinePaused && state.timelineBufferedCount > 0
            ? `${baseLabel} · +${state.timelineBufferedCount} buffered`
            : baseLabel;
    }

    if (streamStateEl) {
        streamStateEl.classList.toggle('paused', state.timelinePaused);
        streamStateEl.classList.toggle('live', !state.timelinePaused);
        streamStateEl.textContent = state.timelinePaused ? 'Paused' : 'Live';
    }

    if (pauseBtn) {
        pauseBtn.textContent = state.timelinePaused ? 'Resume' : 'Pause';
        pauseBtn.setAttribute('aria-pressed', state.timelinePaused ? 'true' : 'false');
    }

    updateTimelineJumpButton();
}

function jumpTimelineToLatest() {
    const container = document.getElementById('timeline-container');
    if (!container) return;

    const newestEvent = container.firstElementChild;
    if (newestEvent && typeof newestEvent.scrollIntoView === 'function') {
        newestEvent.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    // With column-reverse, latest event is at visual bottom and scrollTop=0.
    container.scrollTop = 0;

    window.setTimeout(() => {
        updateTimelineJumpButton();
    }, 80);
}

function updateTimelineJumpButton() {
    const jumpBtn = document.getElementById('timeline-jump-btn');
    if (!jumpBtn) return;

    const shouldShow = state.timelinePaused || isTimelineAwayFromLatest();
    jumpBtn.classList.toggle('hidden', !shouldShow);
}

function isTimelineAwayFromLatest() {
    const container = document.getElementById('timeline-container');
    if (!container) return false;

    const newestEvent = container.firstElementChild;
    if (!(newestEvent instanceof HTMLElement)) return false;

    const containerRect = container.getBoundingClientRect();
    const newestRect = newestEvent.getBoundingClientRect();
    const margin = 8;

    return newestRect.top < containerRect.top - margin || newestRect.bottom > containerRect.bottom + margin;
}

// ── Performance Charts ────────────────────────────────────────────────
function initializeCharts() {
    if (typeof Chart === 'undefined') {
        showToast('Chart library unavailable; performance charts disabled', 'warning');
        return;
    }

    const throughputCtx = document.getElementById('throughput-chart');
    const latencyCtx = document.getElementById('latency-chart');
    const loadCtx = document.getElementById('load-chart');
    const errorCtx = document.getElementById('error-gauge');

    if (!throughputCtx || !latencyCtx || !loadCtx || !errorCtx) {
        return;
    }

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
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                const ds = ctx.dataset;
                                const idx = ctx.dataIndex;
                                const hasSample = Array.isArray(ds.__hasSamples)
                                    ? ds.__hasSamples[idx]
                                    : true;
                                const rawLatency = Array.isArray(ds.__rawValues)
                                    ? ds.__rawValues[idx]
                                    : ctx.parsed.y;

                                if (!hasSample) {
                                    return 'No latency samples yet';
                                }
                                return `Avg latency: ${Math.round(rawLatency)} ms`;
                            },
                        },
                    },
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
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => {
                                const ds = ctx.dataset;
                                const idx = ctx.dataIndex;
                                const rawCount = Array.isArray(ds.__rawValues)
                                    ? ds.__rawValues[idx]
                                    : ctx.parsed.x;

                                if (!rawCount) {
                                    return 'No completed tasks yet';
                                }
                                return `Tasks completed: ${rawCount}`;
                            },
                        },
                    },
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

function initializePerformanceCharts() {
    const panel = document.querySelector('.performance-panel');
    if (!panel) return;

    if (!state.charts && !panel.classList.contains('collapsed')) {
        initializeCharts();
        updatePerformanceCharts();
    }
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
    const latencyRaw = state.agents.map(a => Math.round(a.metrics?.avg_latency_ms || 0));
    const latencyHasSamples = state.agents.map(a => {
        const completed = Number(a.metrics?.tasks_completed || 0);
        const errored = Number(a.metrics?.tasks_errored || 0);
        return completed + errored > 0;
    });
    latencyChart.data.datasets[0].__rawValues = latencyRaw;
    latencyChart.data.datasets[0].__hasSamples = latencyHasSamples;
    latencyChart.data.datasets[0].data = latencyRaw.map((v, idx) => (
        latencyHasSamples[idx] ? v : 1
    ));
    latencyChart.data.datasets[0].backgroundColor = latencyHasSamples.map((hasSample) => (
        hasSample ? COLORS.status.degraded + '80' : COLORS.status.unknown + '55'
    ));
    latencyChart.update('none');

    // Load balance: tasks per agent
    const loadChart = state.charts.load;
    loadChart.data.labels = state.agents.map(a => a.name);
    const loadRaw = state.agents.map(a => Number(a.metrics?.tasks_completed || 0));
    loadChart.data.datasets[0].__rawValues = loadRaw;
    loadChart.data.datasets[0].data = loadRaw.map((v) => (v > 0 ? v : 0.1));
    loadChart.data.datasets[0].backgroundColor = loadRaw.map((v) => (
        v > 0 ? COLORS.status.healthy + '80' : COLORS.status.unknown + '55'
    ));
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

    if (!toggleBtn || !panel) return;

    toggleBtn.addEventListener('click', () => {
        panel.classList.toggle('collapsed');
        toggleBtn.textContent = panel.classList.contains('collapsed') ? '▼' : '▲';

        // Initialize charts on first open
        if (!state.charts && !panel.classList.contains('collapsed')) {
            setTimeout(() => {
                initializeCharts();
                updatePerformanceCharts();
            }, 100);
        } else if (state.charts && !panel.classList.contains('collapsed')) {
            Object.values(state.charts).forEach((chart) => chart.resize());
            updatePerformanceCharts();
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

// ── Clinical Trace Panel ──────────────────────────────────────────────

function initializeTracePanel() {
    const searchInput = document.getElementById('trace-search');
    if (searchInput) {
        searchInput.addEventListener('input', () => renderTraceRunList());
    }
    const exportBtn = document.getElementById('trace-export-btn');
    if (exportBtn) {
        exportBtn.addEventListener('click', () => {
            if (state.selectedTraceId) exportTraceRun(state.selectedTraceId);
        });
    }
}

function humanizeScenarioName(name) {
    if (!name) return 'Unknown Scenario';
    return name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function urgencyColor(urgency) {
    switch ((urgency || '').toLowerCase()) {
        case 'critical': return '#ef4444';
        case 'high':     return '#f59e0b';
        case 'medium':   return '#3b82f6';
        case 'low':      return '#10b981';
        default:         return '#6b7280';
    }
}

function urgencyLabel(urgency) {
    switch ((urgency || '').toLowerCase()) {
        case 'critical': return 'CRITICAL';
        case 'high':     return 'URGENT';
        case 'medium':   return 'ROUTINE';
        case 'low':      return 'LOW PRIORITY';
        default:         return '';
    }
}

function clinicalStatus(status) {
    if (status === 'final' || status === 'completed') return 'Completed';
    if (status === 'error' || status === 'failed') return 'Failed';
    if (status === 'working' || status === 'accepted') return 'In Progress';
    return status || 'Unknown';
}

function humanizeAgentName(agent) {
    if (!agent) return 'Unknown';
    return agent.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

async function loadTraceRuns() {
    try {
        const response = await fetch('/api/traces');
        if (!response.ok) return;
        const payload = await response.json();
        state.traceRuns = Array.isArray(payload) ? payload.slice(0, TRACE_RUN_MAX) : [];
        renderTraceRunList();
        const badge = document.getElementById('trace-count-badge');
        if (badge) badge.textContent = `${state.traceRuns.length} runs`;
        // Auto-select the most recent run
        if (state.traceRuns.length > 0 && !state.selectedTraceId) {
            selectTraceRun(state.traceRuns[0].trace_id);
        }
    } catch (err) {
        console.error('Failed to load trace runs:', err);
    }
}

function handleTraceRunEvent(payload) {
    // Prepend new run to the list (most recent first)
    state.traceRuns = [payload, ...state.traceRuns.filter(r => r.trace_id !== payload.trace_id)];
    if (state.traceRuns.length > TRACE_RUN_MAX) {
        state.traceRuns = state.traceRuns.slice(0, TRACE_RUN_MAX);
    }
    renderTraceRunList();
    const badge = document.getElementById('trace-count-badge');
    if (badge) badge.textContent = `${state.traceRuns.length} runs`;
}

async function selectTraceRun(traceId) {
    state.selectedTraceId = traceId;
    // Highlight active card
    document.querySelectorAll('.trace-run-card').forEach(card => {
        card.classList.toggle('active', card.dataset.traceId === traceId);
    });
    try {
        const response = await fetch(`/api/traces/${traceId}`);
        if (!response.ok) {
            console.error('Trace not found:', traceId);
            return;
        }
        const run = await response.json();
        renderTraceStepTimeline(run);
        renderTracePatientContext(run);
        // Enable export button
        const exportBtn = document.getElementById('trace-export-btn');
        if (exportBtn) exportBtn.disabled = false;
    } catch (err) {
        console.error('Failed to load trace detail:', err);
    }
}

function renderTraceRunList() {
    const container = document.getElementById('trace-run-items');
    if (!container) return;

    const searchInput = document.getElementById('trace-search');
    const filter = searchInput ? searchInput.value.toLowerCase() : '';

    const filtered = state.traceRuns.filter(run => {
        if (!filter) return true;
        const profile = run.patient_profile || {};
        const text = [
            run.scenario_name, run.visit_id, run.status,
            profile.chief_complaint, profile.gender,
            profile.age != null ? String(profile.age) : '',
            profile.urgency,
        ].join(' ').toLowerCase();
        return text.includes(filter);
    });

    if (filtered.length === 0) {
        container.innerHTML = '<div class="trace-empty">No matching patient journeys.</div>';
        return;
    }

    container.innerHTML = filtered.map(run => {
        const profile = run.patient_profile || {};
        const statusCss = (run.status === 'final' || run.status === 'completed') ? 'status-final'
            : (run.status === 'error' || run.status === 'failed') ? 'status-error' : 'status-working';
        const stepCount = run.step_count || (run.steps ? run.steps.length : 0);
        const ts = run.started_at ? new Date(run.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
        const dur = run.total_duration_ms != null ? `${(run.total_duration_ms / 1000).toFixed(1)}s` : '';
        const isActive = state.selectedTraceId === run.trace_id;
        const urgency = profile.urgency || '';
        const uColor = urgencyColor(urgency);
        const uLabel = urgencyLabel(urgency);
        const complaint = profile.chief_complaint || '';
        const patientSummary = [profile.age ? `${profile.age}y` : '', profile.gender || ''].filter(Boolean).join(' ');

        return `<div class="trace-run-card ${statusCss} ${isActive ? 'active' : ''}"
                     data-trace-id="${escapeHtml(run.trace_id)}"
                     onclick="selectTraceRun('${escapeHtml(run.trace_id)}')">
            <div class="run-top-row">
                <span class="run-name">${escapeHtml(humanizeScenarioName(run.scenario_name))}</span>
                ${uLabel ? `<span class="urgency-pill" style="background:${uColor}">${uLabel}</span>` : ''}
            </div>
            ${complaint ? `<div class="run-complaint">${escapeHtml(complaint)}</div>` : ''}
            <div class="run-meta">
                <span>${escapeHtml(patientSummary)}</span>
                <span>${stepCount} steps &middot; ${dur}</span>
                <span class="run-status ${statusCss}">${clinicalStatus(run.status)}</span>
            </div>
            <div class="run-time">${escapeHtml(ts)}</div>
        </div>`;
    }).join('');
}

function renderTraceStepTimeline(run) {
    const container = document.getElementById('trace-step-container');
    if (!container) return;

    const steps = run.steps || [];
    if (steps.length === 0) {
        container.innerHTML = '<div class="trace-empty">No steps recorded for this trace.</div>';
        return;
    }

    const profile = run.patient_profile || {};
    const complaint = profile.chief_complaint || '';
    const urgency = profile.urgency || '';
    const uColor = urgencyColor(urgency);
    const uLabel = urgencyLabel(urgency);
    const patientLine = [profile.age ? `${profile.age}y` : '', profile.gender || ''].filter(Boolean).join(' ');

    container.innerHTML = `
        <div class="timeline-header">
            <h4>${escapeHtml(humanizeScenarioName(run.scenario_name))}</h4>
            <div class="timeline-header-meta">
                ${complaint ? `<span class="timeline-complaint">${escapeHtml(complaint)}</span>` : ''}
                <span>${escapeHtml(patientLine)} &middot; ${steps.length} steps &middot; ${run.total_duration_ms != null ? (run.total_duration_ms / 1000).toFixed(1) + 's' : ''}</span>
                ${uLabel ? `<span class="urgency-pill" style="background:${uColor}">${uLabel}</span>` : ''}
            </div>
        </div>
        ${renderDelegationChain(run)}
        <div class="timeline-steps">
        ${steps.map((step, idx) => {
            const stepOk = step.status === 'final' || step.status === 'success' || step.status === 'completed';
            const stepErr = step.status === 'error' || step.status === 'failed';
            const stepCss = stepErr ? 'step-error' : '';
            const dur = step.duration_ms != null ? step.duration_ms : 0;
            const durLabel = dur >= 1000 ? `${(dur / 1000).toFixed(1)}s` : `${dur.toFixed(0)}ms`;
            const durClass = dur > 5000 ? 'duration-slow' : dur > 2000 ? 'duration-medium' : 'duration-fast';
            const ts = step.timestamp_start
                ? new Date(step.timestamp_start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
                : '';
            const retryInfo = step.retry_count > 0 ? `<span class="retry-badge">${step.retry_count} retries</span>` : '';
            const errorInfo = step.error_message
                ? `<div class="step-error-msg"><strong>Error:</strong> ${escapeHtml(step.error_message)}</div>` : '';
            const maskedFields = (step.redaction_meta && step.redaction_meta.masked_fields) || [];
            const redactBadge = maskedFields.length > 0
                ? `<span class="redaction-badge">${maskedFields.length} fields redacted</span>` : '';
            const statusIcon = stepOk ? '&#10003;' : stepErr ? '&#10007;' : '&#9679;';
            const statusColor = stepOk ? 'var(--status-healthy)' : stepErr ? 'var(--status-unhealthy)' : 'var(--status-degraded)';

            // Detect if this is an avatar step and render conversation-style
            const isAvatar = step.agent === 'clinician_avatar';
            const avatarBadge = isAvatar ? '<span class="avatar-badge">🩺 Avatar</span>' : '';

            // Extract the clinical inputs/outputs
            const reqParams = step.request_redacted?.params?.task || step.request_redacted?.params || {};
            const resResult = step.response_redacted?.result?.status
                ? step.response_redacted.result
                : step.response_redacted?.result?.artifacts?.[0]?.parts?.[0]?.data || step.response_redacted?.result || {};

            // Avatar conversation rendering
            const avatarConv = isAvatar ? renderAvatarConversation(step, reqParams, resResult) : '';

            return `<div class="trace-step-card ${stepCss} ${isAvatar ? 'avatar-step' : ''}" data-step-index="${idx}">
                <div class="step-header" onclick="toggleTraceStep(this)">
                    <div class="step-number" style="color:${statusColor}">
                        <span class="step-icon">${statusIcon}</span> ${idx + 1}
                    </div>
                    <div class="step-info">
                        <span class="step-agent">${escapeHtml(humanizeAgentName(step.agent))}</span>
                        <span class="step-method">${escapeHtml(step.method || '')}</span>
                        ${avatarBadge}
                    </div>
                    <div class="step-timing">
                        <span class="duration ${durClass}">${durLabel}</span>
                        <span>${escapeHtml(ts)}</span>
                        ${retryInfo}
                        ${redactBadge}
                    </div>
                    <span class="step-toggle">&#9654;</span>
                </div>
                <div class="step-body" style="display:none;">
                    <div class="step-correlation">
                        <span class="correlation-label">Correlation:</span>
                        <span class="correlation-id">${escapeHtml(step.correlation_id || '')}</span>
                        <button class="trace-copy-btn" onclick="event.stopPropagation();copyToClipboard('${escapeHtml(step.correlation_id || '')}')">Copy</button>
                    </div>
                    ${errorInfo}
                    ${avatarConv}
                    <div class="step-payloads expanded">
                        <h4>Clinical Input</h4>
                        <pre class="trace-json-block">${escapeHtml(JSON.stringify(reqParams, null, 2) || '{}')}</pre>
                        <h4>Clinical Output</h4>
                        <pre class="trace-json-block">${escapeHtml(JSON.stringify(resResult, null, 2) || '{}')}</pre>
                    </div>
                </div>
            </div>`;
        }).join('')}
        </div>
    `;
}

function renderAvatarConversation(step, reqParams, resResult) {
    const method = step.method || '';
    if (method.includes('start_session')) {
        const persona = reqParams.persona || 'clinician';
        const complaint = reqParams.patient_case?.chief_complaint || '';
        const reply = resResult.greeting || resResult.message || resResult.response || '';
        return `<div class="avatar-conversation">
            <div class="avatar-session-start">
                <span class="avatar-persona">🩺 ${escapeHtml(persona.replace(/_/g, ' '))}</span>
                ${complaint ? `<span class="avatar-complaint">${escapeHtml(complaint)}</span>` : ''}
            </div>
            ${reply ? `<div class="avatar-bubble clinician">${escapeHtml(reply)}</div>` : ''}
        </div>`;
    }
    if (method.includes('patient_message')) {
        const patientMsg = reqParams.message || '';
        const clinicianReply = resResult.response || resResult.message
            || resResult.follow_up_question || resResult.reply || '';
        return `<div class="avatar-conversation">
            ${patientMsg ? `<div class="avatar-bubble patient">${escapeHtml(patientMsg)}</div>` : ''}
            ${clinicianReply ? `<div class="avatar-bubble clinician">${escapeHtml(clinicianReply)}</div>` : ''}
        </div>`;
    }
    return '';
}

function renderDelegationChain(run) {
    const chain = run.delegation_chain || [];
    if (chain.length === 0) return '';

    const skipped = chain.filter(e => e.skipped).length;
    const blocked = chain.filter(e => e.state === 'blocked_escalated' || (!e.allowed && !e.skipped)).length;
    const retryPending = chain.filter(e => e.state === 'retry_pending').length;
    const rerouted = chain.filter(e => e.state === 'rerouted').length;
    const total = chain.length;

    return `<div class="delegation-chain">
        <div class="delegation-header" onclick="toggleDelegationChain(this)">
            <span>🔗 Delegation Chain (${total} handoffs${skipped ? `, ${skipped} skipped` : ''}${blocked ? `, ${blocked} blocked` : ''}${retryPending ? `, ${retryPending} retry` : ''}${rerouted ? `, ${rerouted} rerouted` : ''})</span>
            <span class="delegation-toggle">&#9654;</span>
        </div>
        <div class="delegation-body" style="display:none;">
            ${chain.map(e => {
                const cls = e.skipped ? 'delegation-skipped'
                    : e.state === 'retry_pending' ? 'delegation-retry'
                    : e.state === 'rerouted' ? 'delegation-rerouted'
                    : !e.allowed ? 'delegation-blocked'
                    : 'delegation-ok';
                return `<div class="delegation-event ${cls}">
                    <span class="deleg-from">${escapeHtml(e.from || '')}</span>
                    <span class="deleg-arrow">→</span>
                    <span class="deleg-to">${escapeHtml(e.to || '')}</span>
                    ${e.state ? `<span class="deleg-state">${escapeHtml(e.state)}</span>` : ''}
                    ${e.rationale ? `<span class="deleg-rationale">${escapeHtml(e.rationale)}</span>` : ''}
                    ${e.reason ? `<span class="deleg-reason">${escapeHtml(e.reason)}</span>` : ''}
                    ${e.escalation_target ? `<span class="deleg-escalation">Escalate: ${escapeHtml(e.escalation_target)}</span>` : ''}
                    ${e.duration_ms ? `<span class="deleg-dur">${e.duration_ms.toFixed(0)}ms</span>` : ''}
                </div>`;
            }).join('')}
        </div>
    </div>`;
}

function toggleDelegationChain(headerEl) {
    const body = headerEl.nextElementSibling;
    const toggle = headerEl.querySelector('.delegation-toggle');
    if (body.style.display === 'none') {
        body.style.display = 'block';
        if (toggle) toggle.innerHTML = '&#9660;';
    } else {
        body.style.display = 'none';
        if (toggle) toggle.innerHTML = '&#9654;';
    }
}

function toggleTraceStep(headerEl) {
    const body = headerEl.nextElementSibling;
    const toggle = headerEl.querySelector('.step-toggle');
    if (body.style.display === 'none') {
        body.style.display = 'block';
        if (toggle) toggle.innerHTML = '&#9660;';
    } else {
        body.style.display = 'none';
        if (toggle) toggle.innerHTML = '&#9654;';
    }
}

function renderTracePatientContext(run) {
    const container = document.getElementById('trace-patient-context');
    if (!container) return;

    const profile = run.patient_profile || {};
    const urgency = profile.urgency || '';
    const uColor = urgencyColor(urgency);

    const fields = [
        { label: 'Chief Complaint', value: profile.chief_complaint, highlight: true },
        { label: 'Urgency', value: urgencyLabel(urgency), color: uColor },
        { label: 'Age', value: profile.age ? `${profile.age} years` : '' },
        { label: 'Gender', value: profile.gender ? profile.gender.charAt(0).toUpperCase() + profile.gender.slice(1) : '' },
        { label: 'Symptoms', value: Array.isArray(profile.symptoms) ? profile.symptoms.join(', ') : profile.symptoms },
        { label: 'Acuity Level', value: profile.acuity_level || profile.acuity },
        { label: 'Journey Status', value: clinicalStatus(run.status) },
        { label: 'Started', value: run.started_at ? new Date(run.started_at).toLocaleString() : '' },
        { label: 'Completed', value: run.completed_at ? new Date(run.completed_at).toLocaleString() : '' },
        { label: 'Total Duration', value: run.total_duration_ms != null ? `${(run.total_duration_ms / 1000).toFixed(2)}s` : '' },
        { label: 'Steps', value: run.steps ? `${run.steps.length} clinical interactions` : '' },
    ];

    // List the agents involved
    const agentsUsed = run.steps ? [...new Set(run.steps.map(s => humanizeAgentName(s.agent)))].join(', ') : '';
    if (agentsUsed) fields.push({ label: 'Agents Involved', value: agentsUsed });

    container.innerHTML = `
        <div class="trace-patient-card">
            <h4>Patient Context</h4>
            ${fields
                .filter(f => f.value != null && f.value !== '')
                .map(f => `<div class="patient-field">
                    <strong>${escapeHtml(f.label)}</strong>
                    <span ${f.color ? `style="color:${f.color};font-weight:600"` : ''}
                          ${f.highlight ? 'style="color:var(--text-primary);font-weight:600"' : ''}>
                        ${escapeHtml(String(f.value))}
                    </span>
                </div>`)
                .join('')}
        </div>
    `;
}

async function exportTraceRun(traceId) {
    try {
        const response = await fetch(`/api/traces/${traceId}/export`);
        if (!response.ok) { console.error('Export failed'); return; }
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `trace_${traceId}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    } catch (err) {
        console.error('Failed to export trace:', err);
    }
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('Copied to clipboard', 'success');
    }).catch(() => {
        // Fallback
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        showToast('Copied to clipboard', 'success');
    });
}

// ── Periodic Updates ──────────────────────────────────────────────────
// Poll for agent updates every 2 seconds (in addition to WebSocket events)
setInterval(async () => {
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
