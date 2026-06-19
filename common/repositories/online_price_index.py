from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from redis.asyncio import Redis

from common.catalog.packages import PACKAGE_SIZES
from common.models.user_profiles import UserProfile, UserProfileStatus


@dataclass(frozen=True, slots=True)
class PricedCandidate:
    user_id: int
    full_price: int


_WITH_CODES_KEY = "rank:with_codes"
_TIER_KEY = "rank:tier"


def _pkg_key(size: int) -> str:
    return f"rank:pkg:{size}"


class OnlinePriceIndex:
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis

    async def sync(self, *, profile: UserProfile) -> None:
        eligible = (
            profile.status is UserProfileStatus.ACTIVE
            and profile.is_online
            and bool(profile.prices)
        )
        prices = profile.prices if eligible else None
        member = str(profile.id)
        pipe = self._redis.pipeline(transaction=True)
        for size in PACKAGE_SIZES:
            price = prices.get(size) if prices is not None else None
            if price is not None:
                pipe.zadd(_pkg_key(size), {member: price})
            else:
                pipe.zrem(_pkg_key(size), member)
        if eligible and profile.with_codes:
            pipe.sadd(_WITH_CODES_KEY, member)
        else:
            pipe.srem(_WITH_CODES_KEY, member)
        if eligible:
            pipe.hset(_TIER_KEY, member, profile.tier.value)
        else:
            pipe.hdel(_TIER_KEY, member)
        await pipe.execute()

    async def remove(self, *, user_id: int) -> None:
        member = str(user_id)
        pipe = self._redis.pipeline(transaction=True)
        for size in PACKAGE_SIZES:
            pipe.zrem(_pkg_key(size), member)
        pipe.srem(_WITH_CODES_KEY, member)
        pipe.hdel(_TIER_KEY, member)
        await pipe.execute()

    async def clear(self) -> None:
        await self._redis.delete(
            *(_pkg_key(size) for size in PACKAGE_SIZES),
            _WITH_CODES_KEY,
            _TIER_KEY,
        )

    async def get_cheapest_candidates(
        self,
        *,
        package_counts: Mapping[int, int],
    ) -> list[PricedCandidate]:
        if not package_counts:
            return []
        keys = {_pkg_key(size): count for size, count in package_counts.items()}
        pairs = await self._redis.zinter(keys, aggregate="SUM", withscores=True)
        return [
            PricedCandidate(user_id=int(member), full_price=int(score)) for member, score in pairs
        ]

    async def filter_with_codes(self, *, user_ids: Sequence[int]) -> set[int]:
        if not user_ids:
            return set()
        members = [str(user_id) for user_id in user_ids]
        flags = await self._redis.smismember(_WITH_CODES_KEY, members)
        return {user_id for user_id, present in zip(user_ids, flags, strict=True) if present}

    async def filter_by_min_tier(self, *, user_ids: Sequence[int], min_tier: int) -> set[int]:
        if not user_ids:
            return set()
        members = [str(user_id) for user_id in user_ids]
        raw = await self._redis.hmget(_TIER_KEY, members)
        return {
            user_id
            for user_id, value in zip(user_ids, raw, strict=True)
            if value is not None and int(value) >= min_tier
        }
