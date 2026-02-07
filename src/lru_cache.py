"""LRU cache with O(1) get/put using hashmap + doubly linked list."""

from typing import Optional, Dict


class _Node:
    __slots__ = ("key", "value", "prev", "next")

    def __init__(self, key: int = 0, value: int = 0):
        self.key = key
        self.value = value
        self.prev: Optional["_Node"] = None
        self.next: Optional["_Node"] = None


class LRUCache:
    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self.map: Dict[int, _Node] = {}
        self.head = _Node()  # LRU sentinel (head.next is MRU direction)
        self.tail = _Node()  # MRU sentinel
        self.head.next = self.tail
        self.tail.prev = self.head

    def _remove(self, node: _Node) -> None:
        prev, nxt = node.prev, node.next
        if prev is not None:
            prev.next = nxt
        if nxt is not None:
            nxt.prev = prev
        node.prev = node.next = None

    def _append_mru(self, node: _Node) -> None:
        # Insert before tail (MRU position)
        last = self.tail.prev
        assert last is not None
        last.next = node
        node.prev = last
        node.next = self.tail
        self.tail.prev = node

    def get(self, key: int) -> int:
        node = self.map.get(key)
        if node is None:
            return -1
        self._remove(node)
        self._append_mru(node)
        return node.value

    def put(self, key: int, value: int) -> None:
        node = self.map.get(key)
        if node is not None:
            node.value = value
            self._remove(node)
            self._append_mru(node)
            return

        if len(self.map) >= self.capacity:
            # Evict LRU: node right after head
            lru = self.head.next
            assert lru is not None and lru is not self.tail
            self._remove(lru)
            del self.map[lru.key]

        new_node = _Node(key, value)
        self.map[key] = new_node
        self._append_mru(new_node)
