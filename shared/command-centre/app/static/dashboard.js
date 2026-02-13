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
};

const FLOW_STALE_MS = 30000;
const FLOW_EXPIRE_MS = 10 * 60 * 1000;
const FLOW_SYNTHETIC_DELAY_MS = 8000;
const TOPOLOGY_HINT_DISMISSED_KEY = 'command-centre.topology-hint-dismissed';

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
    loadScenarioCatalog();
    initializeScenarioFlowBoard();
    initializeJourneyPopover();
    initializeFilters();
    initializeToggleButtons();
});

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
            ingestScenarioEvent(message.payload, false);
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
    const dynamicHeight = Math.max(380, Math.min(620, 340 + Math.max(0, state.agents.length - 6) * 26));
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

    // Draw edges (dependencies)
    state.agents.forEach((agent) => {
        const sourcePos = positions.find(p => p.agent.name === agent.name);
        agent.dependencies.forEach((depName) => {
            const targetPos = positions.find(p => p.agent.name === depName);
            if (sourcePos && targetPos) {
                drawEdge(viewport, sourcePos.x, sourcePos.y, targetPos.x, targetPos.y);
            }
        });
    });

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

function drawEdge(svg, x1, y1, x2, y2) {
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', x1);
    line.setAttribute('y1', y1);
    line.setAttribute('x2', x2);
    line.setAttribute('y2', y2);
    line.classList.add('edge-line');
    svg.appendChild(line);
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
    // Update agent metrics based on incoming events
    const agentName = event.agent;
    const agent = state.agents.find(a => a.name === agentName);

    if (agent && event.duration_ms) {
        // Update would happen here in real implementation
        // For now, metrics come from polling
    }
}

// ── Scenario Flow Board ───────────────────────────────────────────────
function initializeScenarioFlowBoard() {
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

    if (phase === 'final' || phase === 'error') {
        current.status = 'completed';
        current.completedAt = now;
    } else {
        current.status = 'active';
    }

    state.scenarios[scenarioId] = current;
    renderScenarioFlowBoard();
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

function getFlowLane(scenario, now = Date.now()) {
    if (scenario.status === 'completed') {
        return 'completed';
    }

    const ageMs = now - scenario.updatedAt;
    if (ageMs > FLOW_STALE_MS || scenario.phase === 'error') {
        return 'at-risk';
    }

    return 'now';
}

function renderScenarioFlowBoard() {
    const laneNow = document.getElementById('flow-lane-now');
    const laneAtRisk = document.getElementById('flow-lane-at-risk');
    const laneCompleted = document.getElementById('flow-lane-completed');

    if (!laneNow || !laneAtRisk || !laneCompleted) return;

    const scenarios = Object.values(state.scenarios)
        .sort((a, b) => b.updatedAt - a.updatedAt)
        .slice(0, 18);

    const lanes = {
        now: [],
        'at-risk': [],
        completed: [],
    };

    scenarios.forEach((scenario) => {
        lanes[getFlowLane(scenario)].push(scenario);
    });

    updateFlowSummaryCounts(lanes);
    updateFlowSourceBadge();

    renderFlowLane(laneNow, lanes.now, 'No active journeys right now');
    renderFlowLane(laneAtRisk, lanes['at-risk'], 'No at-risk journeys');
    renderFlowLane(laneCompleted, lanes.completed, 'No completed journeys yet');
}

function renderFlowLane(container, scenarios, emptyMessage) {
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
        card.className = `flow-card ${scenario.isSynthetic ? 'synthetic' : ''}`;

        const ageSeconds = Math.max(0, Math.floor((Date.now() - scenario.updatedAt) / 1000));
        const durationSeconds = Math.max(0, Math.floor((scenario.updatedAt - scenario.firstSeenAt) / 1000));

        const journeyLabel = escapeHtml(scenario.journeyLabel || 'Unknown Journey');
        const journeyDescription = escapeHtmlAttribute(
            scenario.journeyDescription || 'Scenario description unavailable'
        );
        const scenarioId = escapeHtml(scenario.id || 'unknown-scenario');
        const agentName = escapeHtml(scenario.agent || 'unknown-agent');
        const stepName = escapeHtml(scenario.step || 'unknown-step');
        const phase = escapeHtml(scenario.phase || 'working');

        card.innerHTML = `
            <div class="journey-label" data-description="${journeyDescription}" tabindex="0" aria-describedby="journey-popover">${journeyLabel}</div>
            <div class="scenario-id">${scenarioId}</div>
            <div class="meta">
                <span>${agentName}</span>
                <span>${ageSeconds}s ago</span>
            </div>
            <span class="phase-badge phase-${phase}">${phase}</span>
            <div class="meta">
                <span>Step: ${stepName}</span>
                <span>Elapsed: ${durationSeconds}s</span>
            </div>
        `;

        container.appendChild(card);
    });
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

function updateFlowSummaryCounts(lanes) {
    document.getElementById('flow-now-count').textContent = lanes.now.length;
    document.getElementById('flow-at-risk-count').textContent = lanes['at-risk'].length;
    document.getElementById('flow-completed-count').textContent = lanes.completed.length;
}

function updateFlowSourceBadge() {
    const badge = document.getElementById('flow-board-source');
    if (!badge) return;

    badge.classList.remove('idle', 'live', 'synthetic');
    badge.classList.add(state.flowSource);

    if (state.flowSource === 'live') {
        badge.textContent = 'Live journey events';
    } else if (state.flowSource === 'synthetic') {
        badge.textContent = 'Demo mode (synthetic)';
    } else {
        badge.textContent = 'Waiting for events';
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
