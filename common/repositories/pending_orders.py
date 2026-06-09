from collections.abc import Mapping, Sequence

from redis.asyncio import Redis

_KEY_PREFIX = "orders:pending:"

_RESERVE = """
local current = redis.call('INCR', KEYS[1])
if current > tonumber(ARGV[1]) then
    redis.call('DECR', KEYS[1])
    return 0
end
return 1
"""

_RELEASE = """
for i = 1, #KEYS do
    if redis.call('DECR', KEYS[i]) < 0 then
        redis.call('SET', KEYS[i], 0)
    end
end
"""


def _key(user_id: int) -> str:
    return f"{_KEY_PREFIX}{user_id}"


class PendingOrdersRepository:
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis
        self._reserve_script = redis.register_script(_RESERVE)
        self._release_script = redis.register_script(_RELEASE)

    async def reserve(self, *, user_id: int, limit: int) -> bool:
        reserved = await self._reserve_script(keys=[_key(user_id)], args=[limit])
        return bool(reserved)

    async def release(self, *, user_id: int) -> None:
        await self.release_many(user_ids=[user_id])

    async def release_many(self, *, user_ids: Sequence[int]) -> None:
        if not user_ids:
            return
        await self._release_script(keys=[_key(user_id) for user_id in user_ids])

    async def set_counts(self, *, counts: Mapping[int, int]) -> None:
        if not counts:
            return
        pipe = self._redis.pipeline(transaction=False)
        for user_id, count in counts.items():
            pipe.set(_key(user_id), count)
        await pipe.execute()

    async def reset(self) -> None:
        keys = [key async for key in self._redis.scan_iter(match=f"{_KEY_PREFIX}*")]
        if keys:
            await self._redis.delete(*keys)
