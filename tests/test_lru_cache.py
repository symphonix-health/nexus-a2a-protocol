import os
import sys
import importlib


def import_from(src_dir: str, module: str):
    sys.path.insert(0, os.path.abspath(src_dir))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.pop(0)


def test_lru_cache_eviction():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "lru_cache")

    cache = m.LRUCache(2)
    cache.put(1, 1)  # {1=1}
    cache.put(2, 2)  # {1=1,2=2}
    assert cache.get(1) == 1  # access 1 -> {2=2,1=1}
    cache.put(3, 3)  # evict 2 -> {1=1,3=3}
    assert cache.get(2) == -1
    cache.put(4, 4)  # evict 1 -> {3=3,4=4}
    assert cache.get(1) == -1
    assert cache.get(3) == 3
    assert cache.get(4) == 4
