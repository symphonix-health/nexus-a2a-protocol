"""Health check endpoints with metrics tracking for NEXUS-A2A agents.

Provides reusable health monitoring with rolling metrics windows for:
- Task counters (accepted, completed, errored)
- Latency statistics (average, P95)
- Real-time status reporting
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Deque


@dataclass
class TaskMetrics:
    """Rolling metrics for agent task processing."""
    
    tasks_accepted: int = 0
    tasks_completed: int = 0
    tasks_errored: int = 0
    
    # Latency tracking (rolling window)
    _latencies: Deque[float] = field(default_factory=lambda: deque(maxlen=100))
    _last_task_latency: float = 0.0
    
    def record_accepted(self) -> None:
        """Record a task acceptance."""
        self.tasks_accepted += 1
    
    def record_completed(self, duration_ms: float) -> None:
        """Record a task completion with duration."""
        self.tasks_completed += 1
        self._latencies.append(duration_ms)
        self._last_task_latency = duration_ms
    
    def record_error(self, duration_ms: float = 0.0) -> None:
        """Record a task error."""
        self.tasks_errored += 1
        if duration_ms > 0:
            self._latencies.append(duration_ms)
            self._last_task_latency = duration_ms
    
    @property
    def avg_latency_ms(self) -> float:
        """Calculate average latency from recent tasks."""
        if not self._latencies:
            return 0.0
        return sum(self._latencies) / len(self._latencies)
    
    @property
    def p95_latency_ms(self) -> float:
        """Calculate P95 latency from recent tasks."""
        if not self._latencies:
            return 0.0
        sorted_latencies = sorted(self._latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[min(idx, len(sorted_latencies) - 1)]
    
    @property
    def last_task_ms(self) -> float:
        """Return most recent task latency."""
        return self._last_task_latency
    
    def to_dict(self) -> dict:
        """Convert metrics to dictionary for JSON serialization."""
        return {
            "tasks_accepted": self.tasks_accepted,
            "tasks_completed": self.tasks_completed,
            "tasks_errored": self.tasks_errored,
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "p95_latency_ms": round(self.p95_latency_ms, 2),
            "last_task_ms": round(self.last_task_ms, 2),
        }


@dataclass
class HealthStatus:
    """Health status response model."""
    
    status: str  # "healthy" | "degraded" | "unhealthy"
    name: str
    timestamp: str
    metrics: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON response."""
        return asdict(self)


class HealthMonitor:
    """Health monitoring singleton for an agent.
    
    Usage:
        monitor = HealthMonitor("triage-agent")
        
        # In task handler
        monitor.metrics.record_accepted()
        # ... process task ...
        monitor.metrics.record_completed(duration_ms=1250)
        
        # In FastAPI endpoint
        @app.get("/health")
        async def health():
            return monitor.get_health()
    """
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.metrics = TaskMetrics()
        self._start_time = time.time()
    
    def get_health(self) -> dict:
        """Get current health status with metrics."""
        # Simple health determination based on error rate
        total = self.metrics.tasks_completed + self.metrics.tasks_errored
        error_rate = self.metrics.tasks_errored / total if total > 0 else 0.0
        
        # Status logic
        if error_rate > 0.1:  # >10% errors
            status = "unhealthy"
        elif error_rate > 0.05 or self.metrics.avg_latency_ms > 5000:  # >5% errors or >5s latency
            status = "degraded"
        else:
            status = "healthy"
        
        return HealthStatus(
            status=status,
            name=self.agent_name,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metrics=self.metrics.to_dict(),
        ).to_dict()
    
    @property
    def uptime_seconds(self) -> float:
        """Return agent uptime in seconds."""
        return time.time() - self._start_time
