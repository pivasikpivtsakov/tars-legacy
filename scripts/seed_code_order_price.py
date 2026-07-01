import asyncio
import logging
from decimal import Decimal

from common.logging_config import setup_logging
from common.redis import create_redis
from common.repositories.redis.code_order_price import CodeOrderPriceRepository

logger = logging.getLogger(__name__)

_SEED_PRICE = Decimal("1")


async def main() -> None:
    setup_logging()
    redis = create_redis()
    prices = CodeOrderPriceRepository(redis=redis)
    try:
        await prices.set(price=_SEED_PRICE)
        logger.info("seeded code_order_price=%s", _SEED_PRICE)
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(main())
