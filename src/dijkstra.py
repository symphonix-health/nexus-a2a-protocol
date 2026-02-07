"""Single-source shortest paths (non-negative weights) using Dijkstra."""

from typing import Dict, List, Tuple
import heapq


def shortest_paths(graph: Dict[str, List[Tuple[str, int]]], source: str) -> Dict[str, int]:
    dist: Dict[str, int] = {source: 0}
    pq: List[Tuple[int, str]] = [(0, source)]

    while pq:
        d, u = heapq.heappop(pq)
        if d != dist.get(u, float("inf")):
            continue
        for v, w in graph.get(u, []):
            if w < 0:
                raise ValueError("negative edge weight not allowed")
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                heapq.heappush(pq, (nd, v))
    return dist
