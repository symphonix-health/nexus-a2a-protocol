import os
import sys
import time
import asyncio
import importlib


def import_from(src_dir: str, module: str):
    sys.path.insert(0, os.path.abspath(src_dir))
    try:
        return importlib.import_module(module)
    finally:
        sys.path.pop(0)


def test_run_bounded_order_and_limit():
    src = os.environ.get("SRC_PATH", "src")
    m = import_from(src, "async_pool")

    async def scenario():
        max_concurrent = 0
        current = 0
        lock = asyncio.Lock()

        async def make_job(i: int):
            async def job():
                nonlocal current, max_concurrent
                async with lock:
                    current += 1
                    max_concurrent = max(max_concurrent, current)
                try:
                    await asyncio.sleep(0.02)
                    return i * i
                finally:
                    async with lock:
                        current -= 1

            return job

        jobs = [await make_job(i) for i in range(10)]
        t0 = time.perf_counter()
        results = await asyncio.to_thread(m.run_bounded, jobs, 3)
        dt = time.perf_counter() - t0

        assert results == [i * i for i in range(10)]  # preserves order
        assert max_concurrent <= 3
        assert dt >= 0.06  # at least ~3 waves of 0.02s with concurrency=3

    asyncio.run(scenario())
