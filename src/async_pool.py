"""Bounded-concurrency async runner that preserves input order."""

from typing import Awaitable, Callable, TypeVar, Sequence, List
import asyncio

T = TypeVar("T")


def run_bounded(jobs: Sequence[Callable[[], Awaitable[T]]], concurrency: int) -> List[T]:
    if concurrency <= 0:
        raise ValueError("concurrency must be positive")

    async def _run() -> List[T]:
        sem = asyncio.Semaphore(concurrency)

        async def wrap(job: Callable[[], Awaitable[T]]) -> T:
            async with sem:
                return await job()

        tasks = [wrap(job) for job in jobs]
        return await asyncio.gather(*tasks)

    # Create and run a new event loop for the bounded run
    return asyncio.run(_run())
