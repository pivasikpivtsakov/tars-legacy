import asyncio
import contextlib
import logging

from redis.exceptions import RedisError

from common.bot import create_bot
from common.db import create_pool
from common.environment import (
    DISPATCH_BACKSTOP_SECONDS,
    DISPATCH_BATCH_LIMIT,
    OFFER_RECONCILE_GRACE_SECONDS,
    OFFER_TTL_SECONDS,
    RATING_SPEED_WINDOW,
    TELEGRAM_BOT_TOKEN,
)
from common.i18n import i18n
from common.logging_config import setup_logging
from common.redis import create_redis
from common.repositories.postgres.order_offers import OrderOfferRepository
from common.repositories.postgres.orders import OrderRepository
from common.repositories.postgres.transactions import TransactionsRepository
from common.repositories.postgres.user_profiles import UserProfileRepository
from common.repositories.redis.code_order_price import CodeOrderPriceRepository
from common.repositories.redis.language import LanguageRepository
from common.repositories.redis.offer_deadlines import OfferDeadlineQueue
from common.repositories.redis.online_index import (
    CodeOnlineIndex,
    OnlineIndexRouter,
    PackOnlineIndex,
)
from common.repositories.redis.pending_orders import PendingOrdersRepository
from common.repositories.redis.rating import RatingRepository
from common.repositories.redis.user_roles import UserRole, UserRoleRepository
from common.services.dispatch_signal import DispatchSignal
from common.services.order_fanout import OrderFanoutService
from common.services.ranking import build_strategies

logger = logging.getLogger(__name__)

_RECONNECT_DELAY_SECONDS = 1.0


async def _safe_sweep(*, service: OrderFanoutService, stale_after_seconds: int) -> None:
    try:
        await service.sweep_and_fan_out(
            stale_after_seconds=stale_after_seconds,
            limit=DISPATCH_BATCH_LIMIT,
        )
    except Exception:
        logger.exception("order dispatch sweep failed")


async def main() -> None:
    setup_logging()
    stale_after = OFFER_TTL_SECONDS + OFFER_RECONCILE_GRACE_SECONDS
    async with create_pool() as pool:
        redis = create_redis()
        bot = create_bot(token=TELEGRAM_BOT_TOKEN)
        language = LanguageRepository(redis=redis, default_locale=i18n.default_locale)
        signal = DispatchSignal(redis=redis)
        moderator_ids = await UserRoleRepository(redis=redis).get(role=UserRole.MODERATOR)
        rating = RatingRepository(redis=redis, speed_window=RATING_SPEED_WINDOW)
        online_index = OnlineIndexRouter(
            pack=PackOnlineIndex(redis=redis),
            code=CodeOnlineIndex(redis=redis),
        )
        strategies = build_strategies(
            online_index=online_index,
            rating=rating,
            transactions=TransactionsRepository(pool=pool),
            code_order_price=CodeOrderPriceRepository(redis=redis),
        )
        service = OrderFanoutService(
            bot=bot,
            orders=OrderRepository(pool=pool),
            offers=OrderOfferRepository(pool=pool),
            strategies=strategies,
            profiles=UserProfileRepository(pool=pool),
            rating=rating,
            pending=PendingOrdersRepository(redis=redis),
            deadlines=OfferDeadlineQueue(redis=redis),
            language=language,
            excluded_user_ids=frozenset(moderator_ids),
            moderator_ids=moderator_ids,
        )
        logger.info("starting dispatcher")
        try:
            while True:
                try:
                    async with signal.subscribe() as wakes:
                        # Sweep once on (re)connect to drain backlog before waiting.
                        await _safe_sweep(service=service, stale_after_seconds=stale_after)
                        while True:
                            await wakes.wait(timeout_seconds=DISPATCH_BACKSTOP_SECONDS)
                            await _safe_sweep(service=service, stale_after_seconds=stale_after)
                except RedisError:
                    logger.warning("dispatch wake channel dropped; reconnecting", exc_info=True)
                    await asyncio.sleep(_RECONNECT_DELAY_SECONDS)
        finally:
            await bot.session.close()
            await redis.aclose()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
