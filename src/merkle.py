"""Merkle tree root (SHA-256) over chunks with last-node duplication."""

from typing import List
import hashlib


def merkle_root(chunks: List[bytes]) -> str:
    if not chunks:
        return hashlib.sha256(b"").hexdigest()

    nodes = [hashlib.sha256(c).digest() for c in chunks]
    while len(nodes) > 1:
        if len(nodes) % 2 == 1:
            nodes.append(nodes[-1])
        nodes = [hashlib.sha256(nodes[i] + nodes[i + 1]).digest() for i in range(0, len(nodes), 2)]
    return nodes[0].hex()
