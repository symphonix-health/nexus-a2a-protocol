"""Topological sort over adjacency list; raise ValueError on cycle."""

from typing import Dict, List, Set
from collections import deque


def topo_sort(edges: Dict[str, List[str]]) -> List[str]:
    # Collect all nodes appearing in keys or values
    nodes: Set[str] = set(edges.keys())
    for vs in edges.values():
        nodes.update(vs)

    indeg: Dict[str, int] = {n: 0 for n in nodes}
    adj: Dict[str, List[str]] = {n: [] for n in nodes}
    for u, vs in edges.items():
        for v in vs:
            adj[u].append(v)
            indeg[v] += 1

    q = deque([n for n in nodes if indeg[n] == 0])
    order: List[str] = []
    while q:
        u = q.popleft()
        order.append(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                q.append(v)

    if len(order) != len(nodes):
        raise ValueError("graph contains a cycle")
    return order
