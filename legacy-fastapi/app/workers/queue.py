"""Job queue with two backends: in-process for local dev and tests, arq/Redis for deployments."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any, Protocol

logger = logging.getLogger(__name__)

JobFunc = Callable[..., Awaitable[Any]]


class JobQueue(Protocol):
    async def enqueue(self, name: str, *, defer_by: float = 0, **kwargs: Any) -> None: ...

    async def close(self) -> None: ...


class InlineQueue:
    def __init__(self, jobs: dict[str, JobFunc]):
        self._jobs = jobs
        self._tasks: set[asyncio.Task] = set()

    async def enqueue(self, name: str, *, defer_by: float = 0, **kwargs: Any) -> None:
        task = asyncio.create_task(self._run(name, defer_by, kwargs))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, name: str, defer_by: float, kwargs: dict[str, Any]) -> None:
        if defer_by:
            await asyncio.sleep(defer_by)
        try:
            await self._jobs[name]({}, **kwargs)
        except Exception:
            logger.exception("Job %s failed", name)

    async def drain(self) -> None:
        """Wait until every job, including jobs started by jobs, has finished."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def close(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*list(self._tasks), return_exceptions=True)


class ArqQueue:
    def __init__(self, redis: Any):
        self._redis = redis

    @classmethod
    async def connect(cls, redis_url: str) -> "ArqQueue":
        from arq import create_pool
        from arq.connections import RedisSettings

        return cls(await create_pool(RedisSettings.from_dsn(redis_url)))

    async def enqueue(self, name: str, *, defer_by: float = 0, **kwargs: Any) -> None:
        await self._redis.enqueue_job(name, _defer_by=timedelta(seconds=defer_by) if defer_by else None, **kwargs)

    async def close(self) -> None:
        await self._redis.aclose()


_queue: JobQueue | None = None


def get_queue() -> JobQueue:
    if _queue is None:
        raise RuntimeError("Job queue is not configured")
    return _queue


def set_queue(queue: JobQueue | None) -> None:
    global _queue
    _queue = queue
