import json
from datetime import timedelta
from decimal import Decimal
from typing import Any

import asyncpg

from common.models.order_offers import OrderOfferStatus
from common.models.orders import ExternalOrderStatus, Order, OrderStatus

_TABLE = "orders"


def _dump_json(value: Any) -> str:
    return json.dumps(value if value is not None else {})


_ACTIVE_FANOUT_STATUSES: tuple[str, ...] = (
    OrderStatus.PENDING.value,
    OrderStatus.OFFERING.value,
)

# Inlined literals (not a bound parameter) so the predicate matches the partial
# index orders_active_fanout_idx; a `= ANY($1)` form can't prove that match at plan
# time. Values come from the OrderStatus enum, so this is not user input.
_ACTIVE_FANOUT_STATUS_SQL = ", ".join(f"'{status}'" for status in _ACTIVE_FANOUT_STATUSES)

_SELECT_COLUMNS = (
    "id, original_id, shop_access_key, status, status_reason, amount, pubg_id, "
    "codes, unused_codes, broken_codes, redeemed_codes, additional_data, "
    "offered_at, closed_at, taken_at, taken_by, taken_price, created_at, updated_at, "
    "external_status, is_only_w_codes"
)


class OrderRepository:
    def __init__(self, *, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def add(
        self,
        *,
        original_id: int,
        amount: int,
        shop_access_key: str | None = None,
        pubg_id: int | None = None,
        codes: Any = None,
        unused_codes: Any = None,
        broken_codes: tuple[str, ...] = (),
        redeemed_codes: tuple[str, ...] = (),
        additional_data: Any = None,
        external_status: ExternalOrderStatus | None = None,
        status_reason: str | None = None,
        is_only_w_codes: bool = False,
        conn: asyncpg.Connection | None = None,
    ) -> Order:
        row = await (conn or self._pool).fetchrow(
            f"INSERT INTO {_TABLE} ("
            f"original_id, shop_access_key, status_reason, amount, pubg_id, "
            f"codes, unused_codes, broken_codes, redeemed_codes, additional_data, "
            f"external_status, is_only_w_codes"
            f") VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12) "
            f"RETURNING {_SELECT_COLUMNS}",
            original_id,
            shop_access_key,
            status_reason,
            amount,
            pubg_id,
            _dump_json(codes),
            _dump_json(unused_codes),
            list(broken_codes),
            list(redeemed_codes),
            _dump_json(additional_data),
            external_status,
            is_only_w_codes,
        )
        if row is None:
            msg = "failed to insert order"
            raise LookupError(msg)
        return Order.from_row(row)

    async def get_by_original_id(
        self,
        *,
        original_id: int,
        conn: asyncpg.Connection | None = None,
    ) -> Order | None:
        row = await (conn or self._pool).fetchrow(
            f"SELECT {_SELECT_COLUMNS} FROM {_TABLE} WHERE original_id = $1",
            original_id,
        )
        if row is None:
            return None
        return Order.from_row(row)

    async def remove(
        self,
        *,
        order_id: int,
        conn: asyncpg.Connection | None = None,
    ) -> None:
        await (conn or self._pool).execute(
            f"DELETE FROM {_TABLE} WHERE id = $1",
            order_id,
        )

    async def update_order(
        self,
        *,
        order_id: int,
        amount: int,
        shop_access_key: str | None = None,
        pubg_id: int | None = None,
        codes: Any = None,
        unused_codes: Any = None,
        broken_codes: tuple[str, ...] = (),
        redeemed_codes: tuple[str, ...] = (),
        additional_data: Any = None,
        external_status: ExternalOrderStatus | None = None,
        status_reason: str | None = None,
        conn: asyncpg.Connection | None = None,
    ) -> Order | None:
        row = await (conn or self._pool).fetchrow(
            f"UPDATE {_TABLE} SET "
            f"shop_access_key = $2, "
            f"status_reason = $3, "
            f"amount = $4, "
            f"pubg_id = $5, "
            f"codes = $6, "
            f"unused_codes = $7, "
            f"broken_codes = $8, "
            f"redeemed_codes = $9, "
            f"additional_data = $10, "
            f"external_status = $11, "
            f"updated_at = NOW() "
            f"WHERE id = $1 "
            f"RETURNING {_SELECT_COLUMNS}",
            order_id,
            shop_access_key,
            status_reason,
            amount,
            pubg_id,
            _dump_json(codes),
            _dump_json(unused_codes),
            list(broken_codes),
            list(redeemed_codes),
            _dump_json(additional_data),
            external_status,
        )
        if row is None:
            return None
        return Order.from_row(row)

    async def list_due_for_fanout(self, *, stale_after_seconds: int, limit: int) -> list[Order]:
        rows = await self._pool.fetch(
            f"SELECT {_SELECT_COLUMNS} FROM {_TABLE} o "
            f"WHERE o.status IN ({_ACTIVE_FANOUT_STATUS_SQL}) "
            f"AND NOT EXISTS ("
            f"  SELECT 1 FROM order_offers oo "
            f"  WHERE oo.order_id = o.id "
            f"  AND oo.status = $1::order_offer_status "
            f"  AND oo.offered_at + $2::interval > NOW()"
            f") "
            f"ORDER BY o.created_at ASC "
            f"LIMIT $3",
            OrderOfferStatus.OFFERED.value,
            timedelta(seconds=stale_after_seconds),
            limit,
        )
        return [Order.from_row(row) for row in rows]

    async def mark_offering(self, *, order_id: int) -> None:
        await self._pool.execute(
            f"UPDATE {_TABLE} SET "
            f"status = $2, "
            f"offered_at = COALESCE(offered_at, NOW()), "
            f"updated_at = NOW() "
            f"WHERE id = $1",
            order_id,
            OrderStatus.OFFERING.value,
        )

    async def mark_no_takers(self, *, order_id: int) -> None:
        await self._pool.execute(
            f"UPDATE {_TABLE} SET "
            f"status = $2, "
            f"closed_at = NOW(), "
            f"updated_at = NOW() "
            f"WHERE id = $1",
            order_id,
            OrderStatus.NO_TAKERS.value,
        )

    async def mark_cancelled(
        self,
        *,
        order_id: int,
        conn: asyncpg.Connection | None = None,
    ) -> None:
        await (conn or self._pool).execute(
            f"UPDATE {_TABLE} SET "
            f"status = $2, "
            f"closed_at = NOW(), "
            f"updated_at = NOW() "
            f"WHERE id = $1",
            order_id,
            OrderStatus.CANCELLED.value,
        )

    async def get(
        self,
        *,
        order_id: int,
        conn: asyncpg.Connection | None = None,
    ) -> Order | None:
        row = await (conn or self._pool).fetchrow(
            f"SELECT {_SELECT_COLUMNS} FROM {_TABLE} WHERE id = $1",
            order_id,
        )
        if row is None:
            return None
        return Order.from_row(row)

    async def taken_counts_by_user(self) -> dict[int, int]:
        rows = await self._pool.fetch(
            f"SELECT taken_by, count(*) AS cnt FROM {_TABLE} "
            f"WHERE status = $1::order_status AND taken_by IS NOT NULL "
            f"GROUP BY taken_by",
            OrderStatus.TAKEN.value,
        )
        return {row["taken_by"]: row["cnt"] for row in rows}

    async def count_in_work(
        self,
        *,
        user_id: int,
        conn: asyncpg.Connection | None = None,
    ) -> int:
        return await (conn or self._pool).fetchval(
            f"SELECT count(*) FROM {_TABLE} WHERE taken_by = $1 AND status = $2::order_status",
            user_id,
            OrderStatus.TAKEN.value,
        )

    async def claim_for_take(
        self,
        *,
        order_id: int,
        user_id: int,
        taken_price: Decimal,
        conn: asyncpg.Connection | None = None,
    ) -> Order | None:
        row = await (conn or self._pool).fetchrow(
            f"UPDATE {_TABLE} SET "
            f"status = $3, "
            f"taken_by = $2, "
            f"taken_at = NOW(), "
            f"taken_price = $4, "
            f"updated_at = NOW() "
            f"WHERE id = $1 AND status = ANY($5::order_status[]) "
            f"RETURNING {_SELECT_COLUMNS}",
            order_id,
            user_id,
            OrderStatus.TAKEN.value,
            taken_price,
            list(_ACTIVE_FANOUT_STATUSES),
        )
        if row is None:
            return None
        return Order.from_row(row)

    async def complete(
        self,
        *,
        order_id: int,
        user_id: int,
        conn: asyncpg.Connection | None = None,
    ) -> Order | None:
        return await self._resolve(
            order_id=order_id,
            user_id=user_id,
            status=OrderStatus.COMPLETED,
            conn=conn,
        )

    async def cancel(
        self,
        *,
        order_id: int,
        user_id: int,
        conn: asyncpg.Connection | None = None,
    ) -> Order | None:
        return await self._resolve(
            order_id=order_id,
            user_id=user_id,
            status=OrderStatus.CANCELLED,
            conn=conn,
        )

    async def time_out(
        self,
        *,
        order_id: int,
        user_id: int,
        conn: asyncpg.Connection | None = None,
    ) -> Order | None:
        return await self._resolve(
            order_id=order_id,
            user_id=user_id,
            status=OrderStatus.TIMED_OUT,
            conn=conn,
        )

    async def _resolve(
        self,
        *,
        order_id: int,
        user_id: int,
        status: OrderStatus,
        conn: asyncpg.Connection | None = None,
    ) -> Order | None:
        row = await (conn or self._pool).fetchrow(
            f"UPDATE {_TABLE} SET "
            f"status = $3, "
            f"closed_at = NOW(), "
            f"updated_at = NOW() "
            f"WHERE id = $1 AND taken_by = $2 AND status = $4::order_status "
            f"RETURNING {_SELECT_COLUMNS}",
            order_id,
            user_id,
            status.value,
            OrderStatus.TAKEN.value,
        )
        if row is None:
            return None
        return Order.from_row(row)
