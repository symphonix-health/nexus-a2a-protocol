"""Byte chunking utilities: fixed-size splits and reassembly."""

from typing import List


def chunk_bytes(data: bytes, size: int) -> List[bytes]:
    if size <= 0:
        raise ValueError("size must be > 0")
    return [data[i : i + size] for i in range(0, len(data), size)]


def unchunk_bytes(chunks: List[bytes]) -> bytes:
    return b"".join(chunks)
