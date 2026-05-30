from collections.abc import Collection
from dataclasses import dataclass

from common.packages import PACKAGE_UNIT_COUNT
from common.repositories.orders import Order
from common.repositories.user_profiles import UserProfileRepository

_PACKAGE_SIZES_DESC: tuple[int, ...] = tuple(sorted(PACKAGE_UNIT_COUNT, reverse=True))


@dataclass(frozen=True, slots=True)
class PackageDecomposition:
    parts: tuple[int, ...]
    unique_parts: tuple[int, ...]
    total_units: int


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    user_id: int
    full_price: int


class OrderAmountError(ValueError):
    pass


def decompose_amount(amount: int) -> PackageDecomposition:
    if amount <= 0:
        msg = f"amount must be positive, got {amount}"
        raise OrderAmountError(msg)
    parts: list[int] = []
    remaining = amount
    for size in _PACKAGE_SIZES_DESC:
        count, remaining = divmod(remaining, size)
        parts.extend([size] * count)
    if remaining != 0:
        msg = f"cannot decompose amount={amount} into available packages"
        raise OrderAmountError(msg)
    return PackageDecomposition(
        parts=tuple(parts),
        unique_parts=tuple(sorted(set(parts))),
        total_units=sum(PACKAGE_UNIT_COUNT[p] for p in parts),
    )


class OrderManager:
    def __init__(self, *, profiles: UserProfileRepository) -> None:
        self._profiles = profiles

    async def select_candidates(
        self,
        *,
        order: Order,
        exclude_user_ids: Collection[int] = (),
    ) -> list[RankedCandidate]:
        if order.amount is None:
            msg = f"order id={order.id} has no amount"
            raise OrderAmountError(msg)
        decomposition = decompose_amount(order.amount)
        profiles = await self._profiles.list_online_with_packages(
            required_packages=decomposition.unique_parts,
        )
        excluded = set(exclude_user_ids)
        return [
            RankedCandidate(
                user_id=profile.user_id,
                full_price=profile.price_60 * decomposition.total_units,
            )
            for profile in profiles
            if profile.price_60 is not None and profile.user_id not in excluded
        ]
