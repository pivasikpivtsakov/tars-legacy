from collections.abc import Sequence
from datetime import time

import asyncpg

from common.models.user_profiles import UserProfile, UserProfileStatus

_TABLE = "user_profiles"

_SELECT_COLUMNS = (
    "id, tg_id, works_alone, packages, price_60, withdrawal_method, "
    "work_start, work_end, is_online, with_codes, status, balance"
)


class UserProfileRepository:
    def __init__(self, *, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def _update_field(
        self,
        *,
        profile_id: int,
        column: str,
        value: object,
    ) -> UserProfile:
        row = await self._pool.fetchrow(
            f"UPDATE {_TABLE} SET {column} = $2, updated_at = NOW() "
            f"WHERE id = $1 RETURNING {_SELECT_COLUMNS}",
            profile_id,
            value,
        )
        if row is None:
            msg = f"failed to update {column} for {_TABLE} id={profile_id}"
            raise LookupError(msg)
        return UserProfile.from_row(row)

    async def set_packages(
        self,
        *,
        profile_id: int,
        packages: Sequence[int],
    ) -> UserProfile:
        return await self._update_field(
            profile_id=profile_id,
            column="packages",
            value=list(packages),
        )

    async def set_status(
        self,
        *,
        profile_id: int,
        status: UserProfileStatus,
    ) -> UserProfile:
        return await self._update_field(
            profile_id=profile_id,
            column="status",
            value=status.value,
        )

    async def create_or_update(
        self,
        *,
        tg_id: int,
        works_alone: bool,
        packages: Sequence[int],
        price_60: int,
        withdrawal_method: str,
        work_start: time,
        work_end: time,
    ) -> UserProfile:
        row = await self._pool.fetchrow(
            f"INSERT INTO {_TABLE} "
            f"(tg_id, works_alone, packages, price_60, withdrawal_method, "
            f"work_start, work_end) "
            f"VALUES ($1, $2, $3, $4, $5, $6, $7) "
            f"ON CONFLICT (tg_id) DO UPDATE SET "
            f"works_alone = EXCLUDED.works_alone, "
            f"packages = EXCLUDED.packages, "
            f"price_60 = EXCLUDED.price_60, "
            f"withdrawal_method = EXCLUDED.withdrawal_method, "
            f"work_start = EXCLUDED.work_start, "
            f"work_end = EXCLUDED.work_end, "
            f"updated_at = NOW() "
            f"RETURNING {_SELECT_COLUMNS}",
            tg_id,
            works_alone,
            list(packages),
            price_60,
            withdrawal_method,
            work_start,
            work_end,
        )
        if row is None:
            msg = f"failed to upsert {_TABLE} row for tg_id={tg_id}"
            raise LookupError(msg)
        return UserProfile.from_row(row)

    async def toggle_is_online_and_get(self, *, profile_id: int) -> UserProfile:
        row = await self._pool.fetchrow(
            f"UPDATE {_TABLE} SET is_online = NOT is_online, updated_at = NOW() "
            f"WHERE id = $1 RETURNING {_SELECT_COLUMNS}",
            profile_id,
        )
        if row is None:
            msg = f"no {_TABLE} row to toggle for id={profile_id}"
            raise LookupError(msg)
        return UserProfile.from_row(row)

    async def delete(self, *, profile_id: int) -> None:
        await self._pool.execute(
            f"DELETE FROM {_TABLE} WHERE id = $1",
            profile_id,
        )

    async def get_by_tg_id(self, *, tg_id: int) -> UserProfile | None:
        row = await self._pool.fetchrow(
            f"SELECT {_SELECT_COLUMNS} FROM {_TABLE} WHERE tg_id = $1",
            tg_id,
        )
        if row is None:
            return None
        return UserProfile.from_row(row)

    async def get_tg_id(self, *, profile_id: int) -> int | None:
        return await self._pool.fetchval(
            f"SELECT tg_id FROM {_TABLE} WHERE id = $1",
            profile_id,
        )

    async def credit_balance(
        self,
        *,
        profile_id: int,
        amount: int,
        conn: asyncpg.Connection | None = None,
    ) -> None:
        await (conn or self._pool).execute(
            f"UPDATE {_TABLE} SET balance = balance + $2, updated_at = NOW() "
            f"WHERE id = $1",
            profile_id,
            amount,
        )

    async def list_rankable(self) -> list[UserProfile]:
        rows = await self._pool.fetch(
            f"SELECT {_SELECT_COLUMNS} FROM {_TABLE} "
            "WHERE is_online = TRUE "
            "AND status = $1 "
            "AND price_60 IS NOT NULL "
            "AND packages IS NOT NULL "
            "AND cardinality(packages) > 0",
            UserProfileStatus.ACTIVE.value,
        )
        return [UserProfile.from_row(row) for row in rows]
