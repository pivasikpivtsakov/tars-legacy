from collections.abc import Mapping
from typing import Any

import asyncpg
from aiogram.exceptions import DataNotDictLikeError
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import (
    BaseStorage,
    DefaultKeyBuilder,
    KeyBuilder,
    StateType,
    StorageKey,
)

_TABLE = "aiogram_fsm"


class PostgresStorage(BaseStorage):
    """FSM storage backed by a single Postgres table (see migrations/001_aiogram_fsm.sql).

    The pool is owned by the caller; :meth:`close` is intentionally a no-op so the
    pool can be reused for other application data.
    """

    def __init__(
        self,
        *,
        pool: asyncpg.Pool,
        key_builder: KeyBuilder | None = None,
    ) -> None:
        self._pool = pool
        self._key_builder = key_builder or DefaultKeyBuilder()

    async def close(self) -> None:
        return None

    def resolve_state(self, value: StateType) -> str | None:
        if value is None:
            return None
        if isinstance(value, State):
            return value.state
        return str(value)

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        record_key = self._key_builder.build(key)
        resolved = self.resolve_state(state)
        if resolved is None:
            row = await self._pool.fetchrow(
                f"UPDATE {_TABLE} SET state = NULL, updated_at = NOW() "
                "WHERE key = $1 RETURNING data",
                record_key,
            )
            if row is not None and not row["data"]:
                await self._pool.execute(
                    f"DELETE FROM {_TABLE} WHERE key = $1",
                    record_key,
                )
            return

        await self._pool.execute(
            f"INSERT INTO {_TABLE} (key, state) VALUES ($1, $2) "
            f"ON CONFLICT (key) DO UPDATE "
            "SET state = EXCLUDED.state, updated_at = NOW()",
            record_key,
            resolved,
        )

    async def get_state(self, key: StorageKey) -> str | None:
        record_key = self._key_builder.build(key)
        row = await self._pool.fetchrow(
            f"SELECT state FROM {_TABLE} WHERE key = $1",
            record_key,
        )
        if row is None:
            return None
        return row["state"]

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        if not isinstance(data, dict):
            msg = f"Data must be a dict or dict-like object, got {type(data).__name__}"
            raise DataNotDictLikeError(msg)

        record_key = self._key_builder.build(key)
        if not data:
            row = await self._pool.fetchrow(
                f"UPDATE {_TABLE} SET data = '{{}}'::jsonb, updated_at = NOW() "
                "WHERE key = $1 RETURNING state",
                record_key,
            )
            if row is not None and row["state"] is None:
                await self._pool.execute(
                    f"DELETE FROM {_TABLE} WHERE key = $1",
                    record_key,
                )
            return

        await self._pool.execute(
            f"INSERT INTO {_TABLE} (key, data) VALUES ($1, $2) "
            f"ON CONFLICT (key) DO UPDATE "
            "SET data = EXCLUDED.data, updated_at = NOW()",
            record_key,
            dict(data),
        )

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        record_key = self._key_builder.build(key)
        row = await self._pool.fetchrow(
            f"SELECT data FROM {_TABLE} WHERE key = $1",
            record_key,
        )
        if row is None:
            return {}
        return dict(row["data"])

    async def update_data(
        self,
        key: StorageKey,
        data: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not data:
            return await self.get_data(key)

        record_key = self._key_builder.build(key)
        row = await self._pool.fetchrow(
            f"INSERT INTO {_TABLE} (key, data) VALUES ($1, $2) "
            f"ON CONFLICT (key) DO UPDATE "
            f"SET data = {_TABLE}.data || EXCLUDED.data, updated_at = NOW() "
            "RETURNING data",
            record_key,
            dict(data),
        )
        return dict(row["data"])
