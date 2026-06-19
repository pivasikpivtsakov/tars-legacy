from dataclasses import dataclass
from datetime import time
from enum import StrEnum

import asyncpg

from common.catalog.tiers import Tier


class UserProfileStatus(StrEnum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    BANNED = "banned"


@dataclass(frozen=True, slots=True)
class UserProfile:
    id: int
    tg_id: int
    works_alone: bool | None
    prices: dict[int, int] | None
    withdrawal_method: str | None
    work_start: time | None
    work_end: time | None
    is_online: bool
    with_codes: bool
    status: UserProfileStatus
    balance: int
    tier: Tier

    @property
    def packages(self) -> tuple[int, ...] | None:
        if not self.prices:
            return None
        return tuple(sorted(self.prices))

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> UserProfile:
        prices = row["prices"]
        return cls(
            id=row["id"],
            tg_id=row["tg_id"],
            works_alone=row["works_alone"],
            prices={int(size): int(price) for size, price in prices.items()}
            if prices is not None
            else None,
            withdrawal_method=row["withdrawal_method"],
            work_start=row["work_start"],
            work_end=row["work_end"],
            is_online=row["is_online"],
            with_codes=row["with_codes"],
            status=UserProfileStatus(row["status"]),
            balance=row["balance"],
            tier=Tier(row["tier"]),
        )
