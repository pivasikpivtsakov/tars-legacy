import asyncio
import contextlib
import logging
from collections.abc import Callable

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

_WAKE_CHANNEL = "orders:dispatch:wake"
_WAKE_PAYLOAD = "1"
_RECONNECT_DELAY_SECONDS = 1.0


class DispatchSignal:
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis

    async def request(self) -> None:
        try:
            await self._redis.publish(_WAKE_CHANNEL, _WAKE_PAYLOAD)
        except RedisError:
            logger.warning("failed to publish dispatch wake", exc_info=True)

    async def listen(self, *, on_wake: Callable[[], None]) -> None:
        while True:
            pubsub = self._redis.pubsub()
            try:
                await pubsub.subscribe(_WAKE_CHANNEL)
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        on_wake()
            except asyncio.CancelledError:
                raise
            except RedisError:
                logger.warning("dispatch wake listener dropped; reconnecting", exc_info=True)
                await asyncio.sleep(_RECONNECT_DELAY_SECONDS)
            finally:
                with contextlib.suppress(RedisError):
                    await pubsub.aclose()
