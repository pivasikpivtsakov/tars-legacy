from collections.abc import Collection, Mapping
from datetime import time

import asyncpg

from common.models.user_profiles import UserProfile, UserProfileStatus

_TABLE = "user_profiles"

_SELECT_COLUMNS = (
    "id, tg_id, works_alone, prices, withdrawal_method, "
    "work_start, work_end, is_online, with_codes, status, balance"
)

_MODERATION_RESET = "status = 'inactive', is_online = FALSE"


class UserProfileRepository:
    def __init__(self, *, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def _update_field(
        self,
        *,
        profile_id: int,
        column: str,
        value: object,
        reset_moderation: bool = False,
    ) -> UserProfile:
        extra = f", {_MODERATION_RESET}" if reset_moderation else ""
        row = await self._pool.fetchrow(
            f"UPDATE {_TABLE} SET {column} = $2{extra}, updated_at = NOW() "
            f"WHERE id = $1 RETURNING {_SELECT_COLUMNS}",
            profile_id,
            value,
        )
        if row is None:
            msg = f"failed to update {column} for {_TABLE} id={profile_id}"
            raise LookupError(msg)
        return UserProfile.from_row(row)

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

    async def deactivate(self, *, profile_id: int) -> UserProfile:
        row = await self._pool.fetchrow(
            f"UPDATE {_TABLE} SET {_MODERATION_RESET}, updated_at = NOW() "
            f"WHERE id = $1 RETURNING {_SELECT_COLUMNS}",
            profile_id,
        )
        if row is None:
            msg = f"no {_TABLE} row to deactivate for id={profile_id}"
            raise LookupError(msg)
        return UserProfile.from_row(row)

    async def approve(self, *, profile_id: int, with_codes: bool) -> UserProfile:
        row = await self._pool.fetchrow(
            f"UPDATE {_TABLE} SET status = $2, with_codes = $3, updated_at = NOW() "
            f"WHERE id = $1 RETURNING {_SELECT_COLUMNS}",
            profile_id,
            UserProfileStatus.ACTIVE.value,
            with_codes,
        )
        if row is None:
            msg = f"no {_TABLE} row to approve for id={profile_id}"
            raise LookupError(msg)
        return UserProfile.from_row(row)

    async def set_prices(
        self,
        *,
        profile_id: int,
        prices: Mapping[int, int],
    ) -> UserProfile:
        return await self._update_field(
            profile_id=profile_id,
            column="prices",
            value=dict(prices),
        )

    async def create_or_update(
        self,
        *,
        tg_id: int,
        works_alone: bool,
        with_codes: bool,
        prices: Mapping[int, int],
        withdrawal_method: str,
        work_start: time,
        work_end: time,
    ) -> UserProfile:
        row = await self._pool.fetchrow(
            f"INSERT INTO {_TABLE} "
            f"(tg_id, works_alone, with_codes, prices, "
            f"withdrawal_method, work_start, work_end) "
            f"VALUES ($1, $2, $3, $4, $5, $6, $7) "
            f"ON CONFLICT (tg_id) DO UPDATE SET "
            f"works_alone = EXCLUDED.works_alone, "
            f"with_codes = EXCLUDED.with_codes, "
            f"prices = EXCLUDED.prices, "
            f"withdrawal_method = EXCLUDED.withdrawal_method, "
            f"work_start = EXCLUDED.work_start, "
            f"work_end = EXCLUDED.work_end, "
            f"{_MODERATION_RESET}, "
            f"updated_at = NOW() "
            f"RETURNING {_SELECT_COLUMNS}",
            tg_id,
            works_alone,
            with_codes,
            dict(prices),
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

    async def get_by_id(self, *, profile_id: int) -> UserProfile | None:
        row = await self._pool.fetchrow(
            f"SELECT {_SELECT_COLUMNS} FROM {_TABLE} WHERE id = $1",
            profile_id,
        )
        if row is None:
            return None
        return UserProfile.from_row(row)

    async def get_tg_id(self, *, profile_id: int) -> int | None:
        return await self._pool.fetchval(
            f"SELECT tg_id FROM {_TABLE} WHERE id = $1",
            profile_id,
        )

    async def get_tg_ids(self, *, profile_ids: Collection[int]) -> dict[int, int]:
        if not profile_ids:
            return {}
        rows = await self._pool.fetch(
            f"SELECT id, tg_id FROM {_TABLE} WHERE id = ANY($1)",
            list(profile_ids),
        )
        return {row["id"]: row["tg_id"] for row in rows}

    async def all_tg_ids(self) -> list[int]:
        rows = await self._pool.fetch(f"SELECT tg_id FROM {_TABLE}")
        return [row["tg_id"] for row in rows]

    async def lock_is_online(self, *, profile_id: int, conn: asyncpg.Connection) -> bool | None:
        return await conn.fetchval(
            f"SELECT is_online FROM {_TABLE} WHERE id = $1 FOR UPDATE",
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
            f"UPDATE {_TABLE} SET balance = balance + $2, updated_at = NOW() WHERE id = $1",
            profile_id,
            amount,
        )

    async def list_rankable(self) -> list[UserProfile]:
        rows = await self._pool.fetch(
            f"SELECT {_SELECT_COLUMNS} FROM {_TABLE} "
            "WHERE is_online = TRUE "
            "AND status = $1 "
            "AND prices IS NOT NULL "
            "AND prices <> '{}'::jsonb",
            UserProfileStatus.ACTIVE.value,
        )
        return [UserProfile.from_row(row) for row in rows]

    async def go_everyone_full_offline(self) -> None:
        await self._pool.execute(f"UPDATE {_TABLE} SET is_online = FALSE, updated_at = NOW() ")
