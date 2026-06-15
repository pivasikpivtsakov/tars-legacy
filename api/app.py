import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.dependencies import bot, close_pool, init_pool
from api.routers import orders
from common.environment import MOCK_EXTERNAL_API

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await init_pool()
    try:
        yield
    finally:
        await bot.session.close()
        await close_pool()


app = FastAPI(lifespan=lifespan)

app.include_router(orders.router)

if MOCK_EXTERNAL_API:
    from api.testing import enable_mock_external_api

    logger.warning("MOCK_EXTERNAL_API is enabled: serving canned upstream responses")
    enable_mock_external_api(app)
