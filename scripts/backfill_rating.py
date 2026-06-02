import asyncio
import logging
from datetime import datetime

import asyncpg

from common.db import create_pool
from common.environment import RATING_SPEED_WINDOW
from common.logging_config import setup_logging
from common.redis import create_redis
from common.repositories.rating import RatingRepository

logger = logging.getLogger(__name__)


async def _load_counts(pool: asyncpg.Pool) -> dict[int, dict[str, int]]:
    counts: dict[int, dict[str, int]] = {}
    resolved = await pool.fetch(
        "SELECT taken_by AS user_id, "
        "count(*) FILTER (WHERE status = 'completed') AS complete, "
        "count(*) FILTER (WHERE status = 'cancelled') AS incomplete "
        "FROM orders WHERE taken_by IS NOT NULL GROUP BY taken_by",
    )
    for row in resolved:
        counts[row["user_id"]] = {
            "complete": row["complete"],
            "incomplete": row["incomplete"],
            "not_taken": 0,
        }
    not_taken = await pool.fetch(
        "SELECT oo.user_id AS user_id, count(*) AS not_taken "
        "FROM order_offers oo JOIN orders o ON o.id = oo.order_id "
        "WHERE o.status NOT IN ('pending', 'offering') "
        "AND (o.taken_by IS NULL OR o.taken_by <> oo.user_id) "
        "GROUP BY oo.user_id",
    )
    for row in not_taken:
        user = counts.setdefault(
            row["user_id"],
            {"complete": 0, "incomplete": 0, "not_taken": 0},
        )
        user["not_taken"] = row["not_taken"]
    return counts


async def _load_speed_samples(
    pool: asyncpg.Pool,
    *,
    window: int,
) -> dict[int, list[tuple[datetime, datetime]]]:
    rows = await pool.fetch(
        "SELECT user_id, taken_at, closed_at FROM ("
        "  SELECT taken_by AS user_id, taken_at, closed_at, "
        "         row_number() OVER ("
        "             PARTITION BY taken_by ORDER BY closed_at DESC"
        "         ) AS rn "
        "  FROM orders WHERE status = 'completed' AND taken_by IS NOT NULL"
        ") ranked WHERE rn <= $1 ORDER BY user_id, closed_at DESC",
        window,
    )
    samples: dict[int, list[tuple[datetime, datetime]]] = {}
    for row in rows:
        if row["taken_at"] is None or row["closed_at"] is None:
            continue
        samples.setdefault(row["user_id"], []).append(
            (row["taken_at"], row["closed_at"]),
        )
    return samples


async def main() -> None:
    setup_logging()
    async with create_pool() as pool:
        redis = create_redis()
        rating = RatingRepository(redis=redis, speed_window=RATING_SPEED_WINDOW)
        try:
            counts = await _load_counts(pool)
            samples = await _load_speed_samples(pool, window=RATING_SPEED_WINDOW)
            user_ids = set(counts) | set(samples)
            for user_id in user_ids:
                user_counts = counts.get(
                    user_id,
                    {"complete": 0, "incomplete": 0, "not_taken": 0},
                )
                await rating.replace_user_stats(
                    user_id=user_id,
                    complete=user_counts["complete"],
                    incomplete=user_counts["incomplete"],
                    not_taken=user_counts["not_taken"],
                    speed_samples=samples.get(user_id, []),
                )
            logger.info("rating backfill complete users=%d", len(user_ids))
        finally:
            await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
