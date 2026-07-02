import json
from collections.abc import Mapping, Sequence
from decimal import Decimal

import asyncpg

from common.models.transactions import Transaction, TransactionKind

_TABLE = "transactions"

_SELECT_COLUMNS = "id, profile_id, order_id, public_id, kind, amount, details, created_at"


class TransactionsRepository:
    def __init__(self, *, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def record_credit(
        self,
        *,
        profile_id: int,
        order_id: int,
        public_id: str,
        kind: TransactionKind,
        amount: Decimal,
        details: Mapping[str, int],
        conn: asyncpg.Connection | None = None,
    ) -> None:
        await (conn or self._pool).execute(
            f"INSERT INTO {_TABLE} (profile_id, order_id, public_id, kind, amount, details) "
            f"VALUES ($1, $2, $3, $4::transaction_kind, $5, $6)",
            profile_id,
            order_id,
            public_id,
            kind.value,
            amount,
            json.dumps(dict(details)),
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
    ) -> tuple[list[Transaction], bool]:
        rows = await self._pool.fetch(
            f"SELECT {_SELECT_COLUMNS} FROM {_TABLE} "
            f"WHERE profile_id = $1 "
            f"ORDER BY created_at DESC, id DESC "
            f"LIMIT $2 OFFSET $3",
            profile_id,
            limit + 1,
            offset,
        )
        has_next = len(rows) > limit
        return [Transaction.from_row(row) for row in rows[:limit]], has_next
