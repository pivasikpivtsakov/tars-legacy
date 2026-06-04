import asyncpg

from common.models.orders import Order, OrderStatus

_TABLE = "orders"

_ACTIVE_FANOUT_STATUSES: tuple[str, ...] = (
    OrderStatus.PENDING.value,
    OrderStatus.OFFERING.value,
)

_SELECT_COLUMNS = (
    "id, original_id, shop_access_key, status, status_reason, amount, pubg_id, "
    "codes, unused_codes, broken_codes, redeemed_codes, additional_data, "
    "offered_at, closed_at, taken_at, taken_by, taken_price, created_at, updated_at"
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

    async def list_active_for_fanout(self) -> list[Order]:
        rows = await self._pool.fetch(
            f"SELECT {_SELECT_COLUMNS} FROM {_TABLE} "
            f"WHERE status = ANY($1::order_status[]) "
            f"ORDER BY created_at ASC",
            list(_ACTIVE_FANOUT_STATUSES),
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
            f"SELECT count(*) FROM {_TABLE} "
            f"WHERE taken_by = $1 AND status = $2::order_status",
            user_id,
            OrderStatus.TAKEN.value,
        )

    async def claim_for_take(
        self,
        *,
        order_id: int,
        user_id: int,
        taken_price: int,
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
