from redis.asyncio import Redis

_KEY = "bot:enabled"


class BotSwitchRepository:
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis

    async def is_enabled(self) -> bool:
        value = await self._redis.get(_KEY)
        return value is not None and value.strip().casefold() == "1"

    async def enable(self) -> None:
        await self._redis.set(_KEY, "1")

    async def disable(self) -> None:
        await self._redis.set(_KEY, "0")
