import asyncio
import logging

from common.logging_config import setup_logging
from common.redis import create_redis
from common.repositories.redis.user_roles import UserRole, UserRoleRepository

logger = logging.getLogger(__name__)

_DEFAULT_USER_ID = 9


async def main() -> None:
    setup_logging()
    redis = create_redis()
    roles = UserRoleRepository(redis=redis)
    try:
        for role in UserRole:
            await roles.add(role=role, user_id=_DEFAULT_USER_ID)
            logger.info("seeded role=%s user_id=%d", role.value, _DEFAULT_USER_ID)
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
