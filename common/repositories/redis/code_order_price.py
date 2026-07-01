from decimal import Decimal

from redis.asyncio import Redis

_KEY = "settings:code_order_price"
_DEFAULT_PRICE = Decimal(1)


class CodeOrderPriceRepository:
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis

    async def get(self) -> Decimal:
        value = await self._redis.get(_KEY)
        if value is None:
            return _DEFAULT_PRICE
        return Decimal(value)

    async def set(self, *, price: Decimal) -> None:
        await self._redis.set(_KEY, str(price))
