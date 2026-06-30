import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.dependencies import bot, close_pool, close_redis, init_pool, init_redis
from api.routers import orders

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await init_pool()
    init_redis()
    try:
        yield
    finally:
        await bot.session.close()
        await close_redis()
        await close_pool()


app = FastAPI(lifespan=lifespan)

app.include_router(orders.router)
