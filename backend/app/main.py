from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import router as api_router
from backend.application.container import (
    build_smart_routing_dns_background_worker,
)
from backend.services.smart_routing_dns_background_worker import (
    SmartRoutingDnsBackgroundWorker,
)

# Ensure application and background-worker logs reach Docker stdout/stderr.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    worker: SmartRoutingDnsBackgroundWorker | None = None
    worker_task: asyncio.Task[None] | None = None

    try:
        worker = build_smart_routing_dns_background_worker()
        worker_task = asyncio.create_task(
            worker.run(),
            name="maxvpn-smart-routing-dns",
        )

        app.state.smart_routing_dns_worker = worker
        app.state.smart_routing_dns_worker_task = worker_task

        logger.info("MaxVPN Smart Routing DNS worker started")

        yield

    finally:
        if worker is not None:
            await worker.stop()

        if worker_task is not None:
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception(
                    "MaxVPN Smart Routing DNS worker stopped with error",
                )


app = FastAPI(
    title="MaxVPN API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/")
def root():
    return {"project": "MaxVPN", "status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}
