from collections.abc import Sequence
from dataclasses import dataclass
from datetime import time
from enum import StrEnum

import asyncpg

_TABLE = "user_profiles"


class UserProfileStatus(StrEnum):
    INACTIVE = "inactive"
    ACTIVE = "active"
    BANNED = "banned"


_SELECT_COLUMNS = (
    "user_id, works_alone, packages, withdrawal_method, "
    "work_start, work_end, with_codes, status"
)


@dataclass(frozen=True, slots=True)
class UserProfile:
    user_id: int
    works_alone: bool | None
    packages: tuple[int, ...] | None
    withdrawal_method: str | None
    work_start: time | None
    work_end: time | None
    with_codes: bool
    status: UserProfileStatus


def _row_to_profile(row: asyncpg.Record) -> UserProfile:
    packages = row["packages"]
    return UserProfile(
        user_id=row["user_id"],
        works_alone=row["works_alone"],
        packages=tuple(packages) if packages is not None else None,
        withdrawal_method=row["withdrawal_method"],
        work_start=row["work_start"],
        work_end=row["work_end"],
        with_codes=row["with_codes"],
        status=UserProfileStatus(row["status"]),
    )


class UserProfileRepository:
    def __init__(self, *, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def _upsert_field(
        self,
        *,
        user_id: int,
        column: str,
        value: object,
    ) -> None:
        await self._pool.execute(
            f"INSERT INTO {_TABLE} (user_id, {column}) VALUES ($1, $2) "
            f"ON CONFLICT (user_id) DO UPDATE "
            f"SET {column} = EXCLUDED.{column}, updated_at = NOW()",
            user_id,
            value,
        )

    async def set_works_alone(self, *, user_id: int, works_alone: bool) -> None:
        await self._upsert_field(
            user_id=user_id,
            column="works_alone",
            value=works_alone,
        )

    async def set_packages(
        self,
        *,
        user_id: int,
        packages: Sequence[int],
    ) -> None:
        await self._upsert_field(
            user_id=user_id,
            column="packages",
            value=list(packages),
        )

    async def set_withdrawal_method(
        self,
        *,
        user_id: int,
        withdrawal_method: str,
    ) -> None:
        await self._upsert_field(
            user_id=user_id,
            column="withdrawal_method",
            value=withdrawal_method,
        )

    async def set_work_start(self, *, user_id: int, work_start: time) -> None:
        await self._upsert_field(
            user_id=user_id,
            column="work_start",
            value=work_start,
        )

    async def set_status(
        self,
        *,
        user_id: int,
        status: UserProfileStatus,
    ) -> None:
        await self._upsert_field(
            user_id=user_id,
            column="status",
            value=status.value,
        )

    async def set_work_end_and_get(
        self,
        *,
        user_id: int,
        work_end: time,
    ) -> UserProfile:
        row = await self._pool.fetchrow(
            f"INSERT INTO {_TABLE} (user_id, work_end) VALUES ($1, $2) "
            f"ON CONFLICT (user_id) DO UPDATE "
            f"SET work_end = EXCLUDED.work_end, updated_at = NOW() "
            f"RETURNING {_SELECT_COLUMNS}",
            user_id,
            work_end,
        )
        if row is None:
            msg = f"failed to upsert {_TABLE} row for user_id={user_id}"
            raise LookupError(msg)
        return _row_to_profile(row)

    async def delete(self, *, user_id: int) -> None:
        await self._pool.execute(
            f"DELETE FROM {_TABLE} WHERE user_id = $1",
            user_id,
        )

    async def get(self, *, user_id: int) -> UserProfile | None:
        row = await self._pool.fetchrow(
            f"SELECT {_SELECT_COLUMNS} FROM {_TABLE} WHERE user_id = $1",
            user_id,
        )
        if row is None:
            return None
        return _row_to_profile(row)
