from collections.abc import Sequence
from dataclasses import dataclass

from redis.asyncio import Redis

from common.models.user_profiles import UserProfile, UserProfileStatus
from common.packages import PACKAGE_SIZES


@dataclass(frozen=True, slots=True)
class PricedCandidate:
    user_id: int
    price_60: int


_WITH_CODES_KEY = "rank:with_codes"


def _pkg_key(size: int) -> str:
    return f"rank:pkg:{size}"


class OnlinePriceIndex:
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis

    async def sync(self, *, profile: UserProfile) -> None:
        eligible = (
            profile.status is UserProfileStatus.ACTIVE
            and profile.is_online
            and profile.price_60 is not None
            and bool(profile.packages)
        )
        price = profile.price_60 if eligible else None
        target_sizes = set(profile.packages or ()) if eligible else set()
        member = str(profile.id)
        pipe = self._redis.pipeline(transaction=True)
        for size in PACKAGE_SIZES:
            if price is not None and size in target_sizes:
                pipe.zadd(_pkg_key(size), {member: price})
            else:
                pipe.zrem(_pkg_key(size), member)
        if eligible and profile.with_codes:
            pipe.sadd(_WITH_CODES_KEY, member)
        else:
            pipe.srem(_WITH_CODES_KEY, member)
        await pipe.execute()

    async def remove(self, *, user_id: int) -> None:
        member = str(user_id)
        pipe = self._redis.pipeline(transaction=True)
        for size in PACKAGE_SIZES:
            pipe.zrem(_pkg_key(size), member)
        pipe.srem(_WITH_CODES_KEY, member)
        await pipe.execute()

    async def clear(self) -> None:
        await self._redis.delete(
            *(_pkg_key(size) for size in PACKAGE_SIZES),
            _WITH_CODES_KEY,
        )

    async def get_cheapest_candidates(
        self,
        *,
        required_packages: Sequence[int],
    ) -> list[PricedCandidate]:
        if not required_packages:
            return []
        keys = [_pkg_key(size) for size in required_packages]
        pairs = await self._redis.zinter(keys, aggregate="MIN", withscores=True)
        return [
            PricedCandidate(user_id=int(member), price_60=int(score))
            for member, score in pairs
        ]

    async def filter_with_codes(self, *, user_ids: Sequence[int]) -> set[int]:
        if not user_ids:
            return set()
        members = [str(user_id) for user_id in user_ids]
        flags = await self._redis.smismember(_WITH_CODES_KEY, members)
        return {
            user_id
            for user_id, present in zip(user_ids, flags, strict=True)
            if present
        }
