from redis.asyncio import Redis

from common.environment import REDIS_URL


def create_redis() -> Redis:
    return Redis.from_url(REDIS_URL, decode_responses=True)
