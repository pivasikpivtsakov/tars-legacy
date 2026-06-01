from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

import asyncpg

_TABLE = "order_offers"


class OrderOfferStatus(StrEnum):
    OFFERED = "offered"
    TAKEN = "taken"
    DECLINED = "declined"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class OrderOffer:
    order_id: int
    user_id: int
    status: OrderOfferStatus
    offered_at: datetime
    resolved_at: datetime | None

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> "OrderOffer":
        return cls(
            order_id=row["order_id"],
            user_id=row["user_id"],
            status=OrderOfferStatus(row["status"]),
            offered_at=row["offered_at"],
            resolved_at=row["resolved_at"],
        )


class OrderOfferRepository:
    def __init__(self, *, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def offered_user_ids(self, *, order_id: int) -> set[int]:
        rows = await self._pool.fetch(
            f"SELECT user_id FROM {_TABLE} WHERE order_id = $1",
            order_id,
        )
        return {row["user_id"] for row in rows}

    async def record_offer(self, *, order_id: int, user_id: int) -> None:
        await self._pool.execute(
            f"INSERT INTO {_TABLE} (order_id, user_id) VALUES ($1, $2) "
            f"ON CONFLICT (order_id, user_id) DO NOTHING",
            order_id,
            user_id,
        )

    async def mark_taken(
        self,
        *,
        order_id: int,
        user_id: int,
        conn: asyncpg.Connection | None = None,
    ) -> None:
        await (conn or self._pool).execute(
            f"UPDATE {_TABLE} SET "
            f"status = $3::order_offer_status, "
            f"resolved_at = NOW() "
            f"WHERE order_id = $1 AND user_id = $2 "
            f"AND status = $4::order_offer_status",
            order_id,
            user_id,
            OrderOfferStatus.TAKEN.value,
            OrderOfferStatus.OFFERED.value,
        )

    async def expire_offered(
        self,
        *,
        order_id: int,
        conn: asyncpg.Connection | None = None,
    ) -> None:
        await (conn or self._pool).execute(
            f"UPDATE {_TABLE} SET "
            f"status = $2::order_offer_status, "
            f"resolved_at = NOW() "
            f"WHERE order_id = $1 AND status = $3::order_offer_status",
            order_id,
            OrderOfferStatus.EXPIRED.value,
            OrderOfferStatus.OFFERED.value,
        )
