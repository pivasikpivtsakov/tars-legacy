from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg

_TABLE = "orders"

_SELECT_COLUMNS = (
    "id, original_id, shop_access_key, status, status_reason, amount, pubg_id, "
    "codes, unused_codes, broken_codes, redeemed_codes, additional_data, "
    "created_at, updated_at"
)


@dataclass(frozen=True, slots=True)
class Order:
    id: int
    original_id: int
    shop_access_key: str | None
    status: str | None
    status_reason: str | None
    amount: int | None
    pubg_id: int | None
    codes: Any
    unused_codes: Any
    broken_codes: tuple[str, ...]
    redeemed_codes: tuple[str, ...]
    additional_data: Any
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> "Order":
        return cls(
            id=row["id"],
            original_id=row["original_id"],
            shop_access_key=row["shop_access_key"],
            status=row["status"],
            status_reason=row["status_reason"],
            amount=row["amount"],
            pubg_id=row["pubg_id"],
            codes=row["codes"],
            unused_codes=row["unused_codes"],
            broken_codes=tuple(row["broken_codes"]),
            redeemed_codes=tuple(row["redeemed_codes"]),
            additional_data=row["additional_data"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class OrderRepository:
    def __init__(self, *, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(
        self,
        *,
        original_id: int,
        amount: int,
        pubg_id: int,
    ) -> Order:
        row = await self._pool.fetchrow(
            f"INSERT INTO {_TABLE} (original_id, amount, pubg_id) "
            f"VALUES ($1, $2, $3) "
            f"RETURNING {_SELECT_COLUMNS}",
            original_id,
            amount,
            pubg_id,
        )
        if row is None:
            msg = "failed to insert order"
            raise LookupError(msg)
        return Order.from_row(row)
