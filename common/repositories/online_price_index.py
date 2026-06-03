from collections.abc import Collection, Sequence
from dataclasses import dataclass

from redis.asyncio import Redis

from common.models.user_profiles import UserProfile, UserProfileStatus
from common.packages import PACKAGE_SIZES


@dataclass(frozen=True, slots=True)
class PricedCandidate:
    user_id: int
    price_60: int


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
        member = str(profile.user_id)
        pipe = self._redis.pipeline(transaction=True)
        for size in PACKAGE_SIZES:
            if price is not None and size in target_sizes:
                pipe.zadd(_pkg_key(size), {member: price})
            else:
                pipe.zrem(_pkg_key(size), member)
        await pipe.execute()

    async def remove(self, *, user_id: int) -> None:
        member = str(user_id)
        pipe = self._redis.pipeline(transaction=True)
        for size in PACKAGE_SIZES:
            pipe.zrem(_pkg_key(size), member)
        await pipe.execute()

    async def clear(self) -> None:
        await self._redis.delete(*(_pkg_key(size) for size in PACKAGE_SIZES))

    async def get_cheapest_candidates(
        self,
        *,
        required_packages: Sequence[int],
        exclude_user_ids: Collection[int] = (),
    ) -> list[PricedCandidate]:
        if not required_packages:
            return []
        keys = [_pkg_key(size) for size in required_packages]
        pairs = await self._redis.zinter(keys, aggregate="MIN", withscores=True)
        excluded = set(exclude_user_ids)
        candidates: list[PricedCandidate] = []
        for member, score in pairs:
            user_id = int(member)
            if user_id in excluded:
                continue
            candidates.append(PricedCandidate(user_id=user_id, price_60=int(score)))
        return candidates
