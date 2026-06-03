from dataclasses import dataclass
from datetime import time
from enum import StrEnum

import asyncpg


class UserProfileStatus(StrEnum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    BANNED = "banned"


@dataclass(frozen=True, slots=True)
class UserProfile:
    id: int
    tg_id: int
    works_alone: bool | None
    packages: tuple[int, ...] | None
    price_60: int | None
    withdrawal_method: str | None
    work_start: time | None
    work_end: time | None
    is_online: bool
    with_codes: bool
    status: UserProfileStatus
    balance: int

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> UserProfile:
        packages = row["packages"]
        return cls(
            id=row["id"],
            tg_id=row["tg_id"],
            works_alone=row["works_alone"],
            packages=tuple(packages) if packages is not None else None,
            price_60=row["price_60"],
            withdrawal_method=row["withdrawal_method"],
            work_start=row["work_start"],
            work_end=row["work_end"],
            is_online=row["is_online"],
            with_codes=row["with_codes"],
            status=UserProfileStatus(row["status"]),
            balance=row["balance"],
        )
