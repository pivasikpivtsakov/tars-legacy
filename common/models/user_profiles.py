from dataclasses import dataclass
from datetime import time
from decimal import Decimal
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
    chat_addable: bool | None
    raw_prices: dict[str, str] | None
    withdrawal_method: str | None
    work_start: time | None
    work_end: time | None
    is_online: bool
    with_codes: bool
    status: UserProfileStatus
    tier: Tier

    @property
    def prices(self) -> dict[int, Decimal] | None:
        if self.raw_prices is None:
            return None
        return {int(size): Decimal(str(price)) for size, price in self.raw_prices.items()}

    @property
    def packages(self) -> tuple[int, ...] | None:
        if not self.raw_prices:
            return None
        return tuple(sorted(int(size) for size in self.raw_prices))

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> UserProfile:
        return cls(
            id=row["id"],
            tg_id=row["tg_id"],
            chat_addable=row["chat_addable"],
            raw_prices=row["prices"],
            withdrawal_method=row["withdrawal_method"],
            work_start=row["work_start"],
            work_end=row["work_end"],
            is_online=row["is_online"],
            with_codes=row["with_codes"],
            status=UserProfileStatus(row["status"]),
            tier=Tier(row["tier"]),
        )
