import contextlib
import logging
from collections.abc import AsyncIterator

from redis.asyncio import Redis
from redis.asyncio.client import PubSub
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

_WAKE_CHANNEL = "orders:dispatch:wake"
_WAKE_PAYLOAD = "1"


class WakeStream:
    def __init__(self, *, pubsub: PubSub) -> None:
        self._pubsub = pubsub

    async def wait(self, *, timeout_seconds: float) -> None:
        # Returns when a wake arrives or the timeout elapses; the caller sweeps
        # either way, so a missed publish degrades to backstop latency, not a stall.
        await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=timeout_seconds)


class DispatchSignal:
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis

    async def request(self) -> None:
        try:
            await self._redis.publish(_WAKE_CHANNEL, _WAKE_PAYLOAD)
        except RedisError:
            logger.warning("failed to publish dispatch wake", exc_info=True)

    @contextlib.asynccontextmanager
    async def subscribe(self) -> AsyncIterator[WakeStream]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(_WAKE_CHANNEL)
        try:
            yield WakeStream(pubsub=pubsub)
        finally:
            with contextlib.suppress(RedisError):
                await pubsub.aclose()
