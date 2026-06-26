from __future__ import annotations

import functools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum

from aiogram.utils.i18n import gettext as _

from common.catalog.packages import PACKAGE_SIZES

_UNBOUNDED = "\u221e"


class TierNumber(IntEnum):
    T0 = 0
    T1 = 1
    T2 = 2


@dataclass(frozen=True, eq=False, slots=True)
class TierScheme:
    with_codes: bool
    ranges: Mapping[TierNumber, tuple[int, int | None]]
    name_keys: Mapping[TierNumber, str]

    def tier(self, number: TierNumber) -> Tier:
        return Tier(with_codes=self.with_codes, number=number)

    def tiers(self) -> tuple[Tier, ...]:
        return tuple(self.tier(number) for number in TierNumber)

    def default(self) -> Tier:
        return self.tier(TierNumber.T0)

    def required(self, amounts: Sequence[int]) -> Tier | None:
        for tier in self.tiers():
            if tier.allows(amounts):
                return tier
        return None

    def serving(self, amounts: Sequence[int]) -> list[Tier]:
        return [tier for tier in self.tiers() if tier.allows(amounts)]


@functools.total_ordering
class Tier:
    __slots__ = ("number", "scheme")

    def __init__(self, *, with_codes: bool, number: int) -> None:
        self.number = TierNumber(number)
        self.scheme = tiers_for(with_codes=with_codes)

    @property
    def value(self) -> int:
        return int(self.number)

    def __int__(self) -> int:
        return int(self.number)

    def __repr__(self) -> str:
        return f"Tier(with_codes={self.scheme.with_codes}, number={int(self.number)})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Tier):
            return NotImplemented
        return self.number == other.number and self.scheme is other.scheme

    def __hash__(self) -> int:
        return hash((self.number, self.scheme))

    def __lt__(self, other: Tier) -> bool:
        return self.number < other.number

    def allows(self, amounts: Sequence[int]) -> bool:
        low, high = self.scheme.ranges[self.number]
        return all(low <= amount and (high is None or amount <= high) for amount in amounts)

    def allowed_packs(self) -> tuple[int, ...]:
        low, high = self.scheme.ranges[self.number]
        return tuple(
            size for size in PACKAGE_SIZES if low <= size and (high is None or size <= high)
        )

    def range_label(self) -> str:
        low, high = self.scheme.ranges[self.number]
        return f"{low}-{_UNBOUNDED if high is None else high}"

    def name(self) -> str:
        return _(self.scheme.name_keys[self.number])


_NAME_KEYS: dict[TierNumber, str] = {
    TierNumber.T0: "tier.basic",
    TierNumber.T1: "tier.standard",
    TierNumber.T2: "tier.unlimited",
}

CODE_TIERS = TierScheme(
    with_codes=True,
    ranges={
        TierNumber.T0: (60, 325),
        TierNumber.T1: (60, 1800),
        TierNumber.T2: (60, 8100),
    },
    name_keys=_NAME_KEYS,
)

PACK_TIERS = TierScheme(
    with_codes=False,
    ranges={
        TierNumber.T0: (60, 720),
        TierNumber.T1: (60, 16200),
        TierNumber.T2: (60, None),
    },
    name_keys=_NAME_KEYS,
)


def tiers_for(*, with_codes: bool) -> TierScheme:
    return CODE_TIERS if with_codes else PACK_TIERS
