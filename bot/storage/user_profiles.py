from dataclasses import dataclass

import asyncpg

_TABLE = "user_profiles"


@dataclass(frozen=True, slots=True)
class UserProfile:
    user_id: int
    name: str
    language: str | None


class UserProfileRepository:
    def __init__(self, *, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def set_name(self, *, user_id: int, name: str) -> None:
        await self._pool.execute(
            f"INSERT INTO {_TABLE} (user_id, name) VALUES ($1, $2) "
            f"ON CONFLICT (user_id) DO UPDATE "
            "SET name = EXCLUDED.name, updated_at = NOW()",
            user_id,
            name,
        )

    async def set_language(
        self,
        *,
        user_id: int,
        language: str,
    ) -> UserProfile:
        row = await self._pool.fetchrow(
            f"UPDATE {_TABLE} "
            "SET language = $2, updated_at = NOW() "
            "WHERE user_id = $1 "
            "RETURNING user_id, name, language",
            user_id,
            language,
        )
        if row is None:
            msg = f"no {_TABLE} row for user_id={user_id}"
            raise LookupError(msg)
        return UserProfile(
            user_id=row["user_id"],
            name=row["name"],
            language=row["language"],
        )

    async def delete(self, *, user_id: int) -> None:
        await self._pool.execute(
            f"DELETE FROM {_TABLE} WHERE user_id = $1",
            user_id,
        )

    async def get(self, *, user_id: int) -> UserProfile | None:
        row = await self._pool.fetchrow(
            f"SELECT user_id, name, language FROM {_TABLE} WHERE user_id = $1",
            user_id,
        )
        if row is None:
            return None
        return UserProfile(
            user_id=row["user_id"],
            name=row["name"],
            language=row["language"],
        )
