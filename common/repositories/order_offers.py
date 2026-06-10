from collections.abc import Sequence
from datetime import timedelta

import asyncpg

from common.models.order_offers import OrderOfferStatus

_TABLE = "order_offers"


class OrderOfferRepository:
    def __init__(self, *, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def offered_user_ids(self, *, order_id: int) -> set[int]:
        rows = await self._pool.fetch(
            f"SELECT user_id FROM {_TABLE} WHERE order_id = $1",
            order_id,
        )
        return {row["user_id"] for row in rows}

    async def offered_counts_by_user(self) -> dict[int, int]:
        rows = await self._pool.fetch(
            f"SELECT user_id, count(*) AS cnt FROM {_TABLE} "
            f"WHERE status = $1::order_offer_status "
            f"GROUP BY user_id",
            OrderOfferStatus.OFFERED.value,
        )
        return {row["user_id"]: row["cnt"] for row in rows}

    async def record_offer(self, *, order_id: int, user_id: int) -> None:
        await self._pool.execute(
            f"INSERT INTO {_TABLE} (order_id, user_id) VALUES ($1, $2) "
            f"ON CONFLICT (order_id, user_id) DO NOTHING",
            order_id,
            user_id,
        )

    async def _resolve_offer(
        self,
        *,
        order_id: int,
        user_id: int,
        status: OrderOfferStatus,
        conn: asyncpg.Connection | None = None,
    ) -> int | None:
        return await (conn or self._pool).fetchval(
            f"UPDATE {_TABLE} SET "
            f"status = $3::order_offer_status, "
            f"resolved_at = NOW() "
            f"WHERE order_id = $1 AND user_id = $2 "
            f"AND status = $4::order_offer_status "
            f"RETURNING user_id",
            order_id,
            user_id,
            status.value,
            OrderOfferStatus.OFFERED.value,
        )

    async def mark_taken(
        self,
        *,
        order_id: int,
        user_id: int,
        conn: asyncpg.Connection | None = None,
    ) -> int | None:
        return await self._resolve_offer(
            order_id=order_id,
            user_id=user_id,
            status=OrderOfferStatus.TAKEN,
            conn=conn,
        )

    async def expire_one(
        self,
        *,
        order_id: int,
        user_id: int,
        conn: asyncpg.Connection | None = None,
    ) -> int | None:
        return await self._resolve_offer(
            order_id=order_id,
            user_id=user_id,
            status=OrderOfferStatus.EXPIRED,
            conn=conn,
        )

    async def has_active_offer(
        self,
        *,
        order_id: int,
        ttl_seconds: int,
        conn: asyncpg.Connection | None = None,
    ) -> bool:
        return await (conn or self._pool).fetchval(
            f"SELECT EXISTS(SELECT 1 FROM {_TABLE} "
            f"WHERE order_id = $1 AND status = $2::order_offer_status "
            f"AND offered_at + $3::interval > NOW())",
            order_id,
            OrderOfferStatus.OFFERED.value,
            timedelta(seconds=ttl_seconds),
        )

    async def expire_offered(
        self,
        *,
        order_id: int,
        conn: asyncpg.Connection | None = None,
    ) -> list[int]:
        rows = await (conn or self._pool).fetch(
            f"UPDATE {_TABLE} SET "
            f"status = $2::order_offer_status, "
            f"resolved_at = NOW() "
            f"WHERE order_id = $1 AND status = $3::order_offer_status "
            f"RETURNING user_id",
            order_id,
            OrderOfferStatus.EXPIRED.value,
            OrderOfferStatus.OFFERED.value,
        )
        return [row["user_id"] for row in rows]

    async def expire_many(
        self,
        *,
        offers: Sequence[tuple[int, int]],
    ) -> list[tuple[int, int]]:
        if not offers:
            return []
        order_ids = [order_id for order_id, _ in offers]
        user_ids = [user_id for _, user_id in offers]
        rows = await self._pool.fetch(
            f"UPDATE {_TABLE} AS oo "
            f"SET status = $3::order_offer_status, resolved_at = NOW() "
            f"FROM unnest($1::int[], $2::bigint[]) AS due(order_id, user_id) "
            f"WHERE oo.order_id = due.order_id "
            f"AND oo.user_id = due.user_id "
            f"AND oo.status = $4::order_offer_status "
            f"RETURNING oo.order_id, oo.user_id",
            order_ids,
            user_ids,
            OrderOfferStatus.EXPIRED.value,
            OrderOfferStatus.OFFERED.value,
        )
        return [(row["order_id"], row["user_id"]) for row in rows]
