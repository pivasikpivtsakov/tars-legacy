import json

import asyncpg

from common.environment import (
    RDS_DB_NAME,
    RDS_HOSTNAME,
    RDS_PASSWORD,
    RDS_PORT,
    RDS_USERNAME,
)


async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


def create_pool() -> asyncpg.Pool:
    assert RDS_HOSTNAME and RDS_USERNAME and RDS_PASSWORD and RDS_DB_NAME and RDS_PORT
    return asyncpg.create_pool(
        host=RDS_HOSTNAME,
        port=int(RDS_PORT),
        user=RDS_USERNAME,
        password=RDS_PASSWORD,
        database=RDS_DB_NAME,
        init=_init_connection,
    )
