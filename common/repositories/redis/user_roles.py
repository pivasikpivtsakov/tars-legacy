from collections.abc import Collection
from enum import StrEnum

from redis.asyncio import Redis

_KEY_PREFIX = "settings:role_user_ids"


class UserRole(StrEnum):
    ADMIN = "admin"
    MODERATOR = "moderator"


def _key(role: UserRole) -> str:
    return f"{_KEY_PREFIX}:{role.value}"


class UserRoleRepository:
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis

    async def get(self, *, role: UserRole) -> frozenset[int]:
        members = await self._redis.smembers(_key(role))
        return frozenset(int(member) for member in members)

    async def get_all(self) -> dict[UserRole, frozenset[int]]:
        roles = list(UserRole)
        async with self._redis.pipeline(transaction=False) as pipe:
            for role in roles:
                pipe.smembers(_key(role))
            results = await pipe.execute()
        return {
            role: frozenset(int(member) for member in members)
            for role, members in zip(roles, results, strict=True)
        }

    async def add(self, *, role: UserRole, user_id: int) -> None:
        await self._redis.sadd(_key(role), str(user_id))

    async def remove(self, *, role: UserRole, user_id: int) -> None:
        await self._redis.srem(_key(role), str(user_id))

    async def set(self, *, role: UserRole, user_ids: Collection[int]) -> None:
        key = _key(role)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.delete(key)
            if user_ids:
                pipe.sadd(key, *(str(user_id) for user_id in user_ids))
            await pipe.execute()

    async def reset(self, *, role: UserRole) -> None:
        await self._redis.delete(_key(role))
