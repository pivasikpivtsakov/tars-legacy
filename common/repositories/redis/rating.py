from collections.abc import Mapping, Sequence
from datetime import datetime

from redis.asyncio import Redis

from common.models.rating import RatingStats


def _speed_key(user_id: int) -> str:
    return f"rating:{user_id}:speed"


def _stats_key(user_id: int) -> str:
    return f"rating:{user_id}:stats"


def _encode_speed(taken_at: datetime, closed_at: datetime) -> str:
    # remember not to pass in naive datetimes here
    return f"{int(taken_at.timestamp())}:{int(closed_at.timestamp())}"


def _avg_speed(entries: Sequence[str]) -> int | None:
    if not entries:
        return None
    total = 0
    for entry in entries:
        taken, closed = entry.split(":")
        total += int(closed) - int(taken)
    return total // len(entries)


def _parse_stats(values: Mapping[str, str]) -> tuple[int, int, int]:
    return (
        int(values.get("complete", 0)),
        int(values.get("incomplete", 0)),
        int(values.get("not_taken", 0)),
    )


class RatingRepository:
    def __init__(self, *, redis: Redis, speed_window: int) -> None:
        self._redis = redis
        self._speed_window = speed_window

    async def record_completion(
        self,
        *,
        user_id: int,
        taken_at: datetime,
        closed_at: datetime,
    ) -> None:
        pipe = self._redis.pipeline(transaction=True)
        pipe.lpush(_speed_key(user_id), _encode_speed(taken_at, closed_at))
        pipe.ltrim(_speed_key(user_id), 0, self._speed_window - 1)
        pipe.hincrby(_stats_key(user_id), "complete", 1)
        await pipe.execute()

    async def record_cancellation(self, *, user_id: int) -> None:
        await self._redis.hincrby(_stats_key(user_id), "incomplete", 1)

    async def record_not_taken(self, *, user_ids: Sequence[int]) -> None:
        if not user_ids:
            return
        pipe = self._redis.pipeline(transaction=False)
        for user_id in user_ids:
            pipe.hincrby(_stats_key(user_id), "not_taken", 1)
        await pipe.execute()

    async def replace_user_stats(
        self,
        *,
        user_id: int,
        complete: int,
        incomplete: int,
        not_taken: int,
        speed_samples: Sequence[tuple[datetime, datetime]],
    ) -> None:
        entries = [_encode_speed(taken_at, closed_at) for taken_at, closed_at in speed_samples][
            : self._speed_window
        ]
        pipe = self._redis.pipeline(transaction=True)
        pipe.delete(_stats_key(user_id))
        pipe.hset(
            _stats_key(user_id),
            mapping={
                "complete": complete,
                "incomplete": incomplete,
                "not_taken": not_taken,
            },
        )
        pipe.delete(_speed_key(user_id))
        if entries:
            pipe.rpush(_speed_key(user_id), *entries)
        await pipe.execute()

    async def get(self, *, user_id: int) -> RatingStats:
        pipe = self._redis.pipeline(transaction=False)
        pipe.lrange(_speed_key(user_id), 0, self._speed_window - 1)
        pipe.hgetall(_stats_key(user_id))
        entries, values = await pipe.execute()
        complete, incomplete, not_taken = _parse_stats(values)
        return RatingStats(
            speed_seconds=_avg_speed(entries),
            complete=complete,
            incomplete=incomplete,
            not_taken=not_taken,
        )

    async def get_many(
        self,
        *,
        user_ids: Sequence[int],
    ) -> dict[int, RatingStats]:
        if not user_ids:
            return {}
        pipe = self._redis.pipeline(transaction=False)
        for user_id in user_ids:
            pipe.lrange(_speed_key(user_id), 0, self._speed_window - 1)
            pipe.hgetall(_stats_key(user_id))
        results = await pipe.execute()
        stats_by_user: dict[int, RatingStats] = {}
        for index, user_id in enumerate(user_ids):
            entries = results[index * 2]
            complete, incomplete, not_taken = _parse_stats(results[index * 2 + 1])
            stats_by_user[user_id] = RatingStats(
                speed_seconds=_avg_speed(entries),
                complete=complete,
                incomplete=incomplete,
                not_taken=not_taken,
            )
        return stats_by_user
