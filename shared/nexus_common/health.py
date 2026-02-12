"""Health check endpoints with metrics tracking for NEXUS-A2A agents.

Provides reusable health monitoring with rolling metrics windows for:
- Task counters (accepted, completed, errored)
- Latency statistics (average, P95)
- Real-time status reporting
"""

from __future__ import annotations

import time
from collections import deque
import os
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
        # Thresholds (configurable via env; sensible defaults preserved)
        # Error-rate thresholds
        self._err_unhealthy = float(os.getenv("NEXUS_HEALTH_ERROR_UNHEALTHY", "0.10"))
        self._err_degraded = float(os.getenv("NEXUS_HEALTH_ERROR_DEGRADED", "0.05"))
        # Latency threshold (ms) for degraded state
        self._latency_degraded_ms = float(os.getenv("NEXUS_HEALTH_LATENCY_DEGRADED_MS", "5000"))
        # Require multiple samples before latency alone marks an agent degraded.
        self._latency_min_samples = int(os.getenv("NEXUS_HEALTH_LATENCY_MIN_SAMPLES", "3"))
    
    def get_health(self) -> dict:
        """Get current health status with metrics."""
        # Simple health determination based on error rate
        total = self.metrics.tasks_completed + self.metrics.tasks_errored
        error_rate = self.metrics.tasks_errored / total if total > 0 else 0.0
        
        # Apply latency degradation only after a minimum sample count to avoid
        # one-off cold starts permanently affecting perceived health.
        latency_degraded = (
            len(self.metrics._latencies) >= self._latency_min_samples
            and self.metrics.avg_latency_ms > self._latency_degraded_ms
        )

        # Status logic
        if error_rate > self._err_unhealthy:
            status = "unhealthy"
        elif error_rate > self._err_degraded or latency_degraded:
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
