import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from redis.asyncio import Redis

from common.catalog.packages import PACKAGE_SIZES
from common.catalog.tiers import Tier
from common.models.user_profiles import UserProfile, UserProfileStatus
from common.money import from_minor_units, to_minor_units

_PACK_TIER_KEY = "rank:pkg:tier"


def _pkg_key(size: int) -> str:
    return f"rank:pkg:{size}"


def _code_tier_key(tier: Tier) -> str:
    return f"rank:codes:tier:{int(tier)}"


@dataclass(frozen=True, slots=True)
class PricedCandidate:
    user_id: int
    full_price: Decimal


@dataclass(frozen=True, slots=True)
class CodeCandidate:
    user_id: int


class PackOnlineIndex:
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis

    async def add(self, *, profile: UserProfile) -> None:
        prices = profile.prices or {}
        member = str(profile.id)
        pipe = self._redis.pipeline(transaction=True)
        for size in PACKAGE_SIZES:
            price = prices.get(size)
            if price is not None:
                pipe.zadd(_pkg_key(size), {member: to_minor_units(price)})
            else:
                pipe.zrem(_pkg_key(size), member)
        pipe.hset(_PACK_TIER_KEY, member, profile.tier.value)
        await pipe.execute()

    async def remove(self, *, user_id: int) -> None:
        member = str(user_id)
        pipe = self._redis.pipeline(transaction=True)
        for size in PACKAGE_SIZES:
            pipe.zrem(_pkg_key(size), member)
        pipe.hdel(_PACK_TIER_KEY, member)
        await pipe.execute()

    async def clear(self) -> None:
        await self._redis.delete(*(_pkg_key(size) for size in PACKAGE_SIZES), _PACK_TIER_KEY)

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
            PricedCandidate(user_id=int(member), full_price=from_minor_units(int(score)))
            for member, score in pairs
        ]

    async def filter_by_min_tier(self, *, user_ids: Sequence[int], min_tier: int) -> set[int]:
        if not user_ids:
            return set()
        members = [str(user_id) for user_id in user_ids]
        raw = await self._redis.hmget(_PACK_TIER_KEY, members)
        return {
            user_id
            for user_id, value in zip(user_ids, raw, strict=True)
            if value is not None and int(value) >= min_tier
        }


class CodeOnlineIndex:
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis

    async def add(self, *, profile: UserProfile, online_at: int) -> None:
        await self._redis.zadd(_code_tier_key(profile.tier), {str(profile.id): online_at}, nx=True)

    async def remove(self, *, user_id: int) -> None:
        member = str(user_id)
        pipe = self._redis.pipeline(transaction=True)
        for tier in Tier:
            pipe.zrem(_code_tier_key(tier), member)
        await pipe.execute()

    async def clear(self) -> None:
        await self._redis.delete(*(_code_tier_key(tier) for tier in Tier))

    async def get_candidates(self, *, tiers: Sequence[Tier]) -> list[CodeCandidate]:
        if not tiers:
            return []
        keys = [_code_tier_key(tier) for tier in tiers]
        pairs = await self._redis.zunion(keys, aggregate="MIN", withscores=True)
        ordered = sorted(pairs, key=lambda pair: (pair[1], int(pair[0])))
        return [CodeCandidate(user_id=int(member)) for member, _ in ordered]


class OnlineIndexRouter:
    def __init__(self, *, pack: PackOnlineIndex, code: CodeOnlineIndex) -> None:
        self.pack = pack
        self.code = code

    async def sync(self, *, profile: UserProfile) -> None:
        eligible = profile.status is UserProfileStatus.ACTIVE and profile.is_online
        if not eligible:
            await self.pack.remove(user_id=profile.id)
            await self.code.remove(user_id=profile.id)
            return
        if profile.with_codes:
            await self.code.add(profile=profile, online_at=int(time.time()))
            await self.pack.remove(user_id=profile.id)
        else:
            await self.pack.add(profile=profile)
            await self.code.remove(user_id=profile.id)

    async def remove(self, *, user_id: int) -> None:
        await self.pack.remove(user_id=user_id)
        await self.code.remove(user_id=user_id)

    async def clear(self) -> None:
        await self.pack.clear()
        await self.code.clear()
