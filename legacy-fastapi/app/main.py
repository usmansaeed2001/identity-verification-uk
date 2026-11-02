"""App factory. Run with: uvicorn app.main:create_app --factory"""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import verifications, webhooks
from app.config import Settings, get_settings, set_settings
from app.db import dispose_db, init_db
from app.errors import ServiceError
from app.http import close_http_client, init_http_client
from app.logging_config import configure_logging
from app.security import configure_encryption
from app.workers.jobs import JOBS, purge_expired_data, scan_rtw_expiring
from app.workers.queue import ArqQueue, InlineQueue, set_queue

logger = logging.getLogger(__name__)

PERIODIC_INTERVAL_SECONDS = 3600


async def _run_periodic_jobs() -> None:
    """Inline backend only; with arq these run as cron jobs in the worker."""
    while True:
        for job in (scan_rtw_expiring, purge_expired_data):
            try:
                await job({})
            except Exception:
                logger.exception("Periodic job %s failed", job.__name__)
        await asyncio.sleep(PERIODIC_INTERVAL_SECONDS)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    set_settings(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging()
        configure_encryption(settings.data_encryption_key)
        init_db(settings.database_url)
        init_http_client(settings.internal_base_url, app)
        periodic = None
        if settings.job_backend == "arq":
            queue = await ArqQueue.connect(settings.redis_url)
        else:
            queue = InlineQueue(JOBS)
            if settings.environment != "test":
                periodic = asyncio.create_task(_run_periodic_jobs())
        set_queue(queue)
        app.state.queue = queue
        try:
            yield
        finally:
            if periodic:
                periodic.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await periodic
            await queue.close()
            set_queue(None)
            await close_http_client()
            await dispose_db()

    app = FastAPI(
        title="Driver Verification Service",
        version="0.1.0",
        description="Right to work, identity and HGV licence checks for UK truck drivers.",
        lifespan=lifespan,
    )
    app.state.settings = settings

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError):
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        fields = [
            {"field": ".".join(str(p) for p in err["loc"][1:]), "message": err["msg"].removeprefix("Value error, ")}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "invalid_request", "message": "Some fields are invalid.", "fields": fields}},
        )

    app.include_router(verifications.router)
    app.include_router(verifications.public_router)
    app.include_router(webhooks.router)

    @app.get("/health", tags=["health"])
    async def health():
        return {"status": "ok", "environment": settings.environment}

    if settings.demo_enabled:
        from fastapi.staticfiles import StaticFiles

        from app.demo.routes import router as demo_router

        app.mount("/demo/static", StaticFiles(directory=Path(__file__).parent / "demo" / "static"), name="demo-static")
        app.include_router(demo_router)

    return app
