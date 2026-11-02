"""arq worker entry point: `arq app.workers.arq_worker.WorkerSettings`."""

from typing import Any

from arq.connections import RedisSettings
from arq.cron import cron

from app.config import get_settings
from app.db import dispose_db, init_db
from app.http import close_http_client, init_http_client
from app.logging_config import configure_logging
from app.security import configure_encryption
from app.workers.jobs import JOBS, purge_expired_data, scan_rtw_expiring
from app.workers.queue import ArqQueue, set_queue


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging()
    configure_encryption(settings.data_encryption_key)
    init_db(settings.database_url)
    init_http_client(settings.internal_base_url)
    set_queue(ArqQueue(ctx["redis"]))


async def shutdown(ctx: dict[str, Any]) -> None:
    await close_http_client()
    await dispose_db()


class WorkerSettings:
    functions = list(JOBS.values())
    cron_jobs = [
        cron(scan_rtw_expiring, hour={6}, minute={0}),
        cron(purge_expired_data, hour={3}, minute={0}),
    ]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    on_startup = startup
    on_shutdown = shutdown
