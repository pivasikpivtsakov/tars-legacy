from dataclasses import dataclass

from redis.asyncio import Redis

_KEY_PREFIX = "orders:timeout_msgs:"
_FIELD_CHAT = "chat"
_FIELD_TAKEN = "taken"
_FIELD_TEXT = "text"
_RESERVED_FIELDS = frozenset({_FIELD_CHAT, _FIELD_TAKEN, _FIELD_TEXT})


def _key(order_id: int) -> str:
    return f"{_KEY_PREFIX}{order_id}"


@dataclass(frozen=True, slots=True)
class OrderTimeoutMessages:
    chat_id: int
    taken_message_id: int
    timed_out_text: str
    ping_message_ids: tuple[int, ...]


class OrderTimeoutMessageStore:
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis

    async def remember_taken(
        self,
        *,
        order_id: int,
        chat_id: int,
        message_id: int,
        timed_out_text: str,
        ttl_seconds: int,
    ) -> None:
        key = _key(order_id)
        pipe = self._redis.pipeline(transaction=True)
        pipe.hset(
            key,
            mapping={
                _FIELD_CHAT: chat_id,
                _FIELD_TAKEN: message_id,
                _FIELD_TEXT: timed_out_text,
            },
        )
        pipe.expire(key, ttl_seconds)
        await pipe.execute()

    async def add_ping(self, *, order_id: int, message_id: int) -> None:
        await self._redis.hset(_key(order_id), str(message_id), "")

    async def pop(self, *, order_id: int) -> OrderTimeoutMessages | None:
        key = _key(order_id)
        pipe = self._redis.pipeline(transaction=True)
        pipe.hgetall(key)
        pipe.delete(key)
        fields, _deleted = await pipe.execute()
        if not fields or _FIELD_TAKEN not in fields:
            return None
        ping_message_ids = tuple(
            int(field) for field in fields if field not in _RESERVED_FIELDS
        )
        return OrderTimeoutMessages(
            chat_id=int(fields[_FIELD_CHAT]),
            taken_message_id=int(fields[_FIELD_TAKEN]),
            timed_out_text=fields[_FIELD_TEXT],
            ping_message_ids=ping_message_ids,
        )
