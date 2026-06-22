from redis.asyncio import Redis

from common.catalog.packages import PACKAGE_SIZES, PACKAGE_UNIT_COUNT

_KEY = "settings:pack_price_limit"
_DEFAULT_UNIT_PRICE_CAP = 1000


def _default_limit(size: int) -> int:
    return _DEFAULT_UNIT_PRICE_CAP * PACKAGE_UNIT_COUNT[size]


class PackPriceLimitRepository:
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis

    async def get(self, *, size: int) -> int:
        value = await self._redis.hget(_KEY, str(size))
        if value is None:
            return _default_limit(size)
        return int(value)

    async def get_all(self) -> dict[int, int]:
        raw = await self._redis.hgetall(_KEY)
        return {
            size: int(raw[str(size)]) if str(size) in raw else _default_limit(size)
            for size in PACKAGE_SIZES
        }

    async def set(self, *, size: int, limit: int) -> None:
        await self._redis.hset(_KEY, str(size), str(limit))

    async def reset(self, *, size: int) -> None:
        await self._redis.hdel(_KEY, str(size))

    async def reset_all(self) -> None:
        await self._redis.delete(_KEY)
