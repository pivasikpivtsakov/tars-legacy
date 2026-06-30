from collections import defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal

import asyncpg

from common.models.transactions import Transaction, TransactionGroup, TransactionKind

_TABLE = "transactions"

_SELECT_COLUMNS = "id, profile_id, order_id, kind, pack_size, code, amount, created_at"


class TransactionsRepository:
    def __init__(self, *, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def record_pack_credit(
        self,
        *,
        profile_id: int,
        order_id: int,
        lines: Mapping[int, Decimal],
        conn: asyncpg.Connection | None = None,
    ) -> None:
        if not lines:
            return
        sizes = list(lines.keys())
        amounts = [lines[size] for size in sizes]
        await (conn or self._pool).execute(
            f"INSERT INTO {_TABLE} (profile_id, order_id, kind, pack_size, amount) "
            f"SELECT $1, $2, $3::transaction_kind, size, amount "
            f"FROM unnest($4::int[], $5::numeric[]) AS line(size, amount)",
            profile_id,
            order_id,
            TransactionKind.PACK.value,
            sizes,
            amounts,
        )

    async def record_code_credit(
        self,
        *,
        profile_id: int,
        order_id: int,
        codes: Mapping[str, int],
        conn: asyncpg.Connection | None = None,
    ) -> None:
        if not codes:
            return
        code_values = list(codes.keys())
        amounts = [Decimal(codes[code]) for code in code_values]
        await (conn or self._pool).execute(
            f"INSERT INTO {_TABLE} (profile_id, order_id, kind, code, amount) "
            f"SELECT $1, $2, $3::transaction_kind, code, amount "
            f"FROM unnest($4::text[], $5::numeric[]) AS line(code, amount)",
            profile_id,
            order_id,
            TransactionKind.CODE.value,
            code_values,
            amounts,
        )

    async def balance_of(self, *, profile_id: int) -> Decimal:
        return await self._pool.fetchval(
            f"SELECT COALESCE(SUM(amount), 0) FROM {_TABLE} WHERE profile_id = $1",
            profile_id,
        )

    async def balances_of(self, *, profile_ids: Sequence[int]) -> dict[int, Decimal]:
        if not profile_ids:
            return {}
        rows = await self._pool.fetch(
            f"SELECT profile_id, COALESCE(SUM(amount), 0) AS balance FROM {_TABLE} "
            f"WHERE profile_id = ANY($1) GROUP BY profile_id",
            list(profile_ids),
        )
        return {row["profile_id"]: row["balance"] for row in rows}

    async def history(
        self,
        *,
        profile_id: int,
        limit: int,
        offset: int,
    ) -> tuple[list[TransactionGroup], bool]:
        order_rows = await self._pool.fetch(
            f"SELECT order_id, MAX(created_at) AS last_at FROM {_TABLE} "
            f"WHERE profile_id = $1 "
            f"GROUP BY order_id "
            f"ORDER BY last_at DESC, order_id DESC "
            f"LIMIT $2 OFFSET $3",
            profile_id,
            limit + 1,
            offset,
        )
        has_next = len(order_rows) > limit
        order_ids = [row["order_id"] for row in order_rows[:limit]]
        if not order_ids:
            return [], has_next
        line_rows = await self._pool.fetch(
            f"SELECT {_SELECT_COLUMNS} FROM {_TABLE} "
            f"WHERE profile_id = $1 AND order_id = ANY($2) "
            f"ORDER BY created_at ASC, id ASC",
            profile_id,
            order_ids,
        )
        grouped: dict[int, list[Transaction]] = defaultdict(list)
        for row in line_rows:
            transaction = Transaction.from_row(row)
            grouped[transaction.order_id].append(transaction)
        groups = [TransactionGroup.from_transactions(grouped[order_id]) for order_id in order_ids]
        return groups, has_next
