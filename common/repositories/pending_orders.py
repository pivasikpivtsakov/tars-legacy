from collections.abc import Mapping, Sequence

from redis.asyncio import Redis

_KEY_PREFIX = "orders:pending:"

_RELEASE = """
local current = redis.call('DECR', KEYS[1])
if current < 0 then
    redis.call('SET', KEYS[1], 0)
    return 0
end
return current
"""


def _key(user_id: int) -> str:
    return f"{_KEY_PREFIX}{user_id}"


class PendingOrdersRepository:
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis
        self._release_script = redis.register_script(_RELEASE)

    async def reserve(self, *, user_id: int, limit: int) -> bool:
        new_count = await self._redis.incr(_key(user_id))
        if new_count > limit:
            await self._redis.decr(_key(user_id))
            return False
        return True

    async def release(self, *, user_id: int) -> None:
        await self._release_script(keys=[_key(user_id)])

    async def release_many(self, *, user_ids: Sequence[int]) -> None:
        for user_id in user_ids:
            await self._release_script(keys=[_key(user_id)])

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
