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
    "user_id, works_alone, packages, price_60, withdrawal_method, "
    "work_start, work_end, is_online, with_codes, status, balance"
)

# LATERAL lets each subquery see the outer p.user_id and run once per candidate,
# so speed averages this user's own last 3 completed orders without an N+1.
_CANDIDATE_STATS_JOINS = """
LEFT JOIN LATERAL (
    SELECT extract(epoch FROM avg(o.closed_at - o.taken_at))::int AS speed_seconds
    FROM (
        SELECT closed_at, taken_at FROM orders
        WHERE taken_by = p.user_id AND status = 'completed'
        ORDER BY closed_at DESC LIMIT 3
    ) o
) spd ON true
LEFT JOIN LATERAL (
    SELECT count(*) FILTER (WHERE status = 'completed') AS completed,
           count(*) FILTER (WHERE status = 'cancelled') AS cancelled
    FROM orders WHERE taken_by = p.user_id
) cnt ON true
LEFT JOIN LATERAL (
    SELECT count(*) AS not_picked
    FROM order_offers oo JOIN orders o ON o.id = oo.order_id
    WHERE oo.user_id = p.user_id
      AND o.status NOT IN ('pending', 'offering')
      AND (o.taken_by IS NULL OR o.taken_by <> p.user_id)
) np ON true
"""


@dataclass(frozen=True, slots=True)
class UserProfile:
    user_id: int
    works_alone: bool | None
    packages: tuple[int, ...] | None
    price_60: int | None
    withdrawal_method: str | None
    work_start: time | None
    work_end: time | None
    is_online: bool
    with_codes: bool
    status: UserProfileStatus
    balance: int

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> "UserProfile":
        packages = row["packages"]
        return cls(
            user_id=row["user_id"],
            works_alone=row["works_alone"],
            packages=tuple(packages) if packages is not None else None,
            price_60=row["price_60"],
            withdrawal_method=row["withdrawal_method"],
            work_start=row["work_start"],
            work_end=row["work_end"],
            is_online=row["is_online"],
            with_codes=row["with_codes"],
            status=UserProfileStatus(row["status"]),
            balance=row["balance"],
        )


def selected_packages(profile: UserProfile | None) -> set[int]:
    if profile is None or profile.packages is None:
        return set()
    return set(profile.packages)


@dataclass(frozen=True, slots=True)
class CandidateRow:
    user_id: int
    price_60: int
    speed_seconds: int | None
    completed: int
    cancelled: int
    not_picked: int


@dataclass(frozen=True, slots=True)
class RankingStats:
    speed_seconds: int | None
    completed: int
    cancelled: int
    not_picked: int


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

    async def create_or_update(  # noqa: PLR0913
        self,
        *,
        user_id: int,
        works_alone: bool,
        packages: Sequence[int],
        price_60: int,
        withdrawal_method: str,
        work_start: time,
        work_end: time,
    ) -> UserProfile:
        row = await self._pool.fetchrow(
            f"INSERT INTO {_TABLE} "
            f"(user_id, works_alone, packages, price_60, withdrawal_method, "
            f"work_start, work_end) "
            f"VALUES ($1, $2, $3, $4, $5, $6, $7) "
            f"ON CONFLICT (user_id) DO UPDATE SET "
            f"works_alone = EXCLUDED.works_alone, "
            f"packages = EXCLUDED.packages, "
            f"price_60 = EXCLUDED.price_60, "
            f"withdrawal_method = EXCLUDED.withdrawal_method, "
            f"work_start = EXCLUDED.work_start, "
            f"work_end = EXCLUDED.work_end, "
            f"updated_at = NOW() "
            f"RETURNING {_SELECT_COLUMNS}",
            user_id,
            works_alone,
            list(packages),
            price_60,
            withdrawal_method,
            work_start,
            work_end,
        )
        if row is None:
            msg = f"failed to upsert {_TABLE} row for user_id={user_id}"
            raise LookupError(msg)
        return UserProfile.from_row(row)

    async def toggle_is_online_and_get(self, *, user_id: int) -> UserProfile:
        row = await self._pool.fetchrow(
            f"UPDATE {_TABLE} SET is_online = NOT is_online, updated_at = NOW() "
            f"WHERE user_id = $1 RETURNING {_SELECT_COLUMNS}",
            user_id,
        )
        if row is None:
            msg = f"no {_TABLE} row to toggle for user_id={user_id}"
            raise LookupError(msg)
        return UserProfile.from_row(row)

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
        return UserProfile.from_row(row)

    async def credit_balance(
        self,
        *,
        user_id: int,
        amount: int,
        conn: asyncpg.Connection | None = None,
    ) -> None:
        await (conn or self._pool).execute(
            f"UPDATE {_TABLE} SET balance = balance + $2, updated_at = NOW() "
            f"WHERE user_id = $1",
            user_id,
            amount,
        )

    async def list_online_with_packages(
        self,
        *,
        required_packages: Sequence[int],
    ) -> list[CandidateRow]:
        rows = await self._pool.fetch(
            "SELECT p.user_id, p.price_60, spd.speed_seconds, "
            "cnt.completed, cnt.cancelled, np.not_picked "
            f"FROM {_TABLE} p "
            f"{_CANDIDATE_STATS_JOINS} "
            "WHERE p.is_online = TRUE "
            "AND p.status = $1 "
            "AND p.price_60 IS NOT NULL "
            "AND p.packages @> $2::INTEGER[] "
            "ORDER BY p.price_60 ASC, p.user_id ASC",
            UserProfileStatus.ACTIVE.value,
            list(required_packages),
        )
        return [
            CandidateRow(
                user_id=row["user_id"],
                price_60=row["price_60"],
                speed_seconds=row["speed_seconds"],
                completed=row["completed"],
                cancelled=row["cancelled"],
                not_picked=row["not_picked"],
            )
            for row in rows
        ]

    async def ranking_stats(self, *, user_id: int) -> RankingStats:
        row = await self._pool.fetchrow(
            "SELECT "
            "(SELECT extract(epoch FROM avg(o.closed_at - o.taken_at))::int "
            " FROM (SELECT closed_at, taken_at FROM orders "
            "       WHERE taken_by = $1 AND status = 'completed' "
            "       ORDER BY closed_at DESC LIMIT 3) o) AS speed_seconds, "
            "(SELECT count(*) FROM orders "
            " WHERE taken_by = $1 AND status = 'completed') AS completed, "
            "(SELECT count(*) FROM orders "
            " WHERE taken_by = $1 AND status = 'cancelled') AS cancelled, "
            "(SELECT count(*) FROM order_offers oo JOIN orders o ON o.id = oo.order_id "
            " WHERE oo.user_id = $1 AND o.status NOT IN ('pending', 'offering') "
            "   AND (o.taken_by IS NULL OR o.taken_by <> $1)) AS not_picked",
            user_id,
        )
        return RankingStats(
            speed_seconds=row["speed_seconds"],
            completed=row["completed"],
            cancelled=row["cancelled"],
            not_picked=row["not_picked"],
        )
