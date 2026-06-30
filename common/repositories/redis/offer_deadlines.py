import json
from collections.abc import Sequence
from dataclasses import dataclass

from redis.asyncio import Redis

_KEY = "orders:offer_deadlines"

# Atomically take every member whose deadline (score) is due and remove it, so a
# deadline is handed to exactly one timekeeper poll even with concurrent pollers.
_CLAIM_DUE = """
local due = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, ARGV[2])
if #due > 0 then
    redis.call('ZREM', KEYS[1], unpack(due))
end
return due
"""


@dataclass(frozen=True, slots=True)
class OfferDeadline:
    order_id: int
    user_id: int
    chat_id: int
    message_id: int
    expired_text: str


class OfferDeadlineQueue:
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis
        self._claim_due = redis.register_script(_CLAIM_DUE)

    async def schedule(
        self,
        *,
        order_id: int,
        user_id: int,
        chat_id: int,
        message_id: int,
        expired_text: str,
        deadline_ts: float,
    ) -> None:
        member = json.dumps(
            {
                "order_id": order_id,
                "user_id": user_id,
                "chat_id": chat_id,
                "message_id": message_id,
                "expired_text": expired_text,
            },
        )
        await self._redis.zadd(_KEY, {member: deadline_ts})

    async def claim_due(self, *, now_ts: float, limit: int) -> list[OfferDeadline]:
        members: Sequence[str] = await self._claim_due(keys=[_KEY], args=[now_ts, limit])
        return [OfferDeadline(**json.loads(member)) for member in members]
